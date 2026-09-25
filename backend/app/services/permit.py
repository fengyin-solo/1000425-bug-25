"""受限空间作业业务规则：状态流转、角色权限、归属校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "permit"

# 登记时可写入的业务字段
EDIT_FIELDS = ["许可编号", "作业类型", "作业地点", "归属班组", "监护人", "安全措施", "许可时间", "有效期至"]
REQUIRED_FIELDS = ["许可编号", "作业类型", "作业地点", "归属班组"]

# 许可状态：待申请 -> 已受理 -> 已许可；已驳回、已过期为终态
STATUS_DRAFT = "待申请"
STATUS_ACCEPTED = "已受理"
STATUS_PERMITTED = "已许可"
STATUS_REJECTED = "已驳回"
STATUS_EXPIRED = "已过期"
STATUS_ORDER = [STATUS_DRAFT, STATUS_ACCEPTED, STATUS_PERMITTED, STATUS_REJECTED, STATUS_EXPIRED]
# 待处理口径：只有还在审批流里、需要人跟进的单子才算待处理（已驳回/已许可/已过期均不算）
PENDING_STATUSES = (STATUS_DRAFT, STATUS_ACCEPTED)
ABNORMAL_STATUSES = (STATUS_REJECTED,)

# 受控班组：归属班组只能在这个范围内登记，签发/驳回只认本班组归属
CONTROLLED_TEAMS = ("运行一班", "运行二班", "检修班")

# 平台角色
ROLE_APPLICANT = "申请人"
ROLE_GUARDIAN = "监护人"
ROLE_ISSUER = "签发人"

ACTION_SUBMIT = "提交申请"
ACTION_SIGN = "监护人签字"
ACTION_ISSUE = "签发许可"
ACTION_REJECT = "驳回申请"
# 动作落地后的目标状态；监护人签字只留痕，不改变审批状态
ACTION_RULES = {
    ACTION_SUBMIT: STATUS_ACCEPTED,
    ACTION_SIGN: STATUS_ACCEPTED,
    ACTION_ISSUE: STATUS_PERMITTED,
    ACTION_REJECT: STATUS_REJECTED,
}
# 各动作允许执行的前置状态；终态（已驳回/已许可/已过期）不在任何动作的前置集合里
ACTION_PRECONDITIONS = {
    ACTION_SUBMIT: {STATUS_DRAFT},
    ACTION_SIGN: {STATUS_ACCEPTED},
    ACTION_ISSUE: {STATUS_ACCEPTED},
    ACTION_REJECT: {STATUS_DRAFT, STATUS_ACCEPTED},
}
ISSUER_ACTIONS = (ACTION_ISSUE, ACTION_REJECT)


def _sync_flags(entry: dict[str, Any]) -> None:
    """待处理/异常标记统一由状态推导，避免驳回后的单子还挂在待处理里。"""
    entry["pending"] = entry.get("status") in PENDING_STATUSES
    entry["abnormal"] = entry.get("status") in ABNORMAL_STATUSES


def _parse_day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


class PermitService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("许可编号", ""))]
        if status:
            # “待处理”是概览同口径的虚拟状态，与列表筛选共用一份判定
            if status == "待处理":
                rows = [row for row in rows if row.get("status") in PENDING_STATUSES]
            else:
                rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        cleaned = {field: str(values.get(field) or "").strip() for field in EDIT_FIELDS}
        missing = [field for field in REQUIRED_FIELDS if not cleaned[field]]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        team = cleaned["归属班组"]
        if team not in CONTROLLED_TEAMS:
            return None, f"归属班组「{team}」不在受控范围（{'、'.join(CONTROLLED_TEAMS)}）内，不能登记许可单"
        rows = store.rows(MODULE)
        permit_no = cleaned["许可编号"]
        if any(str(row.get("许可编号", "")).strip() == permit_no for row in rows):
            return None, f"许可编号「{permit_no}」已存在，被驳回的许可单需走重新申请流程，不能重复登记或再次签发"
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: cleaned[field] for field in EDIT_FIELDS})
        entry["status"] = STATUS_DRAFT
        entry["监护人签字"] = ""
        entry["签发人"] = ""
        _sync_flags(entry)
        rows.append(entry)
        return entry, ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        actor: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"作业许可单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于受限空间作业可执行范围"

        actor = actor or {}
        name = str(actor.get("operator") or "").strip()
        role = str(actor.get("role") or "").strip()
        team = str(actor.get("team") or "").strip()
        if not name or not role or not team:
            return None, "操作人身份不完整：请选择角色与所属班组后再执行动作"

        current = str(entry.get("status") or "")
        allowed = ACTION_PRECONDITIONS[action]
        if current not in allowed:
            if current in (STATUS_REJECTED, STATUS_PERMITTED, STATUS_EXPIRED):
                return None, f"许可单当前为「{current}」终态，{action}不能再执行（同一许可编号驳回后不可再次签发）"
            return None, f"许可单当前为「{current}」，不允许执行{action}（需先处于{'、'.join(sorted(allowed))}状态）"

        owner_team = str(entry.get("归属班组") or "").strip()
        if team != owner_team:
            return None, f"归属校验未通过：该许可单归属「{owner_team}」，您当前班组「{team}」无权{action}"

        if action == ACTION_SUBMIT:
            if role != ROLE_APPLICANT:
                return None, f"只有{ROLE_APPLICANT}可以提交申请，当前角色为「{role}」"
        elif action == ACTION_SIGN:
            if role != ROLE_GUARDIAN:
                return None, f"只有{ROLE_GUARDIAN}可以签字确认，当前角色为「{role}」"
        elif action in ISSUER_ACTIONS:
            if role != ROLE_ISSUER:
                return None, f"只有{ROLE_ISSUER}可以{action}，当前角色为「{role}」"

        if action == ACTION_ISSUE and not str(entry.get("监护人签字") or "").strip():
            return None, "监护人尚未签字确认，许可单不能签发；请先由监护人完成现场确认签字"

        if action == ACTION_SIGN:
            entry["监护人签字"] = name
        else:
            entry["status"] = ACTION_RULES[action]
            if action == ACTION_ISSUE:
                entry["签发人"] = name
            _sync_flags(entry)
        return entry, f"作业许可单已{action}"

    def summary(self, today: date | None = None) -> dict[str, Any]:
        """首页统计卡片口径：待处理与列表筛选、运营概览共用 PENDING_STATUSES。"""
        today = today or date.today()
        soon = today + timedelta(days=7)
        pending = valid = expiring = 0
        for row in store.rows(MODULE):
            if row.get("status") in PENDING_STATUSES:
                pending += 1
            if row.get("status") != STATUS_PERMITTED:
                continue
            end_day = _parse_day(row.get("有效期至"))
            if end_day is not None and end_day >= today:
                valid += 1
                if end_day <= soon:
                    expiring += 1
        return {
            "teams": list(CONTROLLED_TEAMS),
            "statuses": list(STATUS_ORDER),
            "pendingStatus": "待处理",
            "stats": {"待处理许可": pending, "有效许可": valid, "即将到期许可": expiring},
        }

"""受限空间作业业务规则：状态流转、角色权限、归属班组与筛选口径都收在这里。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.store import store

MODULE = "permit"
REQUIRED_FIELDS = ["许可编号", "作业类型", "作业地点", "归属班组"]
STATUS_ORDER = ["待申请", "已受理", "已许可", "已驳回", "已过期"]
# 待处理口径：只有待申请、已受理计入待处理；许可、驳回、过期即刻出列，概览与列表保持一致
PENDING_STATUSES = {"待申请", "已受理"}
TERMINAL_STATUSES = {"已许可", "已驳回", "已过期"}

# 归属班组的受控范围：许可单只能挂到这些班组，动作也只能落在本班组
TEAMS = ["运行一班", "运行二班", "检修班"]
ROLES = ["申请人", "班组长", "安全员", "值班管理员"]
ADMIN_ROLES = {"值班管理员"}  # 可跨班组操作的角色

# 动作 -> (允许的起始状态, 目标状态, 可执行角色)：签发与驳回只放行有签发权的角色
ACTION_RULES: dict[str, tuple[set[str], str, set[str]]] = {
    "提交申请": ({"待申请"}, "已受理", set(ROLES)),
    "签发许可": ({"已受理"}, "已许可", {"安全员", "值班管理员"}),
    "驳回申请": ({"待申请", "已受理"}, "已驳回", {"安全员", "值班管理员"}),
}
NEGATIVE_ACTIONS = ["驳回申请"]
ISSUE_REQUIRED_FIELDS = ["监护人", "安全措施"]  # 签发前必须落实，监护人未签认不得签发
ISSUE_EDITABLE_FIELDS = ["监护人", "安全措施", "许可时间", "有效期至"]  # 签发时允许随动作补录


@dataclass(frozen=True)
class Operator:
    """当前操作人：角色决定能不能签，归属班组决定签哪一张。"""

    name: str = ""
    role: str = ""
    team: str = ""


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
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def summary(self) -> dict[str, int]:
        """页面统计口径：待处理只数待申请、已受理，与概览待处理保持一致。"""
        rows = store.rows(MODULE)
        today = date.today()
        expiring = 0
        for row in rows:
            if row.get("status") != "已许可":
                continue
            try:
                deadline = date.fromisoformat(str(row.get("有效期至") or ""))
            except ValueError:
                continue
            if 0 <= (deadline - today).days <= 7:
                expiring += 1
        return {
            "待处理": sum(1 for row in rows if row.get("status") in PENDING_STATUSES),
            "已许可": sum(1 for row in rows if row.get("status") == "已许可"),
            "已驳回": sum(1 for row in rows if row.get("status") == "已驳回"),
            "即将到期": expiring,
            "total": len(rows),
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        team = str(values.get("归属班组")).strip()
        if team not in TEAMS:
            return None, f"归属班组「{team}」不在受控范围内，可选：{'、'.join(TEAMS)}"
        number = str(values.get("许可编号")).strip()
        rows = store.rows(MODULE)
        if any(str(row.get("许可编号")) == number for row in rows):
            return None, f"许可编号 {number} 已存在，同一编号不能重复登记"
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        for field in ISSUE_EDITABLE_FIELDS:
            value = str(values.get(field) or "").strip()
            if value:
                entry[field] = value
        entry["status"] = STATUS_ORDER[0]
        entry["许可状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
        operator: Operator | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"作业许可单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于受限空间作业可执行范围"
        operator = operator or Operator()
        sources, target, roles = ACTION_RULES[action]
        if not operator.role:
            return None, "未提供操作人角色，无法校验动作权限"
        if operator.role not in roles:
            return None, f"角色「{operator.role}」无权{action}，需由{'、'.join(sorted(roles))}操作"
        status = str(entry.get("status") or "")
        if status in TERMINAL_STATUSES:
            return None, f"许可单已处于「{status}」，流程终结后不能再次{action}，如需作业请重新登记"
        if status not in sources:
            return None, f"许可单当前状态为「{status}」，不能执行{action}"
        team = str(entry.get("归属班组") or "")
        if operator.role not in ADMIN_ROLES and team and operator.team != team:
            return None, f"许可单归属「{team}」，超出当前班组（{operator.team or '未指定'}）的受控范围"
        if action == "签发许可":
            for field in ISSUE_EDITABLE_FIELDS:
                value = str((values or {}).get(field) or "").strip()
                if value:
                    entry[field] = value
            missing = [field for field in ISSUE_REQUIRED_FIELDS if not str(entry.get(field) or "").strip()]
            if missing:
                return None, f"签发前需先落实{'、'.join(missing)}，监护人未签认的许可单不得签发"
        entry["status"] = target
        entry["许可状态"] = target
        entry["pending"] = target in PENDING_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if operator.name:
            entry["最近操作人"] = operator.name
        return entry, f"作业许可单已{action}"

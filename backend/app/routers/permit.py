"""受限空间作业接口：维护作业许可单，覆盖提交申请、监护人签字、签发许可、驳回申请等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.permit import PermitService

router = APIRouter(prefix="/api/permit", tags=["受限空间作业"])

service = PermitService()

LIST_FIELDS = ["许可编号", "作业类型", "作业地点", "归属班组", "监护人", "监护人签字", "安全措施", "许可时间", "有效期至", "status"]
STATUSES = ["待申请", "已受理", "已许可", "已驳回", "已过期", "待处理"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按许可编号检索"),
    status: str | None = Query(default=None, description="待申请、已受理、已许可、已驳回、已过期、待处理"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按许可编号与状态过滤受限空间作业列表；没有数据时返回空页，不报错。"""
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"不支持的状态筛选：{status}")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def summary() -> dict[str, Any]:
    """许可首页统计：待处理口径与运营概览、列表「待处理」筛选完全一致。"""
    return service.summary()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出受限空间作业清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "permit", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条作业许可单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"作业许可单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条作业许可单，缺字段或归属班组不受控时说明原因而不是静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="作业许可单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条作业许可单执行动作；角色、归属班组、前置状态与监护人签字任一不满足都会被拦下并说明原因。"""
    values = payload.values
    action = str(values.get("action") or "").strip()
    actor = {
        "operator": values.get("operator"),
        "role": values.get("role"),
        "team": values.get("team"),
    }
    entry, message = service.run_action(entry_id, action, actor)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

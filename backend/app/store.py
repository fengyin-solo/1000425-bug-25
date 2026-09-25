"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS

# 待处理/异常口径：登记在此处的模块按状态实时推导，
# 保证列表筛选、动作流转与运营概览三处口径始终一致（例如已驳回的许可单不计入待处理）。
PENDING_STATUSES: dict[str, tuple[str, ...]] = {
    "permit": ("待申请", "已受理"),
}
ABNORMAL_STATUSES: dict[str, tuple[str, ...]] = {
    "permit": ("已驳回",),
}


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def is_pending(self, module: str, row: dict[str, Any]) -> bool:
        statuses = PENDING_STATUSES.get(module)
        if statuses is not None:
            return row.get("status") in statuses
        return bool(row.get("pending"))

    def is_abnormal(self, module: str, row: dict[str, Any]) -> bool:
        statuses = ABNORMAL_STATUSES.get(module)
        if statuses is not None:
            return row.get("status") in statuses
        return bool(row.get("abnormal"))

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if self.is_pending(name, row)),
                "abnormal": sum(1 for row in rows if self.is_abnormal(name, row)),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()

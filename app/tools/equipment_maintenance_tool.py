"""设备维保查询工具 - 查询设备维保计划和状态。"""

from typing import Any

from app.persistence.postgres import get_business_connection
from app.tools.base import BaseTool


class EquipmentMaintenanceTool(BaseTool):
    name = "equipment_maintenance"
    description = "查询设备维保计划、状态和历史记录"

    # ── MCP 风格 Schema ──────────────────────────────────────
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "关联的 RCA 任务 ID",
            },
            "anomaly_type": {
                "type": "string",
                "description": "异常类型",
            },
            "description": {
                "type": "string",
                "description": "异常描述",
            },
            "status_filter": {
                "type": "array",
                "items": {"type": "string"},
                "description": "维保状态过滤，可选值: planned, in_progress, overdue, completed",
                "default": ["planned", "in_progress", "overdue"],
            },
            "limit": {
                "type": "integer",
                "description": "返回记录数上限",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": ["task_id"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "执行是否成功",
            },
            "data": {
                "type": "array",
                "description": "设备维保数据列表",
            },
            "count": {
                "type": "integer",
                "description": "返回记录数",
            },
            "overdue_count": {
                "type": "integer",
                "description": "逾期维保数",
            },
            "in_progress_count": {
                "type": "integer",
                "description": "进行中维保数",
            },
            "overdue": {
                "type": "array",
                "description": "逾期维保详情列表",
            },
        },
    }

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        status_filter = params.get("status_filter", ["planned", "in_progress", "overdue"])
        limit = params.get("limit", 20)

        conn = get_business_connection()
        try:
            placeholders = ",".join("?" for _ in status_filter)
            rows = conn.execute(
                f"""SELECT * FROM equipment_maintenance
                    WHERE status IN ({placeholders})
                    ORDER BY
                      CASE status
                        WHEN 'overdue' THEN 0
                        WHEN 'in_progress' THEN 1
                        WHEN 'planned' THEN 2
                      END,
                      planned_date ASC
                    LIMIT ?""",
                (*status_filter, limit),
            ).fetchall()

            data = [dict(r) for r in rows]

            # 检查逾期维保
            overdue = [r for r in data if r.get("status") == "overdue"]
            in_progress = [r for r in data if r.get("status") == "in_progress"]

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "overdue_count": len(overdue),
                "in_progress_count": len(in_progress),
                "overdue": overdue,
            }
        finally:
            conn.close()

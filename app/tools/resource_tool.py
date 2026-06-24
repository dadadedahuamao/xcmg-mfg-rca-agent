"""资源查询工具 - 查询设备/人员等生产资源状态。"""

from typing import Any

from app.persistence.postgres import get_business_connection
from app.tools.base import BaseTool


class ResourceTool(BaseTool):
    name = "resource"
    description = "查询设备、人员等生产资源的占用和可用状态"

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
            "resource_type": {
                "type": "string",
                "description": "资源类型，如 equipment、personnel",
                "default": "equipment",
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
                "description": "资源数据列表",
            },
            "count": {
                "type": "integer",
                "description": "返回记录数",
            },
            "conflicts": {
                "type": "array",
                "description": "资源冲突列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "workstation": {"type": "string", "description": "工位"},
                        "conflict_count": {"type": "integer", "description": "冲突数"},
                        "equipment": {"type": "array", "description": "涉及设备"},
                    },
                },
            },
            "conflict_count": {
                "type": "integer",
                "description": "冲突总数",
            },
        },
    }

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = params.get("limit", 20)

        conn = get_business_connection()
        try:
            # 查询设备维保状态作为资源占用情况
            rows = conn.execute(
                """SELECT equipment_id, equipment_name, workstation,
                          maintenance_type, status, planned_date, actual_date
                   FROM equipment_maintenance
                   WHERE status IN ('planned', 'in_progress', 'overdue')
                   ORDER BY
                     CASE status
                       WHEN 'overdue' THEN 0
                       WHEN 'in_progress' THEN 1
                       WHEN 'planned' THEN 2
                     END,
                     planned_date ASC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            data = [dict(r) for r in rows]

            # 分析资源冲突
            conflicts = []
            workstation_groups = {}
            for r in data:
                ws = r.get("workstation", "")
                if ws not in workstation_groups:
                    workstation_groups[ws] = []
                workstation_groups[ws].append(r)

            for ws, items in workstation_groups.items():
                if len(items) > 1:
                    conflicts.append({
                        "workstation": ws,
                        "conflict_count": len(items),
                        "equipment": [i.get("equipment_id") for i in items],
                    })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "conflicts": conflicts,
                "conflict_count": len(conflicts),
            }
        finally:
            conn.close()

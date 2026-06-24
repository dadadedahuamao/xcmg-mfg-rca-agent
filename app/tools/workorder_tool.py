"""工单查询工具 - 查询 MES 工单数据。"""

from typing import Any

from app.persistence.postgres import get_business_connection
from app.tools.base import BaseTool


class WorkOrderTool(BaseTool):
    name = "workorder"
    description = "查询工单状态、进度和异常信息"

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
                "description": "工单状态过滤条件，可选值: pending, in_progress, delayed, blocked, completed",
                "default": ["pending", "in_progress", "delayed"],
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
                "description": "工单数据列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "order_no": {"type": "string", "description": "工单号"},
                        "product_name": {"type": "string", "description": "产品名称"},
                        "workstation": {"type": "string", "description": "工位"},
                        "status": {"type": "string", "description": "工单状态"},
                        "priority": {"type": "integer", "description": "优先级"},
                    },
                },
            },
            "count": {
                "type": "integer",
                "description": "返回记录数",
            },
            "anomaly_count": {
                "type": "integer",
                "description": "异常工单数",
            },
            "anomalies": {
                "type": "array",
                "description": "异常工单详情列表",
            },
        },
    }

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        status_filter = params.get("status_filter", ["pending", "in_progress", "delayed"])
        limit = params.get("limit", 20)

        conn = get_business_connection()
        try:
            placeholders = ",".join("?" for _ in status_filter)
            rows = conn.execute(
                f"""SELECT * FROM work_orders
                    WHERE status IN ({placeholders})
                    ORDER BY priority DESC, created_at DESC
                    LIMIT ?""",
                (*status_filter, limit),
            ).fetchall()

            data = [dict(r) for r in rows]

            # 检查是否有异常工单
            anomalies = [
                r for r in data
                if r.get("status") in ("delayed", "blocked")
            ]

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "anomaly_count": len(anomalies),
                "anomalies": anomalies,
            }
        finally:
            conn.close()

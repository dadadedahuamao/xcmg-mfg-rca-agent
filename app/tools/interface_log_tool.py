"""接口日志查询工具 - 查询系统间接口调用日志。"""

from typing import Any

from app.persistence.postgres import get_business_connection
from app.tools.base import BaseTool


class InterfaceLogTool(BaseTool):
    name = "interface_log"
    description = "查询 MES/APS/WMS/QMS 系统间接口调用日志，检测超时和失败"

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
            "hours_back": {
                "type": "integer",
                "description": "回溯小时数",
                "default": 24,
                "minimum": 1,
                "maximum": 168,
            },
            "limit": {
                "type": "integer",
                "description": "返回记录数上限",
                "default": 50,
                "minimum": 1,
                "maximum": 200,
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
                "description": "接口日志数据列表",
            },
            "count": {
                "type": "integer",
                "description": "返回记录数",
            },
            "failure_count": {
                "type": "integer",
                "description": "失败调用数",
            },
            "timeout_count": {
                "type": "integer",
                "description": "超时调用数（>5s）",
            },
            "slow_count": {
                "type": "integer",
                "description": "慢调用数（1-5s）",
            },
            "failures": {
                "type": "array",
                "description": "失败调用详情（前10条）",
            },
            "timeouts": {
                "type": "array",
                "description": "超时调用详情（前10条）",
            },
        },
    }

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        hours_back = params.get("hours_back", 24)
        limit = params.get("limit", 50)

        conn = get_business_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM interface_logs
                   WHERE request_time >= (NOW() - INTERVAL '1 hour' * ?)::text
                   ORDER BY
                     CASE WHEN success = 0 THEN 0 ELSE 1 END,
                     duration_ms DESC
                   LIMIT ?""",
                (hours_back, limit),
            ).fetchall()

            data = [dict(r) for r in rows]

            # 分析超时和失败
            failures = [r for r in data if not r.get("success")]
            timeouts = [r for r in data if r.get("duration_ms", 0) > 5000]
            slow_calls = [r for r in data if 1000 < r.get("duration_ms", 0) <= 5000]

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "failure_count": len(failures),
                "timeout_count": len(timeouts),
                "slow_count": len(slow_calls),
                "failures": failures[:10],
                "timeouts": timeouts[:10],
            }
        finally:
            conn.close()

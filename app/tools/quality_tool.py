"""质量记录查询工具 - 查询 QMS 质量检测记录和不良品数据。"""

from typing import Any

from app.persistence.postgres import get_business_connection
from app.tools.base import BaseTool


class QualityTool(BaseTool):
    name = "quality"
    description = "查询质量检测记录、不良率和缺陷分布"

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
            "defect_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "缺陷类型过滤，[\"all\"] 表示全部",
                "default": ["all"],
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
                "description": "质量记录数据列表",
            },
            "count": {
                "type": "integer",
                "description": "返回记录数",
            },
            "defect_stats": {
                "type": "object",
                "description": "缺陷分布统计，key 为缺陷类型",
            },
            "total_inspected": {
                "type": "integer",
                "description": "总检验数",
            },
            "total_defects": {
                "type": "integer",
                "description": "总缺陷数",
            },
            "defect_rate": {
                "type": "number",
                "description": "不良率",
            },
            "is_abnormal": {
                "type": "boolean",
                "description": "是否异常（不良率 > 5%）",
            },
        },
    }

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        defect_types = params.get("defect_types", ["all"])
        limit = params.get("limit", 20)

        conn = get_business_connection()
        try:
            if "all" in defect_types:
                rows = conn.execute(
                    """SELECT * FROM quality_records
                       ORDER BY inspection_date DESC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()
            else:
                placeholders = ",".join("?" for _ in defect_types)
                rows = conn.execute(
                    f"""SELECT * FROM quality_records
                        WHERE defect_type IN ({placeholders})
                        ORDER BY inspection_date DESC
                        LIMIT ?""",
                    (*defect_types, limit),
                ).fetchall()

            data = [dict(r) for r in rows]

            # 统计缺陷分布
            defect_stats = {}
            for r in data:
                dt = r.get("defect_type", "未知")
                if dt not in defect_stats:
                    defect_stats[dt] = {"count": 0, "total_defects": 0}
                defect_stats[dt]["count"] += 1
                defect_stats[dt]["total_defects"] += r.get("defect_count", 0)

            # 计算不良率
            total_inspected = sum(r.get("total_inspected", 0) for r in data)
            total_defects = sum(r.get("defect_count", 0) for r in data)
            defect_rate = total_defects / total_inspected if total_inspected > 0 else 0

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "defect_stats": defect_stats,
                "total_inspected": total_inspected,
                "total_defects": total_defects,
                "defect_rate": round(defect_rate, 4),
                "is_abnormal": defect_rate > 0.05,
            }
        finally:
            conn.close()

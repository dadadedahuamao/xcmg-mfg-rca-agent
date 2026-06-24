"""物料库存查询工具 - 查询 WMS 物料库存和短缺情况。"""

from typing import Any

from app.persistence.postgres import get_business_connection
from app.tools.base import BaseTool


class MaterialTool(BaseTool):
    name = "material"
    description = "查询物料库存、安全库存和短缺预警"

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
            "check_safety_stock": {
                "type": "boolean",
                "description": "是否检查安全库存",
                "default": True,
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
                "description": "物料库存数据列表",
            },
            "count": {
                "type": "integer",
                "description": "返回记录数",
            },
            "shortages": {
                "type": "array",
                "description": "短缺物料列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "material_code": {"type": "string", "description": "物料编码"},
                        "material_name": {"type": "string", "description": "物料名称"},
                        "quantity": {"type": "number", "description": "当前库存"},
                        "safety_stock": {"type": "number", "description": "安全库存"},
                        "shortage": {"type": "number", "description": "短缺量"},
                    },
                },
            },
            "shortage_count": {
                "type": "integer",
                "description": "短缺物料数",
            },
            "has_shortage": {
                "type": "boolean",
                "description": "是否存在短缺",
            },
        },
    }

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        check_safety_stock = params.get("check_safety_stock", True)
        limit = params.get("limit", 20)

        conn = get_business_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM material_inventory
                   ORDER BY
                     CASE WHEN quantity <= safety_stock THEN 0 ELSE 1 END,
                     (quantity - safety_stock) ASC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            data = [dict(r) for r in rows]

            # 检查短缺
            shortages = []
            for r in data:
                qty = r.get("quantity", 0)
                safety = r.get("safety_stock", 0)
                if qty <= safety:
                    shortages.append({
                        "material_code": r.get("material_code"),
                        "material_name": r.get("material_name"),
                        "quantity": qty,
                        "safety_stock": safety,
                        "shortage": safety - qty,
                        "warehouse": r.get("warehouse"),
                    })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "shortages": shortages,
                "shortage_count": len(shortages),
                "has_shortage": len(shortages) > 0,
            }
        finally:
            conn.close()

"""Text2SQL 工具 - 自然语言转 SQL 查询。"""

from typing import Any

from app.text2sql.generator import SQLGenerator
from app.text2sql.validator import SQLValidator
from app.text2sql.executor import SQLExecutor
from app.tools.base import BaseTool


class Text2SQLTool(BaseTool):
    name = "text2sql"
    description = "将自然语言查询转换为安全的只读 SQL 并执行"

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
            "query": {
                "type": "string",
                "description": "自然语言查询文本",
            },
        },
        "required": ["task_id", "query"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "执行是否成功",
            },
            "sql": {
                "type": "string",
                "description": "生成的 SQL 语句",
            },
            "data": {
                "type": "array",
                "description": "查询结果数据",
            },
            "count": {
                "type": "integer",
                "description": "返回记录数",
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "列名列表",
            },
            "truncated": {
                "type": "boolean",
                "description": "结果是否被截断",
            },
            "execution_time_ms": {
                "type": "integer",
                "description": "执行耗时（毫秒）",
            },
            "generation_rounds": {
                "type": "integer",
                "description": "SQL 生成轮次（含回退）",
            },
            "intent": {
                "type": "string",
                "description": "查询意图分类: count/detail/aggregate",
            },
            "round_history": {
                "type": "array",
                "description": "多轮生成历史",
            },
            "error": {
                "type": "string",
                "description": "错误信息（仅失败时）",
            },
        },
    }

    def __init__(self):
        super().__init__()
        self._generator = SQLGenerator()
        self._validator = SQLValidator()
        self._executor = SQLExecutor()

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query", "")
        anomaly_type = params.get("anomaly_type", "")

        # 重置生成历史
        self._generator.reset_history()

        # 生成 SQL（第一轮）
        sql = self._generator.generate(query, anomaly_type)

        # 验证 SQL
        is_valid, error = self._validator.validate(sql)
        if not is_valid:
            return {
                "success": False,
                "error": error,
                "sql": sql,
            }

        # 执行 SQL
        try:
            result = self._executor.execute(sql)

            # 多轮回退：如果结果为空，尝试替代查询
            rounds = 1
            while result.get("count", 0) == 0 and rounds < SQLGenerator.MAX_ROUNDS:
                fallback_sql = self._generator.generate_fallback(sql, query)
                if fallback_sql is None:
                    break

                # 验证回退 SQL
                is_valid, error = self._validator.validate(fallback_sql)
                if not is_valid:
                    break

                result = self._executor.execute(fallback_sql)
                sql = fallback_sql
                rounds += 1

            # 构建返回结果
            response = {
                "success": True,
                "sql": sql,
                "data": result.get("data", []),
                "count": result.get("count", 0),
                "columns": result.get("columns", []),
                "truncated": result.get("truncated", False),
                "execution_time_ms": result.get("execution_time_ms", 0),
                "generation_rounds": rounds,
                "round_history": self._generator.get_round_history(),
                "intent": self._generator.classify_intent(query).value,
            }

            if result.get("warning"):
                response["warning"] = result["warning"]

            return response
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "sql": sql,
            }

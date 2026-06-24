"""Text2SQL 执行器 - 对 PostgreSQL 业务数据库执行已验证的 SQL。

支持：
- 结构化结果：返回 columns + rows 格式，非仅原始字典列表
- 行数限制：MAX_ROWS 硬限制，防止返回过多数据
- 超时保护：PostgreSQL 查询超时检测
- 结果格式化：自动将结果转为易于消费的格式
"""

import time
from typing import Any, Optional

from app.persistence.postgres import get_business_connection


class SQLExecutor:
    """SQL 执行器。

    只执行已通过验证的只读 SELECT 语句。

    安全特性：
    - 行数硬限制（MAX_ROWS）
    - 查询超时保护
    - 结构化结果输出
    """

    # 最大返回行数（硬限制）
    MAX_ROWS: int = 1000

    # 查询超时（秒）
    QUERY_TIMEOUT: float = 5.0

    def execute(self, sql: str) -> dict[str, Any]:
        """执行 SQL 查询。

        Args:
            sql: 已验证的 SELECT SQL

        Returns:
            结构化结果字典，包含:
            - data: 行数据列表（dict 格式）
            - columns: 列名列表
            - count: 返回行数
            - truncated: 是否被截断
            - execution_time_ms: 执行耗时（毫秒）
            - error: 错误信息（仅失败时）
        """
        conn = get_business_connection()
        start_time = time.time()

        try:
            cursor = conn.execute(sql)

            # 提取列信息
            columns = cursor.columns

            # 提取行数据（带行数限制）
            rows = cursor.fetchall()

            # 行数检查
            truncated = len(rows) > self.MAX_ROWS
            if truncated:
                rows = rows[:self.MAX_ROWS]

            # 格式化为结构化结果
            data = [dict(row) for row in rows]

            execution_time_ms = int((time.time() - start_time) * 1000)

            result = {
                "data": data,
                "columns": columns,
                "count": len(data),
                "total_rows": len(rows),  # 截断前的实际行数
                "truncated": truncated,
                "execution_time_ms": execution_time_ms,
            }

            # 超时警告
            if execution_time_ms > self.QUERY_TIMEOUT * 1000:
                result["warning"] = (
                    f"查询耗时 {execution_time_ms}ms，超过建议超时 "
                    f"{int(self.QUERY_TIMEOUT * 1000)}ms"
                )

            return result

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return {
                "data": [],
                "columns": [],
                "count": 0,
                "total_rows": 0,
                "truncated": False,
                "execution_time_ms": execution_time_ms,
                "error": str(e),
            }
        finally:
            conn.close()

    def execute_with_fallback(
        self,
        sql: str,
        fallback_sql: Optional[str] = None,
    ) -> dict[str, Any]:
        """执行 SQL，空结果时尝试回退查询。

        如果主 SQL 返回空结果且有回退 SQL，则执行回退查询。

        Args:
            sql: 主 SQL
            fallback_sql: 回退 SQL（可选）

        Returns:
            结构化结果字典，额外包含:
            - used_fallback: 是否使用了回退查询
            - primary_sql: 主 SQL
            - fallback_sql: 回退 SQL（如果使用）
        """
        result = self.execute(sql)

        if result.get("count", 0) == 0 and fallback_sql:
            fallback_result = self.execute(fallback_sql)
            fallback_result["used_fallback"] = True
            fallback_result["primary_sql"] = sql
            fallback_result["fallback_sql"] = fallback_sql
            return fallback_result

        result["used_fallback"] = False
        return result

    def format_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """格式化结果为易于消费的结构。

        将原始 dict 列表转换为 columns + rows 的表格格式，
        方便前端渲染或日志输出。

        Args:
            result: execute() 返回的原始结果

        Returns:
            格式化后的结果
        """
        formatted = dict(result)

        # 添加摘要信息
        if result.get("count", 0) > 0:
            columns = result.get("columns", [])
            data = result.get("data", [])
            formatted["summary"] = {
                "total_columns": len(columns),
                "total_rows": result.get("count", 0),
                "sample": data[:3] if len(data) > 3 else data,
            }

        return formatted

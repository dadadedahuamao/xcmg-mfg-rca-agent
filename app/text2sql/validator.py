"""Text2SQL 验证器 - 确保生成的 SQL 安全可执行。"""

import re
from typing import Tuple

from app.config import settings


class SQLValidator:
    """SQL 安全验证器。

    验证规则：
    1. 只允许 SELECT 语句
    2. 禁止 INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER
    3. 白名单表名
    4. 必须有 LIMIT 子句
    """

    # 禁止的 SQL 关键字
    FORBIDDEN_KEYWORDS = [
        "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
        "ALTER", "CREATE", "EXEC", "EXECUTE", "GRANT", "REVOKE",
        "MERGE", "REPLACE", "LOAD", "IMPORT",
    ]

    # 禁止的 SQL 模式
    FORBIDDEN_PATTERNS = [
        r"--",           # SQL 注释
        r"/\*",          # 块注释开始
        r"\*/",          # 块注释结束
        r";\s*\w",       # 多语句
        r"UNION\s+SELECT",  # UNION 注入
    ]

    def __init__(self):
        self.whitelist_tables = settings.whitelist_tables

    def validate(self, sql: str) -> Tuple[bool, str]:
        """验证 SQL 安全性。

        Returns:
            (is_valid, error_message)
        """
        sql_upper = sql.upper().strip()

        # 1. 必须以 SELECT 开头
        if not sql_upper.startswith("SELECT"):
            return False, "只允许 SELECT 语句"

        # 2. 检查禁止关键字
        for keyword in self.FORBIDDEN_KEYWORDS:
            pattern = r"\b" + keyword + r"\b"
            if re.search(pattern, sql_upper):
                return False, f"禁止使用 {keyword}"

        # 3. 检查禁止模式
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                return False, f"检测到不安全的 SQL 模式"

        # 4. 必须有 LIMIT
        if "LIMIT" not in sql_upper:
            return False, "SELECT 语句必须包含 LIMIT 子句"

        # 5. 检查表名白名单
        tables = self._extract_tables(sql)
        for table in tables:
            if table not in self.whitelist_tables:
                return False, f"表 '{table}' 不在白名单中。允许的表: {', '.join(self.whitelist_tables)}"

        return True, ""

    def _extract_tables(self, sql: str) -> list[str]:
        """从 SQL 中提取表名。"""
        # 匹配 FROM 和 JOIN 后的表名
        pattern = r'(?:FROM|JOIN)\s+(\w+)'
        matches = re.findall(pattern, sql, re.IGNORECASE)
        return list(set(matches))

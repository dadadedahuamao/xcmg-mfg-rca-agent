"""PostgreSQL schema/table 标识符辅助函数。"""

import re


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(identifier: str) -> str:
    """校验并引用 PostgreSQL 标识符。"""
    if not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"非法 PostgreSQL 标识符: {identifier}")
    return f'"{identifier}"'


def split_table_name(table_name: str) -> tuple[str | None, str]:
    """拆分可选 schema 前缀的表名。"""
    parts = table_name.split(".")
    if len(parts) == 1:
        return None, parts[0]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ValueError(f"非法 PostgreSQL 表名: {table_name}")


def schema_qualified_name(default_schema: str, table_name: str) -> str:
    """生成 schema 限定的 PostgreSQL 表名。"""
    explicit_schema, table = split_table_name(table_name)
    schema = explicit_schema or default_schema
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def resolved_schema_name(default_schema: str, table_name: str) -> str:
    """获取表名最终使用的 schema。"""
    explicit_schema, _ = split_table_name(table_name)
    return explicit_schema or default_schema


def schema_qualified_index_name(default_schema: str, table_name: str, suffix: str) -> str:
    """生成带 schema 前缀语义的安全索引名。"""
    explicit_schema, table = split_table_name(table_name)
    schema = explicit_schema or default_schema
    return quote_identifier(f"idx_{schema}_{table}_{suffix}")

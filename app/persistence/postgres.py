"""PostgreSQL 数据库连接管理。"""

import re
import logging
import importlib
from datetime import datetime
from typing import Any, Iterable, Optional

from app.config import settings

_sql_identifiers = importlib.import_module("app.persistence.sql_identifiers")

logger = logging.getLogger(__name__)


def database_timestamp() -> str:
    """返回数据库文本时间戳格式：YYYY-MM-DD HH:MM:SS.mmm。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _connect():
    psycopg = importlib.import_module("psycopg")
    rows = importlib.import_module("psycopg.rows")
    conn = psycopg.connect(settings.database_url, row_factory=rows.dict_row)
    schema = _sql_identifiers.quote_identifier(settings.database_schema)
    conn.execute(f"SET search_path TO {schema}")
    return conn


def _connect_business():
    """连接业务数据库（只读）。"""
    psycopg = importlib.import_module("psycopg")
    rows = importlib.import_module("psycopg.rows")
    conn = psycopg.connect(settings.business_database_url, row_factory=rows.dict_row)
    schema = _sql_identifiers.quote_identifier(settings.business_database_schema)
    conn.execute(f"SET search_path TO {schema}")
    return conn


def _convert_placeholders(sql: str) -> str:
    """将项目现有 DB-API `?` 占位符转换为 psycopg `%s`。"""
    return sql.replace("?", "%s")


def _convert_insert_or_ignore(sql: str) -> str:
    return re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT", sql, flags=re.IGNORECASE)


def _convert_insert_or_replace(sql: str) -> str:
    if "INSERT OR REPLACE INTO rca_reports" not in sql:
        return sql
    return sql.replace("INSERT OR REPLACE INTO rca_reports", "INSERT INTO rca_reports") + (
        " ON CONFLICT (task_id) DO UPDATE SET "
        "root_cause = EXCLUDED.root_cause, "
        "root_cause_category = EXCLUDED.root_cause_category, "
        "hypotheses = EXCLUDED.hypotheses, "
        "evidence_summary = EXCLUDED.evidence_summary, "
        "tool_call_history = EXCLUDED.tool_call_history, "
        "confidence = EXCLUDED.confidence, "
        "reflection_rounds = EXCLUDED.reflection_rounds, "
        "recommendations = EXCLUDED.recommendations, "
        "final_report = EXCLUDED.final_report, "
        "generated_at = EXCLUDED.generated_at"
    )


def _normalize_sql(sql: str) -> str:
    sql = _convert_insert_or_replace(sql)
    sql = _convert_insert_or_ignore(sql)
    return _convert_placeholders(sql)


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self.description = cursor.description

    def fetchone(self) -> Optional[dict[str, Any]]:
        return self._cursor.fetchone()

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._cursor.fetchall())

    @property
    def columns(self) -> list[str]:
        if not self._cursor.description:
            return []
        return [column.name for column in self._cursor.description]

    def __iter__(self):
        return iter(self._cursor)


class PostgresConnection:
    def __init__(self):
        self._conn = _connect()

    def execute(self, sql: str, params: Optional[Iterable[Any]] = None) -> PostgresCursor:
        cursor = self._conn.execute(_normalize_sql(sql), tuple(params or ()))
        return PostgresCursor(cursor)

    def executemany(self, sql: str, params_seq: Iterable[Iterable[Any]]) -> None:
        sql = _normalize_sql(sql)
        if sql.lstrip().upper().startswith("INSERT ") and " ON CONFLICT " not in sql.upper():
            sql += " ON CONFLICT DO NOTHING"
        with self._conn.cursor() as cursor:
            cursor.executemany(sql, [tuple(params) for params in params_seq])

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def get_connection() -> PostgresConnection:
    """获取 PostgreSQL 连接。"""
    return PostgresConnection()


class BusinessPostgresConnection:
    """业务数据库连接（只读查询用）。

    与 PostgresConnection 功能一致，但连接的是业务数据库。
    """

    def __init__(self):
        self._conn = _connect_business()

    def execute(self, sql: str, params: Optional[Iterable[Any]] = None) -> PostgresCursor:
        cursor = self._conn.execute(_normalize_sql(sql), tuple(params or ()))
        return PostgresCursor(cursor)

    def executemany(self, sql: str, params_seq: Iterable[Iterable[Any]]) -> None:
        sql = _normalize_sql(sql)
        if sql.lstrip().upper().startswith("INSERT ") and " ON CONFLICT " not in sql.upper():
            sql += " ON CONFLICT DO NOTHING"
        with self._conn.cursor() as cursor:
            cursor.executemany(sql, [tuple(params) for params in params_seq])

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def get_business_connection() -> BusinessPostgresConnection:
    """获取业务数据库连接（只读查询用）。"""
    return BusinessPostgresConnection()


def init_db() -> None:
    """验证 PostgreSQL 连接；数据库结构请通过 db/*.sql 脚本初始化。"""
    # 验证应用库
    conn = _connect()
    try:
        conn.execute("SELECT 1")
    finally:
        conn.close()

    # 验证业务库（如果与应用库不同）
    if settings.business_database_url != settings.database_url:
        bconn = _connect_business()
        try:
            bconn.execute("SELECT 1")
        finally:
            bconn.close()

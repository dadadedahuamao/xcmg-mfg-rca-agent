"""PostgreSQL/pgvector 知识库向量存储。"""

import json
import logging
import importlib
from typing import Any

from app.config import settings

_sql_identifiers = importlib.import_module("app.persistence.sql_identifiers")

logger = logging.getLogger(__name__)


def _connect(row_factory: bool = False):
    psycopg = importlib.import_module("psycopg")
    if not row_factory:
        return psycopg.connect(settings.vector_database_url or settings.database_url)
    rows = importlib.import_module("psycopg.rows")
    return psycopg.connect(
        settings.vector_database_url or settings.database_url,
        row_factory=rows.dict_row,
    )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


class PGVectorStore:
    def __init__(self) -> None:
        self.database_url = settings.vector_database_url or settings.database_url
        self.schema_name = _sql_identifiers.resolved_schema_name(
            settings.vector_db_schema,
            settings.vector_table_name,
        )
        self.table_name = _sql_identifiers.schema_qualified_name(
            settings.vector_db_schema,
            settings.vector_table_name,
        )
        self.anomaly_type_index_name = _sql_identifiers.schema_qualified_index_name(
            settings.vector_db_schema,
            settings.vector_table_name,
            "anomaly_type",
        )
        self.dimension = settings.embedding_dimension

    @property
    def enabled(self) -> bool:
        return settings.vector_db_provider == "pgvector"

    def init_schema(self) -> None:
        logger.info("向量表初始化已迁移到 db/002_init_vector_schema.sql，运行时不会创建 schema 或表。")

    def search(
        self,
        query_embedding: list[float],
        anomaly_type: str = "",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        vector = _vector_literal(query_embedding)
        sql = (
            f"SELECT id, title, content, anomaly_type, metadata, "
            f"1 - (embedding <=> %s::vector) AS vector_score "
            f"FROM {self.table_name} "
            f"ORDER BY embedding <=> %s::vector LIMIT %s"
        )
        params: tuple[Any, ...] = (vector, vector, limit)
        if anomaly_type:
            sql = (
                f"SELECT id, title, content, anomaly_type, metadata, "
                f"1 - (embedding <=> %s::vector) AS vector_score "
                f"FROM {self.table_name} WHERE anomaly_type IN (%s, 'general') "
                f"ORDER BY embedding <=> %s::vector LIMIT %s"
            )
            params = (vector, anomaly_type, vector, limit)
        with _connect(row_factory=True) as conn:
            rows = conn.execute(sql, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            metadata = item.get("metadata")
            if isinstance(metadata, str):
                item["metadata"] = json.loads(metadata)
            results.append(item)
        return results


vector_store = PGVectorStore()

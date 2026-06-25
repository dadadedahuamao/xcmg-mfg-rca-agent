"""将 data/chunks 分片向量化后写入 PostgreSQL/pgvector。

使用项目 .env 中的 EMBEDDING_*、VECTOR_* 配置。
目标表结构见 db/004_init_vector_schema.sql 的 knowledge_embeddings。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.persistence.sql_identifiers import split_table_name
from app.rag.embedding_client import embedding_client

logger = logging.getLogger(__name__)


DEFAULT_CHUNKS_FILE = PROJECT_ROOT / "data" / "chunks" / "全部分片.json"


def load_chunks(path: Path) -> list[dict[str, Any]]:
    """读取 JSON 数组或 JSONL 格式的分片文件。"""
    if not path.exists():
        raise FileNotFoundError(f"分片文件不存在: {path}")
    if path.suffix.lower() == ".jsonl":
        chunks: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))
        return chunks
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON 分片文件必须是数组")
    return data


def _stable_json_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _day_precision_timestamp(value: Any = None) -> str:
    if isinstance(value, datetime):
        return f"{value.date().isoformat()} 00:00:00"
    if isinstance(value, date):
        return f"{value.isoformat()} 00:00:00"
    if isinstance(value, str):
        stripped_value = value.strip()
        if len(stripped_value) >= 10:
            try:
                parsed_date = date.fromisoformat(stripped_value[:10])
                return f"{parsed_date.isoformat()} 00:00:00"
            except ValueError:
                pass
    return f"{date.today().isoformat()} 00:00:00"


def build_record_from_chunk(chunk: dict[str, Any], version: str = "demo-v1") -> dict[str, Any]:
    """将一个分片映射为 knowledge_embeddings 表记录。"""
    meta_data = dict(chunk.get("meta_data") or {})
    chunk_id = str(chunk.get("chunk_id") or "").strip()
    if not chunk_id:
        content_hash = hashlib.md5(str(chunk.get("content") or "").encode("utf-8")).hexdigest()
        chunk_id = f"chunk_{content_hash[:12]}"
    source_doc = str(chunk.get("source_doc") or meta_data.get("source_doc") or "")
    heading = str(chunk.get("heading") or meta_data.get("heading") or "")
    content = str(chunk.get("plain_text") or chunk.get("content") or "")
    content_hash = str(chunk.get("content_md5") or hashlib.md5(content.encode("utf-8")).hexdigest())
    source_type = str(meta_data.get("doc_format") or Path(source_doc).suffix.lstrip(".") or "unknown")
    tags = list(chunk.get("keywords") or meta_data.get("keywords") or [])
    metadata = {
        **meta_data,
        "chunk_id": chunk_id,
        "source_doc": source_doc,
        "heading": heading,
        "chunk_index": chunk.get("chunk_index", meta_data.get("chunk_index", 0)),
        "global_index": chunk.get("global_index", meta_data.get("global_index")),
        "char_count": chunk.get("char_count", len(content)),
        "token_estimate": chunk.get("token_estimate"),
        "content_md5": content_hash,
    }
    created_at = _day_precision_timestamp(chunk.get("created_at") or meta_data.get("created_at"))
    return {
        "id": chunk_id,
        "title": heading or Path(source_doc).stem,
        "content": content,
        "content_hash": content_hash,
        "metadata": metadata,
        "metadata_hash": _stable_json_hash(metadata),
        "anomaly_type": chunk.get("anomaly_type") or meta_data.get("anomaly_type") or "general",
        "source_file": source_doc,
        "source_name": Path(source_doc).stem,
        "source_type": source_type,
        "page": meta_data.get("page"),
        "section": heading,
        "version": version,
        "tags": tags,
        "created_at": created_at,
        "updated_at": created_at,
    }


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def _connect():
    import psycopg

    return psycopg.connect(settings.vector_database_url or settings.database_url)


def _build_upsert_query(table_identifier: Any) -> Any:
    import psycopg.sql

    return psycopg.sql.SQL("""
        INSERT INTO {table_name} (
            id, title, content, content_hash, metadata, metadata_hash,
            anomaly_type, source_file, source_name, source_type, page,
            section, version, tags, embedding, is_active, created_at, updated_at
        ) VALUES (
            %(id)s, %(title)s, %(content)s, %(content_hash)s, %(metadata)s::jsonb, %(metadata_hash)s,
            %(anomaly_type)s, %(source_file)s, %(source_name)s, %(source_type)s, %(page)s,
            %(section)s, %(version)s, %(tags)s, %(embedding)s::vector, TRUE,
            %(created_at)s::timestamptz, %(updated_at)s::timestamptz
        )
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            content = EXCLUDED.content,
            content_hash = EXCLUDED.content_hash,
            metadata = EXCLUDED.metadata,
            metadata_hash = EXCLUDED.metadata_hash,
            anomaly_type = EXCLUDED.anomaly_type,
            source_file = EXCLUDED.source_file,
            source_name = EXCLUDED.source_name,
            source_type = EXCLUDED.source_type,
            page = EXCLUDED.page,
            section = EXCLUDED.section,
            version = EXCLUDED.version,
            tags = EXCLUDED.tags,
            embedding = EXCLUDED.embedding,
            is_active = TRUE,
            updated_at = EXCLUDED.updated_at
    """).format(table_name=table_identifier)


def upsert_records(records: list[dict[str, Any]]) -> None:
    """批量 upsert 向量记录到 pgvector 表。"""
    if not records:
        return
    import psycopg.sql

    explicit_schema, raw_table_name = split_table_name(settings.vector_table_name)
    schema_name = explicit_schema or settings.vector_db_schema
    table_identifier = psycopg.sql.Identifier(schema_name, raw_table_name)
    query = _build_upsert_query(table_identifier)
    params = []
    for record in records:
        params.append({
            **record,
            "metadata": json.dumps(record["metadata"], ensure_ascii=False),
            "embedding": _vector_literal(record["embedding"]),
        })
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, params)
        conn.commit()


def embed_and_upsert_chunks(
    chunks: list[dict[str, Any]],
    batch_size: int | None = None,
    version: str = "demo-v1",
) -> int:
    """批量向量化分片并写入数据库，返回处理数量。"""
    batch_size = batch_size or settings.embedding_batch_size
    total = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        records = [build_record_from_chunk(chunk, version=version) for chunk in batch]
        texts = [record["content"] for record in records]
        embeddings = embedding_client.embed_documents(texts)
        if len(embeddings) != len(records):
            raise RuntimeError("Embedding 返回数量与分片数量不一致")
        for record, embedding in zip(records, embeddings):
            if len(embedding) != settings.embedding_dimension:
                raise ValueError(
                    f"Embedding 维度不匹配: 实际 {len(embedding)}, 配置 {settings.embedding_dimension}"
                )
            record["embedding"] = embedding
        upsert_records(records)
        total += len(records)
        logger.info("已写入向量分片: %s/%s", total, len(chunks))
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="将 data/chunks 分片向量化后写入 pgvector。")
    parser.add_argument("--chunks-file", type=Path, default=DEFAULT_CHUNKS_FILE, help="分片 JSON 或 JSONL 文件路径")
    parser.add_argument("--version", default="demo-v1", help="写入 knowledge_embeddings.version 的版本号")
    parser.add_argument("--batch-size", type=int, default=settings.embedding_batch_size, help="Embedding 批大小")
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    if not embedding_client.enabled:
        raise RuntimeError("EMBEDDING_API_KEY 未配置，无法向量化分片")
    chunks = load_chunks(args.chunks_file)
    count = embed_and_upsert_chunks(chunks, batch_size=args.batch_size, version=args.version)
    print(json.dumps({"chunks_file": str(args.chunks_file), "upserted": count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""分片向量化入库脚本测试。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _sample_chunk() -> dict:
    return {
        "chunk_id": "设备维保标准操作规程_分片_001_abcd1234",
        "source_doc": "设备维保标准操作规程.md",
        "heading": "维保执行流程",
        "content": "设备维保前必须执行 LOTO，上锁挂牌后方可作业。",
        "plain_text": "设备维保前必须执行 LOTO，上锁挂牌后方可作业。",
        "char_count": 27,
        "token_estimate": 13,
        "anomaly_type": "equipment_conflict",
        "keywords": ["设备", "维保"],
        "chunk_index": 0,
        "global_index": 0,
        "content_md5": "abcd1234abcd1234abcd1234abcd1234",
        "created_at": "2026-06-23 00:00:00",
        "meta_data": {
            "source_doc": "设备维保标准操作规程.md",
            "doc_format": "markdown",
            "business_domain": "设备管理",
            "source_systems": ["MES", "设备管理台账"],
            "created_at": "2026-06-23 00:00:00",
        },
    }


def test_build_record_from_chunk_maps_vector_table_fields():
    """分片应映射为 knowledge_embeddings 表需要的字段。"""
    from app.scripts.embed_chunks_to_vector_db import build_record_from_chunk

    record = build_record_from_chunk(_sample_chunk(), version="demo-v1")

    assert record["id"] == "设备维保标准操作规程_分片_001_abcd1234"
    assert record["title"] == "维保执行流程"
    assert record["content"] == "设备维保前必须执行 LOTO，上锁挂牌后方可作业。"
    assert record["content_hash"] == "abcd1234abcd1234abcd1234abcd1234"
    assert record["metadata"]["business_domain"] == "设备管理"
    assert record["metadata"]["chunk_id"] == record["id"]
    assert record["metadata_hash"]
    assert record["anomaly_type"] == "equipment_conflict"
    assert record["source_file"] == "设备维保标准操作规程.md"
    assert record["source_name"] == "设备维保标准操作规程"
    assert record["source_type"] == "markdown"
    assert record["section"] == "维保执行流程"
    assert record["version"] == "demo-v1"
    assert record["tags"] == ["设备", "维保"]
    assert record["created_at"] == "2026-06-23 00:00:00"
    assert record["updated_at"] == "2026-06-23 00:00:00"


def test_load_chunks_reads_json_array_and_jsonl(tmp_path):
    """脚本应同时支持 JSON 数组和 JSONL 分片文件。"""
    from app.scripts.embed_chunks_to_vector_db import load_chunks

    chunk = _sample_chunk()
    json_path = tmp_path / "chunks.json"
    json_path.write_text(json.dumps([chunk], ensure_ascii=False), encoding="utf-8")

    jsonl_path = tmp_path / "chunks.jsonl"
    jsonl_path.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")

    assert load_chunks(json_path) == [chunk]
    assert load_chunks(jsonl_path) == [chunk]


def test_build_upsert_query_writes_day_precision_timestamps():
    """向量入库 SQL 应显式写入日期零点格式的创建和更新时间。"""
    import psycopg.sql

    from app.scripts.embed_chunks_to_vector_db import _build_upsert_query

    query = _build_upsert_query(psycopg.sql.SQL("knowledge_embeddings")).as_string()
    normalized_query = " ".join(query.split())

    assert "created_at, updated_at" in normalized_query
    assert "%(created_at)s::timestamptz, %(updated_at)s::timestamptz" in normalized_query
    assert "updated_at = EXCLUDED.updated_at" in normalized_query
    assert "updated_at = now()" not in normalized_query


def test_embed_and_upsert_chunks_batches_embeddings_and_writes_records(monkeypatch):
    """向量化入库应按批调用 embedding，并将向量写入 upsert 记录。"""
    import app.scripts.embed_chunks_to_vector_db as script

    chunks = [_sample_chunk(), {**_sample_chunk(), "chunk_id": "chunk-002", "content": "物料库存低于安全库存。"}]
    embedded_texts = []

    def fake_embed_documents(texts):
        embedded_texts.extend(texts)
        return [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]][: len(texts)]

    upserted = []
    monkeypatch.setattr(script.embedding_client, "embed_documents", fake_embed_documents)
    monkeypatch.setattr(script, "upsert_records", lambda records: upserted.extend(records))
    monkeypatch.setattr(script.settings, "embedding_dimension", 3)

    count = script.embed_and_upsert_chunks(chunks, batch_size=2, version="demo-v1")

    assert count == 2
    assert embedded_texts == [chunks[0]["plain_text"], chunks[1]["plain_text"]]
    assert len(upserted) == 2
    assert upserted[0]["embedding"] == [0.1, 0.2, 0.3]
    assert upserted[1]["embedding"] == [0.4, 0.5, 0.6]

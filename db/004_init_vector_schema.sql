-- XCMG RCA Agent 向量库初始化脚本
-- 目标连接：VECTOR_DATABASE_URL
-- 默认向量维度：1024，对应 bge-m3；如更换模型，请同步调整 embedding vector(1024)。
-- 执行前请确认当前数据库用户拥有 CREATE EXTENSION / CREATE SCHEMA / CREATE TABLE 权限。

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id TEXT PRIMARY KEY,
    title TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_hash TEXT NOT NULL,
    anomaly_type TEXT,
    source_file TEXT,
    source_name TEXT,
    source_type TEXT,
    page INTEGER,
    section TEXT,
    version TEXT,
    tags TEXT[] DEFAULT ARRAY[]::TEXT[],
    embedding vector(1024) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT date_trunc('day', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT date_trunc('day', now())
);

CREATE INDEX IF NOT EXISTS idx_rca_vector_knowledge_embeddings_anomaly_type
    ON knowledge_embeddings(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_rca_vector_knowledge_embeddings_source_file
    ON knowledge_embeddings(source_file);
CREATE INDEX IF NOT EXISTS idx_rca_vector_knowledge_embeddings_version
    ON knowledge_embeddings(version);
CREATE INDEX IF NOT EXISTS idx_rca_vector_knowledge_embeddings_is_active
    ON knowledge_embeddings(is_active);
CREATE INDEX IF NOT EXISTS idx_rca_vector_knowledge_embeddings_metadata_gin
    ON knowledge_embeddings USING gin(metadata);
CREATE INDEX IF NOT EXISTS idx_rca_vector_knowledge_embeddings_embedding_hnsw
    ON knowledge_embeddings USING hnsw (embedding vector_cosine_ops);

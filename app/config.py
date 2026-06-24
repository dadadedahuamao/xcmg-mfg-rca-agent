"""应用配置模块，基于 pydantic-settings 从环境变量和 .env 文件加载配置。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """XCMG RCA Agent 全局配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 数据库 ──────────────────────────────────────────────
    database_url: str = "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca"
    database_schema: str = "rca"

    # ── 业务数据库（只读） ──────────────────────────────────
    # 用于连接外部业务系统数据库（MES/WMS/QMS 等），Text2SQL 和业务工具查询此库。
    # 生产环境建议使用只读账号，禁止 INSERT/UPDATE/DELETE/DDL。
    business_database_url: str = "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca"
    business_database_schema: str = "public"

    # ── 服务 ────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    # ── RAG ─────────────────────────────────────────────────
    rag_knowledge_dir: str = "./app/data/knowledge"
    rag_top_k: int = 5

    # ── 向量数据库 ──────────────────────────────────────────
    vector_db_provider: str = "pgvector"
    vector_database_url: str = "postgresql://rca_user:rca_password@localhost:5432/xcmg_rca"
    vector_db_schema: str = "rca_vector"
    vector_collection_name: str = "xcmg_rca_knowledge"
    vector_table_name: str = "knowledge_embeddings"
    vector_db_path: str = "./app/data/vector_store"

    # ── LLM ─────────────────────────────────────────────────
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3

    # ── Embedding ────────────────────────────────────────────
    embedding_provider: str = "openai"
    embedding_model: str = "bge-m3"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_dimension: int = 1024
    embedding_batch_size: int = 32

    # ── Reranker ─────────────────────────────────────────────
    reranker_provider: str = "none"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_base_url: str = ""
    reranker_api_key: str = ""
    reranker_top_n: int = 5

    # ── 工作流 ──────────────────────────────────────────────
    max_reflection_rounds: int = 3
    confidence_threshold: float = 0.7
    reflection_low_score_threshold: float = 0.4

    # ── Text2SQL ────────────────────────────────────────────
    text2sql_whitelist_tables: str = (
        "work_orders,equipment_maintenance,material_inventory,"
        "quality_records,interface_logs"
    )
    text2sql_max_limit: int = 100

    # ── 日志 ────────────────────────────────────────────────
    log_level: str = "INFO"

    @property
    def knowledge_dir(self):
        from pathlib import Path

        return Path(self.rag_knowledge_dir)

    @property
    def whitelist_tables(self) -> list[str]:
        return [t.strip() for t in self.text2sql_whitelist_tables.split(",") if t.strip()]


# 全局单例
settings = Settings()

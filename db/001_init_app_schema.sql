-- XCMG RCA Agent 应用库初始化脚本
-- 目标连接：DATABASE_URL
-- 包含：RCA 应用表 + 元数据层表
-- 执行前请确认当前数据库用户拥有 CREATE TABLE 权限。

-- ════════════════════════════════════════════════════════════
-- 应用层（Application Layer）
-- RCA 工作流核心数据：任务、报告、反馈、检查点、工具去重、聊天
-- ════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS rca_tasks (
    task_id TEXT PRIMARY KEY,
    anomaly_type TEXT NOT NULL,
    description TEXT NOT NULL,
    source_system TEXT DEFAULT 'MES',
    status TEXT DEFAULT 'pending',
    confidence DOUBLE PRECISION DEFAULT 0.0,
    reflection_rounds INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS rca_reports (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    root_cause TEXT,
    root_cause_category TEXT,
    hypotheses TEXT DEFAULT '[]',
    evidence_summary TEXT DEFAULT '[]',
    tool_call_history TEXT DEFAULT '[]',
    confidence DOUBLE PRECISION DEFAULT 0.0,
    reflection_rounds INTEGER DEFAULT 0,
    recommendations TEXT DEFAULT '[]',
    final_report TEXT DEFAULT '{}',
    generated_at TEXT NOT NULL,
    CONSTRAINT fk_rca_reports_task
        FOREIGN KEY (task_id) REFERENCES rca_tasks(task_id)
);

CREATE TABLE IF NOT EXISTS rca_feedback (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_rca_feedback_task
        FOREIGN KEY (task_id) REFERENCES rca_tasks(task_id)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_checkpoints_task
        FOREIGN KEY (task_id) REFERENCES rca_tasks(task_id)
);

CREATE TABLE IF NOT EXISTS rca_step_events (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    node_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    detail TEXT,
    detail_json TEXT,
    checkpoint_id BIGINT,
    created_at TEXT NOT NULL,
    CONSTRAINT fk_step_events_task
        FOREIGN KEY (task_id) REFERENCES rca_tasks(task_id),
    CONSTRAINT fk_step_events_checkpoint
        FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(id),
    CONSTRAINT uq_step_events_task_seq UNIQUE (task_id, seq)
);

CREATE TABLE IF NOT EXISTS tool_dedup (
    id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT uq_tool_dedup_task_tool_params
        UNIQUE (task_id, tool_name, params_hash),
    CONSTRAINT fk_tool_dedup_task
        FOREIGN KEY (task_id) REFERENCES rca_tasks(task_id)
);

-- chat_conversations 聊天会话表
CREATE TABLE IF NOT EXISTS chat_conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    pinned INTEGER DEFAULT 0,
    archived INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_message_at TEXT
);

-- chat_messages 聊天消息表
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content TEXT DEFAULT '',
    anomaly_type TEXT,
    task_id TEXT,
    report_snapshot TEXT,
    error INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

-- 应用表索引
CREATE INDEX IF NOT EXISTS idx_rca_tasks_status
    ON rca_tasks(status);
CREATE INDEX IF NOT EXISTS idx_rca_tasks_created
    ON rca_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_checkpoints_task
    ON checkpoints(task_id, node_name);
CREATE INDEX IF NOT EXISTS idx_tool_dedup_task
    ON tool_dedup(task_id);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_updated
    ON chat_conversations(user_id, archived, pinned, updated_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created
    ON chat_messages(conversation_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_task
    ON chat_messages(task_id);

-- ════════════════════════════════════════════════════════════
-- 元数据层（Metadata Layer）
-- 用于管理外部业务系统的表结构、字段含义、业务术语等元数据
-- ════════════════════════════════════════════════════════════

-- 数据源注册表 — 登记外部业务系统（MES/WMS/QMS/ERP 等）
CREATE TABLE IF NOT EXISTS data_sources (
    id BIGSERIAL PRIMARY KEY,
    source_code TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'postgresql',
    connection_key TEXT,
    schema_name TEXT,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 外部系统表元数据
CREATE TABLE IF NOT EXISTS source_tables (
    id BIGSERIAL PRIMARY KEY,
    source_code TEXT NOT NULL,
    table_name TEXT NOT NULL,
    table_alias TEXT,
    description TEXT,
    is_whitelisted INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_code, table_name)
);

-- 字段元数据
CREATE TABLE IF NOT EXISTS source_columns (
    id BIGSERIAL PRIMARY KEY,
    source_code TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    column_alias TEXT,
    data_type TEXT,
    description TEXT,
    unit TEXT,
    example_value TEXT,
    is_nullable INTEGER DEFAULT 1,
    is_sensitive INTEGER DEFAULT 0,
    sensitivity_level TEXT DEFAULT 'internal',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_code, table_name, column_name)
);

-- 业务术语字典
CREATE TABLE IF NOT EXISTS business_terms (
    id BIGSERIAL PRIMARY KEY,
    term_code TEXT NOT NULL UNIQUE,
    term_name TEXT NOT NULL,
    term_category TEXT,
    definition TEXT,
    synonyms TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 术语到字段映射
CREATE TABLE IF NOT EXISTS term_mappings (
    id BIGSERIAL PRIMARY KEY,
    term_code TEXT NOT NULL,
    source_code TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    filter_condition TEXT,
    calculation_formula TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (term_code, source_code, table_name, column_name)
);

-- 跨表关联关系
CREATE TABLE IF NOT EXISTS join_relationships (
    id BIGSERIAL PRIMARY KEY,
    left_source TEXT NOT NULL,
    left_table TEXT NOT NULL,
    left_column TEXT NOT NULL,
    right_source TEXT NOT NULL,
    right_table TEXT NOT NULL,
    right_column TEXT NOT NULL,
    join_type TEXT DEFAULT 'INNER',
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 语义指标定义
CREATE TABLE IF NOT EXISTS semantic_metrics (
    id BIGSERIAL PRIMARY KEY,
    metric_code TEXT NOT NULL UNIQUE,
    metric_name TEXT NOT NULL,
    metric_category TEXT,
    definition TEXT,
    calculation_formula TEXT,
    unit TEXT,
    related_terms TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 查询模板
CREATE TABLE IF NOT EXISTS query_templates (
    id BIGSERIAL PRIMARY KEY,
    template_code TEXT NOT NULL UNIQUE,
    template_name TEXT NOT NULL,
    description TEXT,
    sql_template TEXT NOT NULL,
    parameters TEXT DEFAULT '{}',
    category TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 元数据表索引
CREATE INDEX IF NOT EXISTS idx_source_tables_source
    ON source_tables(source_code);
CREATE INDEX IF NOT EXISTS idx_source_columns_table
    ON source_columns(source_code, table_name);
CREATE INDEX IF NOT EXISTS idx_term_mappings_term
    ON term_mappings(term_code);
CREATE INDEX IF NOT EXISTS idx_join_relationships_left
    ON join_relationships(left_source, left_table);
CREATE INDEX IF NOT EXISTS idx_join_relationships_right
    ON join_relationships(right_source, right_table);

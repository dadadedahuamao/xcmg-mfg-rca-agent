-- XCMG RCA Agent 业务表初始化脚本（Demo/Sample）
-- 注意：生产环境中这些表应位于业务系统自有数据库，而非 RCA 应用库。
-- 本脚本仅用于本地开发/演示，在业务库中创建示例表结构。
-- 执行目标：BUSINESS_DATABASE_URL / BUSINESS_DATABASE_SCHEMA

CREATE TABLE IF NOT EXISTS work_orders (
    id BIGSERIAL PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    product_name TEXT,
    workstation TEXT,
    planned_start TEXT,
    planned_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equipment_maintenance (
    id BIGSERIAL PRIMARY KEY,
    equipment_id TEXT NOT NULL,
    equipment_name TEXT,
    workstation TEXT,
    maintenance_type TEXT,
    planned_date TEXT,
    actual_date TEXT,
    status TEXT DEFAULT 'planned',
    technician TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS material_inventory (
    id BIGSERIAL PRIMARY KEY,
    material_code TEXT NOT NULL,
    material_name TEXT,
    warehouse TEXT,
    quantity DOUBLE PRECISION DEFAULT 0,
    safety_stock DOUBLE PRECISION DEFAULT 0,
    unit TEXT DEFAULT 'pcs',
    last_updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_records (
    id BIGSERIAL PRIMARY KEY,
    record_no TEXT NOT NULL UNIQUE,
    product_name TEXT,
    workstation TEXT,
    defect_type TEXT,
    defect_count INTEGER DEFAULT 0,
    total_inspected INTEGER DEFAULT 0,
    inspector TEXT,
    inspection_date TEXT NOT NULL,
    status TEXT DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS interface_logs (
    id BIGSERIAL PRIMARY KEY,
    interface_name TEXT NOT NULL,
    source_system TEXT,
    target_system TEXT,
    request_time TEXT NOT NULL,
    response_time TEXT,
    status_code INTEGER,
    success INTEGER DEFAULT 1,
    error_message TEXT,
    duration_ms INTEGER DEFAULT 0
);

-- 业务表索引
CREATE INDEX IF NOT EXISTS idx_work_orders_status
    ON work_orders(status);
CREATE INDEX IF NOT EXISTS idx_equipment_maintenance_status
    ON equipment_maintenance(status);
CREATE INDEX IF NOT EXISTS idx_quality_records_status
    ON quality_records(status);
CREATE INDEX IF NOT EXISTS idx_interface_logs_interface
    ON interface_logs(interface_name);

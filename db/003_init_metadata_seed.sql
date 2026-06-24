-- XCMG RCA Agent 元数据初始数据
-- 目标连接：DATABASE_URL
-- 为元数据层表插入初始数据，供 Text2SQL 白名单验证和字段映射使用。

-- ════════════════════════════════════════════════════════════
-- 数据源注册表
-- ════════════════════════════════════════════════════════════
INSERT INTO data_sources (source_code, source_name, source_type, schema_name, description, is_active, created_at, updated_at)
VALUES
    ('MES', '制造执行系统', 'postgresql', 'public', '制造执行系统，管理工单、设备维保等生产数据', 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('WMS', '仓储管理系统', 'postgresql', 'public', '仓储管理系统，管理物料库存数据', 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', '质量管理系统', 'postgresql', 'public', '质量管理系统，管理质量检验记录', 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ERP', '企业资源计划', 'postgresql', 'public', '企业资源计划系统，管理财务、采购等数据', 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', '企业服务总线', 'postgresql', 'public', '企业服务总线，记录系统间接口调用日志', 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (source_code) DO NOTHING;

-- ════════════════════════════════════════════════════════════
-- 外部系统表元数据
-- ════════════════════════════════════════════════════════════
INSERT INTO source_tables (source_code, table_name, table_alias, description, is_whitelisted, is_active, created_at, updated_at)
VALUES
    ('MES', 'work_orders', '工单表', '生产工单主表，记录每个工单的计划与执行信息', 1, 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', '设备维保表', '设备维保记录表，记录设备保养和维修计划与执行', 1, 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('WMS', 'material_inventory', '物料库存表', '物料库存表，记录各仓库物料库存量和安全库存', 1, 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', '质量记录表', '质量检验记录表，记录产品检验的不良类型和数量', 1, 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', '接口日志表', '系统间接口调用日志表，记录请求响应和状态', 1, 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (source_code, table_name) DO NOTHING;

-- ════════════════════════════════════════════════════════════
-- 字段元数据
-- ════════════════════════════════════════════════════════════

-- work_orders 字段
INSERT INTO source_columns (source_code, table_name, column_name, column_alias, data_type, description, example_value, is_sensitive, sensitivity_level, created_at, updated_at)
VALUES
    ('MES', 'work_orders', 'order_no', '工单号', 'TEXT', '生产工单唯一编号', 'WO-2025-0001', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'product_name', '产品名称', 'TEXT', '生产的产品名称/型号', '挖掘机液压缸-XE200', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'workstation', '工位', 'TEXT', '生产工位编号', 'WS-03', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'planned_start', '计划开始时间', 'TEXT', '计划开始生产时间', '2025-01-15 08:00:00', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'planned_end', '计划结束时间', 'TEXT', '计划完成生产时间', '2025-01-15 16:00:00', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'actual_start', '实际开始时间', 'TEXT', '实际开始生产时间', '2025-01-15 08:30:00', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'actual_end', '实际结束时间', 'TEXT', '实际完成生产时间', '2025-01-15 17:30:00', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'status', '状态', 'TEXT', '工单状态：pending/in_progress/completed/delayed', 'in_progress', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'priority', '优先级', 'INTEGER', '工单优先级，数值越大优先级越高', '1', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'created_at', '创建时间', 'TEXT', '记录创建时间', '2025-01-15 07:00:00', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (source_code, table_name, column_name) DO NOTHING;

-- equipment_maintenance 字段
INSERT INTO source_columns (source_code, table_name, column_name, column_alias, data_type, description, example_value, is_sensitive, sensitivity_level, created_at, updated_at)
VALUES
    ('MES', 'equipment_maintenance', 'equipment_id', '设备编号', 'TEXT', '设备唯一编号', 'EQ-001', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'equipment_name', '设备名称', 'TEXT', '设备名称', '数控加工中心-CNC3', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'workstation', '工位', 'TEXT', '设备所在工位', 'WS-03', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'maintenance_type', '维保类型', 'TEXT', '维保类型：preventive/corrective/inspection', 'preventive', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'planned_date', '计划日期', 'TEXT', '计划维保日期', '2025-01-20', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'actual_date', '实际日期', 'TEXT', '实际维保日期', '2025-01-21', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'status', '状态', 'TEXT', '维保状态：planned/in_progress/completed/overdue', 'planned', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'technician', '技师', 'TEXT', '负责维保的技师姓名', '张师傅', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'notes', '备注', 'TEXT', '维保备注信息', '更换了液压油滤芯', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'equipment_maintenance', 'created_at', '创建时间', 'TEXT', '记录创建时间', '2025-01-10 08:00:00', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (source_code, table_name, column_name) DO NOTHING;

-- material_inventory 字段
INSERT INTO source_columns (source_code, table_name, column_name, column_alias, data_type, description, example_value, is_sensitive, sensitivity_level, created_at, updated_at)
VALUES
    ('WMS', 'material_inventory', 'material_code', '物料编码', 'TEXT', '物料唯一编码', 'MAT-001', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('WMS', 'material_inventory', 'material_name', '物料名称', 'TEXT', '物料名称描述', '液压油缸密封圈', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('WMS', 'material_inventory', 'warehouse', '仓库', 'TEXT', '仓库编号', 'WH-01', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('WMS', 'material_inventory', 'quantity', '库存量', 'DOUBLE PRECISION', '当前库存数量', '500', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('WMS', 'material_inventory', 'safety_stock', '安全库存', 'DOUBLE PRECISION', '安全库存阈值，低于此值需补货', '200', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('WMS', 'material_inventory', 'unit', '单位', 'TEXT', '计量单位', 'pcs', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('WMS', 'material_inventory', 'last_updated', '最后更新', 'TEXT', '库存最后更新时间', '2025-01-15 10:00:00', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (source_code, table_name, column_name) DO NOTHING;

-- quality_records 字段
INSERT INTO source_columns (source_code, table_name, column_name, column_alias, data_type, description, example_value, is_sensitive, sensitivity_level, created_at, updated_at)
VALUES
    ('QMS', 'quality_records', 'record_no', '记录编号', 'TEXT', '质量检验记录唯一编号', 'QR-2025-0001', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', 'product_name', '产品名称', 'TEXT', '被检验产品名称/型号', '挖掘机液压缸-XE200', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', 'workstation', '工位', 'TEXT', '检验所在工位', 'WS-03', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', 'defect_type', '不良类型', 'TEXT', '不良类型：scratch/deformation/crack/leak/other', 'scratch', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', 'defect_count', '不良数', 'INTEGER', '检验发现的不良品数量', '5', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', 'total_inspected', '检验数', 'INTEGER', '总检验数量', '100', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', 'inspector', '检验员', 'TEXT', '检验员姓名', '李工', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', 'inspection_date', '检验日期', 'TEXT', '检验日期', '2025-01-15', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('QMS', 'quality_records', 'status', '状态', 'TEXT', '检验记录状态：open/closed/reviewed', 'open', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (source_code, table_name, column_name) DO NOTHING;

-- interface_logs 字段
INSERT INTO source_columns (source_code, table_name, column_name, column_alias, data_type, description, example_value, is_sensitive, sensitivity_level, created_at, updated_at)
VALUES
    ('ESB', 'interface_logs', 'interface_name', '接口名称', 'TEXT', '接口名称/标识', 'MES.WorkOrder.Query', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', 'source_system', '源系统', 'TEXT', '发起请求的系统', 'RCA-Agent', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', 'target_system', '目标系统', 'TEXT', '接收请求的系统', 'MES', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', 'request_time', '请求时间', 'TEXT', '请求发起时间', '2025-01-15 10:00:00', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', 'response_time', '响应时间', 'TEXT', '响应返回时间', '2025-01-15 10:00:05', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', 'status_code', '状态码', 'INTEGER', 'HTTP 状态码', '200', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', 'success', '是否成功', 'INTEGER', '调用是否成功：1=成功 0=失败', '1', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', 'error_message', '错误信息', 'TEXT', '失败时的错误信息', 'Connection timeout', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('ESB', 'interface_logs', 'duration_ms', '耗时毫秒', 'INTEGER', '接口调用耗时（毫秒）', '5000', 0, 'internal', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (source_code, table_name, column_name) DO NOTHING;

-- ════════════════════════════════════════════════════════════
-- 业务术语字典
-- ════════════════════════════════════════════════════════════
INSERT INTO business_terms (term_code, term_name, term_category, definition, synonyms, created_at, updated_at)
VALUES
    ('work_order', '工单', '生产', '生产工单，指下达给生产线或工位的生产任务指令', '生产工单, 作业工单', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('delayed_order', '延期工单', '生产', '实际完成时间超过计划完成时间的工单', '延期订单, 逾期工单', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('defect_rate', '不良率', '质量', '检验中发现的不良品数量占总检验数量的比例', '不良品率, 次品率', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('safety_stock', '安全库存', '库存', '为应对需求波动而设置的最低库存水平', '最低库存, 安全库存量', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('equipment_downtime', '设备停机', '设备', '设备因故障或维保而停止运行的状态', '设备故障, 停机时间', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('material_shortage', '物料短缺', '库存', '库存量低于安全库存，无法满足生产需求的状况', '缺料, 物料不足', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('interface_timeout', '接口超时', '系统', '系统间接口调用超过预设时间阈值未返回响应', '调用超时, 连接超时', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('inspection', '质量检验', '质量', '对产品进行质量检查和测试的过程', '质检, 质量检查', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('maintenance_overdue', '维保逾期', '设备', '设备维保计划到期但未按时执行的情况', '保养逾期, 维保超期', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('production_anomaly', '生产异常', '生产', '生产过程中出现的非正常事件或状态', '异常事件, 生产故障', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (term_code) DO NOTHING;

-- ════════════════════════════════════════════════════════════
-- 术语到字段映射
-- ════════════════════════════════════════════════════════════
INSERT INTO term_mappings (term_code, source_code, table_name, column_name, filter_condition, calculation_formula, created_at, updated_at)
VALUES
    ('work_order', 'MES', 'work_orders', 'order_no', NULL, NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('work_order', 'MES', 'work_orders', 'status', NULL, NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('delayed_order', 'MES', 'work_orders', 'status', 'status = ''delayed''', NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('defect_rate', 'QMS', 'quality_records', 'defect_count', NULL, 'defect_count / total_inspected * 100', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('defect_rate', 'QMS', 'quality_records', 'total_inspected', NULL, 'defect_count / total_inspected * 100', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('safety_stock', 'WMS', 'material_inventory', 'safety_stock', NULL, NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('material_shortage', 'WMS', 'material_inventory', 'quantity', 'quantity < safety_stock', NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('material_shortage', 'WMS', 'material_inventory', 'safety_stock', 'quantity < safety_stock', NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('equipment_downtime', 'MES', 'equipment_maintenance', 'status', 'status IN (''in_progress'', ''overdue'')', NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('interface_timeout', 'ESB', 'interface_logs', 'duration_ms', 'duration_ms > 3000', NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('inspection', 'QMS', 'quality_records', 'record_no', NULL, NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('maintenance_overdue', 'MES', 'equipment_maintenance', 'status', 'status = ''overdue''', NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (term_code, source_code, table_name, column_name) DO NOTHING;

-- ════════════════════════════════════════════════════════════
-- 跨表关联关系
-- ════════════════════════════════════════════════════════════
INSERT INTO join_relationships (left_source, left_table, left_column, right_source, right_table, right_column, join_type, description, created_at, updated_at)
VALUES
    ('MES', 'work_orders', 'workstation', 'MES', 'equipment_maintenance', 'workstation', 'LEFT', '通过工位关联工单与设备维保，分析设备状态对工单的影响', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'product_name', 'QMS', 'quality_records', 'product_name', 'LEFT', '通过产品名称关联工单与质量记录，分析产品质量问题', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('MES', 'work_orders', 'product_name', 'WMS', 'material_inventory', 'material_name', 'LEFT', '通过产品/物料名称关联工单与库存，分析物料短缺对工单的影响', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT DO NOTHING;

-- ════════════════════════════════════════════════════════════
-- 语义指标定义
-- ════════════════════════════════════════════════════════════
INSERT INTO semantic_metrics (metric_code, metric_name, metric_category, definition, calculation_formula, unit, related_terms, created_at, updated_at)
VALUES
    ('defect_rate', '不良率', '质量', '检验中发现的不良品数量占总检验数量的百分比', 'defect_count / total_inspected * 100', '%', 'defect_rate, inspection', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('delayed_order_rate', '延期工单率', '生产', '延期工单数量占总工单数量的百分比', 'COUNT(CASE WHEN status = ''delayed'' THEN 1 END) / COUNT(*) * 100', '%', 'delayed_order, work_order', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('inventory_coverage', '库存覆盖率', '库存', '当前库存量相对于安全库存的倍数，衡量库存充裕程度', 'quantity / safety_stock', '倍', 'safety_stock, material_shortage', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (metric_code) DO NOTHING;

-- ════════════════════════════════════════════════════════════
-- 查询模板
-- ════════════════════════════════════════════════════════════
INSERT INTO query_templates (template_code, template_name, description, sql_template, parameters, category, is_active, created_at, updated_at)
VALUES
    ('delayed_workorders', '查询延期工单', '查询所有已延期的生产工单，按计划结束时间排序', 'SELECT order_no, product_name, workstation, planned_start, planned_end, actual_end, priority FROM work_orders WHERE status = ''delayed'' ORDER BY planned_end ASC', '{}', '生产查询', 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z'),
    ('high_defect_products', '查询高不良率产品', '查询不良率超过阈值的产品，按不良率降序排列', 'SELECT product_name, workstation, SUM(defect_count) AS total_defects, SUM(total_inspected) AS total_inspected, ROUND(SUM(defect_count) * 100.0 / SUM(total_inspected), 2) AS defect_rate FROM quality_records WHERE inspection_date >= $__start_date__ AND inspection_date <= $__end_date__ GROUP BY product_name, workstation HAVING SUM(defect_count) * 100.0 / SUM(total_inspected) > $__threshold__ ORDER BY defect_rate DESC', '{"start_date": "2025-01-01", "end_date": "2025-01-31", "threshold": "5"}', '质量分析', 1, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')
ON CONFLICT (template_code) DO NOTHING;

"""插入示例数据。

运行前请先执行 db/002_init_business_schema.sql 创建业务库结构。
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.persistence import postgres
from datetime import datetime, timedelta


def _offset_timestamp(days: int = 0) -> str:
    """返回相对当前日期偏移的数据库时间戳格式。"""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def insert_sample_data():
    """插入示例数据到所有业务表。"""
    conn = postgres.get_business_connection()
    now = postgres.database_timestamp()
    yesterday = _offset_timestamp(days=1)
    two_days_ago = _offset_timestamp(days=2)

    try:
        # ── 工单数据 ────────────────────────────────────────
        work_orders = [
            ("WO-2024-0101", "P-1001", "WS-03", yesterday, yesterday, None, None, "delayed", 9, now),
            ("WO-2024-0102", "P-1002", "WS-03", yesterday, yesterday, None, None, "in_progress", 7, now),
            ("WO-2024-0103", "P-1003", "WS-05", two_days_ago, two_days_ago, two_days_ago, None, "delayed", 8, now),
            ("WO-2024-0104", "P-1004", "WS-07", yesterday, yesterday, yesterday, None, "in_progress", 5, now),
            ("WO-2024-0105", "P-1005", "WS-02", yesterday, yesterday, yesterday, yesterday, "completed", 3, now),
            ("WO-2024-0106", "P-1006", "WS-05", now, now, None, None, "pending", 6, now),
            ("WO-2024-0107", "P-1007", "WS-03", two_days_ago, two_days_ago, None, None, "blocked", 10, now),
            ("WO-2024-0108", "P-1008", "WS-08", yesterday, yesterday, None, None, "pending", 4, now),
            ("WO-2024-0109", "P-1009", "WS-05", now, now, None, None, "pending", 8, now),
            ("WO-2024-0110", "P-1010", "WS-04", yesterday, yesterday, yesterday, None, "in_progress", 5, now),
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO work_orders
               (order_no, product_name, workstation, planned_start, planned_end,
                actual_start, actual_end, status, priority, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            work_orders,
        )

        # ── 设备维保数据 ────────────────────────────────────
        maintenance = [
            ("EQ-001", "数控机床-01", "WS-03", "预防性维护", two_days_ago, None, "overdue", "张工", "设备异响需检查", now),
            ("EQ-002", "数控机床-02", "WS-05", "故障维修", yesterday, None, "in_progress", "李工", "主轴精度偏差", now),
            ("EQ-003", "加工中心-01", "WS-07", "预防性维护", now, None, "planned", "王工", "定期保养", now),
            ("EQ-004", "数控机床-03", "WS-02", "预防性维护", yesterday, yesterday, "completed", "赵工", "保养完成", now),
            ("EQ-005", "加工中心-02", "WS-05", "故障维修", two_days_ago, None, "overdue", "李工", "刀库故障", now),
            ("EQ-006", "数控机床-04", "WS-08", "预防性维护", now, None, "planned", "张工", "季度保养", now),
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO equipment_maintenance
               (equipment_id, equipment_name, workstation, maintenance_type,
                planned_date, actual_date, status, technician, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            maintenance,
        )

        # ── 物料库存数据 ────────────────────────────────────
        materials = [
            ("MAT-301", "轴承-6308", "WH-01", 500, 200, "pcs", now),
            ("MAT-302", "密封圈-DN50", "WH-01", 150, 100, "pcs", now),
            ("MAT-303", "液压油-46#", "WH-02", 80, 200, "L", now),
            ("MAT-304", "齿轮-M3Z20", "WH-01", 50, 200, "pcs", now),
            ("MAT-305", "螺栓-M12x50", "WH-03", 2000, 500, "pcs", now),
            ("MAT-306", "传感器-PT100", "WH-02", 30, 50, "pcs", now),
            ("MAT-307", "联轴器-DN40", "WH-01", 120, 80, "pcs", now),
            ("MAT-308", "电机-5.5kW", "WH-03", 5, 10, "pcs", now),
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO material_inventory
               (material_code, material_name, warehouse, quantity,
                safety_stock, unit, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            materials,
        )

        # ── 质量记录数据 ────────────────────────────────────
        quality = [
            ("QR-2024-001", "P-2003", "WS-07", "尺寸超差", 60, 500, "陈质检", yesterday, "open"),
            ("QR-2024-002", "P-1001", "WS-03", "表面粗糙度", 15, 300, "陈质检", yesterday, "open"),
            ("QR-2024-003", "P-2005", "WS-05", "装配不良", 8, 200, "刘质检", two_days_ago, "open"),
            ("QR-2024-004", "P-1004", "WS-07", "尺寸超差", 25, 400, "陈质检", two_days_ago, "open"),
            ("QR-2024-005", "P-1002", "WS-03", "表面粗糙度", 3, 200, "刘质检", now, "open"),
            ("QR-2024-006", "P-2003", "WS-07", "硬度不足", 12, 300, "陈质检", now, "open"),
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO quality_records
               (record_no, product_name, workstation, defect_type, defect_count,
                total_inspected, inspector, inspection_date, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            quality,
        )

        # ── 接口日志数据 ────────────────────────────────────
        interface_logs = [
            ("MES-WMS", "MES", "WMS", yesterday, yesterday, 200, 1, None, 120),
            ("MES-WMS", "MES", "WMS", yesterday, yesterday, 500, 0, "Gateway Timeout", 8500),
            ("MES-WMS", "MES", "WMS", yesterday, yesterday, 500, 0, "Connection refused", 8200),
            ("MES-QMS", "MES", "QMS", yesterday, yesterday, 200, 1, None, 350),
            ("APS-MES", "APS", "MES", yesterday, yesterday, 200, 1, None, 200),
            ("MES-WMS", "MES", "WMS", yesterday, None, None, 0, "Timeout", 10000),
            ("MES-WMS", "MES", "WMS", yesterday, yesterday, 500, 0, "Internal Server Error", 7500),
            ("WMS-APS", "WMS", "APS", yesterday, yesterday, 200, 1, None, 180),
            ("MES-WMS", "MES", "WMS", yesterday, yesterday, 200, 1, None, 95),
            ("MES-QMS", "MES", "QMS", yesterday, yesterday, 200, 1, None, 420),
            ("MES-WMS", "MES", "WMS", yesterday, yesterday, 500, 0, "Timeout", 9200),
            ("APS-MES", "APS", "MES", yesterday, yesterday, 200, 1, None, 150),
        ]
        conn.executemany(
            """INSERT OR IGNORE INTO interface_logs
               (interface_name, source_system, target_system, request_time,
                response_time, status_code, success, error_message, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            interface_logs,
        )

        conn.commit()
        print(f"示例数据已插入:")
        print(f"  - 工单: {len(work_orders)} 条")
        print(f"  - 设备维保: {len(maintenance)} 条")
        print(f"  - 物料库存: {len(materials)} 条")
        print(f"  - 质量记录: {len(quality)} 条")
        print(f"  - 接口日志: {len(interface_logs)} 条")

    finally:
        conn.close()


def main():
    print("插入示例数据（请先执行 db/002_init_business_schema.sql）...")
    insert_sample_data()
    print("示例数据插入完成!")


if __name__ == "__main__":
    main()

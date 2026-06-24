"""Text2SQL 生成器 - 将中文/英文查询模式映射为安全的 SELECT SQL。

支持：
- 多轮对话：空结果时尝试替代查询（最多 3 轮）
- 查询意图分类：count（计数）、detail（明细）、aggregate（聚合）
- 模板驱动：基于关键词和异常类型的规则匹配
"""

import re
from enum import Enum
from typing import Optional


class QueryIntent(str, Enum):
    """查询意图分类。"""
    COUNT = "count"       # 计数查询：返回记录数
    DETAIL = "detail"     # 明细查询：返回具体记录
    AGGREGATE = "aggregate"  # 聚合查询：返回统计信息


class SQLGenerator:
    """基于模板的 SQL 生成器。

    将已知的查询模式映射为预定义的 SELECT 语句。
    不依赖外部 LLM，使用规则匹配。

    多轮生成策略：
    1. 第一轮：根据异常类型和关键词匹配最佳模板
    2. 如果执行返回空结果，尝试放宽条件（去掉状态过滤）
    3. 如果仍然空结果，尝试全表查询
    4. 最多 3 轮，超过则返回最后生成的 SQL
    """

    MAX_ROUNDS = 3  # 最大生成轮次

    # 查询模式 → SQL 模板
    PATTERNS = {
        # 工单查询
        "delayed_orders": """
            SELECT order_no, product_name, workstation, status, priority,
                   planned_end, actual_end
            FROM work_orders
            WHERE status IN ('delayed', 'blocked')
            ORDER BY priority DESC
            LIMIT {limit}
        """,
        "pending_orders": """
            SELECT order_no, product_name, workstation, status,
                   planned_start, planned_end
            FROM work_orders
            WHERE status = 'pending'
            ORDER BY priority DESC, planned_start ASC
            LIMIT {limit}
        """,
        "all_orders": """
            SELECT * FROM work_orders
            ORDER BY created_at DESC
            LIMIT {limit}
        """,
        "order_count": """
            SELECT status, COUNT(*) AS cnt
            FROM work_orders
            GROUP BY status
            ORDER BY cnt DESC
        """,

        # 设备维保查询
        "overdue_maintenance": """
            SELECT equipment_id, equipment_name, workstation,
                   maintenance_type, planned_date, status
            FROM equipment_maintenance
            WHERE status = 'overdue'
            ORDER BY planned_date ASC
            LIMIT {limit}
        """,
        "planned_maintenance": """
            SELECT * FROM equipment_maintenance
            WHERE status = 'planned'
            ORDER BY planned_date ASC
            LIMIT {limit}
        """,
        "all_maintenance": """
            SELECT * FROM equipment_maintenance
            ORDER BY planned_date DESC
            LIMIT {limit}
        """,

        # 物料查询
        "material_shortage": """
            SELECT material_code, material_name, warehouse,
                   quantity, safety_stock,
                   (safety_stock - quantity) AS shortage
            FROM material_inventory
            WHERE quantity <= safety_stock
            ORDER BY shortage DESC
            LIMIT {limit}
        """,
        "all_materials": """
            SELECT * FROM material_inventory
            ORDER BY material_code ASC
            LIMIT {limit}
        """,
        "material_aggregate": """
            SELECT warehouse, COUNT(*) AS material_count,
                   SUM(quantity) AS total_quantity,
                   AVG(quantity) AS avg_quantity
            FROM material_inventory
            GROUP BY warehouse
        """,

        # 质量查询
        "quality_defects": """
            SELECT record_no, product_name, workstation,
                   defect_type, defect_count, total_inspected,
                   CAST(defect_count AS REAL) / NULLIF(total_inspected, 0) AS defect_rate
            FROM quality_records
            WHERE status = 'open'
            ORDER BY defect_count DESC
            LIMIT {limit}
        """,
        "all_quality": """
            SELECT * FROM quality_records
            ORDER BY inspection_date DESC
            LIMIT {limit}
        """,
        "quality_aggregate": """
            SELECT defect_type, COUNT(*) AS cnt,
                   SUM(defect_count) AS total_defects,
                   AVG(CAST(defect_count AS REAL) / NULLIF(total_inspected, 0)) AS avg_defect_rate
            FROM quality_records
            GROUP BY defect_type
            ORDER BY total_defects DESC
        """,

        # 接口日志查询
        "interface_failures": """
            SELECT interface_name, source_system, target_system,
                   request_time, status_code, error_message, duration_ms
            FROM interface_logs
            WHERE success = 0
            ORDER BY request_time DESC
            LIMIT {limit}
        """,
        "interface_timeouts": """
            SELECT interface_name, source_system, target_system,
                   request_time, duration_ms, success
            FROM interface_logs
            WHERE duration_ms > 5000
            ORDER BY duration_ms DESC
            LIMIT {limit}
        """,
        "all_interfaces": """
            SELECT * FROM interface_logs
            ORDER BY request_time DESC
            LIMIT {limit}
        """,
        "interface_aggregate": """
            SELECT interface_name,
                   COUNT(*) AS total_calls,
                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failures,
                   AVG(duration_ms) AS avg_duration_ms,
                   MAX(duration_ms) AS max_duration_ms
            FROM interface_logs
            GROUP BY interface_name
        """,
    }

    # 中文关键词 → 查询模式
    KEYWORD_MAP = {
        "延迟": "delayed_orders",
        "超期": "delayed_orders",
        "工单": "all_orders",
        "设备": "planned_maintenance",
        "维保": "planned_maintenance",
        "逾期": "overdue_maintenance",
        "物料": "all_materials",
        "短缺": "material_shortage",
        "库存": "all_materials",
        "缺料": "material_shortage",
        "质量": "all_quality",
        "不良": "quality_defects",
        "缺陷": "quality_defects",
        "接口": "all_interfaces",
        "超时": "interface_timeouts",
        "失败": "interface_failures",
        "timeout": "interface_timeouts",
        "failure": "interface_failures",
        "delay": "delayed_orders",
        "quality": "all_quality",
        "material": "all_materials",
        "maintenance": "planned_maintenance",
        # 聚合意图关键词
        "统计": "aggregate",
        "汇总": "aggregate",
        "计数": "count",
        "数量": "count",
        "多少": "count",
        "平均": "aggregate",
        "合计": "aggregate",
    }

    # 异常类型 → 默认查询模式
    ANOMALY_SQL_MAP = {
        "overstation_check": "delayed_orders",
        "equipment_conflict": "planned_maintenance",
        "material_shortage": "material_shortage",
        "quality_abnormal": "quality_defects",
        "interface_timeout": "interface_timeouts",
        "schedule_risk": "delayed_orders",
    }

    # 主模式 → 回退模式（放宽条件）
    FALLBACK_MAP = {
        "delayed_orders": "all_orders",
        "pending_orders": "all_orders",
        "overdue_maintenance": "all_maintenance",
        "planned_maintenance": "all_maintenance",
        "material_shortage": "all_materials",
        "quality_defects": "all_quality",
        "interface_failures": "all_interfaces",
        "interface_timeouts": "all_interfaces",
    }

    # 意图关键词 → 聚合查询映射
    INTENT_AGGREGATE_MAP = {
        "delayed_orders": "order_count",
        "all_orders": "order_count",
        "material_shortage": "material_aggregate",
        "all_materials": "material_aggregate",
        "quality_defects": "quality_aggregate",
        "all_quality": "quality_aggregate",
        "interface_failures": "interface_aggregate",
        "all_interfaces": "interface_aggregate",
    }

    def __init__(self):
        self._round_history: list[dict] = []  # 多轮生成历史

    def generate(
        self, query: str, anomaly_type: str = "", limit: int = 50
    ) -> str:
        """根据查询文本和异常类型生成 SQL。

        Args:
            query: 自然语言查询
            anomaly_type: 异常类型
            limit: 返回行数限制

        Returns:
            生成的 SELECT SQL 语句
        """
        pattern_name = self._match_pattern(query, anomaly_type)
        intent = self.classify_intent(query)

        # 如果意图是聚合/计数，优先使用聚合模板
        if intent in (QueryIntent.AGGREGATE, QueryIntent.COUNT):
            agg_pattern = self.INTENT_AGGREGATE_MAP.get(pattern_name)
            if agg_pattern and agg_pattern in self.PATTERNS:
                template = self.PATTERNS[agg_pattern]
                return template.format(limit=min(limit, 100)).strip()

        template = self.PATTERNS.get(pattern_name, self.PATTERNS["all_orders"])
        sql = template.format(limit=min(limit, 100)).strip()

        # 记录生成历史
        self._round_history.append({
            "round": len(self._round_history) + 1,
            "query": query,
            "pattern": pattern_name,
            "intent": intent.value,
            "sql": sql,
        })

        return sql

    def generate_fallback(self, previous_sql: str, query: str = "") -> Optional[str]:
        """生成回退 SQL（放宽条件）。

        当上一轮 SQL 返回空结果时调用，尝试更宽松的查询。

        Args:
            previous_sql: 上一轮生成的 SQL
            query: 原始查询文本

        Returns:
            回退 SQL，如果无法回退则返回 None
        """
        round_num = len(self._round_history)

        if round_num >= self.MAX_ROUNDS:
            return None  # 达到最大轮次

        # 根据轮次选择回退策略
        if round_num == 1:
            # 第一轮回退：使用 FALLBACK_MAP 放宽条件
            last_pattern = self._round_history[-1].get("pattern", "")
            fallback_pattern = self.FALLBACK_MAP.get(last_pattern)
            if fallback_pattern and fallback_pattern in self.PATTERNS:
                template = self.PATTERNS[fallback_pattern]
                sql = template.format(limit=100).strip()
                self._round_history.append({
                    "round": len(self._round_history) + 1,
                    "query": query,
                    "pattern": fallback_pattern,
                    "intent": "fallback",
                    "sql": sql,
                    "reason": f"从 {last_pattern} 回退到 {fallback_pattern}（放宽条件）",
                })
                return sql

        elif round_num == 2:
            # 第二轮回退：全表查询
            # 从上一轮的 SQL 中提取表名
            table = self._extract_table(previous_sql)
            if table:
                all_pattern = f"all_{table}" if not table.endswith("s") else f"all_{table}"
                # 尝试匹配已知的全表模式
                known_all = {
                    "work_orders": "all_orders",
                    "equipment_maintenance": "all_maintenance",
                    "material_inventory": "all_materials",
                    "quality_records": "all_quality",
                    "interface_logs": "all_interfaces",
                }
                pattern = known_all.get(table, "all_orders")
                if pattern in self.PATTERNS:
                    template = self.PATTERNS[pattern]
                    sql = template.format(limit=100).strip()
                    self._round_history.append({
                        "round": len(self._round_history) + 1,
                        "query": query,
                        "pattern": pattern,
                        "intent": "fallback",
                        "sql": sql,
                        "reason": f"全表回退: {table}",
                    })
                    return sql

        return None

    def classify_intent(self, query: str) -> QueryIntent:
        """分类查询意图。

        根据查询文本中的关键词判断意图类型：
        - count: 计数类（多少、数量、计数）
        - aggregate: 聚合类（统计、汇总、平均、合计）
        - detail: 明细类（默认）

        Args:
            query: 自然语言查询

        Returns:
            QueryIntent 枚举值
        """
        query_lower = query.lower()

        # 计数意图
        count_keywords = ["多少", "数量", "计数", "几条", "几个", "count"]
        for kw in count_keywords:
            if kw in query_lower:
                return QueryIntent.COUNT

        # 聚合意图
        agg_keywords = ["统计", "汇总", "平均", "合计", "分组", "aggregate", "summary"]
        for kw in agg_keywords:
            if kw in query_lower:
                return QueryIntent.AGGREGATE

        return QueryIntent.DETAIL

    def get_round_history(self) -> list[dict]:
        """获取多轮生成历史。"""
        return list(self._round_history)

    def reset_history(self) -> None:
        """重置生成历史。"""
        self._round_history.clear()

    def _match_pattern(self, query: str, anomaly_type: str) -> str:
        """匹配查询模式。"""
        query_lower = query.lower()

        # 优先使用异常类型映射
        if anomaly_type in self.ANOMALY_SQL_MAP:
            return self.ANOMALY_SQL_MAP[anomaly_type]

        # 关键词匹配
        for keyword, pattern in self.KEYWORD_MAP.items():
            if keyword.lower() in query_lower:
                # 跳过意图关键词（它们不影响模式匹配）
                if pattern in ("aggregate", "count"):
                    continue
                return pattern

        return "all_orders"

    @staticmethod
    def _extract_table(sql: str) -> Optional[str]:
        """从 SQL 中提取表名。"""
        match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
        return match.group(1) if match else None

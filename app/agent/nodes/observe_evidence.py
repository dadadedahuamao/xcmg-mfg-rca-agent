"""节点 5: 观察证据 - 分析工具返回结果，更新假设概率。"""

import logging
from typing import Any

from app.agent.state import RCAState

logger = logging.getLogger(__name__)

# ── 工具名别名映射 ──────────────────────────────────────────
# 解决 generate_hypotheses.py 中 required_tools 使用
# "material_inventory" 而 select_tool.py 选择 "material" 的不一致问题
TOOL_ALIASES: dict[str, set[str]] = {
    "material": {"material", "material_inventory"},
    "material_inventory": {"material", "material_inventory"},
    "equipment_maintenance": {"equipment_maintenance", "equipment"},
    "equipment": {"equipment_maintenance", "equipment"},
}


def _tool_matches(tool_name: str, required_tools: list[str]) -> bool:
    """检查工具名是否匹配假设的 required_tools（含别名映射）。

    例如：tool_name="material" 可以匹配 required_tools 中的
    "material" 或 "material_inventory"。
    """
    aliases = TOOL_ALIASES.get(tool_name, {tool_name})
    return any(rt in aliases for rt in required_tools)


def observe_evidence_node(state: RCAState) -> RCAState:
    """观察工具返回的证据，更新假设概率。

    对每个假设：
    1. 检查工具结果是否支持/反驳该假设（含别名匹配）
    2. 基于数据值 + 关键词双重评估证据强度
    3. 调整概率
    4. 记录支持/反驳证据
    """
    tool_results = state.tool_call_history

    for hypothesis in state.hypotheses:
        h_id = hypothesis.get("id", "")
        required_tools = hypothesis.get("required_tools", [])

        supporting = []
        refuting = []

        for record in tool_results:
            tool_name = record.get("tool_name", "")
            output = record.get("output", {})
            success = record.get("success", False)

            if not success:
                continue

            # 检查工具是否与假设相关（含别名映射）
            if not _tool_matches(tool_name, required_tools):
                continue

            # 评估证据对假设的支持度
            score = _evaluate_evidence(hypothesis, tool_name, output)
            if score > 0:
                supporting.append({
                    "tool": tool_name,
                    "score": score,
                    "summary": _summarize_output(tool_name, output),
                })
            elif score < 0:
                refuting.append({
                    "tool": tool_name,
                    "score": abs(score),
                    "summary": _summarize_output(tool_name, output),
                })

        # 更新假设概率
        hypothesis["supporting_evidence"] = supporting
        hypothesis["refuting_evidence"] = refuting
        hypothesis["probability"] = _adjust_probability(
            hypothesis.get("probability", 0.5),
            supporting,
            refuting,
        )

        # 更新状态
        if hypothesis["probability"] > 0.6:
            hypothesis["status"] = "confirmed"
        elif hypothesis["probability"] < 0.2:
            hypothesis["status"] = "rejected"
        else:
            hypothesis["status"] = "pending"

    # 收集所有证据到 state.evidence
    for record in tool_results:
        if record.get("success"):
            state.add_evidence({
                "tool_name": record.get("tool_name"),
                "output": record.get("output"),
                "timestamp": record.get("timestamp"),
            })

    confirmed = [h for h in state.hypotheses if h["status"] == "confirmed"]
    logger.info(
        f"[observe_evidence] task={state.task_id} "
        f"confirmed={len(confirmed)} total={len(state.hypotheses)}"
    )

    return state


def _evaluate_evidence(hypothesis: dict, tool_name: str, output: dict) -> float:
    """评估工具输出对假设的支持度 (-1 到 1)。

    采用双重评估策略：
    1. 数据值检查（主要）：检查 output 中的结构化数据字段
    2. 关键词匹配（辅助）：检查 output 字符串化后的关键词
    """
    # ── 数据值检查（主要信号） ──────────────────────────────
    data_score = _evaluate_data_values(tool_name, output)

    # ── 关键词匹配（辅助信号） ──────────────────────────────
    keyword_score = _evaluate_keywords(tool_name, output)

    # 数据值信号权重更高
    if abs(data_score) > 0.1:
        # 数据值有明确信号，以它为主，关键词作为微调
        return max(-1.0, min(1.0, data_score + keyword_score * 0.1))
    else:
        # 数据值无信号，依赖关键词
        return keyword_score


def _evaluate_data_values(tool_name: str, output: dict) -> float:
    """基于工具输出中的结构化数据值评估证据强度。

    检查各工具特有的数据字段，返回 -1 到 1 的评分。
    """
    if not isinstance(output, dict):
        return 0.0

    # ── material 工具 ────────────────────────────────────────
    if tool_name in ("material", "material_inventory"):
        # 检查 has_shortage 字段
        if output.get("has_shortage", False):
            shortage_count = output.get("shortage_count", 0)
            # 短缺物料越多，证据越强
            score = min(0.8, 0.3 + shortage_count * 0.1)
            return score

        # 检查 data 列表中的具体数值
        data = output.get("data", [])
        shortage_signals = 0
        for record in data:
            qty = record.get("quantity", 0)
            safety = record.get("safety_stock", 0)
            if isinstance(qty, (int, float)) and isinstance(safety, (int, float)):
                if qty <= safety and safety > 0:
                    shortage_signals += 1
        if shortage_signals > 0:
            return min(0.8, 0.3 + shortage_signals * 0.1)

        # 检查 shortages 列表
        shortages = output.get("shortages", [])
        if isinstance(shortages, list) and len(shortages) > 0:
            return min(0.8, 0.3 + len(shortages) * 0.1)

        return 0.0

    # ── interface_log 工具 ───────────────────────────────────
    if tool_name == "interface_log":
        failure_count = output.get("failure_count", 0)
        timeout_count = output.get("timeout_count", 0)
        slow_count = output.get("slow_count", 0)

        # 有失败或超时 → 强正信号
        if failure_count > 0 or timeout_count > 0:
            score = min(0.8, 0.3 + (failure_count + timeout_count) * 0.1)
            return score

        # 有慢调用 → 中等正信号
        if slow_count > 0:
            return min(0.6, 0.2 + slow_count * 0.05)

        # 检查 data 列表中的具体数值
        data = output.get("data", [])
        failure_signals = 0
        timeout_signals = 0
        for record in data:
            success_val = record.get("success", 1)
            duration = record.get("duration_ms", 0)
            if not success_val:
                failure_signals += 1
            if isinstance(duration, (int, float)) and duration > 5000:
                timeout_signals += 1
        if failure_signals > 0 or timeout_signals > 0:
            return min(0.8, 0.3 + (failure_signals + timeout_signals) * 0.1)

        return 0.0

    # ── workorder 工具 ───────────────────────────────────────
    if tool_name == "workorder":
        anomaly_count = output.get("anomaly_count", 0)
        anomalies = output.get("anomalies", [])

        if anomaly_count > 0:
            return min(0.8, 0.3 + anomaly_count * 0.1)

        # 检查 data 中的状态
        data = output.get("data", [])
        anomaly_signals = 0
        for record in data:
            status = record.get("status", "")
            if status in ("delayed", "blocked"):
                anomaly_signals += 1
        if anomaly_signals > 0:
            return min(0.8, 0.3 + anomaly_signals * 0.1)

        return 0.0

    # ── quality 工具 ─────────────────────────────────────────
    if tool_name == "quality":
        is_abnormal = output.get("is_abnormal", False)
        defect_rate = output.get("defect_rate", 0)

        if is_abnormal:
            return min(0.8, 0.3 + defect_rate * 5)

        # 检查 data 中的缺陷数
        data = output.get("data", [])
        defect_signals = 0
        for record in data:
            defect_count = record.get("defect_count", 0)
            total_inspected = record.get("total_inspected", 1)
            if isinstance(defect_count, (int, float)) and total_inspected > 0:
                rate = defect_count / total_inspected
                if rate > 0.03:
                    defect_signals += 1
        if defect_signals > 0:
            return min(0.8, 0.3 + defect_signals * 0.1)

        return 0.0

    # ── equipment_maintenance 工具 ───────────────────────────
    if tool_name in ("equipment_maintenance", "equipment"):
        overdue_count = output.get("overdue_count", 0)
        in_progress_count = output.get("in_progress_count", 0)

        if overdue_count > 0:
            return min(0.8, 0.3 + overdue_count * 0.15)

        if in_progress_count > 0:
            return min(0.6, 0.2 + in_progress_count * 0.1)

        # 检查 data 中的状态
        data = output.get("data", [])
        overdue_signals = 0
        for record in data:
            status = record.get("status", "")
            if status == "overdue":
                overdue_signals += 1
        if overdue_signals > 0:
            return min(0.8, 0.3 + overdue_signals * 0.15)

        return 0.0

    # ── resource 工具 ────────────────────────────────────────
    if tool_name == "resource":
        conflict_count = output.get("conflict_count", 0)
        if conflict_count > 0:
            return min(0.8, 0.3 + conflict_count * 0.1)
        return 0.0

    # ── knowledge 工具 ───────────────────────────────────────
    if tool_name == "knowledge":
        count = output.get("count", 0)
        if count > 0:
            return min(0.6, count * 0.1)
        return 0.0

    return 0.0


def _evaluate_keywords(tool_name: str, output: dict) -> float:
    """基于关键词匹配评估证据（辅助信号）。"""
    positive_keywords = {
        "equipment_maintenance": ["故障", "维修", "保养", "异常", "停机"],
        "equipment": ["故障", "维修", "保养", "异常", "停机"],
        "workorder": ["延迟", "超期", "堆积", "等待"],
        "material": ["短缺", "不足", "缺料", "低于安全库存"],
        "material_inventory": ["短缺", "不足", "缺料", "低于安全库存"],
        "quality": ["不良", "缺陷", "超标", "异常"],
        "interface_log": ["超时", "失败", "错误", "timeout"],
        "resource": ["冲突", "争用", "不足", "瓶颈"],
        "knowledge": ["方案", "SOP", "最佳实践", "处理流程"],
        "text2sql": [],
    }

    negative_keywords = {
        "equipment_maintenance": ["正常", "完成", "无异常"],
        "equipment": ["正常", "完成", "无异常"],
        "workorder": ["正常", "按时", "完成"],
        "material": ["充足", "正常", "安全库存以上"],
        "material_inventory": ["充足", "正常", "安全库存以上"],
        "quality": ["合格", "正常", "通过"],
        "interface_log": ["成功", "正常", "200"],
        "resource": ["充足", "空闲", "可用"],
        "knowledge": [],
        "text2sql": [],
    }

    output_str = str(output).lower()

    pos_score = sum(
        1 for kw in positive_keywords.get(tool_name, []) if kw in output_str
    )
    neg_score = sum(
        1 for kw in negative_keywords.get(tool_name, []) if kw in output_str
    )

    if pos_score > neg_score:
        return min(0.8, pos_score * 0.2)
    elif neg_score > pos_score:
        return -min(0.8, neg_score * 0.2)
    return 0.0


def _adjust_probability(
    prior: float,
    supporting: list[dict],
    refuting: list[dict],
) -> float:
    """根据证据调整假设概率。

    强证据（score >= 0.5）使用更高的乘数因子 0.25，
    弱证据使用默认乘数 0.15。
    """
    # 分类证据强度
    strong_support = [s for s in supporting if s.get("score", 0) >= 0.5]
    weak_support = [s for s in supporting if s.get("score", 0) < 0.5]
    strong_refute = [r for r in refuting if r.get("score", 0) >= 0.5]
    weak_refute = [r for r in refuting if r.get("score", 0) < 0.5]

    # 强证据用 0.25 乘数，弱证据用 0.15
    support_weight = (
        sum(s.get("score", 0) for s in strong_support) * 0.25
        + sum(s.get("score", 0) for s in weak_support) * 0.15
    )
    refute_weight = (
        sum(r.get("score", 0) for r in strong_refute) * 0.25
        + sum(r.get("score", 0) for r in weak_refute) * 0.15
    )

    adjusted = prior + support_weight - refute_weight
    return max(0.01, min(0.99, adjusted))


def _summarize_output(tool_name: str, output: dict) -> str:
    """生成工具输出的简短摘要。"""
    if isinstance(output, dict):
        # 优先使用工具特有的摘要字段
        if tool_name in ("material", "material_inventory"):
            if output.get("has_shortage"):
                return f"发现 {output.get('shortage_count', 0)} 种物料短缺"
            return f"返回 {output.get('count', 0)} 条物料记录"
        if tool_name == "interface_log":
            fc = output.get("failure_count", 0)
            tc = output.get("timeout_count", 0)
            if fc > 0 or tc > 0:
                return f"发现 {fc} 次失败, {tc} 次超时"
            return f"返回 {output.get('count', 0)} 条接口日志"
        if tool_name == "workorder":
            ac = output.get("anomaly_count", 0)
            if ac > 0:
                return f"发现 {ac} 个异常工单"
            return f"返回 {output.get('count', 0)} 条工单记录"
        if tool_name == "quality":
            if output.get("is_abnormal"):
                return f"不良率 {output.get('defect_rate', 0):.1%}，存在异常"
            return f"返回 {output.get('count', 0)} 条质量记录"
        if tool_name in ("equipment_maintenance", "equipment"):
            oc = output.get("overdue_count", 0)
            if oc > 0:
                return f"发现 {oc} 项逾期维保"
            return f"返回 {output.get('count', 0)} 条维保记录"
        if tool_name == "resource":
            cc = output.get("conflict_count", 0)
            if cc > 0:
                return f"发现 {cc} 处资源冲突"
            return f"返回 {output.get('count', 0)} 条资源记录"

        if "count" in output:
            return f"返回 {output['count']} 条记录"
        if "data" in output and isinstance(output["data"], list):
            return f"返回 {len(output['data'])} 条记录"
        if "results" in output and isinstance(output["results"], list):
            return f"返回 {len(output['results'])} 条结果"
    return "执行成功"

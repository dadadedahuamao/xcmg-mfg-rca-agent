"""节点 7: 反思 — 5 维度自评估 RCA 草稿质量，决定下一步行动。

五维度评估体系：
1. 证据充分性 (evidence_sufficiency)    — 权重 0.25
2. 置信度水平 (confidence_level)        — 权重 0.30
3. 工具覆盖度 (tool_coverage)           — 权重 0.15
4. 证据一致性 (evidence_consistency)    — 权重 0.15
5. 假设收敛性 (hypothesis_convergence)  — 权重 0.15

决策规则（阈值由 settings 动态配置）：
- 综合得分 >= CONFIDENCE_THRESHOLD → PROCEED
- 综合得分 >= REFLECTION_LOW_SCORE_THRESHOLD 且未达最大轮次 → NEED_MORE_EVIDENCE
- 综合得分 < REFLECTION_LOW_SCORE_THRESHOLD → NEED_MORE_EVIDENCE
- reflection_round >= MAX_REFLECTION_ROUNDS - 1 → PROCEED（强制结束）
"""

import logging

from app.agent.state import RCAState
from app.config import settings
from app.prompts.templates import PromptManager

logger = logging.getLogger(__name__)

# Prompt 管理器（模块级单例）
_prompt_manager = PromptManager()

# 五维度权重
WEIGHTS = {
    "evidence_sufficiency": 0.25,
    "confidence_level": 0.30,
    "tool_coverage": 0.15,
    "evidence_consistency": 0.15,
    "hypothesis_convergence": 0.15,
}


def reflect_node(state: RCAState) -> RCAState:
    """5 维度自反思评估。

    对当前 RCA 草稿进行五维度量化评估，综合得分决定下一步行动：
    - PROCEED: 证据充分，可生成最终报告
    - NEED_MORE_EVIDENCE: 证据不足，需要补充工具调用
    """
    # ── Prompt Engineering: 渲染并记录 prompt ────────────────
    try:
        prompt = _prompt_manager.render(
            "reflect",
            anomaly_type=state.anomaly_type,
            draft_rca=state.draft_rca or "暂无草稿",
            hypotheses=str(state.hypotheses),
            tool_call_history=str(state.tool_call_history),
            reflection_round=str(state.reflection_round),
            max_rounds=str(settings.max_reflection_rounds),
        )
        state.add_prompt_record("reflect", prompt)
        logger.debug(f"[reflect] Prompt 已渲染并记录")
    except Exception as e:
        logger.warning(f"[reflect] Prompt 渲染失败: {e}")

    round_num = state.reflection_round
    hypotheses = state.hypotheses
    total_h = len(hypotheses)
    confidence = state.confidence

    # 统计假设状态
    confirmed_h = [h for h in hypotheses if h.get("status") == "confirmed"]
    rejected_h = [h for h in hypotheses if h.get("status") == "rejected"]
    confirmed_count = len(confirmed_h)
    rejected_count = len(rejected_h)

    # 收集已调用的工具名
    called_tools: set[str] = set()
    for r in state.tool_call_history:
        tn = r.get("tool_name")
        if isinstance(tn, str):
            called_tools.add(tn)

    # 收集所有假设所需的工具
    all_required_tools: set[str] = set()
    for h in hypotheses:
        all_required_tools.update(h.get("required_tools", []))

    # ── 维度 1: 证据充分性 ──────────────────────────────────
    evidence_sufficiency = _calc_evidence_sufficiency(
        confirmed_count, total_h
    )

    # ── 维度 2: 置信度水平 ──────────────────────────────────
    confidence_level = _calc_confidence_level(confidence)

    # ── 维度 3: 工具覆盖度 ──────────────────────────────────
    tool_coverage = _calc_tool_coverage(called_tools, all_required_tools)

    # ── 维度 4: 证据一致性 ──────────────────────────────────
    evidence_consistency = _calc_evidence_consistency(hypotheses)

    # ── 维度 5: 假设收敛性 ──────────────────────────────────
    hypothesis_convergence = _calc_hypothesis_convergence(
        rejected_count, total_h
    )

    # ── 加权综合得分 ────────────────────────────────────────
    overall_score = (
        evidence_sufficiency * WEIGHTS["evidence_sufficiency"]
        + confidence_level * WEIGHTS["confidence_level"]
        + tool_coverage * WEIGHTS["tool_coverage"]
        + evidence_consistency * WEIGHTS["evidence_consistency"]
        + hypothesis_convergence * WEIGHTS["hypothesis_convergence"]
    )

    # ── 决策 ────────────────────────────────────────────────
    action, reasoning, missing_evidence = _decide_action(
        overall_score=overall_score,
        round_num=round_num,
        confirmed_count=confirmed_count,
        total_h=total_h,
        state=state,
    )

    # ── 构建维度详情 ────────────────────────────────────────
    dimensions = {
        "evidence_sufficiency": {
            "score": round(evidence_sufficiency, 3),
            "detail": (
                f"已确认 {confirmed_count}/{total_h} 个假设"
                if total_h > 0
                else "无假设"
            ),
        },
        "confidence_level": {
            "score": round(confidence_level, 3),
            "detail": f"当前置信度 {confidence:.0%}",
        },
        "tool_coverage": {
            "score": round(tool_coverage, 3),
            "detail": (
                f"已调用 {len(called_tools)}/{len(all_required_tools)} 个所需工具"
                if all_required_tools
                else "无所需工具"
            ),
        },
        "evidence_consistency": {
            "score": round(evidence_consistency, 3),
            "detail": _consistency_detail(hypotheses),
        },
        "hypothesis_convergence": {
            "score": round(hypothesis_convergence, 3),
            "detail": (
                f"已排除 {rejected_count}/{total_h} 个假设"
                if total_h > 0
                else "无假设"
            ),
        },
    }

    result = {
        "action": action,
        "reasoning": reasoning,
        "missing_evidence": missing_evidence,
        "confidence_adjustment": 0.0,
        "dimensions": dimensions,
        "overall_score": round(overall_score, 3),
    }

    state.set_reflection(result)

    logger.info(
        f"[reflect] task={state.task_id} round={round_num} "
        f"action={action} overall={overall_score:.3f} "
        f"ES={evidence_sufficiency:.2f} CL={confidence_level:.2f} "
        f"TC={tool_coverage:.2f} EC={evidence_consistency:.2f} "
        f"HC={hypothesis_convergence:.2f}"
    )

    return state


# ═══════════════════════════════════════════════════════════════
# 五维度计算函数
# ═══════════════════════════════════════════════════════════════

def _calc_evidence_sufficiency(confirmed_count: int, total_h: int) -> float:
    """维度 1: 证据充分性 — 已确认假设数 / 总假设数。

    已确认的假设越多，说明证据越充分。
    如果没有任何假设，返回 0。
    """
    if total_h == 0:
        return 0.0
    return min(1.0, confirmed_count / total_h)


def _calc_confidence_level(confidence: float) -> float:
    """维度 2: 置信度水平 — 直接使用 draft_rca 的 confidence 值。

    confidence 本身已在 0-1 范围内，直接作为得分。
    """
    return max(0.0, min(1.0, confidence))


def _calc_tool_coverage(
    called_tools: set[str], all_required_tools: set[str]
) -> float:
    """维度 3: 工具覆盖度 — 已调用工具数 / 假设所需工具数。

    覆盖度越高，说明收集的证据维度越全面。
    如果没有任何所需工具，返回 0。
    """
    if not all_required_tools:
        return 0.0
    return min(1.0, len(called_tools & all_required_tools) / len(all_required_tools))


def _calc_evidence_consistency(hypotheses: list[dict]) -> float:
    """维度 4: 证据一致性 — 支持证据 vs 反驳证据，无矛盾为高分。

    检查所有假设中支持证据和反驳证据的关系：
    - 无反驳证据 → 高分
    - 支持证据多且反驳少 → 中等
    - 反驳证据多 → 低分
    - 同一工具既支持又反驳多个假设 → 扣分（矛盾信号）
    """
    if not hypotheses:
        return 1.0  # 无假设，无矛盾

    total_supporting = 0
    total_refuting = 0

    for h in hypotheses:
        total_supporting += len(h.get("supporting_evidence", []))
        total_refuting += len(h.get("refuting_evidence", []))

    total_evidence = total_supporting + total_refuting

    if total_evidence == 0:
        return 0.5  # 无证据，中性

    # 基础得分：支持证据占比
    base_score = total_supporting / total_evidence

    # 扣分项：同一工具在多个假设中同时出现支持和反驳（矛盾信号）
    tool_roles: dict[str, set[str]] = {}  # tool_name → {"support", "refute"}
    for h in hypotheses:
        for ev in h.get("supporting_evidence", []):
            tool = ev.get("tool", "")
            if tool:
                tool_roles.setdefault(tool, set()).add("support")
        for ev in h.get("refuting_evidence", []):
            tool = ev.get("tool", "")
            if tool:
                tool_roles.setdefault(tool, set()).add("refute")

    contradiction_count = sum(
        1 for roles in tool_roles.values() if len(roles) > 1
    )
    penalty = min(0.5, contradiction_count * 0.1)

    return max(0.0, base_score - penalty)


def _calc_hypothesis_convergence(rejected_count: int, total_h: int) -> float:
    """维度 5: 假设收敛性 — 已排除假设数 / 总假设数。

    排除的假设越多，说明分析越收敛，方向越明确。
    如果没有任何假设，返回 0。
    """
    if total_h == 0:
        return 0.0
    return min(1.0, rejected_count / total_h)


# ═══════════════════════════════════════════════════════════════
# 决策函数
# ═══════════════════════════════════════════════════════════════

def _decide_action(
    overall_score: float,
    round_num: int,
    confirmed_count: int,
    total_h: int,
    state: RCAState,
) -> tuple[str, str, list[str]]:
    """根据综合得分和轮次决定下一步行动。

    Returns:
        (action, reasoning, missing_evidence)
    """
    has_confirmed_evidence = _has_confirmed_supporting_evidence(state)

    # 强制结束条件：达到最大反思轮次
    if round_num >= settings.max_reflection_rounds - 1:
        if not has_confirmed_evidence:
            return (
                "ESCALATE",
                f"已达到最大反思轮次 ({round_num + 1})，但仍缺少可确认根因的证据，不能强行给出结论",
                _identify_missing_evidence(state),
            )
        return (
            "PROCEED",
            f"已达到最大反思轮次 ({round_num + 1})，综合分 {overall_score:.3f}，强制结束",
            [],
        )

    # 综合决策
    if overall_score >= settings.confidence_threshold:
        return (
            "PROCEED",
            f"综合分 {overall_score:.3f} 达标（>= {settings.confidence_threshold}），证据充分，可生成报告",
            [],
        )
    elif overall_score >= settings.reflection_low_score_threshold:
        return (
            "NEED_MORE_EVIDENCE",
            f"综合分 {overall_score:.3f} 不足（>= {settings.reflection_low_score_threshold}），已确认 {confirmed_count}/{total_h} 个假设，需补充证据",
            _identify_missing_evidence(state),
        )
    else:
        return (
            "NEED_MORE_EVIDENCE",
            f"综合分 {overall_score:.3f} 过低（< {settings.reflection_low_score_threshold}），证据严重不足，需大幅补充",
            _identify_missing_evidence(state),
        )


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _consistency_detail(hypotheses: list[dict]) -> str:
    """生成证据一致性的文字说明。"""
    if not hypotheses:
        return "无假设"

    total_supporting = sum(
        len(h.get("supporting_evidence", [])) for h in hypotheses
    )
    total_refuting = sum(
        len(h.get("refuting_evidence", [])) for h in hypotheses
    )

    if total_supporting == 0 and total_refuting == 0:
        return "尚无证据，无法评估一致性"

    if total_refuting == 0:
        return f"全部 {total_supporting} 条证据均为支持，无矛盾"

    ratio = total_supporting / max(total_supporting + total_refuting, 1)
    if ratio >= 0.8:
        return f"支持证据占优 ({total_supporting} 支持 / {total_refuting} 反驳)"
    elif ratio >= 0.5:
        return f"存在一定矛盾 ({total_supporting} 支持 / {total_refuting} 反驳)"
    else:
        return f"反驳证据较多 ({total_supporting} 支持 / {total_refuting} 反驳)，需重新审视"


def _identify_missing_evidence(state: RCAState) -> list[str]:
    """识别缺失的证据类型。

    遍历所有未确认的假设，收集其所需但尚未调用的工具，
    映射为中文标签返回。
    """
    missing = set()
    called_tools: set[str] = set()
    for r in state.tool_call_history:
        tn = r.get("tool_name")
        if isinstance(tn, str):
            called_tools.add(tn)

    # 工具名 → 中文标签映射
    tool_label_map = {
        "workorder": "工单数据",
        "resource": "资源数据",
        "material": "物料数据",
        "material_inventory": "物料数据",
        "equipment_maintenance": "设备数据",
        "quality": "质量数据",
        "interface_log": "接口日志",
        "knowledge": "知识文档",
        "text2sql": "SQL查询",
    }

    for h in state.hypotheses:
        if h.get("status") != "confirmed":
            for tool in h.get("required_tools", []):
                if tool not in called_tools:
                    label = tool_label_map.get(tool, tool)
                    missing.add(label)

    # 额外检查：常用工具中尚未调用的
    common_tools = {
        "工单数据": "workorder",
        "设备数据": "equipment_maintenance",
        "物料数据": "material",
        "质量数据": "quality",
        "接口日志": "interface_log",
    }
    for label, tool_name in common_tools.items():
        if tool_name not in called_tools and any(
            tool_name in h.get("required_tools", []) for h in state.hypotheses
        ):
            missing.add(label)

    return list(missing)[:5]


def _has_confirmed_supporting_evidence(state: RCAState) -> bool:
    """是否存在已确认且有支持证据的根因假设。"""
    for hypothesis in state.hypotheses:
        if hypothesis.get("status") != "confirmed":
            continue
        supporting = hypothesis.get("supporting_evidence", [])
        if isinstance(supporting, list) and len(supporting) > 0:
            return True
    return False

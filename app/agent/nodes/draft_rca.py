"""节点 6: 起草 RCA - 基于证据和假设生成根因分析草稿。"""

import logging

from app.agent.state import RCAState
from app.prompts.templates import PromptManager

logger = logging.getLogger(__name__)

# Prompt 管理器（模块级单例）
_prompt_manager = PromptManager()


def draft_rca_node(state: RCAState) -> RCAState:
    """基于当前证据和假设起草 RCA 结论。

    选择概率最高的已确认假设作为根因，
    生成根因描述和证据链。
    """
    # ── Prompt Engineering: 渲染并记录 prompt ────────────────
    try:
        prompt = _prompt_manager.render(
            "draft_rca",
            anomaly_type=state.anomaly_type,
            description=state.description,
            hypotheses=str(state.hypotheses),
            tool_call_history=str(state.tool_call_history),
            confidence=str(state.confidence),
        )
        state.add_prompt_record("draft_rca", prompt)
        logger.debug(f"[draft_rca] Prompt 已渲染并记录")
    except Exception as e:
        logger.warning(f"[draft_rca] Prompt 渲染失败: {e}")

    # 按概率排序假设
    sorted_hypotheses = sorted(
        state.hypotheses,
        key=lambda h: h.get("probability", 0),
        reverse=True,
    )

    # 只接受已确认且有支持证据的假设作为根因。
    # 不能用最高先验概率兜底，否则证据不足时会强行给结论。
    top_hypothesis = None
    for h in sorted_hypotheses:
        supporting = h.get("supporting_evidence", [])
        if (
            h.get("status") == "confirmed"
            and h.get("probability", 0) > 0.5
            and isinstance(supporting, list)
            and len(supporting) > 0
        ):
            top_hypothesis = h
            break

    if top_hypothesis:
        root_cause = top_hypothesis.get("description", "无法确定根因")
        confidence = top_hypothesis.get("probability", 0.5)

        # 构建证据链
        evidence_chain = []
        for ev in top_hypothesis.get("supporting_evidence", []):
            evidence_chain.append(f"[支持] {ev.get('tool', '')}: {ev.get('summary', '')}")
        for ev in top_hypothesis.get("refuting_evidence", []):
            evidence_chain.append(f"[反驳] {ev.get('tool', '')}: {ev.get('summary', '')}")

        draft = f"""## RCA 草稿

### 根因
{root_cause}

### 置信度
{confidence:.0%}

### 证据链
{chr(10).join(f'- {e}' for e in evidence_chain) if evidence_chain else '- 暂无充分证据'}

### 备选假设
{chr(10).join(f'- [{h.get("status", "?")}] {h.get("description", "")} (概率: {h.get("probability", 0):.0%})' for h in sorted_hypotheses[1:4])}
"""
    else:
        root_cause = "无法确定根因"
        confidence = 0.0
        draft = "## RCA 草稿\n\n### 根因\n无法确定根因\n\n### 置信度\n0%\n\n### 证据链\n- 暂无充分证据\n\n### 说明\n当前证据不足以确认任何根因假设，建议补充业务数据后重新分析。"

    state.draft_rca = draft
    state.confidence = confidence

    logger.info(
        f"[draft_rca] task={state.task_id} "
        f"root_cause={root_cause[:50]} confidence={confidence:.2f}"
    )

    return state

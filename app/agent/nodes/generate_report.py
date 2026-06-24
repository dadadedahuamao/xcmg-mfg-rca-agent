"""节点 8: 生成报告 - 生成最终 RCA 报告并持久化。

优先调用 LLM 生成报告，LLM 不可用时回退到硬编码模板。
"""

import logging
from datetime import datetime

from app.agent.state import RCAState
from app.persistence.repositories import RCAReportRepository
from app.prompts.templates import PromptManager

logger = logging.getLogger(__name__)

# Prompt 管理器（模块级单例）
_prompt_manager = PromptManager()


def generate_report_node(state: RCAState) -> RCAState:
    """生成最终 RCA 报告。

    优先调用 LLM 生成报告，LLM 不可用时回退到硬编码模板。
    """
    # 确定根因
    sorted_hypotheses = sorted(
        state.hypotheses,
        key=lambda h: h.get("probability", 0),
        reverse=True,
    )
    top_h = _select_confirmed_root_cause(sorted_hypotheses)

    has_confirmed_root_cause = top_h is not None
    root_cause = top_h.get("description", "无法确定根因") if top_h else "无法确定根因"
    root_cause_category = _categorize(state.anomaly_type)

    # 证据摘要
    evidence_summary = []
    for record in state.tool_call_history:
        if record.get("success"):
            evidence_summary.append({
                "tool": record.get("tool_name"),
                "summary": _summarize(record.get("output", {})),
                "timestamp": record.get("timestamp"),
            })
    evidence = _build_display_evidence(state.tool_call_history)

    # ── Prompt Engineering: 渲染并记录 prompt ────────────────
    try:
        prompt = _prompt_manager.render(
            "generate_report",
            task_id=state.task_id,
            anomaly_type=state.anomaly_type,
            description=state.description,
            source_system=state.source_system,
            root_cause=root_cause,
            root_cause_category=root_cause_category,
            confidence=str(state.confidence),
            reflection_rounds=str(state.reflection_round),
            hypotheses=str(state.hypotheses),
            evidence_summary=str(evidence_summary),
            tool_call_history=str(state.tool_call_history),
            symptom_tags=str(state.metadata.get("symptom_tags", [])),
            severity=state.metadata.get("severity", "medium"),
        )
        state.add_prompt_record("generate_report", prompt)
        logger.debug("[generate_report] Prompt 已渲染并记录")
    except Exception as e:
        logger.warning("[generate_report] Prompt 渲染失败: %s", e)

    # ── 优先 LLM 生成报告 ────────────────────────────────────
    llm_report = _try_llm_report(state, root_cause, root_cause_category, evidence_summary)

    # 改进建议
    recommendations = _generate_recommendations(state.anomaly_type, root_cause)
    if not has_confirmed_root_cause:
        recommendations = [
            "当前证据不足以确认根因，避免按单一假设直接处置",
            "补充关键业务数据后重新分析，例如工单、设备维保、物料、质量和接口日志",
            "优先核对工具返回为空或正常的数据源是否真实覆盖了异常发生时间窗口",
        ]

    report = {
        "task_id": state.task_id,
        "anomaly_type": state.anomaly_type,
        "description": state.description,
        "root_cause": root_cause,
        "root_cause_category": root_cause_category,
        "hypotheses": state.hypotheses,
        "evidence": evidence,
        "evidence_summary": evidence_summary,
        "tool_call_history": state.tool_call_history,
        "confidence": state.confidence if has_confirmed_root_cause else 0.0,
        "reflection_rounds": state.reflection_round,
        "recommendations": recommendations,
        "generated_at": datetime.now().isoformat(),
        "metadata": {
            "source_system": state.source_system,
            "symptom_tags": state.metadata.get("symptom_tags", []),
            "severity": state.metadata.get("severity", "medium"),
            "conclusion_status": (
                "confirmed" if has_confirmed_root_cause else "insufficient_evidence"
            ),
            "reflection_action": (
                state.reflection_result or {}
            ).get("action"),
            "reflection_reasoning": (
                state.reflection_result or {}
            ).get("reasoning"),
        },
    }

    # 合并 LLM 报告内容
    if llm_report:
        report["llm_report"] = llm_report

    state.final_report = report

    # 持久化报告
    try:
        RCAReportRepository.save(state.task_id, report)
        logger.info("[generate_report] 报告已保存: task=%s", state.task_id)
    except Exception as e:
        logger.error("[generate_report] 报告保存失败: %s", e)

    return state


def _try_llm_report(
    state: RCAState,
    root_cause: str,
    root_cause_category: str,
    evidence_summary: list,
) -> str | None:
    """尝试通过 LLM 生成报告，失败返回 None。"""
    try:
        from app.llm.client import llm_client

        if not llm_client.enabled:
            logger.info("[generate_report] LLM 未配置，使用模板")
            return None

        template = _prompt_manager.load("generate_report")
        user_prompt = _prompt_manager.render_user_prompt(
            "generate_report",
            task_id=state.task_id,
            anomaly_type=state.anomaly_type,
            description=state.description,
            source_system=state.source_system,
            root_cause=root_cause,
            root_cause_category=root_cause_category,
            confidence=str(state.confidence),
            reflection_rounds=str(state.reflection_round),
            hypotheses=str(state.hypotheses),
            evidence_summary=str(evidence_summary),
            tool_call_history=str(state.tool_call_history),
            symptom_tags=str(state.metadata.get("symptom_tags", [])),
            severity=state.metadata.get("severity", "medium"),
        )

        result = llm_client.complete(template, user_prompt)
        if not result or not result.strip():
            logger.warning("[generate_report] LLM 返回空内容")
            return None

        logger.info("[generate_report] LLM 报告生成成功")
        return result.strip()

    except Exception as e:
        logger.warning("[generate_report] LLM 调用失败，使用模板: %s", e)
        return None


def _select_confirmed_root_cause(hypotheses: list[dict]) -> dict | None:
    """选择已确认且有支持证据的根因假设。"""
    for hypothesis in hypotheses:
        supporting = hypothesis.get("supporting_evidence", [])
        if (
            hypothesis.get("status") == "confirmed"
            and hypothesis.get("probability", 0) > 0.5
            and isinstance(supporting, list)
            and len(supporting) > 0
        ):
            return hypothesis
    return None


def _build_display_evidence(tool_call_history: list[dict]) -> list[dict]:
    """将工具调用结果转换为前端报告可直接展示的证据列表。"""
    evidence = []
    for index, record in enumerate(tool_call_history, start=1):
        if not record.get("success"):
            continue
        output = record.get("output", {})
        relevance_score = _estimate_relevance(output)
        confidence = _estimate_evidence_confidence(output)
        if relevance_score <= 0 or confidence <= 0:
            continue
        evidence.append({
            "id": f"E{index}",
            "source": record.get("tool_name") or "unknown",
            "tool_name": record.get("tool_name") or "unknown",
            "content": _summarize(output),
            "relevance_score": relevance_score,
            "confidence": confidence,
            "timestamp": record.get("timestamp"),
        })
    return evidence


def _estimate_relevance(output: dict) -> float:
    """基于工具返回规模估算展示相关度。"""
    if not isinstance(output, dict) or not output:
        return 0.0
    if output.get("error"):
        return 0.0
    if output.get("has_shortage") or output.get("is_abnormal"):
        return 0.8
    for key in ("anomaly_count", "failure_count", "timeout_count", "conflict_count", "overdue_count"):
        value = output.get(key, 0)
        if isinstance(value, (int, float)) and value > 0:
            return min(0.9, 0.5 + value * 0.05)
    if _count_output_items(output) > 0:
        return 0.5
    return 0.0


def _estimate_evidence_confidence(output: dict) -> float:
    """基于工具返回内容估算展示置信度。"""
    if not isinstance(output, dict) or not output or output.get("error"):
        return 0.0
    if _count_output_items(output) > 0:
        return 0.7
    if output.get("has_shortage") or output.get("is_abnormal"):
        return 0.7
    return 0.3


def _count_output_items(output: dict) -> int:
    """统计工具输出中的记录数量。"""
    if not isinstance(output, dict):
        return 0
    count = output.get("count")
    if isinstance(count, int):
        return count
    for key in ("data", "results", "shortages", "anomalies"):
        value = output.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _categorize(anomaly_type: str) -> str:
    """将异常类型映射到根因分类。"""
    mapping = {
        "overstation_check": "生产执行异常",
        "equipment_conflict": "资源调度异常",
        "material_shortage": "物料供应异常",
        "quality_abnormal": "质量控制异常",
        "interface_timeout": "系统集成异常",
        "schedule_risk": "计划排程异常",
    }
    return mapping.get(anomaly_type, "其他异常")


def _summarize(output: dict) -> str:
    """生成工具输出的简短摘要。"""
    if not output:
        return "无数据"
    if isinstance(output, dict):
        if "count" in output:
            return f"返回 {output['count']} 条记录"
        if "data" in output and isinstance(output["data"], list):
            return f"返回 {len(output['data'])} 条记录"
        if "results" in output and isinstance(output["results"], list):
            return f"返回 {len(output['results'])} 条结果"
        if "error" in output:
            return f"错误: {output['error']}"
    return "执行成功"


def _generate_recommendations(anomaly_type: str, root_cause: str) -> list[str]:
    """根据异常类型和根因生成改进建议。"""
    base_recommendations = {
        "overstation_check": [
            "检查并优化瓶颈工位的工艺参数",
            "加强设备预防性维护，减少非计划停机",
            "优化物料配送流程，确保准时供料",
            "建立超站预警机制，实时监控工序节拍",
        ],
        "equipment_conflict": [
            "优化设备排程算法，避免资源争用",
            "建立设备维保与生产计划的协调机制",
            "评估关键设备产能，合理分配生产任务",
            "建立紧急插单的资源冲突检测机制",
        ],
        "material_shortage": [
            "优化安全库存设置，提高需求预测精度",
            "建立供应商交付预警机制",
            "加强与生产计划的物料需求联动",
            "评估替代物料方案，降低单一来源风险",
        ],
        "quality_abnormal": [
            "加强设备参数监控和定期校准",
            "完善来料检验流程和标准",
            "强化操作人员 SOP 培训和执行检查",
            "建立质量异常的快速响应机制",
        ],
        "interface_timeout": [
            "优化接口超时配置和重试策略",
            "建立接口监控和告警机制",
            "评估目标系统性能和容量",
            "实施接口调用限流和降级方案",
        ],
        "schedule_risk": [
            "优化排程算法，提高计划可行性",
            "建立产能瓶颈的早期识别机制",
            "加强与物料供应的排程联动",
            "设置排程缓冲时间，应对不确定性",
        ],
    }

    return base_recommendations.get(anomaly_type, [
        "进一步收集数据以确定改进方向",
        "建立异常监控和预警机制",
    ])

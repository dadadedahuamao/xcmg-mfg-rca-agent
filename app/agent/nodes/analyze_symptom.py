"""节点 1: 分析症状 - 解析异常事件，提取关键症状特征。"""

import logging

from app.agent.state import RCAState
from app.llm.client import llm_client
from app.prompts.templates import PromptManager

logger = logging.getLogger(__name__)

# Prompt 管理器（模块级单例）
_prompt_manager = PromptManager()


def analyze_symptom_node(state: RCAState) -> RCAState:
    """分析异常事件症状。

    提取关键信息：
    - 异常类型映射
    - 影响范围评估
    - 紧急程度判断
    - 关键症状标签
    """
    anomaly_type = state.anomaly_type
    description = state.description

    # ── LLM: 渲染 prompt 并调用真实大模型 ────────────────────
    llm_analysis = None
    try:
        template = _prompt_manager.load("analyze_symptom")
        user_prompt = _prompt_manager.render_user_prompt(
            "analyze_symptom",
            anomaly_type=anomaly_type,
            description=description,
            source_system=state.source_system,
        )
        prompt = _prompt_manager.render(
            "analyze_symptom",
            anomaly_type=anomaly_type,
            description=description,
            source_system=state.source_system,
        )
        state.add_prompt_record("analyze_symptom", prompt)
        if llm_client.enabled:
            llm_analysis = llm_client.complete_json(template, user_prompt)
            logger.info("[analyze_symptom] 已使用 LLM 完成症状分析")
    except Exception as e:
        logger.warning(f"[analyze_symptom] LLM 症状分析失败，回退模板逻辑: {e}")

    symptom_analysis = _normalize_llm_analysis(llm_analysis, anomaly_type, description)
    if symptom_analysis is None:
        symptom_analysis = _analyze(anomaly_type, description)

    # 将分析结果存入 metadata
    state.metadata["symptom_analysis"] = symptom_analysis
    state.metadata["symptom_tags"] = symptom_analysis.get("tags", [])
    state.metadata["severity"] = symptom_analysis.get("severity", "medium")
    state.metadata["affected_scope"] = symptom_analysis.get("affected_scope", [])

    logger.info(
        f"[analyze_symptom] task={state.task_id} "
        f"type={anomaly_type} severity={symptom_analysis.get('severity')}"
    )

    return state


def _normalize_llm_analysis(data: object, anomaly_type: str, description: str) -> dict | None:
    if not isinstance(data, dict):
        return None
    raw_tags = data.get("tags")
    raw_affected_scope = data.get("affected_scope")
    raw_key_questions = data.get("key_questions")
    raw_severity = data.get("severity")
    tags = raw_tags if isinstance(raw_tags, list) else []
    affected_scope = raw_affected_scope if isinstance(raw_affected_scope, list) else []
    key_questions = raw_key_questions if isinstance(raw_key_questions, list) else []
    severity = raw_severity if isinstance(raw_severity, str) else "medium"
    return {
        "anomaly_type": str(data.get("anomaly_type") or anomaly_type),
        "description": str(data.get("description") or description),
        "tags": [str(item) for item in tags],
        "severity": severity,
        "affected_scope": [str(item) for item in affected_scope],
        "key_questions": [str(item) for item in key_questions],
    }


def _analyze(anomaly_type: str, description: str) -> dict:
    """基于异常类型和描述的症状分析（模板驱动）。"""
    type_configs = {
        "overstation_check": {
            "tags": ["超站", "工序异常", "生产节拍"],
            "severity": "high",
            "affected_scope": ["生产计划", "下游工序", "交付周期"],
            "key_questions": [
                "哪个工位发生了超站？",
                "超站时长是多少？",
                "是否影响后续工序？",
                "是否有设备故障或物料短缺？",
            ],
        },
        "equipment_conflict": {
            "tags": ["设备冲突", "资源争用", "排程异常"],
            "severity": "high",
            "affected_scope": ["设备利用率", "生产排程", "交付计划"],
            "key_questions": [
                "哪些设备存在冲突？",
                "冲突的时间段是什么？",
                "是否有多工单争用同一设备？",
                "设备维保计划是否冲突？",
            ],
        },
        "material_shortage": {
            "tags": ["物料短缺", "库存不足", "供应链"],
            "severity": "critical",
            "affected_scope": ["生产执行", "交付承诺", "采购计划"],
            "key_questions": [
                "哪种物料短缺？",
                "当前库存和需求量的差距？",
                "安全库存是否触发？",
                "是否有替代物料？",
            ],
        },
        "quality_abnormal": {
            "tags": ["质量异常", "不良率", "缺陷"],
            "severity": "high",
            "affected_scope": ["产品质量", "客户满意度", "返工成本"],
            "key_questions": [
                "什么类型的质量缺陷？",
                "不良率是多少？",
                "是否集中在某个工位/批次？",
                "是否有质量记录可追溯？",
            ],
        },
        "interface_timeout": {
            "tags": ["接口超时", "系统集成", "数据同步"],
            "severity": "medium",
            "affected_scope": ["数据一致性", "业务流程", "系统可用性"],
            "key_questions": [
                "哪个接口超时？",
                "超时频率和持续时间？",
                "是否影响下游系统？",
                "是否有接口日志？",
            ],
        },
        "schedule_risk": {
            "tags": ["排程风险", "交付延期", "产能瓶颈"],
            "severity": "medium",
            "affected_scope": ["交付计划", "客户承诺", "资源分配"],
            "key_questions": [
                "哪些工单存在排程风险？",
                "风险原因是什么？",
                "是否有缓冲时间？",
                "产能利用率如何？",
            ],
        },
    }

    config = type_configs.get(anomaly_type, {
        "tags": ["未知异常"],
        "severity": "medium",
        "affected_scope": ["待评估"],
        "key_questions": ["需要进一步分析"],
    })

    return {
        "anomaly_type": anomaly_type,
        "description": description,
        **config,
    }

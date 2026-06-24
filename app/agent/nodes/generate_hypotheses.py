"""节点 2: 生成假设 - 基于症状分析生成根因假设列表。

优先调用 LLM 生成假设，LLM 不可用时回退到硬编码模板。
"""

import json
import logging

from app.agent.state import RCAState
from app.prompts.templates import PromptManager

logger = logging.getLogger(__name__)

# Prompt 管理器（模块级单例）
_prompt_manager = PromptManager()


def generate_hypotheses_node(state: RCAState) -> RCAState:
    """基于症状分析生成根因假设。

    优先调用 LLM 生成假设列表，LLM 不可用或返回非法数据时回退到硬编码模板。
    """
    anomaly_type = state.anomaly_type
    symptom_tags = state.metadata.get("symptom_tags", [])

    # ── Prompt Engineering: 渲染并记录 prompt ────────────────
    try:
        prompt = _prompt_manager.render(
            "generate_hypotheses",
            anomaly_type=anomaly_type,
            symptom_tags=str(symptom_tags),
            severity=state.metadata.get("severity", "medium"),
            affected_scope=str(state.metadata.get("affected_scope", [])),
            key_questions=str(state.metadata.get("symptom_analysis", {}).get("key_questions", [])),
        )
        state.add_prompt_record("generate_hypotheses", prompt)
        logger.debug("[generate_hypotheses] Prompt 已渲染并记录")
    except Exception as e:
        logger.warning("[generate_hypotheses] Prompt 渲染失败: %s", e)

    # ── 优先 LLM ──────────────────────────────────────────────
    hypotheses = _try_llm_hypotheses(anomaly_type, symptom_tags, state)

    for h in hypotheses:
        state.add_hypothesis(h)

    logger.info(
        "[generate_hypotheses] task=%s generated %d hypotheses",
        state.task_id,
        len(hypotheses),
    )

    return state


def _try_llm_hypotheses(
    anomaly_type: str, tags: list[str], state: RCAState
) -> list[dict]:
    """尝试通过 LLM 生成假设，失败则回退到模板。"""
    try:
        from app.llm.client import llm_client

        if not llm_client.enabled:
            logger.info("[generate_hypotheses] LLM 未配置，使用模板")
            return _generate(anomaly_type, tags)

        template = _prompt_manager.load("generate_hypotheses")
        user_prompt = _prompt_manager.render_user_prompt(
            "generate_hypotheses",
            anomaly_type=anomaly_type,
            symptom_tags=str(tags),
            severity=state.metadata.get("severity", "medium"),
            affected_scope=str(state.metadata.get("affected_scope", [])),
            key_questions=str(state.metadata.get("symptom_analysis", {}).get("key_questions", [])),
        )

        result = llm_client.complete_json(template, user_prompt)
        hypotheses = result.get("hypotheses", [])

        if not isinstance(hypotheses, list) or len(hypotheses) == 0:
            logger.warning("[generate_hypotheses] LLM 返回空假设列表，回退模板")
            return _generate(anomaly_type, tags)

        # 标准化 LLM 返回的假设格式
        validated = []
        for i, h in enumerate(hypotheses):
            if not isinstance(h, dict):
                continue
            validated.append({
                "id": h.get("id", f"H{i + 1}"),
                "description": str(h.get("description", "未知假设")),
                "probability": float(h.get("probability", 0.5)),
                "supporting_evidence": h.get("supporting_evidence", []),
                "refuting_evidence": h.get("refuting_evidence", []),
                "status": h.get("status", "pending"),
                "required_tools": h.get("required_tools", ["knowledge"]),
            })

        if len(validated) == 0:
            logger.warning("[generate_hypotheses] LLM 返回数据无法解析，回退模板")
            return _generate(anomaly_type, tags)

        logger.info("[generate_hypotheses] LLM 生成 %d 个假设", len(validated))
        return validated

    except Exception as e:
        logger.warning("[generate_hypotheses] LLM 调用失败，回退模板: %s", e)
        return _generate(anomaly_type, tags)


def _generate(anomaly_type: str, tags: list[str]) -> list[dict]:
    """模板驱动的假设生成（LLM 回退方案）。"""
    templates = {
        "overstation_check": [
            {
                "id": "H1",
                "description": "设备故障导致工位停滞，无法按节拍完成工序",
                "probability": 0.35,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["equipment_maintenance", "workorder"],
            },
            {
                "id": "H2",
                "description": "上游物料未及时到位，导致当前工位等待",
                "probability": 0.30,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["material_inventory", "workorder"],
            },
            {
                "id": "H3",
                "description": "人员技能不足或人员缺勤导致操作效率下降",
                "probability": 0.15,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["resource", "workorder"],
            },
            {
                "id": "H4",
                "description": "工艺参数异常导致工序执行时间超出标准",
                "probability": 0.12,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["quality", "knowledge"],
            },
            {
                "id": "H5",
                "description": "排程不合理，工位任务堆积导致超站",
                "probability": 0.08,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["workorder", "resource"],
            },
        ],
        "equipment_conflict": [
            {
                "id": "H1",
                "description": "多工单在同一时段争用同一设备资源",
                "probability": 0.40,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["workorder", "resource"],
            },
            {
                "id": "H2",
                "description": "设备维保计划与生产计划冲突",
                "probability": 0.25,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["equipment_maintenance", "workorder"],
            },
            {
                "id": "H3",
                "description": "设备产能评估不准确，实际产能低于计划",
                "probability": 0.20,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["equipment_maintenance", "quality"],
            },
            {
                "id": "H4",
                "description": "紧急插单导致原有排程被打乱",
                "probability": 0.15,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["workorder", "resource"],
            },
        ],
        "material_shortage": [
            {
                "id": "H1",
                "description": "供应商交付延迟导致物料库存不足",
                "probability": 0.35,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["material_inventory", "interface_log"],
            },
            {
                "id": "H2",
                "description": "需求预测偏差导致安全库存设置过低",
                "probability": 0.25,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["material_inventory", "knowledge"],
            },
            {
                "id": "H3",
                "description": "生产计划变更导致物料需求突增",
                "probability": 0.20,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["workorder", "material_inventory"],
            },
            {
                "id": "H4",
                "description": "仓库管理问题导致物料未及时上架或盘点不准",
                "probability": 0.12,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["material_inventory", "quality"],
            },
            {
                "id": "H5",
                "description": "物料质量问题导致批次退回或报废",
                "probability": 0.08,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["quality", "material_inventory"],
            },
        ],
        "quality_abnormal": [
            {
                "id": "H1",
                "description": "设备参数漂移导致加工精度下降",
                "probability": 0.30,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["equipment_maintenance", "quality"],
            },
            {
                "id": "H2",
                "description": "来料批次质量问题",
                "probability": 0.25,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["material_inventory", "quality"],
            },
            {
                "id": "H3",
                "description": "操作人员未按 SOP 执行",
                "probability": 0.20,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["knowledge", "quality"],
            },
            {
                "id": "H4",
                "description": "环境因素（温湿度、洁净度）影响产品质量",
                "probability": 0.15,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["quality", "knowledge"],
            },
            {
                "id": "H5",
                "description": "检测设备本身存在误差",
                "probability": 0.10,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["quality", "equipment_maintenance"],
            },
        ],
        "interface_timeout": [
            {
                "id": "H1",
                "description": "目标系统响应慢或不可用",
                "probability": 0.35,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["interface_log", "resource"],
            },
            {
                "id": "H2",
                "description": "网络延迟或丢包导致超时",
                "probability": 0.25,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["interface_log"],
            },
            {
                "id": "H3",
                "description": "数据量过大导致接口处理超时",
                "probability": 0.20,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["interface_log", "text2sql"],
            },
            {
                "id": "H4",
                "description": "接口配置参数不合理（超时设置过短）",
                "probability": 0.12,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["knowledge", "interface_log"],
            },
            {
                "id": "H5",
                "description": "并发请求过多导致资源耗尽",
                "probability": 0.08,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["resource", "interface_log"],
            },
        ],
        "schedule_risk": [
            {
                "id": "H1",
                "description": "产能瓶颈工位导致整体排程延迟",
                "probability": 0.35,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["workorder", "resource"],
            },
            {
                "id": "H2",
                "description": "关键设备可用性不足",
                "probability": 0.25,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["equipment_maintenance", "workorder"],
            },
            {
                "id": "H3",
                "description": "物料供应不稳定导致排程无法执行",
                "probability": 0.20,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["material_inventory", "workorder"],
            },
            {
                "id": "H4",
                "description": "紧急订单插入打乱原有排程",
                "probability": 0.12,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["workorder"],
            },
            {
                "id": "H5",
                "description": "排程算法参数不合理",
                "probability": 0.08,
                "supporting_evidence": [],
                "refuting_evidence": [],
                "status": "pending",
                "required_tools": ["knowledge", "resource"],
            },
        ],
    }

    return templates.get(anomaly_type, [
        {
            "id": "H1",
            "description": f"与 {anomaly_type} 相关的根因待分析",
            "probability": 0.5,
            "supporting_evidence": [],
            "refuting_evidence": [],
            "status": "pending",
            "required_tools": ["knowledge"],
        },
    ])

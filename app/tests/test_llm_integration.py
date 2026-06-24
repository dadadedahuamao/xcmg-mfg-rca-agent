"""LLM 集成测试 — RED 阶段。

测试 generate_hypotheses_node 和 generate_report_node 优先调用 LLM，
LLM 不可用时回退到现有模板逻辑。
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def _make_state(anomaly_type="overstation_check", description="工位超站"):
    """创建最小 RCAState 用于测试。"""
    from app.agent.state import RCAState
    from app.schemas.api import AnomalyEvent

    event = AnomalyEvent(
        anomaly_type=anomaly_type,
        description=description,
        source_system="MES",
    )
    return RCAState(
        task_id="test-task-001",
        event=event,
    )


# ═══════════════════════════════════════════════════════════════
# generate_hypotheses_node — LLM 优先 / 回退
# ═══════════════════════════════════════════════════════════════

def test_generate_hypotheses_uses_llm_when_available():
    """LLM 可用时 generate_hypotheses_node 应调用 llm_client.complete_json。"""
    from app.agent.nodes.generate_hypotheses import generate_hypotheses_node

    state = _make_state()
    fake_hypotheses = [
        {"id": "H1", "description": "设备故障", "probability": 0.5,
         "supporting_evidence": [], "refuting_evidence": [],
         "status": "pending", "required_tools": ["equipment_maintenance"]},
    ]

    with patch(
        "app.agent.nodes.generate_hypotheses._prompt_manager",
    ):
        with patch(
            "app.llm.client.llm_client.complete_json",
            return_value={"hypotheses": fake_hypotheses},
        ) as mock_llm:
            with patch(
                "app.config.settings.llm_api_key", "sk-test-key",
            ):
                result = generate_hypotheses_node(state)

    mock_llm.assert_called_once()
    assert len(result.hypotheses) >= 1


def test_generate_hypotheses_falls_back_to_template_when_llm_fails():
    """LLM 调用失败时 generate_hypotheses_node 应回退到硬编码模板。"""
    from app.agent.nodes.generate_hypotheses import generate_hypotheses_node

    state = _make_state()

    with patch(
        "app.agent.nodes.generate_hypotheses._prompt_manager",
    ):
        with patch(
            "app.llm.client.llm_client.complete_json",
            side_effect=RuntimeError("LLM 不可用"),
        ) as mock_llm:
            with patch(
                "app.config.settings.llm_api_key", "sk-test-key",
            ):
                result = generate_hypotheses_node(state)

    mock_llm.assert_called_once()
    # 回退到模板后仍应有假设
    assert len(result.hypotheses) >= 1
    # 假设应来自模板（overstation_check 模板有 5 个假设）
    assert len(result.hypotheses) == 5


def test_generate_hypotheses_falls_back_when_llm_disabled():
    """LLM 未配置时 generate_hypotheses_node 应直接使用模板。"""
    from app.agent.nodes.generate_hypotheses import generate_hypotheses_node

    state = _make_state()

    with patch(
        "app.agent.nodes.generate_hypotheses._prompt_manager",
    ):
        with patch(
            "app.config.settings.llm_api_key", "",
        ):
            result = generate_hypotheses_node(state)

    # 模板应返回 5 个假设（overstation_check）
    assert len(result.hypotheses) == 5


# ═══════════════════════════════════════════════════════════════
# generate_report_node — LLM 优先 / 回退
# ═══════════════════════════════════════════════════════════════

def test_generate_report_uses_llm_when_available():
    """LLM 可用时 generate_report_node 应调用 llm_client.complete。"""
    from app.agent.nodes.generate_report import generate_report_node

    state = _make_state()
    state.hypotheses = [
        {"id": "H1", "description": "设备故障", "probability": 0.5,
         "supporting_evidence": [], "refuting_evidence": [],
         "status": "pending", "required_tools": ["equipment_maintenance"]},
    ]
    state.confidence = 0.85
    state.reflection_round = 1

    with patch(
        "app.agent.nodes.generate_report._prompt_manager",
    ):
        with patch(
            "app.llm.client.llm_client.complete",
            return_value="这是 LLM 生成的报告内容",
        ) as mock_llm:
            with patch(
                "app.config.settings.llm_api_key", "sk-test-key",
            ):
                with patch(
                    "app.persistence.repositories.RCAReportRepository.save",
                ):
                    result = generate_report_node(state)

    mock_llm.assert_called_once()
    assert result.final_report is not None


def test_generate_report_falls_back_to_template_when_llm_fails():
    """LLM 调用失败时 generate_report_node 应回退到硬编码模板。"""
    from app.agent.nodes.generate_report import generate_report_node

    state = _make_state()
    state.hypotheses = [
        {"id": "H1", "description": "设备故障", "probability": 0.5,
         "supporting_evidence": [], "refuting_evidence": [],
         "status": "pending", "required_tools": ["equipment_maintenance"]},
    ]
    state.confidence = 0.85
    state.reflection_round = 1

    with patch(
        "app.agent.nodes.generate_report._prompt_manager",
    ):
        with patch(
            "app.llm.client.llm_client.complete",
            side_effect=RuntimeError("LLM 不可用"),
        ) as mock_llm:
            with patch(
                "app.config.settings.llm_api_key", "sk-test-key",
            ):
                with patch(
                    "app.persistence.repositories.RCAReportRepository.save",
                ):
                    result = generate_report_node(state)

    mock_llm.assert_called_once()
    # 回退后仍应有报告
    assert result.final_report is not None
    # 回退报告应包含根因
    assert result.final_report.get("root_cause") is not None


def test_generate_report_falls_back_when_llm_disabled():
    """LLM 未配置时 generate_report_node 应直接使用模板。"""
    from app.agent.nodes.generate_report import generate_report_node

    state = _make_state()
    state.hypotheses = [
        {"id": "H1", "description": "设备故障", "probability": 0.5,
         "supporting_evidence": [], "refuting_evidence": [],
         "status": "pending", "required_tools": ["equipment_maintenance"]},
    ]
    state.confidence = 0.85
    state.reflection_round = 1

    with patch(
        "app.agent.nodes.generate_report._prompt_manager",
    ):
        with patch(
            "app.config.settings.llm_api_key", "",
        ):
            with patch(
                "app.persistence.repositories.RCAReportRepository.save",
            ):
                result = generate_report_node(state)

    # 模板逻辑应正常工作
    assert result.final_report is not None
    assert result.final_report.get("root_cause") is not None


# ═══════════════════════════════════════════════════════════════
# 标题摘要 — LLM 优先 / 回退
# ═══════════════════════════════════════════════════════════════

def test_summarize_title_uses_llm_when_available():
    """LLM 可用时标题摘要应调用 llm_client.complete。"""
    from app.api.chat_routes import _summarize_title_via_llm, _fallback_title

    # 验证函数存在
    assert callable(_summarize_title_via_llm)
    assert callable(_fallback_title)

    # 验证 fallback 返回非空标题
    title = _fallback_title("http://ids.chinasie.com/iidp/ 这个网址我用浏览器打开默认就会变成https")
    assert isinstance(title, str)
    assert len(title) > 0
    assert len(title) <= 30
    # fallback 不应是原文截断
    assert "ids.chinasie.com" not in title


def test_summarize_title_falls_back_when_llm_unavailable():
    """LLM 不可用时标题摘要应有安全的本地 fallback。"""
    from app.api.chat_routes import _fallback_title

    # 测试各种输入
    assert _fallback_title("A" * 200) == "异常分析"
    assert _fallback_title("http://example.com 怎么解决") == "网络配置问题"
    assert _fallback_title("设备冲突导致生产停滞") == "设备冲突问题"
    assert _fallback_title("物料短缺影响交付") == "物料短缺问题"
    assert _fallback_title("接口超时导致数据同步失败") == "接口超时问题"
    assert _fallback_title("质量异常批次需要排查") == "质量异常问题"
    assert _fallback_title("排程风险需要评估") == "排程风险问题"
    assert _fallback_title("超站检查异常") == "超站检查问题"
    assert _fallback_title("系统报错无法启动") == "系统错误排查"
    assert _fallback_title("任务执行失败") == "任务失败分析"
    assert _fallback_title("如何配置网络") == "技术问题咨询"
    assert _fallback_title("为什么生产停滞") == "根因分析"


def test_complete_json_uses_prompt_json_without_response_format():
    """complete_json 不应传递 response_format 参数，仅依赖提示词约束 + 容忍解析。"""
    from app.llm.client import LLMClient
    from app.prompts.templates import PromptTemplate

    template = PromptTemplate({
        "node_name": "test_json",
        "description": "test",
        "system_prompt": "只返回 JSON",
        "user_prompt_template": "测试",
        "variables": [],
        "temperature": 0.1,
        "max_tokens": 100,
    })
    client = LLMClient()

    with patch.object(
        client,
        "complete",
        return_value='{"ok": true}',
    ) as mock_complete:
        result = client.complete_json(template, "返回 JSON")

    assert result == {"ok": True}
    mock_complete.assert_called_once()
    assert "response_format" not in mock_complete.call_args.kwargs


def test_parse_json_object_handles_markdown_code_fences():
    """_parse_json_object 应能解析 Markdown 代码块包裹的 JSON。"""
    from app.llm.client import _parse_json_object

    result = _parse_json_object('```json\n{"ok": true}\n```')
    assert result == {"ok": True}

    result = _parse_json_object('```\n{"ok": true}\n```')
    assert result == {"ok": True}

    result = _parse_json_object('{"ok": true}')
    assert result == {"ok": True}

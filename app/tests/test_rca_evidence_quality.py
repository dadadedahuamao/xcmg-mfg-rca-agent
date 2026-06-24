"""RCA 证据质量与不确定结论测试。"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _make_state():
    from app.agent.state import RCAState
    from app.schemas.api import AnomalyEvent

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="样例问题，缺少可验证业务数据",
        source_system="MES",
    )
    return RCAState(task_id="evidence-test", event=event)


def test_reflect_escalates_when_max_rounds_reached_without_confirmed_evidence():
    """达到最大轮次但仍无确认假设时，不应强制 PROCEED。"""
    from app.agent.nodes.reflect import reflect_node

    state = _make_state()
    state.reflection_round = 2
    state.confidence = 0.35
    state.hypotheses = [
        {
            "id": "H1",
            "description": "设备故障导致停滞",
            "probability": 0.55,
            "status": "pending",
            "required_tools": ["equipment_maintenance"],
            "supporting_evidence": [],
            "refuting_evidence": [],
        }
    ]
    state.tool_call_history = [
        {
            "tool_name": "equipment_maintenance",
            "success": True,
            "output": {"data": [], "count": 0},
        }
    ]

    with patch("app.agent.nodes.reflect._prompt_manager"):
        result = reflect_node(state)

    assert result.reflection_result is not None
    assert result.reflection_result["action"] == "ESCALATE"
    assert "证据" in result.reflection_result["reasoning"]


def test_draft_rca_does_not_select_top_prior_without_confirmed_evidence():
    """无确认假设和支持证据时，不应把最高先验概率假设写成根因。"""
    from app.agent.nodes.draft_rca import draft_rca_node

    state = _make_state()
    state.hypotheses = [
        {
            "id": "H1",
            "description": "设备故障导致工位停滞",
            "probability": 0.65,
            "status": "pending",
            "supporting_evidence": [],
            "refuting_evidence": [],
        }
    ]

    with patch("app.agent.nodes.draft_rca._prompt_manager"):
        result = draft_rca_node(state)

    assert result.confidence == 0.0
    assert result.draft_rca is not None
    assert "无法确定根因" in result.draft_rca
    assert "设备故障导致工位停滞" not in result.draft_rca.split("### 根因", 1)[-1]


def test_generate_report_marks_root_cause_unknown_when_no_confirmed_evidence():
    """最终报告在无确认假设时必须明确证据不足，而不是强行给根因。"""
    from app.agent.nodes.generate_report import generate_report_node

    state = _make_state()
    state.confidence = 0.0
    state.reflection_round = 3
    state.reflection_result = {
        "action": "ESCALATE",
        "reasoning": "达到最大轮次后仍无确认假设，证据不足",
    }
    state.hypotheses = [
        {
            "id": "H1",
            "description": "设备故障导致工位停滞",
            "probability": 0.65,
            "status": "pending",
            "supporting_evidence": [],
            "refuting_evidence": [],
        }
    ]
    state.tool_call_history = []

    with patch("app.agent.nodes.generate_report._prompt_manager"), patch(
        "app.persistence.repositories.RCAReportRepository.save"
    ):
        result = generate_report_node(state)

    assert result.final_report is not None
    assert result.final_report["root_cause"] == "无法确定根因"
    assert result.final_report["confidence"] == 0.0
    assert result.final_report["metadata"]["conclusion_status"] == "insufficient_evidence"


def test_generate_report_exposes_tool_results_as_displayable_evidence():
    """最终报告应把工具调用结果转换为前端可展示的 evidence 列表。"""
    from app.agent.nodes.generate_report import generate_report_node

    state = _make_state()
    state.confidence = 0.75
    state.hypotheses = [
        {
            "id": "H1",
            "description": "物料短缺导致等待加工",
            "probability": 0.75,
            "status": "confirmed",
            "supporting_evidence": [
                {"tool": "material", "score": 0.7, "summary": "发现 2 种物料短缺"}
            ],
            "refuting_evidence": [],
        }
    ]
    state.tool_call_history = [
        {
            "tool_name": "material",
            "success": True,
            "output": {"has_shortage": True, "shortage_count": 2, "count": 2},
            "timestamp": "2026-06-23T10:00:00",
        }
    ]

    with patch("app.agent.nodes.generate_report._prompt_manager"), patch(
        "app.persistence.repositories.RCAReportRepository.save"
    ):
        result = generate_report_node(state)

    assert result.final_report is not None
    evidence = result.final_report.get("evidence")
    assert isinstance(evidence, list)
    assert evidence
    assert evidence[0]["id"] == "E1"
    assert evidence[0]["source"] == "material"
    assert evidence[0]["tool_name"] == "material"
    assert evidence[0]["content"] == "返回 2 条记录"
    assert evidence[0]["confidence"] > 0


def test_generate_report_omits_empty_tool_results_from_display_evidence():
    """无有效业务数据的工具调用不应生成空白证据卡片。"""
    from app.agent.nodes.generate_report import generate_report_node

    state = _make_state()
    state.confidence = 0.0
    state.hypotheses = []
    state.tool_call_history = [
        {
            "tool_name": "workorder",
            "success": True,
            "output": {"count": 0, "data": [], "anomaly_count": 0},
            "timestamp": "2026-06-23T10:00:00",
        },
        {
            "tool_name": "material",
            "success": True,
            "output": {"count": 0, "data": [], "has_shortage": False},
            "timestamp": "2026-06-23T10:00:01",
        },
    ]

    with patch("app.agent.nodes.generate_report._prompt_manager"), patch(
        "app.persistence.repositories.RCAReportRepository.save"
    ):
        result = generate_report_node(state)

    assert result.final_report is not None
    assert result.final_report["evidence"] == []


def test_report_api_returns_normalized_evidence_from_final_report():
    """报告接口应优先返回 final_report.evidence，而不是 evidence_summary 摘要。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    task = {
        "task_id": "rca-evidence-api",
        "status": "completed",
        "anomaly_type": "overstation_check",
        "description": "证据接口测试",
        "confidence": 0.8,
        "reflection_rounds": 1,
        "created_at": None,
        "completed_at": None,
    }
    final_report = {
        "root_cause": "物料短缺",
        "hypotheses": [],
        "evidence": [
            {
                "id": "E1",
                "source": "material",
                "tool_name": "material",
                "content": "返回 2 条记录",
                "relevance_score": 0.8,
                "confidence": 0.7,
            }
        ],
    }
    report = {
        "root_cause": "物料短缺",
        "hypotheses": "[]",
        "evidence_summary": "[{\"tool\": \"material\", \"summary\": \"返回 2 条记录\"}]",
        "final_report": __import__("json").dumps(final_report, ensure_ascii=False),
    }

    with patch("app.api.routes.RCATaskRepository.get", return_value=task), patch(
        "app.api.routes.RCAReportRepository.get", return_value=report
    ):
        response = client.get("/api/v1/rca/reports/rca-evidence-api")

    assert response.status_code == 200
    data = response.json()
    assert data["evidence"] == final_report["evidence"]

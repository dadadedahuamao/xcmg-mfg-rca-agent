"""单元测试 - 冒烟级别。"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def test_imports():
    """验证所有核心模块可导入。"""
    from app.config import settings
    from app.schemas.api import AnomalyEvent
    from app.schemas.evidence import Evidence
    from app.schemas.report import RCAReport
    from app.agent.state import RCAState
    from app.agent.workflow import RCAWorkflow
    from app.tools.registry import ToolRegistry
    from app.text2sql.generator import SQLGenerator
    from app.text2sql.validator import SQLValidator
    from app.rag.hybrid_retriever import HybridRetriever
    from app.skills.loader import SkillsLoader
    from app.persistence.postgres import init_db
    from app.main import app

    assert settings is not None
    assert app is not None


def test_postgres_schema_identifier_helpers():
    """测试 PostgreSQL schema/table 标识符拼接。"""
    import importlib

    sql_identifiers = importlib.import_module("app.persistence.sql_identifiers")
    quote_identifier = sql_identifiers.quote_identifier
    schema_qualified_name = sql_identifiers.schema_qualified_name

    assert quote_identifier("rca") == '"rca"'
    assert schema_qualified_name("rca", "rca_tasks") == '"rca"."rca_tasks"'
    assert (
        schema_qualified_name("rca", "custom_schema.knowledge_embeddings")
        == '"custom_schema"."knowledge_embeddings"'
    )

    try:
        quote_identifier("rca;drop schema public")
    except ValueError:
        pass
    else:
        raise AssertionError("非法 PostgreSQL 标识符必须被拒绝")


def test_database_initialization_uses_sql_scripts_only():
    """测试数据库初始化必须由 db 目录下的 SQL 脚本提供。"""
    import inspect

    import app.persistence.postgres as postgres
    from app.rag.vector_store import PGVectorStore

    project_root = Path(__file__).resolve().parent.parent.parent
    business_script = project_root / "db" / "002_init_business_schema.sql"
    vector_script = project_root / "db" / "004_init_vector_schema.sql"

    assert business_script.exists()
    assert vector_script.exists()

    connect_source = inspect.getsource(postgres._connect)
    init_db_source = inspect.getsource(postgres.init_db)
    vector_store_source = inspect.getsource(PGVectorStore)

    assert "CREATE SCHEMA" not in connect_source
    assert "CREATE TABLE" not in init_db_source
    assert "CREATE SCHEMA" not in vector_store_source
    assert "CREATE TABLE" not in vector_store_source


def test_anomaly_event():
    """测试异常事件模型。"""
    from app.schemas.api import AnomalyEvent

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="测试超站事件",
        source_system="MES",
    )
    assert event.anomaly_type == "overstation_check"
    assert event.source_system == "MES"


def test_rca_state():
    """测试 RCA 状态模型。"""
    from app.schemas.api import AnomalyEvent
    from app.agent.state import RCAState

    event = AnomalyEvent(
        anomaly_type="material_shortage",
        description="物料短缺测试",
    )
    state = RCAState(task_id="test-001", event=event)

    assert state.task_id == "test-001"
    assert state.anomaly_type == "material_shortage"

    state.add_hypothesis({"id": "H1", "description": "测试假设", "probability": 0.5})
    assert len(state.hypotheses) == 1

    state.set_reflection({"action": "PROCEED", "reasoning": "测试"})
    assert state.reflection_round == 1
    assert not state.needs_more_evidence()


def test_sql_validator():
    """测试 SQL 验证器。"""
    from app.text2sql.validator import SQLValidator

    validator = SQLValidator()

    # 合法 SQL
    valid, err = validator.validate(
        "SELECT * FROM work_orders WHERE status = 'delayed' LIMIT 10"
    )
    assert valid, f"Expected valid: {err}"

    # 非法 SQL - 无 LIMIT
    valid, err = validator.validate("SELECT * FROM work_orders")
    assert not valid

    # 非法 SQL - DROP
    valid, err = validator.validate("DROP TABLE work_orders")
    assert not valid

    # 非法 SQL - 不在白名单
    valid, err = validator.validate("SELECT * FROM users LIMIT 10")
    assert not valid


def test_sql_generator():
    """测试 SQL 生成器。"""
    from app.text2sql.generator import SQLGenerator

    gen = SQLGenerator()

    sql = gen.generate("查询延迟工单", "overstation_check")
    assert "SELECT" in sql
    assert "LIMIT" in sql
    assert "work_orders" in sql.lower()

    sql = gen.generate("物料短缺", "material_shortage")
    assert "material_inventory" in sql.lower()


def test_tool_registry():
    """测试工具注册中心。"""
    from app.tools.registry import ToolRegistry

    registry = ToolRegistry()
    tools = registry.list_tools()

    tool_names = {t["name"] for t in tools}
    expected = {"workorder", "resource", "material", "interface_log",
                "quality", "equipment_maintenance", "knowledge", "text2sql"}
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


def test_skills_loader():
    """测试技能加载器。"""
    from app.skills.loader import SkillsLoader

    loader = SkillsLoader()
    skills = loader.list_skills()

    assert len(skills) >= 6, f"Expected >= 6 skills, got {len(skills)}"

    skill = loader.get_skill("overstation_check")
    assert skill is not None
    assert skill["anomaly_type"] == "overstation_check"
    assert len(skill.get("tools", [])) > 0


def test_hybrid_retriever():
    """测试混合检索器。"""
    from app.rag.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever()
    results = retriever.search("超站处理", "overstation_check", top_k=3)

    assert isinstance(results, list)


def test_workflow_basic():
    """测试基本工作流执行 — 使用 mock 图避免真实 DB 持久化。"""
    from unittest.mock import Mock, patch

    from app.agent.workflow import RCAWorkflow
    from app.agent.state import rca_state_to_graph_state
    from app.schemas.api import AnomalyEvent, TaskStatus

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="工位 WS-03 超站测试",
    )

    workflow = RCAWorkflow()
    task_id = f"pytest-wf-{uuid.uuid4().hex[:8]}"

    with patch.object(workflow, "_build_graph") as mock_build, \
         patch("app.agent.workflow.StepEventRepository.append_event"), \
         patch.object(workflow.checkpointer, "save"):

        mock_compiled = Mock()

        nodes = [
            "analyze_symptom", "generate_hypotheses", "select_tool",
            "execute_tool", "observe_evidence", "draft_rca",
            "reflect", "generate_report",
        ]
        mock_compiled.stream.return_value = iter([
            {node_name: {}} for node_name in nodes
        ])

        # 构造一个完成的 RCAState 作为 get_state 返回值
        from app.agent.state import RCAState as _RCAState
        final_state = _RCAState(
            task_id=task_id,
            event=event,
            status=TaskStatus.COMPLETED,
            hypotheses=[
                {"id": "H1", "description": "设备故障", "probability": 0.85, "status": "confirmed"},
            ],
            final_report={"root_cause": "设备故障", "confidence": 0.85},
            confidence=0.85,
            reflection_round=1,
        )
        graph_state = rca_state_to_graph_state(final_state)
        mock_snapshot = Mock()
        mock_snapshot.values = graph_state
        mock_compiled.get_state.return_value = mock_snapshot

        mock_build.return_value = mock_compiled

        state = workflow.run(event=event, task_id=task_id, skip_persistence=True)

    assert state.task_id == task_id
    assert state.status.value == "completed"
    assert len(state.hypotheses) > 0
    assert state.final_report is not None


# ═══════════════════════════════════════════════════════════════
# 官方 LangGraph 冒烟测试
# ═══════════════════════════════════════════════════════════════

def test_langgraph_state_graph_basic():
    """测试官方 LangGraph StateGraph 基本功能：添加节点、边、编译、执行。"""
    import operator
    from typing import Annotated, TypedDict

    from langgraph.graph import END, START, StateGraph

    class SimpleState(TypedDict):
        path: Annotated[list[str], operator.add]
        count: Annotated[int, operator.add]

    def node_a(state: SimpleState) -> SimpleState:
        return {"path": ["a"], "count": 1}

    def node_b(state: SimpleState) -> SimpleState:
        return {"path": ["b"], "count": 1}

    graph = StateGraph(SimpleState)
    graph.add_node("a", node_a)
    graph.add_node("b", node_b)
    graph.add_edge(START, "a")
    graph.add_edge("a", "b")
    graph.add_edge("b", END)

    compiled = graph.compile()
    result = compiled.invoke({"path": [], "count": 0})

    assert result["path"] == ["a", "b"]
    assert result["count"] == 2


def test_langgraph_conditional_edges():
    """测试官方 LangGraph 条件边：根据状态动态路由。"""
    import operator
    from typing import Annotated, Any, TypedDict

    from langgraph.graph import END, START, StateGraph

    class RouteState(TypedDict):
        path: Annotated[list[str], operator.add]
        flag: str

    def node_start(state: RouteState) -> dict[str, Any]:
        return {"path": ["start"]}

    def node_a(state: RouteState) -> dict[str, Any]:
        return {"path": ["a"]}

    def node_b(state: RouteState) -> dict[str, Any]:
        return {"path": ["b"]}

    def node_end(state: RouteState) -> dict[str, Any]:
        return {"path": ["end"]}

    def decide(state: RouteState) -> str:
        return "go_a" if state.get("flag") == "a" else "go_b"

    graph = StateGraph(RouteState)
    graph.add_node("start", node_start)
    graph.add_node("a", node_a)
    graph.add_node("b", node_b)
    graph.add_node("end", node_end)

    graph.add_edge(START, "start")
    graph.add_conditional_edges(
        "start", decide, {"go_a": "a", "go_b": "b"}
    )
    graph.add_edge("a", "end")
    graph.add_edge("b", "end")
    graph.add_edge("end", END)

    compiled = graph.compile()

    # 测试路由到 a
    result_a = compiled.invoke({"path": [], "flag": "a"})
    assert "a" in result_a["path"]
    assert "b" not in result_a["path"]
    assert result_a["path"][-1] == "end"

    # 测试路由到 b
    result_b = compiled.invoke({"path": [], "flag": "b"})
    assert "b" in result_b["path"]
    assert "a" not in result_b["path"]
    assert result_b["path"][-1] == "end"


def test_langgraph_loop_with_checkpointer():
    """测试官方 LangGraph 循环回退 + InMemorySaver 检查点。"""
    import operator
    from typing import Annotated, Any, TypedDict

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langchain_core.runnables.config import RunnableConfig

    class LoopState(TypedDict):
        path: Annotated[list[str], operator.add]
        count: int

    def node_work(state: LoopState) -> dict[str, Any]:
        new_count = state["count"] + 1
        return {"path": [f"work_{new_count}"], "count": new_count}

    def node_check(state: LoopState) -> dict[str, Any]:
        return {"path": [f"check_{state['count']}"]}

    def should_loop(state: LoopState) -> str:
        return "LOOP" if state["count"] < 3 else "DONE"

    graph = StateGraph(LoopState)
    graph.add_node("work", node_work)
    graph.add_node("check", node_check)

    graph.add_edge(START, "work")
    graph.add_edge("work", "check")
    graph.add_conditional_edges(
        "check", should_loop, {"LOOP": "work", "DONE": END}
    )

    checkpointer = InMemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    config: RunnableConfig = {"configurable": {"thread_id": "test-loop-1"}}
    result = compiled.invoke({"path": [], "count": 0}, config)

    assert result["count"] == 3
    assert result["path"] == [
        "work_1", "check_1",
        "work_2", "check_2",
        "work_3", "check_3",
    ]

    # 验证检查点可读取
    snapshot = compiled.get_state(config)
    assert snapshot.values["count"] == 3


# ═══════════════════════════════════════════════════════════════
# 5 维度反思测试
# ═══════════════════════════════════════════════════════════════

def test_reflect_five_dimensions():
    """测试反思节点输出5维度评估结果。"""
    from app.schemas.api import AnomalyEvent
    from app.agent.state import RCAState
    from app.agent.nodes.reflect import reflect_node

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="测试超站",
    )
    state = RCAState(task_id="test-reflect-5d", event=event)

    # 模拟一些假设和证据
    state.hypotheses = [
        {
            "id": "H1", "description": "设备故障",
            "probability": 0.75, "status": "confirmed",
            "supporting_evidence": [{"tool": "equipment_maintenance", "score": 0.6}],
            "refuting_evidence": [],
            "required_tools": ["equipment_maintenance", "workorder"],
        },
        {
            "id": "H2", "description": "物料短缺",
            "probability": 0.15, "status": "rejected",
            "supporting_evidence": [],
            "refuting_evidence": [{"tool": "material", "score": 0.4}],
            "required_tools": ["material", "workorder"],
        },
        {
            "id": "H3", "description": "人员问题",
            "probability": 0.30, "status": "pending",
            "supporting_evidence": [],
            "refuting_evidence": [],
            "required_tools": ["resource"],
        },
    ]
    state.tool_call_history = [
        {"tool_name": "equipment_maintenance", "success": True},
        {"tool_name": "workorder", "success": True},
        {"tool_name": "material", "success": True},
    ]
    state.confidence = 0.75
    state.reflection_round = 0

    state = reflect_node(state)

    result = state.reflection_result
    assert result is not None

    # 验证顶层结构
    assert "action" in result
    assert "reasoning" in result
    assert "dimensions" in result
    assert "overall_score" in result
    assert "missing_evidence" in result

    # 验证 5 个维度都存在
    dims = result["dimensions"]
    expected_dims = [
        "evidence_sufficiency",
        "confidence_level",
        "tool_coverage",
        "evidence_consistency",
        "hypothesis_convergence",
    ]
    for dim_name in expected_dims:
        assert dim_name in dims, f"缺少维度: {dim_name}"
        assert "score" in dims[dim_name], f"维度 {dim_name} 缺少 score"
        assert "detail" in dims[dim_name], f"维度 {dim_name} 缺少 detail"
        assert 0.0 <= dims[dim_name]["score"] <= 1.0, (
            f"维度 {dim_name} score 超出范围: {dims[dim_name]['score']}"
        )

    # 验证 overall_score 在 0-1 范围内
    assert 0.0 <= result["overall_score"] <= 1.0

    # 验证 action 是有效值
    assert result["action"] in ("PROCEED", "NEED_MORE_EVIDENCE")


def test_reflect_high_confidence_proceed():
    """测试高置信度场景：综合得分 >= 0.7 应返回 PROCEED。"""
    from app.schemas.api import AnomalyEvent
    from app.agent.state import RCAState
    from app.agent.nodes.reflect import reflect_node

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="高置信度测试",
    )
    state = RCAState(task_id="test-high-conf", event=event)

    # 构造高分场景：所有假设已确认，工具全覆盖，无反驳
    state.hypotheses = [
        {
            "id": "H1", "description": "设备故障",
            "probability": 0.85, "status": "confirmed",
            "supporting_evidence": [
                {"tool": "equipment_maintenance", "score": 0.8},
                {"tool": "workorder", "score": 0.6},
            ],
            "refuting_evidence": [],
            "required_tools": ["equipment_maintenance", "workorder"],
        },
    ]
    state.tool_call_history = [
        {"tool_name": "equipment_maintenance", "success": True},
        {"tool_name": "workorder", "success": True},
    ]
    state.confidence = 0.85
    state.reflection_round = 0

    state = reflect_node(state)

    result = state.reflection_result
    assert result is not None
    assert result["overall_score"] >= 0.7, (
        f"高置信度场景 overall_score 应 >= 0.7，实际: {result['overall_score']}"
    )
    assert result["action"] == "PROCEED"


def test_reflect_max_rounds_escalates_when_evidence_insufficient():
    """测试达到最大反思轮次但证据不足时不强行 PROCEED。"""
    from app.schemas.api import AnomalyEvent
    from app.agent.state import RCAState
    from app.agent.nodes.reflect import reflect_node

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="强制结束测试",
    )
    state = RCAState(task_id="test-force-end", event=event)

    # 构造低分场景但已达到最大轮次
    state.hypotheses = [
        {
            "id": "H1", "description": "未知问题",
            "probability": 0.1, "status": "pending",
            "supporting_evidence": [],
            "refuting_evidence": [],
            "required_tools": ["knowledge"],
        },
    ]
    state.tool_call_history = []
    state.confidence = 0.1
    state.reflection_round = 2  # 第3轮（0-indexed），达到 max_reflection_rounds - 1

    state = reflect_node(state)

    result = state.reflection_result
    assert result is not None
    assert result["action"] == "ESCALATE", (
        f"达到最大轮次但证据不足应 ESCALATE，实际: {result['action']}"
    )
    assert "证据" in result["reasoning"]


def test_reflect_dimension_scores_range():
    """测试各维度得分均在 0-1 范围内。"""
    from app.schemas.api import AnomalyEvent
    from app.agent.state import RCAState
    from app.agent.nodes.reflect import reflect_node

    event = AnomalyEvent(
        anomaly_type="material_shortage",
        description="维度范围测试",
    )
    state = RCAState(task_id="test-dim-range", event=event)

    # 中等场景
    state.hypotheses = [
        {
            "id": "H1", "description": "供应商延迟",
            "probability": 0.55, "status": "confirmed",
            "supporting_evidence": [{"tool": "material", "score": 0.5}],
            "refuting_evidence": [{"tool": "interface_log", "score": 0.3}],
            "required_tools": ["material", "interface_log", "workorder"],
        },
        {
            "id": "H2", "description": "需求预测偏差",
            "probability": 0.20, "status": "rejected",
            "supporting_evidence": [],
            "refuting_evidence": [{"tool": "material", "score": 0.5}],
            "required_tools": ["material", "knowledge"],
        },
    ]
    state.tool_call_history = [
        {"tool_name": "material", "success": True},
        {"tool_name": "interface_log", "success": True},
    ]
    state.confidence = 0.55
    state.reflection_round = 0

    state = reflect_node(state)

    result = state.reflection_result
    assert result is not None

    for dim_name, dim_data in result["dimensions"].items():
        score = dim_data["score"]
        assert 0.0 <= score <= 1.0, (
            f"维度 {dim_name} score={score} 超出 [0,1] 范围"
        )

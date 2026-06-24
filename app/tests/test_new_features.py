"""新增功能测试 - Prompt 模板系统和 Text2SQL 增强。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ═══════════════════════════════════════════════════════════════
# Prompt 模板系统测试
# ═══════════════════════════════════════════════════════════════

def test_prompt_manager_load_all():
    """测试 PromptManager 能加载所有 5 个节点模板。"""
    from app.prompts.templates import PromptManager

    manager = PromptManager()
    templates = manager.list_templates()

    expected = [
        "analyze_symptom",
        "draft_rca",
        "generate_hypotheses",
        "generate_report",
        "reflect",
        "summarize_title",
    ]
    for name in expected:
        assert name in templates, f"缺少模板: {name}"

    assert len(templates) >= 6


def test_prompt_manager_load_single():
    """测试加载单个模板并验证字段完整性。"""
    from app.prompts.templates import PromptManager

    manager = PromptManager()
    template = manager.load("analyze_symptom")

    assert template.node_name == "analyze_symptom"
    assert len(template.system_prompt) > 0
    assert len(template.user_prompt_template) > 0
    assert len(template.variables) >= 3
    assert 0 < template.temperature <= 1.0
    assert template.max_tokens > 0

    # 验证必填变量
    required = template.get_required_variables()
    assert "anomaly_type" in required
    assert "description" in required
    assert "source_system" in required


def test_prompt_manager_render():
    """测试渲染模板生成完整 prompt。"""
    from app.prompts.templates import PromptManager

    manager = PromptManager()
    prompt = manager.render(
        "analyze_symptom",
        anomaly_type="overstation_check",
        description="工位 WS-03 超站测试",
        source_system="MES",
    )

    assert "[System Prompt]" in prompt
    assert "[User Prompt]" in prompt
    assert "overstation_check" in prompt
    assert "WS-03" in prompt
    assert "MES" in prompt


def test_prompt_manager_render_missing_required():
    """测试缺少必填变量时抛出 ValueError。"""
    import pytest
    from app.prompts.templates import PromptManager

    manager = PromptManager()

    with pytest.raises(ValueError, match="缺少必填变量"):
        manager.render("analyze_symptom", anomaly_type="test")


def test_prompt_manager_cache():
    """测试模板缓存机制。"""
    from app.prompts.templates import PromptManager

    manager = PromptManager()

    # 第一次加载
    t1 = manager.load("reflect")
    # 第二次加载（应命中缓存）
    t2 = manager.load("reflect")

    assert t1 is t2  # 同一对象

    # 清空缓存后重新加载
    manager.clear_cache()
    t3 = manager.load("reflect")
    assert t3 is not t1  # 不同对象


def test_prompt_manager_get_info():
    """测试获取模板元信息。"""
    from app.prompts.templates import PromptManager

    manager = PromptManager()
    info = manager.get_template_info("draft_rca")

    assert info["node_name"] == "draft_rca"
    assert len(info["description"]) > 0
    assert isinstance(info["variables"], list)
    assert isinstance(info["temperature"], float)
    assert isinstance(info["max_tokens"], int)


def test_prompt_in_state_history():
    """测试工作流执行后 state.prompt_history 包含记录。"""
    import uuid
    from app.agent.workflow import RCAWorkflow
    from app.schemas.api import AnomalyEvent

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="工位 WS-03 超站测试",
    )

    workflow = RCAWorkflow()
    task_id = f"pytest-prompt-{uuid.uuid4().hex[:8]}"
    state = workflow.run(event=event, task_id=task_id)

    # 验证 prompt_history 不为空
    assert len(state.prompt_history) > 0, (
        "prompt_history 应包含至少一条记录"
    )

    # 验证记录结构
    for record in state.prompt_history:
        assert "node_name" in record
        assert "prompt" in record
        assert "timestamp" in record
        assert len(record["prompt"]) > 0

    # 验证至少包含 analyze_symptom 节点的 prompt
    node_names = {r["node_name"] for r in state.prompt_history}
    assert "analyze_symptom" in node_names, (
        f"应包含 analyze_symptom 节点，实际: {node_names}"
    )


# ═══════════════════════════════════════════════════════════════
# 工具 Schema 测试
# ═══════════════════════════════════════════════════════════════

def test_tool_schema_in_list():
    """测试 list_tools() 返回每个工具的 input_schema 和 output_schema。"""
    from app.tools.registry import ToolRegistry

    registry = ToolRegistry()
    tools = registry.list_tools()

    for tool in tools:
        assert "input_schema" in tool, (
            f"工具 {tool['name']} 缺少 input_schema"
        )
        assert "output_schema" in tool, (
            f"工具 {tool['name']} 缺少 output_schema"
        )
        assert isinstance(tool["input_schema"], dict)
        assert isinstance(tool["output_schema"], dict)
        # 至少应有 type 字段
        assert tool["input_schema"].get("type") == "object"
        assert tool["output_schema"].get("type") == "object"


def test_tool_schema_in_history():
    """测试 execute_tool 节点在 tool_call_history 中记录 schema。"""
    import uuid
    from app.agent.workflow import RCAWorkflow
    from app.schemas.api import AnomalyEvent

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="测试 schema 记录",
    )

    workflow = RCAWorkflow()
    task_id = f"pytest-schema-{uuid.uuid4().hex[:8]}"
    state = workflow.run(event=event, task_id=task_id)

    # 验证 tool_call_history 包含 schema
    assert len(state.tool_call_history) > 0, (
        "tool_call_history 应包含至少一条记录"
    )

    for record in state.tool_call_history:
        assert "input_schema" in record, (
            f"记录缺少 input_schema: {record.get('tool_name')}"
        )
        assert "output_schema" in record, (
            f"记录缺少 output_schema: {record.get('tool_name')}"
        )


# ═══════════════════════════════════════════════════════════════
# Text2SQL 增强测试
# ═══════════════════════════════════════════════════════════════

def test_sql_generator_intent_classification():
    """测试查询意图分类。"""
    from app.text2sql.generator import SQLGenerator, QueryIntent

    gen = SQLGenerator()

    # 计数意图
    assert gen.classify_intent("有多少延迟工单") == QueryIntent.COUNT
    assert gen.classify_intent("物料数量统计") == QueryIntent.COUNT

    # 聚合意图
    assert gen.classify_intent("按工位统计不良率") == QueryIntent.AGGREGATE
    assert gen.classify_intent("汇总质量数据") == QueryIntent.AGGREGATE

    # 明细意图（默认）
    assert gen.classify_intent("查询工单状态") == QueryIntent.DETAIL


def test_sql_generator_multi_round():
    """测试多轮生成和回退机制。"""
    from app.text2sql.generator import SQLGenerator

    gen = SQLGenerator()

    # 第一轮生成
    sql1 = gen.generate("查询延迟工单", "overstation_check")
    assert "delayed" in sql1.lower() or "blocked" in sql1.lower()

    history = gen.get_round_history()
    assert len(history) == 1

    # 第一轮回退（放宽条件）
    sql2 = gen.generate_fallback(sql1, "查询延迟工单")
    assert sql2 is not None
    assert "work_orders" in sql2.lower()

    history = gen.get_round_history()
    assert len(history) == 2

    # 第二轮回退（全表）
    sql3 = gen.generate_fallback(sql2, "查询延迟工单")
    assert sql3 is not None

    history = gen.get_round_history()
    assert len(history) == 3

    # 第三轮应返回 None（达到 MAX_ROUNDS）
    sql4 = gen.generate_fallback(sql3, "查询延迟工单")
    assert sql4 is None


def test_sql_generator_aggregate_intent():
    """测试聚合意图生成聚合 SQL。"""
    from app.text2sql.generator import SQLGenerator

    gen = SQLGenerator()

    # 聚合意图应生成 GROUP BY 查询
    sql = gen.generate("统计各工位不良率", "quality_abnormal")
    assert "GROUP BY" in sql.upper()
    assert "quality_records" in sql.lower()


def test_sql_executor_structured_result():
    """测试 executor 返回结构化结果。"""
    from app.text2sql.executor import SQLExecutor

    executor = SQLExecutor()
    result = executor.execute(
        "SELECT * FROM work_orders LIMIT 5"
    )

    # 验证结构化字段
    assert "data" in result
    assert "columns" in result
    assert "count" in result
    assert "total_rows" in result
    assert "truncated" in result
    assert "execution_time_ms" in result

    assert isinstance(result["data"], list)
    assert isinstance(result["columns"], list)
    assert isinstance(result["count"], int)
    assert isinstance(result["truncated"], bool)


def test_sql_executor_format_result():
    """测试结果格式化。"""
    from app.text2sql.executor import SQLExecutor

    executor = SQLExecutor()
    result = executor.execute(
        "SELECT * FROM work_orders LIMIT 3"
    )
    formatted = executor.format_result(result)

    assert "summary" in formatted
    assert "total_columns" in formatted["summary"]
    assert "total_rows" in formatted["summary"]
    assert "sample" in formatted["summary"]


def test_sql_executor_execute_with_fallback():
    """测试带回退的执行。"""
    from app.text2sql.executor import SQLExecutor

    executor = SQLExecutor()
    result = executor.execute_with_fallback(
        "SELECT * FROM work_orders WHERE status = 'nonexistent' LIMIT 5",
        "SELECT * FROM work_orders LIMIT 5",
    )

    # 主查询返回空，应使用回退
    assert result.get("used_fallback", False) is True
    assert result.get("count", 0) > 0


def test_text2sql_tool_multi_round():
    """测试 Text2SQL 工具的多轮生成。"""
    from app.tools.text2sql_tool import Text2SQLTool

    tool = Text2SQLTool()
    result = tool.execute({
        "task_id": "test-multi-round",
        "query": "查询延迟工单",
        "anomaly_type": "overstation_check",
    })

    assert result["success"] is True
    assert "generation_rounds" in result
    assert "round_history" in result
    assert "intent" in result
    assert result["intent"] in ("count", "detail", "aggregate")

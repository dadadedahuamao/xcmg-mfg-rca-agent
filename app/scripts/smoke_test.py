"""冒烟测试 - 验证项目核心模块可正常导入和运行。"""

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def test_imports():
    """测试所有核心模块可导入。"""
    print("测试模块导入...")

    # 配置
    from app.config import settings
    assert settings is not None
    print("  ✓ app.config")

    # Schemas
    from app.schemas.api import AnomalyEvent, RCAAnalyzeRequest, TaskStatus
    from app.schemas.evidence import Evidence, EvidenceCollection
    from app.schemas.report import RCAReport, Hypothesis, ReflectionResult
    print("  ✓ app.schemas")

    # Persistence
    from app.persistence.postgres import init_db, get_connection
    from app.persistence.repositories import RCATaskRepository, RCAReportRepository
    from app.persistence.checkpointer import Checkpointer
    print("  ✓ app.persistence")

    # Agent
    from app.agent.state import RCAState
    from app.agent.workflow import RCAWorkflow
    from app.agent.node_adapter import ADAPTED_NODES
    print("  ✓ app.agent (含 LangGraph 工作流)")

    # Nodes
    from app.agent.nodes.analyze_symptom import analyze_symptom_node
    from app.agent.nodes.generate_hypotheses import generate_hypotheses_node
    from app.agent.nodes.select_tool import select_tool_node
    from app.agent.nodes.execute_tool import execute_tool_node
    from app.agent.nodes.observe_evidence import observe_evidence_node
    from app.agent.nodes.draft_rca import draft_rca_node
    from app.agent.nodes.reflect import reflect_node
    from app.agent.nodes.generate_report import generate_report_node
    print("  ✓ app.agent.nodes (8 nodes)")

    # Tools
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry()
    tools = registry.list_tools()
    assert len(tools) >= 7, f"Expected >= 7 tools, got {len(tools)}"
    print(f"  ✓ app.tools ({len(tools)} tools)")

    # Text2SQL
    from app.text2sql.generator import SQLGenerator
    from app.text2sql.validator import SQLValidator
    from app.text2sql.executor import SQLExecutor
    print("  ✓ app.text2sql")

    # RAG
    from app.rag.hybrid_retriever import HybridRetriever
    from app.rag.reranker import Reranker
    from app.rag.knowledge_loader import KnowledgeLoader
    print("  ✓ app.rag")

    # Skills
    from app.skills.loader import SkillsLoader
    loader = SkillsLoader()
    skills = loader.list_skills()
    print(f"  ✓ app.skills ({len(skills)} skills: {', '.join(skills)})")

    # API
    from app.api.routes import router
    print("  ✓ app.api")

    # Main
    from app.main import app
    print("  ✓ app.main (FastAPI app)")

    print("\n所有模块导入成功!")


def test_database():
    """测试数据库初始化和基本操作。"""
    print("\n测试数据库操作...")

    from app.persistence.postgres import get_connection
    from app.persistence.repositories import RCATaskRepository

    print("  ℹ 使用已初始化的业务库结构（db/001_init_app_schema.sql 和 db/002_init_business_schema.sql）")

    # 使用唯一 task_id 避免重复运行冲突
    task_id = f"smoke-db-{uuid.uuid4().hex[:8]}"

    # 创建任务
    task = RCATaskRepository.create(
        task_id=task_id,
        anomaly_type="overstation_check",
        description="冒烟测试任务",
    )
    assert task is not None
    assert task["task_id"] == task_id
    print("  ✓ 创建任务")

    # 查询任务
    task = RCATaskRepository.get(task_id)
    assert task is not None
    assert task["status"] == "pending"
    print("  ✓ 查询任务")

    # 更新状态
    RCATaskRepository.update_status(task_id, "completed", confidence=0.85)
    task = RCATaskRepository.get(task_id)
    assert task is not None, "更新后查询任务不应为 None"
    assert task["status"] == "completed"
    print("  ✓ 更新任务状态")

    print("数据库操作测试通过!")


def test_workflow():
    """测试完整的 RCA 工作流。"""
    print("\n测试 RCA 工作流...")

    from app.agent.workflow import RCAWorkflow
    from app.schemas.api import AnomalyEvent

    event = AnomalyEvent(
        anomaly_type="overstation_check",
        description="工位 WS-03 连续超站，影响下游工序",
        source_system="MES",
    )

    workflow = RCAWorkflow()
    task_id = f"smoke-wf-{uuid.uuid4().hex[:8]}"
    state = workflow.run(event=event, task_id=task_id)

    assert state.task_id == task_id
    assert state.status.value == "completed"
    assert state.confidence >= 0.0
    assert len(state.hypotheses) > 0
    assert state.final_report is not None

    print(f"  ✓ 工作流完成: confidence={state.confidence:.0%}, rounds={state.reflection_round}")
    print(f"  ✓ 假设数: {len(state.hypotheses)}")
    print(f"  ✓ 根因: {state.final_report.get('root_cause', 'N/A')[:60]}")

    print("RCA 工作流测试通过!")


def test_text2sql():
    """测试 Text2SQL 模块。"""
    print("\n测试 Text2SQL...")

    from app.text2sql.generator import SQLGenerator
    from app.text2sql.validator import SQLValidator

    generator = SQLGenerator()
    validator = SQLValidator()

    # 测试生成
    sql = generator.generate("查询延迟工单", "overstation_check")
    assert "SELECT" in sql
    assert "LIMIT" in sql
    print(f"  ✓ SQL 生成: {sql[:60]}...")

    # 测试验证
    is_valid, error = validator.validate(sql)
    assert is_valid, f"SQL 验证失败: {error}"
    print("  ✓ SQL 验证通过")

    # 测试拒绝危险 SQL
    is_valid, error = validator.validate("DROP TABLE work_orders")
    assert not is_valid
    print(f"  ✓ 危险 SQL 被拒绝: {error}")

    print("Text2SQL 测试通过!")


def test_rag():
    """测试 RAG 模块。"""
    print("\n测试 RAG...")

    from app.rag.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever()
    results = retriever.search(
        query="工位超站如何处理",
        anomaly_type="overstation_check",
        top_k=3,
    )

    print(f"  ✓ RAG 检索: 返回 {len(results)} 条结果")
    if results:
        print(f"  ✓ 第一条: {results[0].get('title', 'N/A')[:50]}")

    print("RAG 测试通过!")


def main():
    print("=" * 60)
    print("  XCMG Manufacturing RCA Agent - 冒烟测试")
    print("=" * 60)

    try:
        test_imports()
        test_database()
        test_text2sql()
        test_rag()
        test_workflow()

        print("\n" + "=" * 60)
        print("  所有测试通过! ✓")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

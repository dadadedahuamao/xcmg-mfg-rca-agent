# LangGraph 迁移方案：以官方库替换自研 StateGraph

## 1. 目标

将当前位于 `app/agent/graph.py` 的自研 `StateGraph` / `CompiledGraph` 实现，迁移至官方 `langgraph` 库。迁移完成后：

- 图编排由 `langgraph.graph.StateGraph` 接管，获得官方支持的循环、并发、断点、流式输出等能力。
- 保留 `RCAState`（Pydantic BaseModel）作为业务边界模型和序列化格式，降低对上游 API 与下游持久化的冲击。
- 检查点（checkpoint）第一阶段使用 `InMemorySaver`，生产阶段可平滑切换为 `langgraph-checkpoint-postgres`。
- `StepEventRepository` 继续负责 SSE 事件写入，通过 LangGraph 的 `stream` / `astream_events` 拦截节点生命周期事件。
- 最终删除或归档 `app/agent/graph.py`，减少约 270 行自研维护代码。

## 2. 迁移策略

### 2.1 整体思路：适配器 + 双轨并行

不一次性重写所有节点，而是：

1. **新增状态类型**：引入 `RCAGraphState`（`TypedDict` 或 `dataclass`），满足 LangGraph 对状态对象的要求。
2. **节点适配器**：保持现有 8 个节点函数签名不变（`(RCAState) -> RCAState`），新增薄层适配器将 `RCAGraphState <-> RCAState` 互转。
3. **workflow.py 切换图引擎**：将 `_build_graph` 中的自研 `StateGraph` 替换为 `langgraph.graph.StateGraph`，边和条件路由保持语义一致。
4. **检查点迁移**：先用 `InMemorySaver` 跑通，再视情况引入持久化 checkpoint。
5. **事件发射迁移**：将 `on_node_start` / `on_node_complete` / `on_node_error` 回调，迁移到 LangGraph 的 `stream` / `astream_events` 拦截机制。
6. **测试兜底**：在替换自研实现前，确保所有现有测试通过；替换后补全 LangGraph 特有的集成测试。

### 2.2 为什么保留 RCAState

- `RCAState` 目前被 `Checkpointer`、`StepEventRepository`、`RCATaskRepository` 以及多个 API schema 直接引用。
- 如果直接改为 `TypedDict`，所有持久化层的序列化/反序列化逻辑都需要重写。
- 保留 `RCAState` 作为业务模型，仅在图执行边界做类型转换，风险最小。

## 3. 受影响文件

| 文件 | 影响类型 | 说明 |
|------|----------|------|
| `app/agent/graph.py` | 删除/归档 | 自研 StateGraph 实现，迁移完成后移除 |
| `app/agent/workflow.py` | 重写核心逻辑 | 改用 `langgraph.graph.StateGraph` 构建图 |
| `app/agent/state.py` | 新增 | 新增 `RCAGraphState`，保留 `RCAState` |
| `pyproject.toml` | 修改 | 添加 `langgraph` 依赖；生产环境可选加 `langgraph-checkpoint-postgres` |
| `app/tests/test_rca_workflow_progress_events.py` | 修改 | 更新测试以适配新图引擎 |
| `app/tests/test_rca_async_analyze.py` | 可选修改 | 异步分析入口测试，确认流式行为正常 |
| `app/tests/test_rca_sse.py` | 可选修改 | SSE 事件流测试，验证 `stream` 事件顺序 |
| `app/tests/test_smoke.py` | 修改 | 冒烟测试，确保端到端功能无损 |
| `app/persistence/checkpointer.py` | 可选修改 | 若改用 LangGraph 原生 checkpoint，可逐步废弃 |
| `app/api/routes.py` | 可选修改 | 若暴露 stream 接口，需要配合 `astream_events` |

## 4. 实施步骤

以下按执行顺序排列，每一步包含**操作**、**验证**和**涉及文件**。

---

### 步骤 1：添加依赖

**操作：**

在 `pyproject.toml` 的 `[project] dependencies` 中新增：

```toml
dependencies = [
    # ... 现有依赖
    "langgraph>=1.2.0",
    # 生产环境 checkpoint（可选，第二阶段再引入）
    # "langgraph-checkpoint-postgres",
]
```

然后执行安装：

```bash
python -m pip install -e .
```

**验证：**

```bash
python -c "from langgraph.graph import StateGraph, START, END; print('langgraph OK')"
```

**文件：** `pyproject.toml`

---

### 步骤 2：新增 RCAGraphState

**操作：**

在 `app/agent/state.py` 末尾新增 `RCAGraphState`：

```python
from typing import TypedDict, Annotated
from operator import add

class RCAGraphState(TypedDict):
    """LangGraph 执行期状态（内部使用）。

    字段与 RCAState 保持一致，但使用 TypedDict 以满足 LangGraph 要求。
    列表字段使用 Annotated + reducer 实现合并语义。
    """
    task_id: str
    status: str
    current_node: str | None
    event: dict | None
    hypotheses: Annotated[list[dict], add]
    evidence: Annotated[list[dict], add]
    selected_tools: Annotated[list[str], add]
    tool_call_history: Annotated[list[dict], add]
    reflection_round: int
    draft_rca: str | None
    reflection_result: dict | None
    confidence: float
    final_report: dict | None
    prompt_history: Annotated[list[dict], add]
    anomaly_type: str
    description: str
    source_system: str
    metadata: dict
    created_at: str
    completed_at: str | None
```

**验证：**

```bash
python -c "from app.agent.state import RCAGraphState; print('RCAGraphState OK')"
```

**文件：** `app/agent/state.py`

---

### 步骤 3：新增节点适配器

**操作：**

新建 `app/agent/node_adapter.py`，为每个现有节点包装适配器：

```python
"""节点适配器：将 LangGraph 的 dict 状态转换为 RCAState 后调用现有节点。"""

from app.agent.state import RCAState, RCAGraphState
from app.agent.nodes.analyze_symptom import analyze_symptom_node
from app.agent.nodes.generate_hypotheses import generate_hypotheses_node
from app.agent.nodes.select_tool import select_tool_node
from app.agent.nodes.execute_tool import execute_tool_node
from app.agent.nodes.observe_evidence import observe_evidence_node
from app.agent.nodes.draft_rca import draft_rca_node
from app.agent.nodes.reflect import reflect_node
from app.agent.nodes.generate_report import generate_report_node


def _to_rca_state(state: RCAGraphState) -> RCAState:
    """将 RCAGraphState 转换为 RCAState。"""
    return RCAState(**state)


def _to_graph_state(rca_state: RCAState) -> RCAGraphState:
    """将 RCAState 转换为 RCAGraphState。"""
    return RCAGraphState(**rca_state.model_dump())


def _wrap_node(node_func):
    """通用节点包装器。"""
    def wrapped(state: RCAGraphState) -> RCAGraphState:
        rca_state = _to_rca_state(state)
        result = node_func(rca_state)
        return _to_graph_state(result)
    return wrapped


# 导出自带适配的节点
adapted_analyze_symptom = _wrap_node(analyze_symptom_node)
adapted_generate_hypotheses = _wrap_node(generate_hypotheses_node)
adapted_select_tool = _wrap_node(select_tool_node)
adapted_execute_tool = _wrap_node(execute_tool_node)
adapted_observe_evidence = _wrap_node(observe_evidence_node)
adapted_draft_rca = _wrap_node(draft_rca_node)
adapted_reflect = _wrap_node(reflect_node)
adapted_generate_report = _wrap_node(generate_report_node)
```

**验证：**

```bash
python -c "from app.agent.node_adapter import adapted_analyze_symptom; print('adapter OK')"
```

**文件：** 新建 `app/agent/node_adapter.py`

---

### 步骤 4：重写 workflow.py 的图构建逻辑

**操作：**

修改 `app/agent/workflow.py`：

1. 删除 `from app.agent.graph import StateGraph`
2. 新增 `from langgraph.graph import StateGraph, START, END`
3. 新增 `from langgraph.checkpoint.memory import InMemorySaver`
4. 新增 `from app.agent.node_adapter import (...)`
5. 新增 `from app.agent.state import RCAGraphState`
6. 重写 `_build_graph` 方法：

```python
def _build_graph(self):
    """使用官方 LangGraph 构建 RCA 工作流。"""
    graph = StateGraph(RCAGraphState)

    # 注册节点（使用适配器包装后的版本）
    graph.add_node("analyze_symptom", adapted_analyze_symptom)
    graph.add_node("generate_hypotheses", adapted_generate_hypotheses)
    graph.add_node("select_tool", adapted_select_tool)
    graph.add_node("execute_tool", adapted_execute_tool)
    graph.add_node("observe_evidence", adapted_observe_evidence)
    graph.add_node("draft_rca", adapted_draft_rca)
    graph.add_node("reflect", adapted_reflect)
    graph.add_node("generate_report", adapted_generate_report)

    # 普通边
    graph.add_edge(START, "analyze_symptom")
    graph.add_edge("analyze_symptom", "generate_hypotheses")
    graph.add_edge("generate_hypotheses", "select_tool")
    graph.add_edge("select_tool", "execute_tool")
    graph.add_edge("execute_tool", "observe_evidence")
    graph.add_edge("observe_evidence", "draft_rca")
    graph.add_edge("draft_rca", "reflect")

    # 条件边
    graph.add_conditional_edges(
        "reflect",
        _reflect_condition_adapter,
        {
            "PROCEED": "generate_report",
            "NEED_MORE_EVIDENCE": "select_tool",
        },
    )

    graph.add_edge("generate_report", END)

    return graph.compile(checkpointer=InMemorySaver())
```

7. 新增 `_reflect_condition_adapter`：

```python
def _reflect_condition_adapter(state: RCAGraphState) -> str:
    """适配 LangGraph 的条件路由函数。"""
    rca_state = RCAState(**state)
    return rca_state.get_reflection_action()
```

8. 修改 `run` 方法中的调用方式：

```python
# 编译图（已内置 MemorySaver）
app = self._build_graph()

# 使用 stream 执行并拦截事件
config = {"configurable": {"thread_id": task_id}}

for event in app.stream(initial_graph_state, config=config):
    # event 是 dict，key 为节点名，value 为状态片段
    for node_name, output in event.items():
        # 这里可复用现有的 _emit_event 逻辑
        ...

# 获取最终状态
final_state = app.get_state(config)
state = RCAState(**final_state.values)
```

**验证：**

```bash
python -c "from app.agent.workflow import RCAWorkflow; w = RCAWorkflow(); print('workflow build OK')"
```

**文件：** `app/agent/workflow.py`

---

### 步骤 5：事件发射迁移到 LangGraph stream

**操作：**

在 `run` 方法中，将原有的 `on_node_start` / `on_node_complete` / `on_node_error` 回调替换为基于 `stream` 的事件拦截：

```python
# 执行图并实时发射事件
config = {"configurable": {"thread_id": task_id}}

try:
    for chunk in app.stream(initial_graph_state, config=config):
        for node_name, output in chunk.items():
            # 节点完成事件
            self._emit_event(
                task_id=task_id,
                node_name=node_name,
                event_type="node_completed",
                status="completed",
                title=f"完成{self._node_title(node_name)}",
                summary=f"{self._node_title(node_name)} 执行完成",
                detail_json={"node_name": node_name},
            )

    # 获取最终状态
    final_state = app.get_state(config)
    state = RCAState(**final_state.values)

except Exception as e:
    # 异常处理：发射 task_error
    ...
```

注意：`stream` 默认在节点执行后输出，因此 `node_started` 事件可以在调用 `stream` 前统一发射 `task_started`，或在 `stream` 外层通过 `_node_start_times` 手动记录开始时间。

**验证：**

运行 `python app/scripts/run_demo.py`，确认 SSE 事件流正常输出。

**文件：** `app/agent/workflow.py`

---

### 步骤 6：检查点迁移（第一阶段：InMemorySaver）

**操作：**

当前 `_build_graph` 已使用 `InMemorySaver`。此步骤无需额外代码，只需确认：

- `InMemorySaver` 在进程重启后状态会丢失，适合演示和测试环境。
- `RCAWorkflow.run(resume=True)` 的逻辑需要调整：不再使用自研的 `resume_from` 参数，而是利用 LangGraph 的 `thread_id` 自动恢复。

修改断点恢复逻辑：

```python
if resume:
    config = {"configurable": {"thread_id": task_id}}
    # LangGraph 会自动从 checkpoint 恢复状态
    # 只需传入空状态或部分更新
    state = app.get_state(config)
    if state is None or not state.values:
        logger.info(f"未找到 checkpoint，从头开始: task_id={task_id}")
        state = self._init_state(event, task_id)
    else:
        logger.info(f"从 checkpoint 恢复: task_id={task_id}")
        state = RCAState(**state.values)
else:
    state = self._init_state(event, task_id)
```

**验证：**

1. 启动一次分析任务。
2. 在任务中途停止进程。
3. 使用相同 `task_id` 调用 `run(resume=True)`，确认从断点继续。

**文件：** `app/agent/workflow.py`

---

### 步骤 7：检查点迁移（第二阶段：PostgresSaver，可选）

**操作：**

当需要生产级持久化时：

1. 安装依赖：`python -m pip install langgraph-checkpoint-postgres`
2. 在 `pyproject.toml` 中取消注释该依赖。
3. 修改 `_build_graph`：

```python
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection

# 在 __init__ 中创建连接池或连接
self._checkpointer = PostgresSaver(Connection.connect(DATABASE_URL))

# 编译图时使用 PostgresSaver
return graph.compile(checkpointer=self._checkpointer)
```

**验证：**

在 K8s / Docker 环境中部署，确认任务状态在 Pod 重启后可恢复。

**文件：** `app/agent/workflow.py`、`pyproject.toml`

---

### 步骤 8：更新测试

**操作：**

1. 修改 `app/tests/test_rca_workflow_progress_events.py`：
   - 确保 `RCAWorkflow.run()` 的调用方式不变。
   - 新增测试：验证 `stream` 输出的事件顺序与节点拓扑一致。
   - 新增测试：验证 `resume=True` 时能从 checkpoint 恢复。
2. 可选修改 `app/tests/test_rca_async_analyze.py` 和 `app/tests/test_rca_sse.py`，确认异步入口和 SSE 事件流行为正常。
3. 修改 `app/tests/test_smoke.py`，确保端到端功能无损。
4. 新增 `app/tests/test_node_adapter.py`：
   - 测试 `_to_rca_state` 和 `_to_graph_state` 的字段一致性。
   - 测试每个 adapted 节点执行后返回正确的 `RCAGraphState`。

**验证：**

```bash
pytest app/tests/test_rca_workflow_progress_events.py -v
pytest app/tests/test_node_adapter.py -v
pytest app/tests/test_smoke.py -v
```

**文件：** `app/tests/test_rca_workflow_progress_events.py`、新建 `app/tests/test_node_adapter.py`、`app/tests/test_smoke.py`

---

### 步骤 9：删除/归档自研 graph.py

**操作：**

确认以下事项全部完成后，删除 `app/agent/graph.py`：

- [ ] `workflow.py` 已不再导入 `app.agent.graph`。
- [ ] 所有测试通过（pytest 全绿）。
- [ ] `run_demo.py` 和 `smoke_test.py` 运行正常。
- [ ] 文档（README.md）中关于自研 StateGraph 的描述已更新。

建议将 `graph.py` 移动到 `archive/` 目录而非直接删除，以便日后参考（以下为 PowerShell 示例）：

```powershell
New-Item -ItemType Directory -Path "archive" -Force
Move-Item -Path "app/agent/graph.py" -Destination "archive/graph_legacy.py"
```

> Linux/macOS 示例：
> ```bash
> mkdir -p archive
> mv app/agent/graph.py archive/graph_legacy.py
> ```

**验证：**

```bash
pytest app/tests/ -v
python app/scripts/smoke_test.py
```

**文件：** `app/agent/graph.py`

## 5. 验证清单

迁移完成后，执行以下验证项确认系统行为正常：

| 序号 | 验证项 | 操作 | 期望结果 |
|------|--------|------|----------|
| 1 | 依赖安装 | `python -c "from langgraph.graph import StateGraph"` | 无报错 |
| 2 | 图编译 | `python -c "from app.agent.workflow import RCAWorkflow; w = RCAWorkflow()"` | 无报错 |
| 3 | 端到端执行 | `python app/scripts/run_demo.py` | 正常完成，输出报告 |
| 4 | SSE 事件流 | 调用 `/api/v1/rca/analyze` 后访问 `/api/v1/rca/events/{task_id}` | 收到 8 个节点的 `node_completed` 事件 |
| 5 | 反思循环 | 构造需要多轮证据的异常描述 | `reflect` 节点触发 `NEED_MORE_EVIDENCE`，回退到 `select_tool` |
| 6 | 断点恢复 | 中途停止进程后使用相同 `task_id` 调用 `run(resume=True)` | 从上次执行的下一个节点继续 |
| 7 | 单元测试 | `pytest app/tests/ -v` | 全部通过 |
| 8 | 冒烟测试 | `python app/scripts/smoke_test.py` | 全部通过 |
| 9 | 性能基线 | 对比迁移前后 `run_demo.py` 的执行时间 | 差异不超过 20% |
| 10 | 并发安全 | 同时提交 3 个不同 `task_id` 的任务 | 互不干扰，结果正确 |

## 6. 风险与回退

### 6.1 主要风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| `RCAGraphState` 与 `RCAState` 字段不一致 | 节点执行时 KeyError 或数据丢失 | 在 `node_adapter.py` 中增加字段映射检查；单元测试覆盖全部字段 |
| LangGraph `stream` 行为与自研回调不一致 | SSE 事件丢失或顺序错乱 | 保留 `_emit_event` 逻辑不变，仅改变调用位置；对比测试验证事件顺序 |
| `InMemorySaver` 进程重启丢状态 | 演示环境断点恢复失效 | 第一阶段明确文档说明；第二阶段尽快切 PostgresSaver |
| 依赖版本冲突 | `langgraph` 与现有 `pydantic` / `typing-extensions` 不兼容 | 在虚拟环境中先行验证；锁定版本号 |
| 反射循环次数超限 | LangGraph 默认循环限制与自研的 `max_iterations=50` 不同 | 显式配置 `recursion_limit`；保持与现有逻辑一致 |

### 6.2 回退方案

若迁移后出现严重问题，可按以下步骤回退：

1. **代码回退**：从 Git 恢复 `app/agent/graph.py`、`app/agent/workflow.py`、`app/agent/state.py` 的原始版本。
2. **依赖回退**：从 `pyproject.toml` 中移除 `langgraph` 相关依赖，重新安装。
3. **验证回退**：运行 `pytest app/tests/ -v` 和 `python app/scripts/smoke_test.py` 确认恢复。

建议在整个迁移过程中保持 feature branch，合并前在 PR 中跑完全量测试。

## 7. 推荐落地顺序

### 第一阶段：环境准备与状态隔离（1 天）

- [ ] 步骤 1：添加 `langgraph` 依赖
- [ ] 步骤 2：新增 `RCAGraphState`
- [ ] 步骤 3：新增 `node_adapter.py`
- [ ] 编写 `test_node_adapter.py`，确保适配器字段无损转换

**里程碑：** 现有代码零改动，新增代码全部测试通过。

### 第二阶段：图引擎切换（1-2 天）

- [ ] 步骤 4：重写 `workflow.py` 的 `_build_graph`
- [ ] 步骤 5：事件发射迁移到 `stream`
- [ ] 步骤 6：检查点迁移到 `InMemorySaver`
- [ ] 更新 `test_rca_workflow_progress_events.py`，补全 stream 和 resume 测试
- [ ] 运行 `run_demo.py` 和 `smoke_test.py`

**里程碑：** 自研 `graph.py` 不再被导入，全量测试通过。

### 第三阶段：清理与生产优化（1 天）

- [ ] 步骤 7：评估并引入 `PostgresSaver`（可选）
- [ ] 步骤 8：删除/归档 `graph.py`
- [ ] 更新 README.md 中关于自研 StateGraph 的描述
- [ ] 步骤 9：最终验证清单全部打勾

**里程碑：** 代码库精简约 270 行，功能无损，生产 checkpoint 就绪。

### 总体时间估计

- **最小可行**：2 天（跳过 PostgresSaver，直接 InMemorySaver + 清理）
- **推荐节奏**：3 天（按上述三阶段执行，留足测试时间）
- **保守估计**：5 天（含完整的集成测试、K8s 验证和文档更新）
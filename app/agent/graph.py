"""轻量级 StateGraph 图编排引擎。

不依赖 langgraph 库，纯 Python 实现：
- 节点注册与拓扑排序执行
- 条件边动态路由
- 循环回退支持（反思 → 重新选工具）
- 节点执行后回调（用于检查点保存）
"""

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 节点函数签名: (state) -> state
NodeFunc = Callable[[Any], Any]
# 条件函数签名: (state) -> str，返回下一个节点名称
ConditionFunc = Callable[[Any], str]
# 回调函数签名: (node_name, state) -> None
CallbackFunc = Callable[[str, Any], None]
# 错误回调函数签名: (node_name, state, error) -> None
ErrorCallbackFunc = Callable[[str, Any, Exception], None]


class CompiledGraph:
    """编译后的可执行图。

    按拓扑顺序执行节点，遇到条件边时动态路由。
    支持循环：条件边可以指向已执行过的节点（用于反思回退）。
    """

    def __init__(self, graph: "StateGraph"):
        self._graph = graph
        self._entry_point = graph._entry_point
        self._nodes = dict(graph._nodes)
        self._edges = list(graph._edges)
        self._conditional_edges = dict(graph._conditional_edges)
        self._on_node_complete: Optional[CallbackFunc] = None
        self._on_node_start: Optional[CallbackFunc] = None
        self._on_node_error: Optional[ErrorCallbackFunc] = None

    def set_callback(self, callback: CallbackFunc) -> None:
        """设置节点完成回调（用于检查点保存等）。"""
        self._on_node_complete = callback

    def set_start_callback(self, callback: CallbackFunc) -> None:
        """设置节点开始回调（用于进度事件等）。"""
        self._on_node_start = callback

    def set_error_callback(self, callback: ErrorCallbackFunc) -> None:
        """设置节点错误回调。"""
        self._on_node_error = callback

    def invoke(self, initial_state: Any, resume_from: Optional[str] = None) -> Any:
        """执行图，从入口节点开始。

        Args:
            initial_state: 初始状态对象
            skip_until: 如果指定，跳过该节点之前的所有节点（用于断点恢复）

        Returns:
            执行完成后的最终状态
        """
        state = initial_state

        # ── 构建邻接表：每个节点的后继节点列表 ────────────────
        successors: dict[str, list[str]] = {name: [] for name in self._nodes}
        for src, dst in self._edges:
            successors.setdefault(src, []).append(dst)

        # ── 确定起始节点 ──────────────────────────────────────
        current = self._entry_point
        if current is None:
            raise ValueError("图未设置入口节点")

        # 断点恢复：直接从指定节点开始执行
        if resume_from is not None:
            if resume_from in self._nodes:
                logger.info(f"断点恢复: 从 '{resume_from}' 继续执行")
                current = resume_from
            else:
                logger.warning(
                    f"断点恢复: 节点 '{resume_from}' 未注册，从入口开始"
                )
                current = self._entry_point

        # ── 记录已执行节点（用于循环检测和断点恢复） ──────────
        executed: set[str] = set()
        max_iterations = 50  # 安全上限，防止死循环

        for _ in range(max_iterations):
            if current is None:
                break  # 无后续节点，执行结束

            # 执行当前节点
            node_func = self._nodes.get(current)
            if node_func is None:
                logger.error(f"节点 '{current}' 未注册")
                break

            logger.info(f"[Graph] 执行节点: {current}")

            # 节点开始回调
            if self._on_node_start:
                self._on_node_start(current, state)

            try:
                state = node_func(state)
            except Exception as exc:
                # 节点错误回调
                if self._on_node_error:
                    self._on_node_error(current, state, exc)
                raise

            executed.add(current)

            # 节点完成回调
            if self._on_node_complete:
                self._on_node_complete(current, state)

            # ── 确定下一个节点 ────────────────────────────────
            next_node = None

            # 优先检查条件边
            if current in self._conditional_edges:
                cond_func, mapping = self._conditional_edges[current]
                decision = cond_func(state)
                next_node = mapping.get(decision)
                logger.info(
                    f"[Graph] 条件路由: {current} → {decision} → {next_node}"
                )

            # 否则走普通边
            if next_node is None:
                next_nodes = successors.get(current, [])
                if len(next_nodes) == 1:
                    next_node = next_nodes[0]
                elif len(next_nodes) > 1:
                    # 多条普通边，取第一条（通常不会出现这种情况）
                    logger.warning(
                        f"节点 '{current}' 有多条普通边但无条件边，"
                        f"取第一条: {next_nodes[0]}"
                    )
                    next_node = next_nodes[0]

            current = next_node

        else:
            logger.warning(f"图执行达到最大迭代次数 {max_iterations}，强制终止")

        return state

class StateGraph:
    """轻量级状态图构建器。

    使用方式:
        graph = StateGraph()
        graph.add_node("step1", func1)
        graph.add_node("step2", func2)
        graph.add_edge("step1", "step2")
        graph.add_conditional_edges("step2", decide, {"A": "step3a", "B": "step3b"})
        graph.set_entry_point("step1")
        compiled = graph.compile()
        result = compiled.invoke(initial_state)
    """

    def __init__(self):
        self._nodes: dict[str, NodeFunc] = {}
        self._edges: list[tuple[str, str]] = []
        self._conditional_edges: dict[str, tuple[ConditionFunc, dict[str, str]]] = {}
        self._entry_point: Optional[str] = None

    def add_node(self, name: str, func: NodeFunc) -> "StateGraph":
        """注册一个节点。

        Args:
            name: 节点名称（唯一标识）
            func: 节点函数，签名为 (state) -> state
        """
        if name in self._nodes:
            raise ValueError(f"节点 '{name}' 已存在")
        self._nodes[name] = func
        return self

    def add_edge(self, from_node: str, to_node: str) -> "StateGraph":
        """添加一条普通边（无条件跳转）。

        Args:
            from_node: 源节点名称
            to_node: 目标节点名称
        """
        if from_node not in self._nodes:
            raise ValueError(f"源节点 '{from_node}' 未注册")
        if to_node not in self._nodes:
            raise ValueError(f"目标节点 '{to_node}' 未注册")
        self._edges.append((from_node, to_node))
        return self

    def add_conditional_edges(
        self,
        from_node: str,
        condition_func: ConditionFunc,
        mapping: dict[str, str],
    ) -> "StateGraph":
        """添加条件边（根据状态动态路由）。

        Args:
            from_node: 源节点名称
            condition_func: 条件函数，签名为 (state) -> str，返回决策键
            mapping: 决策键 → 目标节点名称的映射
        """
        if from_node not in self._nodes:
            raise ValueError(f"源节点 '{from_node}' 未注册")
        for target in mapping.values():
            if target not in self._nodes:
                raise ValueError(f"条件边目标节点 '{target}' 未注册")
        self._conditional_edges[from_node] = (condition_func, mapping)
        return self

    def set_entry_point(self, name: str) -> "StateGraph":
        """设置入口节点。

        Args:
            name: 入口节点名称
        """
        if name not in self._nodes:
            raise ValueError(f"入口节点 '{name}' 未注册")
        self._entry_point = name
        return self

    def compile(self) -> CompiledGraph:
        """编译图为可执行对象。

        Returns:
            CompiledGraph 实例
        """
        if self._entry_point is None:
            raise ValueError("未设置入口节点，请调用 set_entry_point()")

        # 验证所有节点可达（从入口出发）
        reachable = self._find_reachable()
        unreachable = set(self._nodes.keys()) - reachable
        if unreachable:
            logger.warning(f"以下节点从入口不可达: {unreachable}")

        return CompiledGraph(self)

    def _find_reachable(self) -> set[str]:
        """从入口节点出发，找到所有可达节点。"""
        if self._entry_point is None:
            return set()

        reachable: set[str] = set()
        stack = [self._entry_point]

        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)

            # 普通边
            for src, dst in self._edges:
                if src == node and dst not in reachable:
                    stack.append(dst)

            # 条件边
            if node in self._conditional_edges:
                _, mapping = self._conditional_edges[node]
                for target in mapping.values():
                    if target not in reachable:
                        stack.append(target)

        return reachable

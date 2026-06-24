"""工作流检查点 - 保存/恢复 RCAState 到 PostgreSQL。"""

import json
from typing import Optional

from app.agent.state import RCAState
from app.persistence.repositories import CheckpointRepository


class Checkpointer:
    """基于 PostgreSQL 的工作流检查点管理器。"""

    @staticmethod
    def save(state: RCAState) -> None:
        """保存当前状态到检查点。"""
        state_json = json.dumps(state.model_dump(), ensure_ascii=False, default=str)
        CheckpointRepository.save(
            task_id=state.task_id,
            node_name=state.current_node or "unknown",
            state_json=state_json,
        )

    @staticmethod
    def load(task_id: str) -> Optional[RCAState]:
        """从最新检查点恢复状态。"""
        record = CheckpointRepository.get_latest(task_id)
        if record is None:
            return None
        data = json.loads(record["state_json"])
        return RCAState(**data)

    @staticmethod
    def get_history(task_id: str) -> list[dict]:
        """获取任务的所有检查点历史。"""
        return CheckpointRepository.get_all(task_id)

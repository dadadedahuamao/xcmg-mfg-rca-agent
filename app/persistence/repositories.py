"""数据仓库层 - RCA 任务、报告、反馈、检查点、工具去重的 CRUD 操作。"""

import json
import hashlib
import uuid
from typing import Any, Optional

from app.persistence import postgres


class RCATaskRepository:
    """RCA 任务仓库。"""

    @staticmethod
    def create(
        task_id: str,
        anomaly_type: str,
        description: str,
        source_system: str = "MES",
        metadata: Optional[dict] = None,
    ) -> dict:
        conn = postgres.get_connection()
        try:
            now = postgres.database_timestamp()
            conn.execute(
                """INSERT INTO rca_tasks (task_id, anomaly_type, description, source_system,
                   status, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)""",
                (task_id, anomaly_type, description, source_system,
                 json.dumps(metadata or {}, ensure_ascii=False), now, now),
            )
            conn.commit()
            result = RCATaskRepository.get(task_id)
            assert result is not None, f"Failed to retrieve created task {task_id}"
            return result
        finally:
            conn.close()

    @staticmethod
    def get(task_id: str) -> Optional[dict]:
        conn = postgres.get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM rca_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    @staticmethod
    def update_status(task_id: str, status: str, **kwargs) -> None:
        conn = postgres.get_connection()
        try:
            now = postgres.database_timestamp()
            fields = ["status = ?", "updated_at = ?"]
            values = [status, now]
            for key, val in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(val)
            if status == "completed":
                fields.append("completed_at = ?")
                values.append(now)
            values.append(task_id)
            conn.execute(
                f"UPDATE rca_tasks SET {', '.join(fields)} WHERE task_id = ?",
                values,
            )
            conn.commit()
        finally:
            conn.close()


class RCAReportRepository:
    """RCA 报告仓库。"""

    @staticmethod
    def save(task_id: str, report_data: dict) -> None:
        conn = postgres.get_connection()
        try:
            now = postgres.database_timestamp()
            conn.execute(
                """INSERT OR REPLACE INTO rca_reports
                   (task_id, root_cause, root_cause_category, hypotheses,
                    evidence_summary, tool_call_history, confidence,
                    reflection_rounds, recommendations, final_report, generated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    report_data.get("root_cause"),
                    report_data.get("root_cause_category"),
                    json.dumps(report_data.get("hypotheses", []), ensure_ascii=False),
                    json.dumps(report_data.get("evidence_summary", []), ensure_ascii=False),
                    json.dumps(report_data.get("tool_call_history", []), ensure_ascii=False),
                    report_data.get("confidence", 0.0),
                    report_data.get("reflection_rounds", 0),
                    json.dumps(report_data.get("recommendations", []), ensure_ascii=False),
                    json.dumps(report_data, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get(task_id: str) -> Optional[dict]:
        conn = postgres.get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM rca_reports WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()


class CheckpointRepository:
    """检查点仓库。"""

    @staticmethod
    def save(task_id: str, node_name: str, state_json: str) -> None:
        conn = postgres.get_connection()
        try:
            now = postgres.database_timestamp()
            conn.execute(
                """INSERT INTO checkpoints (task_id, node_name, state_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (task_id, node_name, state_json, now),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_latest(task_id: str) -> Optional[dict]:
        conn = postgres.get_connection()
        try:
            row = conn.execute(
                """SELECT * FROM checkpoints WHERE task_id = ?
                   ORDER BY id DESC LIMIT 1""",
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()

    @staticmethod
    def get_all(task_id: str) -> list[dict]:
        conn = postgres.get_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM checkpoints WHERE task_id = ?
                   ORDER BY id ASC""",
                (task_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


class StepEventRepository:
    """RCA 步骤事件仓库 — 追加式持久化，支持按 seq 增量查询。"""

    @staticmethod
    def append_event(
        task_id: str,
        node_name: str,
        event_type: str,
        status: str,
        title: str,
        summary: Optional[str] = None,
        detail: Optional[str] = None,
        detail_json: Optional[dict] = None,
        checkpoint_id: Optional[int] = None,
    ) -> None:
        conn = postgres.get_connection()
        try:
            now = postgres.database_timestamp()
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS seq FROM rca_step_events WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            seq = row["seq"] if row else 1
            conn.execute(
                """INSERT INTO rca_step_events
                   (task_id, seq, node_name, event_type, status, title,
                    summary, detail, detail_json, checkpoint_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    seq,
                    node_name,
                    event_type,
                    status,
                    title,
                    summary,
                    detail,
                    json.dumps(detail_json, ensure_ascii=False) if detail_json is not None else None,
                    checkpoint_id,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def list_events(task_id: str, after_seq: int = 0) -> list[dict]:
        conn = postgres.get_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM rca_step_events
                   WHERE task_id = ? AND seq > ?
                   ORDER BY seq ASC""",
                (task_id, after_seq),
            ).fetchall()
            events = []
            for r in rows:
                event = dict(r)
                if event.get("detail_json") is not None:
                    event["detail_json"] = json.loads(event["detail_json"])
                events.append(event)
            return events
        finally:
            conn.close()


class ToolDedupRepository:
    """工具去重仓库。"""

    @staticmethod
    def check_and_record(
        task_id: str, tool_name: str, params: dict
    ) -> Optional[dict]:
        """检查是否已有相同调用，若无则记录并返回 None，若有则返回缓存结果。"""
        params_hash = hashlib.md5(
            json.dumps(params, sort_keys=True).encode()
        ).hexdigest()
        conn = postgres.get_connection()
        try:
            row = conn.execute(
                """SELECT result_json FROM tool_dedup
                   WHERE task_id = ? AND tool_name = ? AND params_hash = ?""",
                (task_id, tool_name, params_hash),
            ).fetchone()
            if row:
                return json.loads(row["result_json"]) if row["result_json"] else {}
            now = postgres.database_timestamp()
            conn.execute(
                """INSERT INTO tool_dedup (task_id, tool_name, params_hash, created_at)
                   VALUES (?, ?, ?, ?)""",
                (task_id, tool_name, params_hash, now),
            )
            conn.commit()
            return None
        finally:
            conn.close()

    @staticmethod
    def update_result(
        task_id: str, tool_name: str, params: dict, result: dict
    ) -> None:
        params_hash = hashlib.md5(
            json.dumps(params, sort_keys=True).encode()
        ).hexdigest()
        conn = postgres.get_connection()
        try:
            conn.execute(
                """UPDATE tool_dedup SET result_json = ?
                   WHERE task_id = ? AND tool_name = ? AND params_hash = ?""",
                (json.dumps(result, ensure_ascii=False), task_id, tool_name, params_hash),
            )
            conn.commit()
        finally:
            conn.close()

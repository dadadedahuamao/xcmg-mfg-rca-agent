"""API 路由 - RCA 分析接口。"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from starlette.responses import StreamingResponse

from app import __version__
from app.agent.workflow import RCAWorkflow
from app.persistence.repositories import RCATaskRepository, RCAReportRepository, StepEventRepository
from app.schemas.api import (
    AnomalyEvent,
    HealthResponse,
    RCAAnalyzeRequest,
    RCAAnalyzeResponse,
    RCAReportResponse,
    RCATaskResponse,
    TaskStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/rca", tags=["RCA"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查。"""
    return HealthResponse(
        status="healthy",
        version=__version__,
        timestamp=datetime.now(),
    )


@router.post("/analyze", response_model=RCAAnalyzeResponse, status_code=202)
async def analyze(request: RCAAnalyzeRequest, background_tasks: BackgroundTasks):
    """创建 RCA 分析任务（异步）。

    接收异常事件，创建任务记录并调度后台执行，
    立即返回 HTTP 202 及任务标识。
    """
    task_id = request.task_id or f"rca-{uuid.uuid4().hex[:12]}"

    try:
        # 1. 先创建任务记录（status=pending）
        RCATaskRepository.create(
            task_id=task_id,
            anomaly_type=request.event.anomaly_type,
            description=request.event.description,
            source_system=request.event.source_system,
            metadata=request.event.metadata,
        )

        # 2. 调度后台执行
        event_dict = {
            "anomaly_type": request.event.anomaly_type,
            "description": request.event.description,
            "source_system": request.event.source_system,
            "metadata": request.event.metadata,
        }
        background_tasks.add_task(_run_rca_background, task_id, event_dict)

        # 3. 立即返回 202
        events_url = f"/api/v1/rca/tasks/{task_id}/events"
        return RCAAnalyzeResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message=f"RCA 分析任务已创建，将通过 {events_url} 推送进度",
            events_url=events_url,
        )
    except Exception as e:
        logger.error(f"创建 RCA 任务失败: task_id={task_id}, error={e}")
        raise HTTPException(
            status_code=500,
            detail=f"创建 RCA 任务失败: {str(e)}",
        )


def _run_rca_background(
    task_id: str,
    event_dict: dict[str, Any],
    _workflow: Any = None,
) -> None:
    """后台执行 RCA 工作流。

    由 FastAPI BackgroundTasks 调度，执行完整工作流并更新任务状态。
    _workflow 参数用于测试注入 mock。
    """
    from app.schemas.api import AnomalyEvent

    try:
        # 更新状态为 running
        RCATaskRepository.update_status(task_id, "running")

        # 构造事件对象
        event = AnomalyEvent(
            anomaly_type=event_dict["anomaly_type"],
            description=event_dict["description"],
            source_system=event_dict.get("source_system", "MES"),
            metadata=event_dict.get("metadata", {}),
        )

        # 执行工作流（skip_persistence=True 避免重复创建/更新）
        workflow = _workflow if _workflow is not None else RCAWorkflow()
        state = workflow.run(event=event, task_id=task_id, skip_persistence=True)

        # 更新最终状态
        RCATaskRepository.update_status(
            task_id, "completed",
            confidence=state.confidence,
            reflection_rounds=state.reflection_round,
        )

        logger.info(
            f"后台 RCA 完成: task_id={task_id}, "
            f"confidence={state.confidence:.2f}"
        )

    except Exception as e:
        logger.error(f"后台 RCA 失败: task_id={task_id}, error={e}")
        RCATaskRepository.update_status(task_id, "failed")


@router.get("/reports/{task_id}", response_model=RCAReportResponse)
async def get_report(task_id: str):
    """获取 RCA 报告。"""
    task = RCATaskRepository.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    report = RCAReportRepository.get(task_id)

    import json

    final_report = json.loads(report["final_report"]) if report and report.get("final_report") else None
    evidence = []
    if final_report and isinstance(final_report.get("evidence"), list):
        evidence = final_report["evidence"]
    elif report and report.get("evidence_summary"):
        evidence = json.loads(report["evidence_summary"])

    return RCAReportResponse(
        task_id=task_id,
        status=TaskStatus(task["status"]),
        anomaly_type=task["anomaly_type"],
        description=task["description"],
        root_cause=report.get("root_cause") if report else None,
        hypotheses=json.loads(report["hypotheses"]) if report and report.get("hypotheses") else [],
        evidence=evidence,
        confidence=task.get("confidence", 0.0),
        reflection_rounds=task.get("reflection_rounds", 0),
        final_report=final_report,
        created_at=task.get("created_at"),
        completed_at=task.get("completed_at"),
    )


@router.get("/tasks/{task_id}", response_model=RCATaskResponse)
async def get_task(task_id: str):
    """获取 RCA 任务状态。"""
    task = RCATaskRepository.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    return RCATaskResponse(
        task_id=task_id,
        status=TaskStatus(task["status"]),
        anomaly_type=task["anomaly_type"],
        description=task["description"],
        confidence=task.get("confidence", 0.0),
        created_at=task.get("created_at"),
        completed_at=task.get("completed_at"),
    )


# ═══════════════════════════════════════════════════════════════
# SSE 步骤事件流
# ═══════════════════════════════════════════════════════════════

_HEARTBEAT_INTERVAL = 15  # 心跳间隔（秒）
_POLL_INTERVAL = 1        # DB 轮询间隔（秒）


def _format_sse(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    """将事件格式化为 SSE 帧。

    Args:
        event: SSE 事件类型（step/done/error/heartbeat）
        data: 事件数据字典
        event_id: 可选的事件 ID（seq 号）

    Returns:
        符合 SSE 规范的帧字符串，以 \\n\\n 结尾。
    """
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    lines.append("")  # 空行作为帧分隔符
    return "\n".join(lines) + "\n"


async def _event_stream(task_id: str, after: int) -> AsyncGenerator[str, None]:
    """SSE 事件流异步生成器。

    1. 重放 DB 中 seq > after 的所有已有事件
    2. 进入轮询循环：每 _POLL_INTERVAL 秒查询新事件
    3. 每 _HEARTBEAT_INTERVAL 秒发送心跳
    4. 任务终态（completed/failed）且无新事件时发送终端帧并关闭

    Args:
        task_id: 任务 ID
        after: 起始 seq（只返回 seq > after 的事件）
    """
    last_seq = after
    last_heartbeat = 0.0

    while True:
        # 查询任务状态
        task = RCATaskRepository.get(task_id)
        if task is None:
            break

        # 查询新事件
        new_events = StepEventRepository.list_events(task_id, after_seq=last_seq)
        for evt in new_events:
            seq = evt["seq"]
            last_seq = max(last_seq, seq)
            # 构建事件数据（不含大字段，仅关键信息）
            event_data: dict[str, Any] = {
                "task_id": evt["task_id"],
                "seq": seq,
                "node_name": evt["node_name"],
                "event_type": evt["event_type"],
                "status": evt["status"],
                "title": evt["title"],
                "summary": evt.get("summary"),
                "detail": evt.get("detail"),
                "detail_json": evt.get("detail_json"),
                "created_at": evt.get("created_at"),
            }
            yield _format_sse("step", event_data, event_id=seq)

        # 检查终端状态
        status = task["status"]
        is_terminal = status in ("completed", "failed")
        has_new_events = len(new_events) > 0

        if is_terminal and not has_new_events:
            # 发送终端帧
            terminal_event = "done" if status == "completed" else "error"
            terminal_data = {
                "task_id": task_id,
                "status": status,
            }
            yield _format_sse(terminal_event, terminal_data)
            break

        # 心跳
        now = asyncio.get_event_loop().time()
        if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
            last_heartbeat = now
            yield _format_sse("heartbeat", {"task_id": task_id})

        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str, request: Request, after: int = 0):
    """SSE 步骤事件流端点。

    返回 text/event-stream，实时推送 RCA 工作流执行进度。

    - `after` 查询参数：只返回 seq > after 的事件（默认 0）
    - `Last-Event-ID` 请求头：当 after=0 时作为回退值
    """
    # 验证任务存在
    task = RCATaskRepository.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")

    # Last-Event-ID 回退
    if after == 0:
        last_event_id = request.headers.get("Last-Event-ID")
        if last_event_id is not None:
            try:
                after = int(last_event_id)
            except (ValueError, TypeError):
                after = 0

    return StreamingResponse(
        _event_stream(task_id, after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

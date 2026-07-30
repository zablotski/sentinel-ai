import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from app.agents import graph as graph_runtime

logger = logging.getLogger("sentinel.history")
router = APIRouter()


def _serialize_state_snapshot(state: Any) -> dict[str, Any]:
    configurable = {}
    if state.config and isinstance(state.config, dict):
        configurable = state.config.get("configurable") or {}

    checkpoint_id = configurable.get("checkpoint_id")
    next_node = state.next
    if isinstance(next_node, tuple):
        next_node = list(next_node)

    return {
        "checkpoint_id": checkpoint_id,
        "next_node": next_node,
        "values": state.values if isinstance(state.values, dict) else {},
    }


@router.get("/audit/{thread_id}/history")
async def get_audit_thread_history(thread_id: str):
    if not thread_id or not thread_id.strip():
        raise HTTPException(status_code=400, detail="thread_id is required")

    if graph_runtime.app_graph is None:
        raise HTTPException(
            status_code=503,
            detail="Audit graph is not initialized. Checkpointer startup may have failed.",
        )

    normalized_thread_id = thread_id.strip()
    config = {"configurable": {"thread_id": normalized_thread_id}}
    history_log: list[dict[str, Any]] = []

    try:
        async for state in graph_runtime.app_graph.aget_state_history(config):
            history_log.append(_serialize_state_snapshot(state))
    except Exception as err:
        logger.exception(
            "Failed to load checkpoint history for thread_id=%s",
            normalized_thread_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load checkpoint history: {err}",
        ) from err

    if not history_log:
        raise HTTPException(
            status_code=404,
            detail=f"No checkpoint history found for thread_id '{normalized_thread_id}'",
        )

    logger.info(
        "Returned %d checkpoint(s) for thread_id=%s",
        len(history_log),
        normalized_thread_id,
    )

    return {
        "thread_id": normalized_thread_id,
        "checkpoint_count": len(history_log),
        "history": history_log,
    }

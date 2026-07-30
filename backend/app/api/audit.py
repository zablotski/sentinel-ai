import logging
import uuid
from typing import Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.agents import graph as graph_runtime

logger = logging.getLogger("sentinel.audit")
router = APIRouter()


class PackageJsonPayload(BaseModel):
    name: Optional[str] = None
    version: Optional[str] = None
    dependencies: Dict[str, str] = Field(default_factory=dict)
    devDependencies: Dict[str, str] = Field(default_factory=dict)


def _resolve_thread_id(header_thread_id: Optional[str]) -> str:
    if header_thread_id and header_thread_id.strip():
        return header_thread_id.strip()
    return str(uuid.uuid4())


@router.post("/audit")
async def trigger_dependency_audit(
    payload: PackageJsonPayload,
    x_thread_id: Optional[str] = Header(default=None, alias="X-Thread-Id"),
):
    if graph_runtime.app_graph is None:
        raise HTTPException(
            status_code=503,
            detail="Audit graph is not initialized. Checkpointer startup may have failed.",
        )

    raw_package_list = payload.model_dump()
    dep_count = len(payload.dependencies or {})
    dev_dep_count = len(payload.devDependencies or {})
    thread_id = _resolve_thread_id(x_thread_id)

    logger.info(
        "Incoming audit request (thread_id=%s): %d dependencies, %d devDependencies",
        thread_id,
        dep_count,
        dev_dep_count,
    )

    try:
        initial_state = {
            "raw_package_list": raw_package_list,
            "packages_to_analyze": [],
            "analyzed_dependencies": [],
            "global_verdict": "",
            "global_summary": "",
            "security_compromised": False,
        }

        config = {"configurable": {"thread_id": thread_id}}

        logger.info(
            "Starting LangGraph audit pipeline for thread_id=%s "
            "(guardrail -> scout -> parallel fan-out -> lawyer/critic -> judge)",
            thread_id,
        )
        final_state = await graph_runtime.app_graph.ainvoke(initial_state, config)

        if final_state.get("security_compromised"):
            logger.warning(
                "Audit blocked by guardrail for thread_id=%s — security compromise detected",
                thread_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Security Exception: malicious prompt injection detected.",
            )

        results = final_state.get("analyzed_dependencies") or []
        global_verdict = final_state.get("global_verdict", "")
        global_summary = final_state.get("global_summary", "")
        verdict_summary = [
            f"{r.get('package_name', '?')}={r.get('verdict', 'PENDING')}"
            for r in results
        ]
        logger.info(
            "Audit pipeline finished (thread_id=%s): %s | global=%s",
            thread_id,
            ", ".join(verdict_summary) if verdict_summary else "no results",
            global_verdict or "n/a",
        )

        return {
            "status": "success",
            "thread_id": thread_id,
            "global_verdict": global_verdict,
            "global_summary": global_summary,
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Audit request failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail=str(e))

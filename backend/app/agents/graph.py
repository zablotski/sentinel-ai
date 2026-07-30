import logging
import time
from pathlib import Path
from typing import Any, Dict, Literal

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from app.agents.state import AgentState, PackageState, dict_to_package_state, package_state_to_result
from app.agents.nodes.guardrail import guardrail_node
from app.agents.nodes.scout import scout_node
from app.agents.nodes.judge import judge_node
from app.agents.subgraph_builder import compiled_heavy_subgraph, compiled_standard_subgraph
from app.core.config import configure_observability
from app.core.models import ModelRegistry
from app.services.llm_service import get_active_provider
from app.core.terminal import CYAN, GREEN, MAGENTA, NC, YELLOW
from app.services.qdrant_service import get_cached_verdict, save_verdict_to_cache
from app.services.token_service import count_package_context_tokens

configure_observability()
logger = logging.getLogger("sentinel.graph")

TOKEN_ROUTING_THRESHOLD = 1500


def route_after_guardrail(state: AgentState) -> Literal["blocked", "continue"]:
    if state.get("security_compromised"):
        print(f"{CYAN}[GRAPH] Guardrail blocked — bypassing scout and parallel audit{NC}", flush=True)
        logger.warning("Graph route: security block — terminating pipeline")
        return "blocked"
    return "continue"


async def _run_audit_bridge(
    state: PackageState,
    subgraph: Any,
    tier_label: str,
) -> Dict[str, Any]:
    package_name = state.get("package_name", "unknown")
    license_name = state.get("license", "UNKNOWN")

    cached = await get_cached_verdict(package_name, license_name)
    if cached:
        print(
            f"{CYAN}[CACHE HIT/{tier_label}] Bypassing LLM for {package_name}{NC}",
            flush=True,
        )
        cached_result = package_state_to_result(state)
        cached_verdict = cached.get("verdict", "")
        if cached_verdict in ("SAFE", "FORBIDDEN"):
            cached_result["verdict"] = cached_verdict
        cached_result["reasoning"] = cached.get("reasoning", "")
        return {"analyzed_dependencies": [cached_result]}

    print(
        f"{CYAN}[CACHE MISS/{tier_label}] Invoking {tier_label} subgraph for {package_name}{NC}",
        flush=True,
    )

    cycle_start = time.perf_counter()
    final_package_state = await subgraph.ainvoke(state)
    cycle_duration = time.perf_counter() - cycle_start

    print(
        f"{YELLOW}[TELEMETRY/{tier_label}] Package '{package_name}' completed Actor-Critic "
        f"cycle in {cycle_duration:.2f} seconds.{NC}",
        flush=True,
    )

    result = package_state_to_result(final_package_state)

    await save_verdict_to_cache(
        package_name,
        license_name,
        result.get("verdict", "PENDING"),
        result.get("reasoning", ""),
    )

    print(
        f"{GREEN}[GRAPH/{tier_label}] Fan-in complete for {package_name}{NC}",
        flush=True,
    )
    return {"analyzed_dependencies": [result]}


async def audit_standard_package_node(state: PackageState) -> Dict[str, Any]:
    package_name = state.get("package_name", "unknown")
    token_count = count_package_context_tokens(dict(state))
    provider = get_active_provider()
    standard_model = ModelRegistry.model_for_role(provider, "standard")
    print(
        f"{GREEN}[ROUTING] {package_name} -> STANDARD tier "
        f"({standard_model}, {token_count} tokens){NC}",
        flush=True,
    )
    return await _run_audit_bridge(state, compiled_standard_subgraph, "STANDARD")


async def audit_heavy_package_node(state: PackageState) -> Dict[str, Any]:
    package_name = state.get("package_name", "unknown")
    token_count = count_package_context_tokens(dict(state))
    provider = get_active_provider()
    heavy_model = ModelRegistry.model_for_role(provider, "heavy")
    print(
        f"{MAGENTA}[ROUTING] {package_name} -> HEAVY tier "
        f"({heavy_model}, {token_count} tokens){NC}",
        flush=True,
    )
    return await _run_audit_bridge(state, compiled_heavy_subgraph, "HEAVY")


def parallel_fan_out(state: AgentState) -> list[Send] | str:
    packages = state.get("packages_to_analyze") or []

    if not packages:
        print(
            f"{CYAN}[GRAPH] Scout short-circuit — skipping fan-out and parallel audit{NC}",
            flush=True,
        )
        return "finish_early"

    sends: list[Send] = []
    standard_count = 0
    heavy_count = 0

    for package in packages:
        package_state = dict_to_package_state(package)
        token_count = count_package_context_tokens(package)
        package_name = package.get("package_name", "unknown")

        if token_count > TOKEN_ROUTING_THRESHOLD:
            sends.append(Send("audit_heavy_package_node", package_state))
            heavy_count += 1
            logger.info(
                "Token routing: %s -> HEAVY (%d tokens)",
                package_name,
                token_count,
            )
        else:
            sends.append(Send("audit_standard_package_node", package_state))
            standard_count += 1
            logger.info(
                "Token routing: %s -> STANDARD (%d tokens)",
                package_name,
                token_count,
            )

    print(
        f"{GREEN}[GRAPH] Fan-out: {len(sends)} branch(es) "
        f"({standard_count} standard, {heavy_count} heavy){NC}",
        flush=True,
    )
    return sends


workflow = StateGraph(AgentState)
workflow.add_node("guardrail", guardrail_node)
workflow.add_node("scout", scout_node)
workflow.add_node("audit_standard_package_node", audit_standard_package_node)
workflow.add_node("audit_heavy_package_node", audit_heavy_package_node)
workflow.add_node("judge", judge_node)

workflow.set_entry_point("guardrail")
workflow.add_conditional_edges(
    "guardrail",
    route_after_guardrail,
    {
        "blocked": END,
        "continue": "scout",
    },
)
workflow.add_conditional_edges(
    "scout",
    parallel_fan_out,
    {
        "audit_standard_package_node": "audit_standard_package_node",
        "audit_heavy_package_node": "audit_heavy_package_node",
        "finish_early": END,
    },
)
workflow.add_edge("audit_standard_package_node", "judge")
workflow.add_edge("audit_heavy_package_node", "judge")
workflow.add_edge("judge", END)

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"
SENTINEL_STATE_DB_PATH = DATA_DIR / "sentinel_state.db"

memory: AsyncSqliteSaver | MemorySaver | None = None
_saver_context_manager = None
_app_graph_ci = False
app_graph = None


def _ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return SENTINEL_STATE_DB_PATH


def get_executable_graph(is_ci: bool = False, checkpointer: Any | None = None):
    """Compile the audit workflow with an in-memory (CI) or persistent checkpointer."""
    if is_ci:
        saver = checkpointer if checkpointer is not None else MemorySaver()
        return workflow.compile(checkpointer=saver)

    if checkpointer is None:
        raise ValueError("checkpointer is required when is_ci is False")

    return workflow.compile(checkpointer=checkpointer)


async def activate_checkpointer(is_ci: bool | None = None) -> None:
    global memory, app_graph, _saver_context_manager, _app_graph_ci

    if app_graph is not None:
        return

    from app.core.config import is_ci_environment
    from app.services.qdrant_service import set_ci_mode

    ci = is_ci_environment() if is_ci is None else is_ci

    if ci:
        set_ci_mode(True)
        memory = MemorySaver()
        app_graph = get_executable_graph(is_ci=True, checkpointer=memory)
        _app_graph_ci = True
        logger.info("Stateless CI graph compiled with MemorySaver")
        return

    set_ci_mode(False)
    db_path = _ensure_data_dir()
    _saver_context_manager = AsyncSqliteSaver.from_conn_string(str(db_path))
    memory = await _saver_context_manager.__aenter__()
    app_graph = get_executable_graph(is_ci=False, checkpointer=memory)
    _app_graph_ci = False
    logger.info("Persistent checkpointer activated: %s", db_path)


async def deactivate_checkpointer() -> None:
    global memory, app_graph, _saver_context_manager, _app_graph_ci

    from app.services.qdrant_service import set_ci_mode

    if _app_graph_ci:
        memory = None
        app_graph = None
        _app_graph_ci = False
        set_ci_mode(False)
        logger.info("CI in-memory checkpointer deactivated")
        return

    if _saver_context_manager is not None:
        await _saver_context_manager.__aexit__(None, None, None)

    memory = None
    app_graph = None
    _saver_context_manager = None
    set_ci_mode(False)
    logger.info("Persistent checkpointer deactivated")

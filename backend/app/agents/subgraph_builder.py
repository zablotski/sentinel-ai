import logging
from typing import Any, Callable, Dict, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.agents.nodes.critic import run_critic_review
from app.agents.nodes.lawyer import run_lawyer_audit
from app.agents.state import PackageState
from app.core.models import ModelRegistry
from app.core.terminal import CYAN, GREEN, NC
from app.services.llm_service import get_active_provider, get_node_llm

logger = logging.getLogger("sentinel.subgraph")


def route_local_critic(state: PackageState) -> Literal["retry_lawyer", "finish"]:
    feedback = state.get("critic_feedback", "")
    attempts = state.get("correction_attempts", 0)
    package_name = state.get("package_name", "unknown")

    if feedback != "APPROVED" and attempts < 3:
        print(
            f"{CYAN}[SUBGRAPH] {package_name}: retry_lawyer (attempt {attempts}/3){NC}",
            flush=True,
        )
        logger.info("Subgraph route: retry_lawyer for %s", package_name)
        return "retry_lawyer"

    print(f"{GREEN}[SUBGRAPH] {package_name}: lawyer-critic loop complete{NC}", flush=True)
    logger.info("Subgraph route: finish for %s", package_name)
    return "finish"


def create_lawyer_node(lawyer_llm: BaseChatModel, tier_label: str) -> Callable:
    async def lawyer_node(state: PackageState) -> Dict[str, Any]:
        return await run_lawyer_audit(state, lawyer_llm, tier_label=tier_label)

    return lawyer_node


def create_critic_node(critic_llm: BaseChatModel, tier_label: str) -> Callable:
    async def critic_node(state: PackageState) -> Dict[str, Any]:
        return await run_critic_review(state, critic_llm, tier_label=tier_label)

    return critic_node


def build_actor_critic_subgraph(lawyer_role: str, critic_role: str, tier_label: str):
    provider = get_active_provider()
    lawyer_model = ModelRegistry.model_for_role(provider, lawyer_role)
    critic_model = ModelRegistry.model_for_role(provider, critic_role)
    lawyer_llm = get_node_llm(lawyer_role)
    critic_llm = get_node_llm(critic_role)

    subgraph_workflow = StateGraph(PackageState)
    subgraph_workflow.add_node("lawyer", create_lawyer_node(lawyer_llm, tier_label))
    subgraph_workflow.add_node("critic", create_critic_node(critic_llm, tier_label))
    subgraph_workflow.add_edge(START, "lawyer")
    subgraph_workflow.add_edge("lawyer", "critic")
    subgraph_workflow.add_conditional_edges(
        "critic",
        route_local_critic,
        {
            "retry_lawyer": "lawyer",
            "finish": END,
        },
    )

    logger.info(
        "Compiled %s subgraph (lawyer=%s, critic=%s)",
        tier_label,
        lawyer_model,
        critic_model,
    )
    return subgraph_workflow.compile()


compiled_standard_subgraph = build_actor_critic_subgraph(
    lawyer_role="standard",
    critic_role="standard",
    tier_label="STANDARD",
)

compiled_heavy_subgraph = build_actor_critic_subgraph(
    lawyer_role="heavy",
    critic_role="standard",
    tier_label="HEAVY",
)

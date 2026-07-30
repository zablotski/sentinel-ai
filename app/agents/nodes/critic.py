import logging
from typing import Any, Dict, Literal

from langchain_openai import ChatOpenAI

from app.agents.state import PackageState
from app.core.terminal import CYAN, GREEN, RED, YELLOW, NC
from app.services.llm_service import get_node_llm

logger = logging.getLogger("sentinel.critic")


def _extract_reject_reason(feedback: str) -> str:
    upper = feedback.upper()
    reject_index = upper.find("REJECT:")
    if reject_index == -1:
        return feedback.strip()
    return feedback[reject_index:].strip()


def _normalize_structured_verdict(
    verdict: str,
) -> Literal["SAFE", "FORBIDDEN", "REVIEW_REQUIRED"] | None:
    if verdict in ("SAFE", "FORBIDDEN", "REVIEW_REQUIRED"):
        return verdict
    return None


def _build_critic_prompt(proposed_verdict: str) -> str:
    return (
        "You are a lightweight gatekeeper. Do NOT debate legal philosophy.\n"
        f"The Lawyer already issued this final verdict: {proposed_verdict}\n\n"
        "Rules:\n"
        "- If the final verdict is SAFE, FORBIDDEN, or REVIEW_REQUIRED, reply exactly: APPROVED\n"
        "- Reply REJECT only if the structured verdict field contradicts the reasoning.\n\n"
        "Reply with exactly one line: APPROVED or REJECT: <short reason>"
    )


def _critic_fast_approve(proposed_verdict: str) -> Dict[str, Any] | None:
    normalized = _normalize_structured_verdict(proposed_verdict)
    if normalized is None:
        return None

    return {
        "critic_feedback": "APPROVED",
        "verdict": normalized,
    }


async def run_critic_review(
    state: PackageState,
    llm: ChatOpenAI,
    tier_label: str = "STANDARD",
) -> Dict[str, Any]:
    package_name = state.get("package_name", "unknown")
    proposed_verdict = state.get("verdict", "PENDING")
    attempts = state.get("correction_attempts", 0)
    structured_verdict = _normalize_structured_verdict(proposed_verdict)

    print(
        f"{YELLOW}[CRITIC/{tier_label}] Reviewing {package_name} "
        f"(structured verdict: {proposed_verdict}){NC}",
        flush=True,
    )

    fast_path = _critic_fast_approve(proposed_verdict)
    if fast_path is not None:
        print(
            f"{GREEN}[CRITIC/{tier_label}] Outcome: APPROVED — "
            f"trusting structured Lawyer verdict ({fast_path['verdict']}){NC}",
            flush=True,
        )
        logger.info("Critic fast-approved %s as %s", package_name, fast_path["verdict"])
        return fast_path

    if attempts >= 3:
        fallback_verdict = structured_verdict or "FORBIDDEN"
        print(
            f"{GREEN}[CRITIC/{tier_label}] Max attempts reached — "
            f"preserving verdict ({fallback_verdict}){NC}",
            flush=True,
        )
        return {
            "critic_feedback": "APPROVED",
            "verdict": fallback_verdict,
        }

    prompt = _build_critic_prompt(structured_verdict or "FORBIDDEN")

    print(
        f"{CYAN}[CRITIC/{tier_label}] Waiting for LLM gatekeeper response for {package_name}...{NC}",
        flush=True,
    )

    try:
        res = await llm.ainvoke([{"role": "user", "content": prompt}])
        feedback = res.content.strip() if res.content else ""
    except Exception as err:
        logger.error("Critic LLM call failed for %s: %s", package_name, err, exc_info=True)
        print(
            f"{RED}[CRITIC/{tier_label}] Model connection failure for {package_name}: {err}{NC}",
            flush=True,
        )
        return {
            "critic_feedback": "APPROVED",
            "verdict": structured_verdict or "FORBIDDEN",
        }

    if "REJECT:" in feedback.upper() and attempts < 3:
        reason = _extract_reject_reason(feedback)
        reject_feedback = (
            reason if reason.upper().startswith("REJECT:") else f"REJECT: {reason}"
        )
        print(f"{RED}[CRITIC/{tier_label}] Outcome: {reject_feedback}{NC}", flush=True)
        return {
            "critic_feedback": reject_feedback,
            "correction_attempts": attempts + 1,
            "verdict": structured_verdict or proposed_verdict,
        }

    print(f"{GREEN}[CRITIC/{tier_label}] Outcome: APPROVED — {package_name}{NC}", flush=True)
    return {
        "critic_feedback": "APPROVED",
        "verdict": structured_verdict or "FORBIDDEN",
    }


async def critic_node(state: PackageState) -> Dict[str, Any]:
    return await run_critic_review(state, get_node_llm("standard"), tier_label="STANDARD")

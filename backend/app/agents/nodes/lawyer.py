import json
import logging
from typing import Any, Dict, List, Literal

from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from app.agents.state import PackageState
from app.core.config import SentinelConfig, load_sentinel_config
from app.core.terminal import CYAN, GREEN, MAGENTA, RED, YELLOW, NC
from app.services.llm_service import get_node_llm

logger = logging.getLogger("sentinel.lawyer")

LawyerVerdict = Literal["SAFE", "FORBIDDEN", "REVIEW_REQUIRED"]


class LawyerAuditResponse(BaseModel):
    verdict: LawyerVerdict = Field(
        description=(
            "Compliance verdict: SAFE, FORBIDDEN, or REVIEW_REQUIRED per corporate policy."
        ),
    )
    reasoning: str = Field(
        description="Detailed internal compliance engineering trace and justification.",
    )


def _format_spdx_list(spdx_ids: list[str]) -> str:
    if not spdx_ids:
        return "  (none configured)"
    return "\n".join(f"  - {spdx}" for spdx in spdx_ids)


def build_lawyer_system_prompt(config: SentinelConfig) -> str:
    policy = config.policy
    return (
        "You are an expert Software Security and Legal Compliance Officer.\n"
        f"Corporate license policy version: {config.version}\n\n"
        "Analyze the LICENSE EVIDENCE in the user message against the SPDX lists below.\n"
        "Return JSON with exactly two top-level keys: verdict and reasoning.\n"
        "Do not nest fields inside audit or other wrapper objects.\n"
        "reasoning must be a single string paragraph.\n\n"
        "VERDICT RULES:\n"
        "- SAFE: Use when the package SPDX identifier (or license evidence) matches an "
        "entry in ALLOWED and does not trigger FORBIDDEN or REVIEW_REQUIRED rules.\n"
        "- FORBIDDEN: Use when the SPDX identifier matches FORBIDDEN, or license evidence "
        "shows strong copyleft, AGPL, or commercial-use restrictions incompatible with policy.\n"
        "- REVIEW_REQUIRED: Use when the SPDX identifier matches REVIEW_REQUIRED, or evidence "
        "is ambiguous, weak copyleft, or needs human escalation before production use.\n\n"
        f"ALLOWED (yield SAFE when matched and evidence agrees):\n"
        f"{_format_spdx_list(policy.allowed)}\n\n"
        f"FORBIDDEN (yield FORBIDDEN when matched or clearly indicated by evidence):\n"
        f"{_format_spdx_list(policy.forbidden)}\n\n"
        f"REVIEW_REQUIRED (yield REVIEW_REQUIRED when matched unless evidence clearly "
        f"supports SAFE or FORBIDDEN):\n"
        f"{_format_spdx_list(policy.review_required)}\n\n"
        "verdict must be exactly one of: SAFE, FORBIDDEN, REVIEW_REQUIRED."
    )


def build_lawyer_messages(
    config: SentinelConfig,
    license_text: str,
    critic_feedback: str = "",
) -> List[Dict[str, str]]:
    user_content = f"LICENSE EVIDENCE:\n{license_text}"

    if critic_feedback and critic_feedback != "APPROVED":
        user_content += (
            f"\n\n[CRITICAL FEEDBACK FROM PREVIOUS AUDIT]\n{critic_feedback}\n"
            "Your previous answer was rejected. Fix your logic based on this feedback."
        )

    return [
        {"role": "system", "content": build_lawyer_system_prompt(config)},
        {"role": "user", "content": user_content},
    ]


def audit_response_to_state(response: LawyerAuditResponse) -> Dict[str, str]:
    return {
        "verdict": response.verdict,
        "reasoning": response.reasoning,
    }


def _normalize_audit_payload(payload: dict[str, Any]) -> dict[str, str]:
    nested = payload.get("audit")
    source = nested if isinstance(nested, dict) else payload

    verdict_raw = str(source.get("verdict", "FORBIDDEN")).strip().upper()
    if verdict_raw == "SAFE":
        verdict: LawyerVerdict = "SAFE"
    elif verdict_raw == "REVIEW_REQUIRED":
        verdict = "REVIEW_REQUIRED"
    else:
        verdict = "FORBIDDEN"

    reasoning_raw = source.get("reasoning", "")
    if isinstance(reasoning_raw, list):
        reasoning = " ".join(str(item) for item in reasoning_raw)
    else:
        reasoning = str(reasoning_raw)

    return {"verdict": verdict, "reasoning": reasoning}


def _coerce_lawyer_audit_response(raw_object: Any) -> LawyerAuditResponse:
    if isinstance(raw_object, LawyerAuditResponse):
        return raw_object

    if isinstance(raw_object, dict):
        return LawyerAuditResponse.model_validate(_normalize_audit_payload(raw_object))

    if isinstance(raw_object, str):
        parsed = json.loads(raw_object)
        if isinstance(parsed, dict):
            return LawyerAuditResponse.model_validate(_normalize_audit_payload(parsed))

    raise ValueError(f"Unsupported lawyer structured payload type: {type(raw_object)}")


def _recover_audit_from_parser_error(err: Exception) -> LawyerAuditResponse | None:
    candidate_objects: list[Any] = []

    if isinstance(err, OutputParserException):
        if getattr(err, "llm_output", None):
            candidate_objects.append(err.llm_output)
        if getattr(err, "observation", None):
            candidate_objects.append(err.observation)

    message = str(err)
    start = message.find("{")
    end = message.rfind("}")
    if start >= 0 and end > start:
        try:
            candidate_objects.append(json.loads(message[start : end + 1]))
        except json.JSONDecodeError:
            pass

    for candidate in candidate_objects:
        try:
            return _coerce_lawyer_audit_response(candidate)
        except (ValidationError, ValueError, json.JSONDecodeError):
            continue

    return None


async def invoke_structured_lawyer_audit(
    llm: ChatOpenAI,
    messages: List[Dict[str, str]],
    package_name: str,
) -> LawyerAuditResponse:
    structured_llm = llm.with_structured_output(LawyerAuditResponse, method="json_mode")

    try:
        response = await structured_llm.ainvoke(messages)
        return _coerce_lawyer_audit_response(response)
    except (OutputParserException, ValidationError) as err:
        recovered = _recover_audit_from_parser_error(err)
        if recovered is not None:
            logger.warning(
                "Recovered nested lawyer JSON for %s after parser mismatch.",
                package_name,
            )
            return recovered

        logger.error(
            "Lawyer structured output failed for %s: %s",
            package_name,
            err,
            exc_info=True,
        )
        print(
            f"{RED}[LAWYER] Structured output validation failure for "
            f"{package_name}: {err}{NC}",
            flush=True,
        )
        return LawyerAuditResponse(
            verdict="FORBIDDEN",
            reasoning=f"Lawyer audit failed due to structured output validation error: {err}",
        )
    except Exception as err:
        logger.error(
            "Lawyer model connection failed for %s: %s",
            package_name,
            err,
            exc_info=True,
        )
        print(
            f"{RED}[LAWYER] Model connection failure for {package_name}: {err}{NC}",
            flush=True,
        )
        return LawyerAuditResponse(
            verdict="FORBIDDEN",
            reasoning=f"Lawyer audit failed due to model connection error: {err}",
        )


async def run_lawyer_audit(
    state: PackageState,
    llm: ChatOpenAI,
    tier_label: str = "STANDARD",
) -> Dict[str, Any]:
    package_name = state.get("package_name", "unknown")
    feedback = state.get("critic_feedback", "")
    attempt = state.get("correction_attempts", 0)

    print(
        f"{MAGENTA}[LAWYER/{tier_label}] Auditing {package_name} | attempt {attempt + 1}/3{NC}",
        flush=True,
    )

    license_text = state.get("license_text") or state.get("license") or "UNKNOWN"
    sentinel_config = load_sentinel_config()
    messages = build_lawyer_messages(sentinel_config, license_text, feedback)

    print(
        f"{CYAN}[LAWYER/{tier_label}] Waiting for structured LLM response for {package_name}...{NC}",
        flush=True,
    )

    response = await invoke_structured_lawyer_audit(llm, messages, package_name)
    verdict = response.verdict
    if verdict == "FORBIDDEN":
        verdict_color = RED
    elif verdict == "REVIEW_REQUIRED":
        verdict_color = YELLOW
    else:
        verdict_color = GREEN

    print(
        f"{verdict_color}[LAWYER/{tier_label}] Verdict for {package_name}: {verdict}{NC}",
        flush=True,
    )
    logger.info("Lawyer structured verdict for %s: %s", package_name, verdict)

    return audit_response_to_state(response)


async def lawyer_node(state: PackageState) -> Dict[str, Any]:
    logger.info(
        "Graph node: lawyer — analyzing %s (attempt %d)",
        state.get("package_name", "unknown"),
        state.get("correction_attempts", 0),
    )
    return await run_lawyer_audit(state, get_node_llm("standard"), tier_label="STANDARD")

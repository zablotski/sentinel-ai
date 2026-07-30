import logging
from typing import Any, Dict

from app.agents.state import AgentState
from app.core.terminal import CYAN, GREEN, MAGENTA, NC
from app.services.llm_service import get_node_llm

logger = logging.getLogger("sentinel.judge")

PERMISSIVE_LICENSES = (
    "MIT",
    "Apache-2.0",
    "Apache 2.0",
    "BSD",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "0BSD",
    "Unlicense",
)


def _build_judge_prompt(dependencies: list[dict]) -> str:
    lines = []
    for dep in dependencies:
        name = dep.get("package_name", "unknown")
        version = dep.get("version", "")
        license_name = dep.get("license", "UNKNOWN")
        verdict = dep.get("verdict", "PENDING")
        lines.append(f"- {name}@{version} | license={license_name} | verdict={verdict}")

    dependency_block = "\n".join(lines) if lines else "(no dependencies audited)"

    return (
        "You are the Global Compliance Judge for a corporate software project.\n"
        "Apply the rulebook below exactly. Do not over-analyze standard open-source stacks.\n\n"
        "RULEBOOK:\n"
        "Rule 1: Permissive licenses (MIT, Apache-2.0, BSD-3-Clause, ISC, and similar) "
        "are 100% compatible with each other. If the project contains ONLY permissive "
        "licenses (or UNKNOWN licenses without copyleft evidence), you MUST return:\n"
        "GLOBAL_VERDICT: APPROVED\n\n"
        "Rule 2: You may ONLY output REJECTED_WITH_CONFLICTS if there is a strict "
        "Copyleft license (GPLv2, GPLv3, AGPL, or equivalent) mixed with proprietary, "
        "commercially restricted, or clearly incompatible packages in the same tree.\n\n"
        "Rule 3: Do not invent conflicts. Standard combinations of MIT + Apache + BSD "
        "packages are always APPROVED.\n\n"
        f"DEPENDENCIES:\n{dependency_block}\n\n"
        "Respond in exactly this format (no extra sections):\n"
        "GLOBAL_VERDICT: APPROVED\n"
        "GLOBAL_SUMMARY: <one or two sentences>\n"
        "or\n"
        "GLOBAL_VERDICT: REJECTED_WITH_CONFLICTS\n"
        "GLOBAL_SUMMARY: <one or two sentences>"
    )


def _parse_judge_response(content: str) -> tuple[str, str]:
    global_verdict = "REJECTED_WITH_CONFLICTS"
    global_summary = content.strip()

    for line in content.splitlines():
        upper = line.upper()
        if upper.startswith("GLOBAL_VERDICT:"):
            value = line.split(":", 1)[1].strip().upper()
            if "APPROVED" in value and "REJECTED" not in value:
                global_verdict = "APPROVED"
            else:
                global_verdict = "REJECTED_WITH_CONFLICTS"
        elif upper.startswith("GLOBAL_SUMMARY:"):
            global_summary = line.split(":", 1)[1].strip()

    return global_verdict, global_summary


def _all_permissive_or_unknown(dependencies: list[dict]) -> bool:
    for dep in dependencies:
        license_name = (dep.get("license") or "UNKNOWN").upper()
        if license_name == "UNKNOWN":
            continue
        if not any(perm.upper() in license_name for perm in PERMISSIVE_LICENSES):
            if any(
                marker in license_name
                for marker in ("GPL", "AGPL", "COPYLEFT", "LGPL")
            ):
                return False
    return True


async def judge_node(state: AgentState) -> Dict[str, Any]:
    dependencies = state.get("analyzed_dependencies") or []

    print(f"{MAGENTA}[JUDGE] Starting global license compatibility evaluation{NC}", flush=True)
    logger.info("Judge node: evaluating %d audited dependencies", len(dependencies))

    if not dependencies:
        print(f"{CYAN}[JUDGE] No dependencies to evaluate — defaulting to APPROVED{NC}", flush=True)
        return {
            "global_verdict": "APPROVED",
            "global_summary": "No dependencies were audited.",
        }

    if _all_permissive_or_unknown(dependencies):
        print(
            f"{GREEN}[JUDGE] All licenses permissive or unknown — rule-based APPROVED{NC}",
            flush=True,
        )
        logger.info("Judge: permissive-only tree, skipping LLM over-analysis")
        return {
            "global_verdict": "APPROVED",
            "global_summary": (
                "All audited dependencies use permissive or unknown licenses with no "
                "detected copyleft conflict."
            ),
        }

    prompt = _build_judge_prompt(dependencies)
    response = await get_node_llm("heavy").ainvoke([{"role": "user", "content": prompt}])
    content = response.content.strip() if response.content else ""

    global_verdict, global_summary = _parse_judge_response(content)

    print(
        f"{GREEN}[JUDGE] Finished — global verdict: {global_verdict}{NC}",
        flush=True,
    )
    logger.info("Judge node complete: %s", global_verdict)

    return {
        "global_verdict": global_verdict,
        "global_summary": global_summary,
    }

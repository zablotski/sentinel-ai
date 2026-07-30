#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

from app.core.config import configure_observability, is_ci_environment, load_local_env

load_local_env()
configure_observability()

from app.agents import graph as graph_runtime

logger = logging.getLogger("sentinel.cli")


def _load_package_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def build_markdown_report(final_state: dict[str, Any]) -> str:
    """Build a GitHub-friendly Markdown audit report from graph final state."""
    compromised = bool(final_state.get("security_compromised"))
    global_verdict = str(final_state.get("global_verdict") or "UNKNOWN")
    global_summary = str(final_state.get("global_summary") or "").strip()
    dependencies = final_state.get("analyzed_dependencies") or []

    if compromised:
        status_line = "**Security status:** BLOCKED (prompt injection or policy violation detected)"
        global_line = "**Global verdict:** `403_BLOCKED`"
    else:
        status_line = "**Security status:** OK"
        global_line = f"**Global verdict:** `{global_verdict}`"

    lines = [
        "## Sentinel AI Dependency Audit",
        "",
        status_line,
        global_line,
        "",
    ]

    if global_summary:
        lines.extend(["### Summary", "", global_summary, ""])

    lines.extend(
        [
            "### Package results",
            "",
            "| Package | Version | License | Verdict |",
            "| --- | --- | --- | --- |",
        ]
    )

    if dependencies:
        for dep in dependencies:
            name = dep.get("package_name") or "unknown"
            version = dep.get("version") or "-"
            license_name = dep.get("license") or "UNKNOWN"
            verdict = dep.get("verdict") or "PENDING"
            lines.append(f"| {name} | {version} | {license_name} | {verdict} |")
    else:
        lines.append("| _none audited_ | - | - | - |")

    lines.append("")
    return "\n".join(lines)


def write_github_step_summary(markdown_report: str) -> None:
    summary_path = (os.getenv("GITHUB_STEP_SUMMARY") or "").strip()
    if not summary_path:
        logger.debug("GITHUB_STEP_SUMMARY not set; skipping step summary")
        return

    path = Path(summary_path)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(markdown_report)
            if not markdown_report.endswith("\n"):
                handle.write("\n")
        logger.info("Wrote audit report to GitHub step summary: %s", path)
    except OSError as err:
        logger.warning("Failed to write GitHub step summary (%s): %s", path, err)


def _read_pull_request_number() -> int | None:
    event_name = (os.getenv("GITHUB_EVENT_NAME") or "").strip()
    if event_name != "pull_request":
        return None

    event_path = (os.getenv("GITHUB_EVENT_PATH") or "").strip()
    if not event_path:
        logger.warning("GITHUB_EVENT_NAME=pull_request but GITHUB_EVENT_PATH is unset")
        return None

    try:
        with Path(event_path).open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as err:
        logger.warning("Failed to read GitHub event payload from %s: %s", event_path, err)
        return None

    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        logger.warning("GitHub event payload missing pull_request object")
        return None

    number = pull_request.get("number")
    if isinstance(number, int):
        return number
    if isinstance(number, str) and number.isdigit():
        return int(number)

    logger.warning("GitHub event pull_request.number is missing or invalid")
    return None


def post_pull_request_comment(markdown_report: str) -> None:
    pr_number = _read_pull_request_number()
    if pr_number is None:
        return

    repository = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = (os.getenv("GITHUB_TOKEN") or "").strip()

    if not repository or "/" not in repository:
        logger.warning("GITHUB_REPOSITORY missing or invalid; skipping PR comment")
        return

    if not token:
        logger.warning("GITHUB_TOKEN missing; skipping PR comment")
        return

    url = f"https://api.github.com/repos/{repository}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json={"body": markdown_report},
            timeout=30,
        )
        if response.status_code >= 400:
            logger.warning(
                "GitHub PR comment failed (HTTP %s): %s",
                response.status_code,
                response.text[:500],
            )
            return
        logger.info("Posted audit report as PR comment on #%s", pr_number)
    except requests.RequestException as err:
        logger.warning("GitHub PR comment request failed: %s", err)


def publish_github_report(markdown_report: str) -> None:
    write_github_step_summary(markdown_report)
    post_pull_request_comment(markdown_report)


def resolve_exit_code(final_state: dict[str, Any]) -> int:
    if final_state.get("security_compromised"):
        return 1

    global_verdict = str(final_state.get("global_verdict") or "").upper()
    if global_verdict == "REJECTED_WITH_CONFLICTS":
        return 1

    for dep in final_state.get("analyzed_dependencies") or []:
        verdict = str(dep.get("verdict") or "").upper()
        if verdict == "FORBIDDEN":
            return 1

    return 0


async def run_audit(package_json_path: Path) -> tuple[dict[str, Any], str]:
    payload = _load_package_json(package_json_path)
    ci = is_ci_environment()
    await graph_runtime.activate_checkpointer(is_ci=ci)

    if graph_runtime.app_graph is None:
        raise RuntimeError("Audit graph failed to initialize")

    initial_state = {
        "raw_package_list": payload,
        "packages_to_analyze": [],
        "analyzed_dependencies": [],
        "global_verdict": "",
        "global_summary": "",
        "security_compromised": False,
    }
    thread_id = f"cli-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = await graph_runtime.app_graph.ainvoke(initial_state, config)
    finally:
        await graph_runtime.deactivate_checkpointer()

    report = build_markdown_report(final_state)
    return final_state, report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sentinel AI dependency audit CLI")
    parser.add_argument(
        "--package-json",
        default="package.json",
        help="Path to package.json to audit (default: package.json)",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write the Markdown report locally",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    package_path = Path(args.package_json).expanduser().resolve()

    if not package_path.is_file():
        logger.error("package.json not found: %s", package_path)
        return 1

    try:
        final_state, report = asyncio.run(run_audit(package_path))
    except Exception as err:
        logger.exception("Audit failed: %s", err)
        failure_report = f"## Sentinel AI Dependency Audit\n\n**Audit failed:** `{err}`\n"
        publish_github_report(failure_report)
        return 1

    print(report)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.write_text(report, encoding="utf-8")
        logger.info("Wrote report to %s", out_path)

    publish_github_report(report)
    return resolve_exit_code(final_state)


if __name__ == "__main__":
    sys.exit(main())

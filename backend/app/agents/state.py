import operator
from typing import Annotated, Any, TypedDict


class PackageState(TypedDict):
    package_name: str
    version: str
    license: str
    license_text: str
    vulnerabilities: list[dict[str, Any]]
    verdict: str
    reasoning: str
    critic_feedback: str  # Single flat string; overwritten each turn (no message history)
    correction_attempts: int


class AgentState(TypedDict):
    raw_package_list: dict
    packages_to_analyze: list[dict]
    analyzed_dependencies: Annotated[list[dict], operator.add]
    global_verdict: str
    global_summary: str
    security_compromised: bool


def package_state_to_result(state: PackageState) -> dict:
    return {
        "package_name": state.get("package_name", ""),
        "version": state.get("version", ""),
        "license": state.get("license", "UNKNOWN"),
        "license_text": state.get("license_text", ""),
        "vulnerabilities": state.get("vulnerabilities") or [],
        "verdict": state.get("verdict", "PENDING"),
        "reasoning": state.get("reasoning", ""),
    }


def dict_to_package_state(package: dict) -> PackageState:
    return {
        "package_name": package.get("package_name", ""),
        "version": package.get("version", ""),
        "license": package.get("license", "UNKNOWN"),
        "license_text": package.get("license_text", ""),
        "vulnerabilities": package.get("vulnerabilities") or [],
        "verdict": package.get("verdict", "PENDING"),
        "reasoning": package.get("reasoning", ""),
        "critic_feedback": "",
        "correction_attempts": 0,
    }

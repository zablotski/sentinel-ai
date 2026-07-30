import logging
from typing import Any, Dict

import httpx

from app.agents.state import AgentState
from app.core.terminal import CYAN, GREEN, NC

logger = logging.getLogger("sentinel.scout")

NPM_REGISTRY_TIMEOUT_SECONDS = 5.0


def _parse_npm_license(metadata: dict) -> str:
    license_field = metadata.get("license")

    if isinstance(license_field, str) and license_field.strip():
        return license_field.strip()

    if isinstance(license_field, dict):
        license_type = license_field.get("type") or license_field.get("name")
        if isinstance(license_type, str) and license_type.strip():
            return license_type.strip()

    licenses_list = metadata.get("licenses")
    if isinstance(licenses_list, list) and licenses_list:
        first_entry = licenses_list[0]
        if isinstance(first_entry, dict):
            license_type = first_entry.get("type") or first_entry.get("name")
            if isinstance(license_type, str) and license_type.strip():
                return license_type.strip()
        if isinstance(first_entry, str) and first_entry.strip():
            return first_entry.strip()

    return "UNKNOWN"


async def _fetch_package_metadata(
    client: httpx.AsyncClient,
    package_name: str,
) -> tuple[str, str]:
    url = f"https://registry.npmjs.org/{package_name}/latest"
    response = await client.get(url)
    response.raise_for_status()
    data = response.json()
    license_value = _parse_npm_license(data)
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        version = ""
    return license_value, version


async def scout_node(state: AgentState) -> Dict[str, Any]:
    print(f"{CYAN}[SCOUT] Starting package.json ingestion...{NC}", flush=True)

    raw_package_list = state.get("raw_package_list") or {}
    dependencies = raw_package_list.get("dependencies") or {}
    dev_dependencies = raw_package_list.get("devDependencies") or {}

    if not isinstance(dependencies, dict):
        dependencies = {}
    if not isinstance(dev_dependencies, dict):
        dev_dependencies = {}

    merged: Dict[str, str] = {**dependencies, **dev_dependencies}
    dep_count = len(dependencies)
    dev_dep_count = len(dev_dependencies)

    print(
        f"{GREEN}[SCOUT] Found {len(merged)} dependencies "
        f"({dep_count} dependencies + {dev_dep_count} devDependencies){NC}",
        flush=True,
    )

    if not merged:
        print(
            f"{GREEN}[SCOUT] Empty dependency tree — short-circuiting to APPROVED{NC}",
            flush=True,
        )
        logger.info("Scout: no dependencies found, returning automatic compliance")
        return {
            "packages_to_analyze": [],
            "global_verdict": "APPROVED",
            "global_summary": "No dependencies found in the project. Automatically compliant.",
        }

    packages_to_analyze: list[dict] = []

    async with httpx.AsyncClient(timeout=NPM_REGISTRY_TIMEOUT_SECONDS) as client:
        for package_name, version_spec in merged.items():
            if not package_name:
                continue

            manifest_version = str(version_spec) if version_spec is not None else ""
            license_value = "UNKNOWN"
            resolved_version = manifest_version

            try:
                license_value, registry_version = await _fetch_package_metadata(
                    client, package_name
                )
                if registry_version:
                    resolved_version = registry_version

                print(
                    f"{GREEN}[SCOUT] Fetched {package_name}@{resolved_version} "
                    f"— license: {license_value}{NC}",
                    flush=True,
                )
                logger.info(
                    "Scout fetched NPM metadata: %s@%s (license=%s)",
                    package_name,
                    resolved_version,
                    license_value,
                )
            except httpx.HTTPStatusError as err:
                if err.response.status_code == 404:
                    print(
                        f"{CYAN}[SCOUT] {package_name} not found on NPM — license: UNKNOWN{NC}",
                        flush=True,
                    )
                    logger.warning("Scout: package not found on NPM: %s", package_name)
                else:
                    print(
                        f"{CYAN}[SCOUT] NPM HTTP error for {package_name} "
                        f"({err.response.status_code}) — license: UNKNOWN{NC}",
                        flush=True,
                    )
                    logger.warning(
                        "Scout: NPM HTTP %s for %s",
                        err.response.status_code,
                        package_name,
                    )
            except (httpx.TimeoutException, httpx.RequestError) as err:
                print(
                    f"{CYAN}[SCOUT] NPM request failed for {package_name} "
                    f"({type(err).__name__}) — license: UNKNOWN{NC}",
                    flush=True,
                )
                logger.warning("Scout: NPM request failed for %s: %s", package_name, err)
            except Exception as err:
                print(
                    f"{CYAN}[SCOUT] Unexpected error for {package_name} "
                    f"— license: UNKNOWN{NC}",
                    flush=True,
                )
                logger.exception("Scout: unexpected error fetching %s", package_name)

            entry = {
                "package_name": package_name,
                "version": resolved_version,
                "license": license_value,
                "license_text": "",
                "vulnerabilities": [],
                "verdict": "PENDING",
                "reasoning": "",
            }
            packages_to_analyze.append(entry)

    print(
        f"{CYAN}[SCOUT] Finished ingestion — {len(packages_to_analyze)} package(s) queued for parallel audit{NC}",
        flush=True,
    )

    return {"packages_to_analyze": packages_to_analyze}

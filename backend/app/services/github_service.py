import base64
import logging
import re

import httpx

logger = logging.getLogger("sentinel.github")


async def get_license_from_github(package_name: str) -> tuple[str | None, str | None]:
    """Return (spdx_id, license_text) from the package's GitHub repo, or (None, None)."""
    npm_url = f"https://registry.npmjs.org/{package_name}/latest"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(npm_url)
            repo_data = res.json().get("repository", {})
            url = repo_data.get("url", "") if isinstance(repo_data, dict) else repo_data

            if not url:
                return None, None

            # Regex to extract "user/repo" from various formats (git+, https, ssh, git://)
            match = re.search(
                r"github\.com[:/](.+?)(?:\.git)?$", url.replace("git+https://", "https://")
            )
            if not match:
                return None, None

            repo_path = match.group(1)
            api_url = f"https://api.github.com/repos/{repo_path}/license"

            # Note: GitHub API without a token is limited to 60 req/h.
            # For large scans, add headers={"Authorization": "token YOUR_TOKEN"}
            github_res = await client.get(api_url)
            if github_res.status_code != 200:
                return None, None

            data = github_res.json()
            spdx_id = None
            license_obj = data.get("license")
            if isinstance(license_obj, dict):
                spdx_id = license_obj.get("spdx_id")
                if spdx_id in (None, "NOASSERTION"):
                    spdx_id = None

            license_text = None
            content_b64 = data.get("content", "")
            if content_b64:
                try:
                    license_text = base64.b64decode(content_b64).decode(
                        "utf-8", errors="replace"
                    )
                except Exception:
                    license_text = None

            return spdx_id, license_text
        except Exception as e:
            logger.warning("GitHub license lookup error for %s: %s", package_name, e)
            return None, None

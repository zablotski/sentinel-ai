import httpx
import base64
import re

async def get_license_from_github(package_name: str):
    npm_url = f"https://registry.npmjs.org/{package_name}/latest"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(npm_url)
            repo_data = res.json().get("repository", {})
            url = repo_data.get("url", "") if isinstance(repo_data, dict) else repo_data
            
            if not url: return None

            # Regex to extract "user/repo" from various formats (git+, https, ssh, git://)
            match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url.replace("git+https://", "https://"))
            if not match: return None
            
            repo_path = match.group(1)
            api_url = f"https://api.github.com/repos/{repo_path}/license"
            
            # Note: GitHub API without a token is limited to 60 req/h.
            # For large scans, add headers={"Authorization": "token YOUR_TOKEN"}
            github_res = await client.get(api_url)
            if github_res.status_code == 200:
                data = github_res.json()
                content_b64 = data.get("content", "")
                return base64.b64decode(content_b64).decode('utf-8')
        except Exception as e:
            print(f"GitHub Error for {package_name}: {e}")
            return None
    return None

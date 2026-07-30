import httpx

async def get_vulnerabilities(package_name: str, version: str):
    url = "https://api.osv.dev/v1/query"
    payload = {
        "package": {"name": package_name, "ecosystem": "npm"},
        "version": version
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        data = response.json()
        return [vuln['id'] for vuln in data.get('vulns', [])]

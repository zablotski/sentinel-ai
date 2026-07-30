import httpx

async def get_package_license(package_name: str):
    url = f"https://registry.npmjs.org/{package_name}/latest"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            data = response.json()
            # NPM stores licenses in varying formats; extract the string
            license_data = data.get("license")
            if isinstance(license_data, dict):
                return license_data.get("type")
            return license_data
        except:
            return "UNKNOWN"

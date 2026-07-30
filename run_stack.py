import os
import sys
import time
import subprocess
import urllib.request
import urllib.error
import json

# Terminal log colors
CYAN = '\033[0;36m'
GREEN = '\033[0;32m'
RED = '\033[0;31m'
NC = '\033[0m'

QDRANT_URL = "http://localhost:6333"
POLICY_COLLECTION = "corporate_policies"
EXPECTED_POLICY_COUNT = 4


def wait_for_qdrant(max_attempts=30, delay_sec=1):
    for _ in range(max_attempts):
        try:
            with urllib.request.urlopen(f"{QDRANT_URL}/healthz", timeout=2):
                return True
        except Exception:
            time.sleep(delay_sec)
    return False


def get_policy_point_count():
    try:
        req = urllib.request.Request(
            f"{QDRANT_URL}/collections/{POLICY_COLLECTION}/points/count",
            data=json.dumps({"exact": True}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data.get("result", {}).get("count", 0)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return 0
        raise


def ensure_policy_seeded():
    if not wait_for_qdrant():
        print(f"{RED}❌ Error: Qdrant did not become ready in time.{NC}")
        sys.exit(1)

    count = get_policy_point_count()
    if count >= EXPECTED_POLICY_COUNT:
        print(f"Qdrant policy collection verified ({count} records).")
        return

    print(f"Policy collection missing or incomplete ({count} records). Running seed_policy...")
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    seed_script = os.path.join(backend_dir, "scripts", "seed_policy.py")
    subprocess.run([sys.executable, seed_script], check=True, cwd=backend_dir)


print(f"{CYAN}=== Sentinel AI: Initializing Local Environment ==={NC}")

# --- STEP 1: Verify Docker and Qdrant Status ---
try:
    subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
except (subprocess.CalledProcessError, FileNotFoundError):
    print(f"{RED}❌ Error: Docker daemon is not running! Launch Docker Desktop and try again.{NC}")
    sys.exit(1)

print(f"{GREEN}🐳 Docker is active. Verifying Qdrant vector database...{NC}")

# Check if Qdrant container is actively running
running_containers = subprocess.run(["docker", "ps", "-q", "-f", "name=qdrant"], capture_output=True, text=True).stdout.strip()

if not running_containers:
    # Check if container exists but is stopped (Single line to prevent terminal clip)
    all_containers = subprocess.run(["docker", "ps", "-aq", "-f", "name=qdrant"], capture_output=True, text=True).stdout.strip()
    
    if all_containers:
        print("Starting existing Qdrant container...")
        subprocess.run(["docker", "start", "qdrant"], check=True)
    else:
        print("Pulling and deploying a new Qdrant container...")
        subprocess.run(["docker", "run", "-d", "--name", "qdrant", "-p", "6333:6333", "-p", "6334:6334", "qdrant/qdrant"], check=True)
else:
    print("Qdrant container is already running on port 6333.")

print(f"{GREEN}📚 Verifying Qdrant policy data...{NC}")
ensure_policy_seeded()

# --- STEP 2: Verify Ollama and Registry Models ---
print(f"{GREEN}🤖 Checking Ollama local service status...{NC}")

try:
    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as response:
        tags_data = json.loads(response.read().decode())
except Exception:
    print(f"{RED}❌ Error: Ollama is offline! Please start the Ollama application.{NC}")
    sys.exit(1)

# Dynamically import inventory requirements from our single source of truth
try:
    from app.core.models import ModelRegistry
    required_models = list(
        set(
            [
                ModelRegistry.LAWYER_NODE_MODEL,
                ModelRegistry.CRITIC_NODE_MODEL,
                ModelRegistry.GUARDRAIL_MODEL,
            ]
        )
    )
except Exception as e:
    print(f"{RED}❌ Error: Failed to read Model Registry file: {e}{NC}")
    sys.exit(1)

print("Auditing Model Registry inventory tracking requirements...")
downloaded_models = [m['name'] for m in tags_data.get('models', [])]

for model in required_models:
    print(f"Verifying model availability: {CYAN}{model}{NC}")
    
    # Check if exact tag exists within local Ollama manifest
    if not any(model in local_m for local_m in downloaded_models):
        print(f"{CYAN}Model {model} not found locally. Fetching from Ollama registry...{NC}")
        subprocess.run(["ollama", "pull", model], check=True)
    else:
        print(f"Model {model} is successfully verified and available.")

# --- STEP 3: Launch FastAPI Application ---
print(f"{GREEN}🚀 Launching FastAPI server...{NC}")

# Keep relative module import paths secure by invoking app.main directly
subprocess.run([sys.executable, "-m", "app.main"])

# 🛡️ Sentinel AI - Intelligent Dependency Auditor

**Sentinel AI** is a local dependency security gatekeeper. It uses a LangGraph Actor–Critic loop (Lawyer ↔ Critic) with Ollama and Qdrant—no cloud LLM APIs.

## 🏗️ Project Structure

```text
backend/
├── run_stack.py              # Bootstrap: Docker/Qdrant, policy seed, Ollama, FastAPI
├── fixtures/
│   └── package.json          # Sample package.json for audit
├── scripts/
│   └── seed_policy.py        # Seeds corporate_policies into Qdrant
├── app/
│   ├── main.py
│   ├── core/                 # config.py, models.py
│   ├── agents/               # graph, state, nodes (lawyer, critic)
│   ├── services/
│   └── api/audit.py          # POST /api/v1/audit
└── requirements.txt
```

## 🚀 Quick Start

### 1. System Requirements

* **Docker Desktop** — running (used for Qdrant)
* **Ollama** — running at `http://localhost:11434`
* **Python venv** with dependencies installed

### 2. One-Time Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Required models are defined in `app/core/models.py` (`deepseek-r1:8b` for Lawyer, `llama3.2:3b` for Critic). `run_stack.py` pulls any missing models automatically.

### 3. Start Everything

Use the venv Python (activation optional):

```bash
cd backend
venv/bin/python run_stack.py
```

Or activate first: `source venv/bin/activate` then `python run_stack.py`.

`run_stack.py` uses whichever interpreter launched it—system `python` will fail if dependencies are only installed in `venv`.

`run_stack.py` performs these steps automatically:

1. **Docker** — verifies the daemon is running
2. **Qdrant** — starts existing `qdrant` container or creates a new one on ports `6333` / `6334`
3. **Policy data** — waits for Qdrant health, checks `corporate_policies` (≥ 4 records); runs `scripts/seed_policy.py` if missing
4. **Ollama** — verifies service is up, reads `ModelRegistry`, runs `ollama pull` for missing models
5. **FastAPI** — launches `python -m app.main` on `http://0.0.0.0:8000`

## 🛠️ How It Works

1. **Scout Node** — Parses `package.json` into `packages_to_analyze`.
2. **Parallel fan-out** — LangGraph `Send` spawns one lawyer/critic branch per package.
3. **Lawyer Node (Actor)** — RAG over corporate policies per package.
4. **Critic Node (Auditor)** — Zero-trust review with up to **3** correction attempts per branch.
5. **Fan-in** — Completed branches merge into `analyzed_dependencies` via `operator.add`.

## 🧪 Testing

With the server running (`python run_stack.py`):

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/audit" \
     -H "Content-Type: application/json" \
     -d @fixtures/package.json
```

Edit `fixtures/package.json` to try other dependencies.

## 📝 Developer Notes

* **Qdrant persistence**: Without a Docker volume, policy vectors are lost on restart; `run_stack.py` re-seeds when the collection is empty.
* **Model changes**: Update `app/core/models.py`; the next `run_stack.py` run pulls new models.

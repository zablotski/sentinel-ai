# Sentinel AI — Configuration

Two YAML files drive Sentinel, plus environment variables. Everything is optional — built-in defaults live in `app/core/config.py` and `app/core/models.py`.

| File | Purpose |
| --- | --- |
| `.sentinel.yml` | License policy, UNKNOWN-license handling, Judge rulebook |
| `sentinel.models.yml` | LLM provider + per-role model selection |

Templates: `.sentinel.yml.example` (copy to `.sentinel.yml`).

## Environment variables

| Env var | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | from `sentinel.models.yml` (default `groq`) | Selects cloud vs local models; overrides the YAML |
| `GROQ_API_KEY` / `LLM_API_KEY` | — | Required for the Groq provider |
| `SENTINEL_MODELS_PATH` | `sentinel.models.yml` | Override location of the model-selection file |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI-compatible endpoint |
| `QDRANT_HOST` | `http://localhost:6333` | Vector DB for policy RAG + verdict cache |
| `SENTINEL_CI` | unset | Stateless mode: MemorySaver checkpointer, verdict cache bypassed |
| `SENTINEL_CONFIG_PATH` | `.sentinel.yml` | Override location of the license policy file |
| `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` | off | Optional LangSmith observability |

## License policy (`.sentinel.yml`)

```yaml
policy:
  allowed: [MIT, Apache-2.0, BSD-3-Clause, ISC]
  forbidden: [GPL-2.0-only, GPL-3.0-only, AGPL-3.0-only]
  review_required: [LGPL-2.1-only, LGPL-3.0-only, MPL-2.0]

unknown_license_handling:        # when npm declares license = UNKNOWN
  fetch_github_evidence: true    # Scout pulls the LICENSE text from GitHub
  auto_classify_threshold: 0.85  # similarity >= this: treat as the matched SPDX
  review_threshold: 0.60         # between thresholds: REVIEW_REQUIRED with evidence
                                 # below: REVIEW_REQUIRED, insufficient evidence

judge:                           # global-compatibility rulebook inputs
  permissive_licenses: [MIT, Apache-2.0, BSD, ISC, 0BSD, Unlicense]
  copyleft_markers: [GPL, AGPL, LGPL, COPYLEFT]
```

Permissive-vs-copyleft defaults are built in when the file is absent (see `default_sentinel_config()` in `app/core/config.py`).

### How UNKNOWN licenses are resolved

1. **Evidence** — Scout fetches the package's LICENSE file via the GitHub API.
2. **Classification** — the text is embedded (`all-MiniLM-L6-v2`) and compared by cosine similarity against canonical license signatures (`app/services/license_signatures.py`).
3. **Confidence tiers** — high-confidence matches are audited as the classified SPDX id; medium/low matches become `REVIEW_REQUIRED` for a human, with the nearest match and score recorded in the report (`UNKNOWN → GPL-2.0-only (0.72)`).
4. **Cache safety** — the verdict cache key includes a hash of the whole policy, so editing `.sentinel.yml` automatically invalidates stale verdicts.

## Provider and models (`sentinel.models.yml`)

The single place to decide which provider runs and which model serves each role:

```yaml
provider: groq            # groq | ollama

models:
  groq:
    heavy: openai/gpt-oss-20b            # big-context packages / Lawyer
    standard: openai/gpt-oss-20b         # default tier
    guardrail: meta-llama/llama-prompt-guard-2-22m
  ollama:
    heavy: deepseek-r1:8b
    standard: llama3.2:3b
    guardrail: llama-guard3:1b
```

Precedence rules:

* **Provider**: `LLM_PROVIDER` env var > `provider:` in the YAML > `groq`. If the selected provider is `groq` but no API key is set, Sentinel falls back to `ollama`.
* **Model ids**: YAML `models.<provider>.<role>` > built-in defaults in `app/core/models.py`. Every key is optional — omit any to keep its default.
* `run_stack.py` reads the same file: with `provider: groq` it skips the Ollama service/model checks entirely; with `provider: ollama` it pulls only the models the YAML selects.
* Point at a different file with `SENTINEL_MODELS_PATH` (useful to keep a local `ollama` variant out of git).

The shipped config targets GitHub Actions (Groq). For fully-local runs, set `provider: ollama`.

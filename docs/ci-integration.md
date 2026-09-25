# Sentinel AI — CI Integration

## GitHub Action

`.github/workflows/sentinel-test.yml` runs the CLI audit on PRs to `main`/`master`:

* Starts a `qdrant/qdrant` service container
* Uses Groq cloud models (`GROQ_API_KEY` secret; provider comes from `sentinel.models.yml`)
* Posts the audit report as a PR comment via `GITHUB_TOKEN`
* Fails the check on forbidden licenses or a security block

## Change gating

The audit only runs when **watched files change** on the PR. Otherwise the job skips with a "no watched changes" step summary and stays green — no LLM calls, no PR comment.

Watched paths are configured in the `ci:` section of `.sentinel.yml`:

```yaml
ci:
  watch_paths:
    - package.json
    - package-lock.json
    - .sentinel.yml
    - sentinel.models.yml
  run_on_no_match: false   # true = always audit, even with no watched changes
```

Pattern rules: a trailing `/` matches a whole directory, a pattern with `/` is matched against the full path, a bare name matches the file name at any depth (`frontend/package.json` matches `package.json`).

### How it works

The workflow has a gate step before the audit:

```yaml
- name: Check watched paths
  id: gate
  run: python -m app.cli --should-run

- name: Run Sentinel AI Audit
  if: steps.gate.outputs.should_run == 'true'
  run: python -m app.cli --package-json package.json
```

`--should-run` diffs `origin/<base>...HEAD` (base from `GITHUB_BASE_REF`) against `watch_paths`, prints `true`/`false`, and writes `should_run=<decision>` to `$GITHUB_OUTPUT`. It always exits `0`, so a skip never fails the check — important if the audit check is ever made required (a `paths:` trigger filter would instead leave PRs stuck pending).

Requires `actions/checkout` with `fetch-depth: 0` so the base diff is available.

## Supported manifests

Sentinel audits **`package.json` (npm) only**. Other ecosystems (`pyproject.toml`, `go.mod`, `pom.xml`, `Cargo.toml`, …) are not supported yet — add them to `ci.watch_paths` only when you also plan to extend Scout.

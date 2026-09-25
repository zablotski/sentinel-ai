# Sentinel AI — CI Integration

## GitHub Action

`.github/workflows/sentinel-test.yml` runs the CLI audit on PRs to `main`/`master`:

* Starts a `qdrant/qdrant` service container
* Uses Groq cloud models (`GROQ_API_KEY` secret; provider comes from `sentinel.models.yml`)
* Posts the audit report as a PR comment via `GITHUB_TOKEN`
* Fails the check on forbidden licenses or a security block

## Change gating

The workflow only **triggers** when watched files change on the PR — if nothing relevant changed, the job never starts (no runner boot, no dependency install, no Qdrant container):

```yaml
on:
  pull_request:
    branches: [ main, master ]
    paths:
      - 'package.json'
      - 'package-lock.json'
      - '.sentinel.yml'
      - 'sentinel.models.yml'
```

Edit the `paths:` list in the workflow file to change what triggers an audit.

> **Caveat:** if the audit check is ever marked *required* in branch protection, a PR with no watched changes will sit with a pending check forever (the job never runs to report success). Keep the check non-blocking, or move back to an in-job gate if you make it required.

## Supported manifests

Sentinel audits **`package.json` (npm) only**. Other ecosystems (`pyproject.toml`, `go.mod`, `pom.xml`, `Cargo.toml`, …) are not supported yet — add them to `paths:` only when you also plan to extend Scout.

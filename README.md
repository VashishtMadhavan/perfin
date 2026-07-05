# Perfin

A personal-finance CLI for account sync, deterministic analytics, and later
LLM-assisted planning.

## Local Development

Install and run through `uv`:

```bash
uv run perfin --help
```

The Phase 1 local path uses a deterministic fake data source, so no Plaid keys
or network access are required:

```bash
uv run perfin sync --source fake
uv run perfin spend --months 3
uv run perfin spend --months 3 --group-by merchant
uv run perfin networth
uv run perfin savings-rate --months 3
uv run perfin profile
```

Run tests with:

```bash
uv run pytest
```

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
uv run perfin afford 3000 --months 3
uv run perfin retire --age 65 --annual-contribution 18000
uv run perfin profile
```

Plaid sandbox wiring is available behind an explicit source flag:

```bash
PLAID_CLIENT_ID=... PLAID_SECRET=... uv run perfin link --source plaid
uv run perfin sync --source plaid
```

`PERFIN_SYNC_DEFAULT_SOURCE` controls the auto-sync source and defaults to
`fake`, keeping local read commands offline by default.

Run tests with:

```bash
uv run pytest
```

Alembic migration scaffolding is included. To migrate the configured local app
database:

```bash
uv run alembic upgrade head
```

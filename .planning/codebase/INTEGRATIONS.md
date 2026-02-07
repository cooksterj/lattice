# External Integrations

**Analysis Date:** 2026-02-06

## APIs & External Services

**No external API integrations detected.**

Lattice does not integrate with external APIs like cloud services, payment processors, or SaaS platforms. The framework is self-contained and designed to orchestrate user-defined asset functions.

## Data Storage

**Databases:**
- SQLite (built-in, no external database required)
  - Connection: File-based at `lattice_runs.db` (configurable path in CLI via `--db` flag)
  - Client: Python stdlib `sqlite3`
  - Purpose: Stores run history, logs, lineage events, check results, asset execution metadata
  - Schema: `src/lattice/observability/history/sqlite.py`

**File Storage:**
- Local filesystem only
  - Asset data storage via IOManager implementations:
    - `MemoryIOManager`: In-process memory (testing/ephemeral runs)
    - `FileIOManager`: Pickle files in local filesystem (default)
    - `ParquetIOManager`: Parquet files in local filesystem (optional, for DataFrames)
  - Configurable base paths for each manager
  - Supports directory creation on demand

**Caching:**
- None - No caching layer configured
- Asset dependencies resolved at execution time
- Caching can be implemented at the user's application level via custom IOManager

## Authentication & Identity

**Auth Provider:**
- None - No built-in authentication
- Framework does not authenticate users or gate access to assets
- Web server (FastAPI) runs without auth middleware by default
- Users should add authentication layer if deploying in multi-user environment

## Monitoring & Observability

**Error Tracking:**
- None - No external error tracking service (Sentry, Rollbar, etc.)
- Errors captured and stored in SQLite run history
- Error details available via CLI (`lattice show <run_id> --all`)

**Logs:**
- Python standard logging module (configurable via INI file)
- Stored in SQLite as JSON in run history: `logs_json` column
- Configuration file: `src/lattice/logging/logging.conf`
- Environment variable override: `LATTICE_LOGGING_CONFIG`
- Log levels: DEBUG, INFO, WARNING, ERROR
- Logs captured per-asset during execution and persisted in run records

**Lineage Tracking:**
- Built-in lineage tracking (not external)
- Stored in SQLite: `lineage_json` column
- Lineage events: loaded, stored, computed for each asset
- Accessible via CLI and web UI

**Asset Checks:**
- Built-in data quality checks (not external)
- Stored in SQLite: `check_results_json` column
- Check results include: check name, asset key, pass/fail status, duration, error details
- Accessible via CLI and web UI

## CI/CD & Deployment

**Hosting:**
- None specified - Lattice is a framework for users to host
- Users can deploy the web server (FastAPI + Uvicorn) on any Python-compatible platform
- Examples: Docker containers, cloud functions, traditional servers, local machines

**CI Pipeline:**
- None configured
- Project uses Conventional Commits for release automation (separate from this repo)
- Pre-commit hooks configured for local development (`src/lattice/.pre-commit-config.yaml`)

## Environment Configuration

**Required env vars:**
- None required by default
- Optional: `LATTICE_LOGGING_CONFIG` - Path to logging configuration INI file

**Secrets location:**
- Not applicable - Framework does not handle secrets
- Users should manage secrets at application level (API keys, database credentials, etc.)
- No `.env` file usage in Lattice core

## Webhooks & Callbacks

**Incoming:**
- None - Framework does not expose webhook endpoints for external systems

**Outgoing:**
- None - Framework does not call out to external webhooks
- User-defined asset functions can make HTTP requests (via requests/httpx at application level)

## Web Server Capabilities

**HTTP Endpoints:**
- REST API for asset graph querying: `/api/graph`, `/api/assets`
- REST API for execution: `/api/execute`
- REST API for history: `/api/history`
- WebSocket endpoint for real-time execution streaming: `/ws`
- Static file serving: `/static` (Vue.js web UI)
- HTML template rendering: `/` (main visualization page)

**WebSocket Features:**
- Real-time execution status updates
- Memory usage snapshots during asset execution
- Individual asset completion notifications
- Used by web UI for live progress visualization

**HTTP Client:**
- HTTPx (0.28.0+) used in tests via `httpx.AsyncClient`
- Not a core dependency - only in `dev` group

---

*Integration audit: 2026-02-06*

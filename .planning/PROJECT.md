# Lattice Web UI — Multi-Window Asset Monitoring

## What This Is

Enhancements to Lattice's web UI to support multi-window asset monitoring during pipeline execution. Users can click any asset on the main DAG graph to open a dedicated browser window showing live log streaming during execution, asset details when idle, and access to run history in its own window — all without interrupting downstream asset execution.

## Core Value

Users can monitor individual asset execution in real-time without losing visibility of the overall pipeline or disrupting downstream execution.

## Requirements

### Validated

- ✓ DAG visualization with D3.js on main page — existing
- ✓ WebSocket-based real-time execution status updates — existing
- ✓ Asset detail page with run history — existing
- ✓ ExecutionManager tracks running executions with state — existing
- ✓ LogCapture intercepts Python logging per-asset during execution — existing
- ✓ SQLite-backed run history store — existing
- ✓ REST API for graph, execution, and history — existing
- ✓ Background execution (async executor with semaphore-limited concurrency) — existing

### Active

- [ ] Clicking an asset on the main graph opens a new browser window (not tab, not navigation)
- [ ] Asset window streams live logs in real-time during execution via WebSocket
- [ ] Asset window shows asset info and details when no execution is running
- [ ] When asset execution completes, logs stop and a success/failure banner is displayed
- [ ] Asset window has a button/link to navigate back (refocus) the main window
- [ ] Asset window has a "Run History" link that opens run history in its own browser window
- [ ] Downstream assets continue executing while viewing any asset window
- [ ] Main graph window remains functional and updating while asset windows are open

### Out of Scope

- Authentication/authorization for the web UI — framework assumes local/trusted network
- Mobile-responsive design — development tool, desktop browser only
- Drag-and-drop window management — browser native window positioning is sufficient
- Multi-user concurrent execution monitoring — single-user tool

## Context

Lattice is a Python DAG orchestration framework (similar to Dagster) with a FastAPI web server for visualization and execution. The current web UI navigates away from the main graph when clicking an asset, losing the execution view entirely. The asset detail page only shows run history, not live execution state.

The existing WebSocket infrastructure broadcasts execution updates to connected clients. The enhancement needs to extend this so individual asset windows can subscribe to updates for their specific asset and receive per-asset log entries in real-time.

Key existing infrastructure:
- `src/lattice/web/execution.py` — ExecutionManager with WebSocket broadcasting
- `src/lattice/web/routes.py` — Current asset detail routes
- `src/lattice/web/templates/` — Jinja2 templates (index.html, asset_detail.html)
- `src/lattice/web/static/` — JavaScript with D3.js visualization and WebSocket client
- `src/lattice/observability/log_capture.py` — LogCapture handler for per-asset log interception

## Constraints

- **Tech stack**: Must use existing stack — FastAPI, Jinja2 templates, vanilla JS, WebSocket. No new frontend frameworks.
- **Window management**: Use `window.open()` for new browser windows. No iframe-based solutions.
- **Backward compatibility**: Existing API endpoints and WebSocket protocol must remain functional for any existing consumers.
- **Execution isolation**: Asset windows are purely observational — opening/closing them must never affect execution state.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| New browser windows (not tabs/modals) | User explicitly wants independent windows they can arrange alongside the main graph | — Pending |
| Separate live view from run history | Live execution logs and historical runs serve different purposes and should be distinct views | — Pending |
| WebSocket per-asset log streaming | Existing WebSocket infrastructure can be extended to support asset-scoped log delivery | — Pending |

---
*Last updated: 2026-02-06 after initialization*

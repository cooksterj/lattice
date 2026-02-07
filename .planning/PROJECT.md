# Lattice Web UI — Multi-Window Asset Monitoring

## What This Is

Enhancements to Lattice's web UI enabling multi-window asset monitoring during pipeline execution. Users click any asset on the main DAG graph to open a dedicated browser window showing live log streaming during execution, asset details when idle, and access to run history — all without interrupting downstream asset execution or leaving the graph view.

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
- ✓ Clicking an asset on the main graph opens a new browser window (not tab, not navigation) — v1.0
- ✓ Asset window streams live logs in real-time during execution via WebSocket — v1.0
- ✓ Asset window shows asset info and details when no execution is running — v1.0
- ✓ When asset execution completes, logs stop and a success/failure banner is displayed — v1.0
- ✓ Asset window has a button to refocus the main graph window — v1.0
- ✓ Asset window has a "Run History" link that opens run history in its own browser window — v1.0
- ✓ Downstream assets continue executing while viewing any asset window — v1.0
- ✓ Main graph window remains functional and updating while asset windows are open — v1.0

### Active

(None — v1.0 complete. Define new requirements with `/gsd:new-milestone` for v2.)

### Out of Scope

- Authentication/authorization for the web UI — framework assumes local/trusted network
- Mobile-responsive design — development tool, desktop browser only
- Drag-and-drop window management — browser native window positioning is sufficient
- Multi-user concurrent execution monitoring — single-user tool

## Context

Lattice is a Python DAG orchestration framework with a FastAPI web server for visualization and execution. v1.0 shipped multi-window asset monitoring with 1,607 lines of code across 9 source files.

**Current tech stack:** FastAPI, Jinja2 templates, vanilla JS, D3.js, WebSocket, SQLite

**Key infrastructure added in v1.0:**
- `src/lattice/observability/log_capture.py` — ExecutionLogHandler with on_entry callback
- `src/lattice/web/execution.py` — Per-asset subscriber registry, WebSocket endpoint, replay buffer
- `src/lattice/web/routes.py` — Asset live route (`/asset/{key}/live`)
- `src/lattice/web/templates/asset_live.html` — 891-line live monitoring template with state machine
- `src/lattice/web/static/js/graph.js` — Window.open integration, dedup tracking, popup fallback

## Constraints

- **Tech stack**: Must use existing stack — FastAPI, Jinja2 templates, vanilla JS, WebSocket. No new frontend frameworks.
- **Window management**: Use `window.open()` for new browser windows. No iframe-based solutions.
- **Backward compatibility**: Existing API endpoints and WebSocket protocol must remain functional.
- **Execution isolation**: Asset windows are purely observational — opening/closing them must never affect execution state.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| New browser windows (not tabs/modals) | User wants independent windows to arrange alongside the main graph | ✓ Good |
| Separate live view from run history | Live execution logs and historical runs serve different purposes | ✓ Good |
| WebSocket per-asset log streaming | Existing WebSocket infrastructure extended for asset-scoped delivery | ✓ Good |
| Per-window WebSocket with server-side filtering | Each window gets its own connection; server filters by asset key | ✓ Good |
| asyncio.Queue as sync-to-async bridge | emit() never blocks execution thread; queue bridges to async WebSocket | ✓ Good |
| Live route before greedy detail route | Prevents FastAPI's `:path` converter from capturing `/live` suffix | ✓ Good |
| textContent for XSS safety | All user content rendered via textContent, not innerHTML | ✓ Good |
| DOM cap at 2000 log entries | FIFO eviction prevents browser slowdown on long-running assets | ✓ Good |
| Named window targeting for refocus | window.opener.focus() unreliable in modern browsers; named window + window.open is user-gesture-compliant | ✓ Good |
| Synchronous window.open in click handler | Async operations before window.open trigger popup blockers | ✓ Good |
| event.defaultPrevented for click-vs-drag | D3's drag behavior sets defaultPrevented; checking this prevents accidental window opens | ✓ Good |

---
*Last updated: 2026-02-06 after v1.0 milestone*

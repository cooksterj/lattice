# Lattice Web UI

## What This Is

A web UI for the Lattice DAG orchestration framework featuring persistent sidebar navigation, real-time execution monitoring, live per-asset log streaming, and failed asset recovery with targeted downstream re-execution.

## Core Value

Users can monitor execution, view logs, and recover from failures without leaving the main workflow or dealing with popup windows.

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
- ✓ Real-time per-asset log streaming via WebSocket with replay buffer — v1.0
- ✓ Live monitoring page with state machine (idle/running/completed/failed) — v1.0
- ✓ Completion banner with success/failure styling — v1.0
- ✓ Execution isolation — viewing pages never affects pipeline state — v1.0
- ✓ Persistent icon rail sidebar on all pages with tooltips — v2.0
- ✓ Active page highlighting in sidebar — v2.0
- ✓ Full-page navigation with browser back/forward support — v2.0
- ✓ Active runs page with real-time WebSocket updates during execution — v2.0
- ✓ Active runs page shows last completed run summary when idle — v2.0
- ✓ Click running asset to navigate to live logs — v2.0
- ✓ Run history page in sidebar layout — v2.0
- ✓ Full-page live logs with sidebar and back button — v2.0
- ✓ Graph click-to-select with visual highlighting — v2.0
- ✓ Context-aware Execute button for targeted re-execution from failed assets — v2.0
- ✓ All v1 popup infrastructure removed — v2.0

### Active

(No active requirements — start next milestone with `/gsd:new-milestone`)

### Out of Scope

- Authentication/authorization — framework assumes local/trusted network
- Mobile-responsive design — development tool, desktop browser only
- Multi-user concurrent execution monitoring — single-user tool
- SPA client-side routing — requires JS framework, violates stack constraint
- Expandable sidebar with text labels — overkill for 3 nav items
- Modal overlays for run details — full-page views are the design choice
- Automatic retry on failure — masks real failures, complicates execution model

## Context

Lattice is a Python DAG orchestration framework with a FastAPI web server for visualization and execution. v1.0 shipped multi-window asset monitoring, v2.0 replaced popups with sidebar navigation and added failure recovery.

**Current codebase:**
- 32 files modified across v2.0 (net +4,319 lines)
- Tech stack: FastAPI, Jinja2 templates, vanilla JS, D3.js, WebSocket, SQLite
- 276 passing tests
- Zero popup/multi-window code remaining

**Key infrastructure:**
- `src/lattice/observability/log_capture.py` — ExecutionLogHandler with on_entry callback
- `src/lattice/web/execution.py` — Per-asset subscriber registry, WebSocket endpoint, replay buffer
- `src/lattice/web/routes.py` — All routes including /runs, /asset/{key}/live, /asset/{key}/detail
- `src/lattice/web/templates/base.html` — Jinja2 base template with sidebar
- `src/lattice/web/static/js/graph.js` — DAG visualization with click-to-select and targeted execution
- `src/lattice/web/static/css/styles.css` — Shared styles including sidebar and statusPulse animation

## Constraints

- **Tech stack**: Must use existing stack — FastAPI, Jinja2 templates, vanilla JS, WebSocket. No new frontend frameworks.
- **Navigation model**: Full-page navigation with back button. No popups, no modals, no iframes.
- **Backward compatibility**: Existing API endpoints and WebSocket protocol must remain functional.
- **Execution isolation**: Viewing pages must never affect execution state. Only the explicit Execute action triggers runs.
- **Commit style**: Conventional commits for release-please (`feat:`, `fix:`, `docs:`, `chore:`, etc.)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Separate live view from run history | Live execution logs and historical runs serve different purposes | ✓ Good |
| WebSocket per-asset log streaming | Existing WebSocket infrastructure extended for asset-scoped delivery | ✓ Good |
| Per-window WebSocket with server-side filtering | Each connection gets its own connection; server filters by asset key | ✓ Good |
| asyncio.Queue as sync-to-async bridge | emit() never blocks execution thread; queue bridges to async WebSocket | ✓ Good |
| Live route before greedy detail route | Prevents FastAPI's `:path` converter from capturing `/live` suffix | ✓ Good |
| textContent for XSS safety | All user content rendered via textContent, not innerHTML | ✓ Good |
| DOM cap at 2000 log entries | FIFO eviction prevents browser slowdown on long-running assets | ✓ Good |
| event.defaultPrevented for click-vs-drag | D3's drag behavior sets defaultPrevented; checking this prevents accidental actions | ✓ Good |
| Replace popups with sidebar navigation | Better UX, no popup blockers, consistent layout | ✓ Good |
| Graph click selects/highlights only | Decouples asset selection from navigation; sidebar handles navigation | ✓ Good |
| Re-execute from failed asset downstream | Reuses existing ExecutionPlan.resolve for targeted re-execution | ✓ Good |
| No new dependencies for v2.0 | Entire milestone built on existing stack, minimizes complexity | ✓ Good |
| REST polling for sidebar state | Avoids WebSocket churn on navigation between pages | ✓ Good |
| Jinja2 template inheritance with base.html | Consistent sidebar on all pages, DRY template structure | ✓ Good |
| Dual-mode active runs page | WebSocket for live execution, REST for idle summary — clean state transitions | ✓ Good |
| Clear selection after execution completes | Clean state for both success and failure cases | ✓ Good |

---
*Last updated: 2026-02-08 after v2.0 milestone*

# Lattice Web UI — Sidebar Navigation & Recovery

## What This Is

Enhancements to Lattice's web UI replacing the popup-based monitoring approach with persistent sidebar navigation and adding failed asset recovery. Users monitor execution via a sidebar available on every page — with icons for run history and active/queued runs — and can re-execute failed assets plus their downstream dependencies directly from the graph.

## Core Value

Users can monitor execution, view logs, and recover from failures without leaving the main workflow or dealing with popup windows.

## Current Milestone: v2.0 Sidebar Navigation & Failed Asset Recovery

**Goal:** Replace popup windows with sidebar-driven full-page navigation and add the ability to re-execute failed assets with downstream propagation.

**Target features:**
- Persistent sidebar with run history and active runs icons on all pages
- Full-page views for run history, active/queued runs, and live asset logs
- Failed asset re-execution (select failed asset + downstream, click Execute)
- Remove v1 popup window behavior entirely

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

- [ ] Persistent sidebar with icons on all pages (run history, active runs)
- [ ] Run history full page — shows past execution runs
- [ ] Active runs full page — shows running/queued assets during execution, last completed run when idle
- [ ] Click running asset on active runs page to navigate to live logs full page
- [ ] All detail views are full pages with back button
- [ ] Failed asset re-execution — click failed asset on graph to highlight it + downstream, click Execute to re-run from that point
- [ ] Graph click behavior changed to select/highlight only (no popups)
- [ ] Remove v1 popup window behavior entirely

### Out of Scope

- Authentication/authorization for the web UI — framework assumes local/trusted network
- Mobile-responsive design — development tool, desktop browser only
- Multi-user concurrent execution monitoring — single-user tool
- Popup/multi-window approach — replaced by sidebar navigation in v2

## Context

Lattice is a Python DAG orchestration framework with a FastAPI web server for visualization and execution. v1.0 shipped multi-window asset monitoring with 1,607 lines of code across 9 source files. v2.0 replaces the popup approach with sidebar navigation and adds failure recovery.

**Current tech stack:** FastAPI, Jinja2 templates, vanilla JS, D3.js, WebSocket, SQLite

**Key infrastructure from v1.0 (reusable):**
- `src/lattice/observability/log_capture.py` — ExecutionLogHandler with on_entry callback
- `src/lattice/web/execution.py` — Per-asset subscriber registry, WebSocket endpoint, replay buffer
- `src/lattice/web/routes.py` — Asset live route (`/asset/{key}/live`)
- `src/lattice/web/templates/asset_live.html` — 891-line live monitoring template with state machine
- `src/lattice/web/static/js/graph.js` — Window.open integration (to be replaced with select/highlight)

**v2.0 changes:** The popup window infrastructure (window.open, named windows, refocus) will be removed. The WebSocket per-asset streaming and log capture infrastructure remains — it just delivers to an in-page view instead of a popup. The ExecutionManager needs extension to support partial re-execution from a specific asset downstream.

## Constraints

- **Tech stack**: Must use existing stack — FastAPI, Jinja2 templates, vanilla JS, WebSocket. No new frontend frameworks.
- **Navigation model**: Full-page navigation with back button. No popups, no modals, no iframes.
- **Backward compatibility**: Existing API endpoints and WebSocket protocol must remain functional.
- **Execution isolation**: Viewing pages must never affect execution state. Only the explicit Execute action triggers runs.
- **Commit style**: Conventional commits for release-please (`feat:`, `fix:`, `docs:`, `chore:`, etc.)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| New browser windows (not tabs/modals) | User wants independent windows to arrange alongside the main graph | ⚠️ Revisit — replaced by sidebar navigation in v2 |
| Separate live view from run history | Live execution logs and historical runs serve different purposes | ✓ Good |
| WebSocket per-asset log streaming | Existing WebSocket infrastructure extended for asset-scoped delivery | ✓ Good |
| Per-window WebSocket with server-side filtering | Each window gets its own connection; server filters by asset key | ✓ Good |
| asyncio.Queue as sync-to-async bridge | emit() never blocks execution thread; queue bridges to async WebSocket | ✓ Good |
| Live route before greedy detail route | Prevents FastAPI's `:path` converter from capturing `/live` suffix | ✓ Good |
| textContent for XSS safety | All user content rendered via textContent, not innerHTML | ✓ Good |
| DOM cap at 2000 log entries | FIFO eviction prevents browser slowdown on long-running assets | ✓ Good |
| Named window targeting for refocus | window.opener.focus() unreliable in modern browsers; named window + window.open is user-gesture-compliant | ⚠️ Revisit — no longer needed with sidebar navigation |
| Synchronous window.open in click handler | Async operations before window.open trigger popup blockers | ⚠️ Revisit — no longer needed with sidebar navigation |
| Replace popups with sidebar navigation | User prefers full-page views with persistent sidebar over popup windows | — Pending |
| Graph click selects/highlights only | Decouples asset selection from navigation; sidebar handles all navigation | — Pending |
| Re-execute from failed asset downstream | Enables recovery without re-running the entire pipeline | — Pending |
| event.defaultPrevented for click-vs-drag | D3's drag behavior sets defaultPrevented; checking this prevents accidental window opens | ✓ Good |

---
*Last updated: 2026-02-07 after v2.0 milestone initialization*

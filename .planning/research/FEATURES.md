# Features Research: Multi-Window Real-Time Asset Monitoring

## Research Context

**Question**: What features do DAG orchestration tool UIs have for real-time task/asset monitoring? What is table stakes vs differentiating?

**Tools Surveyed**: Dagster, Apache Airflow, Prefect, dbt Cloud

**Lattice Current State**: FastAPI web server with D3.js DAG visualization, WebSocket-based execution status broadcasting, asset detail page (navigates away from graph), run history with SQLite, modal-based run detail views, per-asset log capture during execution (stored but not streamed live to browser).

---

## Feature Inventory

### 1. Live Log Streaming During Execution

| Tool | What It Does |
|------|-------------|
| **Dagster** | Structured log viewer in run detail page. Logs appear in real-time during execution with level filtering (DEBUG/INFO/WARNING/ERROR), step-scoped filtering, and text search. Stdout/stderr capture per step. Compute log viewer for raw output. |
| **Airflow** | Per-task log viewer accessible from Grid/Graph views. Logs fetched via REST (not true streaming in OSS -- refreshes on interval). External log storage support (S3, GCS, ES). Airflow 2.6+ added real-time log tailing in the UI. |
| **Prefect** | Streaming logs in flow run detail view. Logs captured from Python's logging module. Level filtering, task-scoped filtering. Prefect Cloud shows logs inline as they arrive via SSE/polling. |
| **dbt Cloud** | Console-style log output per run. Real-time streaming during execution. Raw and structured views. Model-level log filtering. |

**Lattice Gap**: `ExecutionLogHandler` captures logs per-asset but stores them only in memory/SQLite after completion. No mechanism to stream individual log entries to WebSocket clients during execution. The `broadcast()` method sends `asset_start` and `asset_complete` messages but no `log_entry` messages.

---

### 2. Multi-Window / Multi-Panel Experiences

| Tool | What It Does |
|------|-------------|
| **Dagster** | Single-page application with deep linking. Left sidebar navigation with collapsible panels. Run detail opens as a page (not a new window). Asset detail is a full page with tabs (Definition, Lineage, Activity, Checks, Automation). No native multi-window support -- users manually open links in new tabs. |
| **Airflow** | Grid View is multi-panel: DAG structure on left, task detail on right. Clicking a task instance opens a side panel with tabs (Logs, XCom, Details, Mapped Tasks). No built-in multi-window. Log viewer can be opened in a new tab manually. |
| **Prefect** | Dashboard with multiple cards/widgets. Flow run detail is a dedicated page. Task runs listed within flow run page. No multi-window paradigm -- standard SPA navigation. |
| **dbt Cloud** | IDE has multi-panel layout (file tree, editor, results, logs). Run monitoring is separate pages. No multi-window for monitoring. |

**Key Insight**: None of the major tools provide native multi-window monitoring. All use single-page application patterns with panels/sidebars. Lattice's planned `window.open()` approach for asset monitoring is genuinely novel in this space.

---

### 3. Execution Progress Indicators

| Tool | What It Does |
|------|-------------|
| **Dagster** | Run status indicator (queued/in-progress/success/failure) with asset-level Gantt chart showing parallel execution timeline. Step-level status badges. Progress bar showing N/M steps completed. Color-coded status on the asset graph. |
| **Airflow** | Grid View: color-coded cells per task instance per DAG run (green=success, red=fail, lime=running, orange=up-for-retry). Task duration bars. Gantt chart view. Progress indicated by how many cells are colored in a run column. |
| **Prefect** | Run status badges (Pending/Running/Completed/Failed/Cancelled). Task run counts displayed. Timeline view showing task durations. State change history. |
| **dbt Cloud** | Model-level status badges. Run progress showing "X of Y models completed". Color-coded DAG nodes during execution. |

**Lattice Current State**: Has real-time node color changes via WebSocket (`status-running`, `status-completed`, `status-failed` CSS classes). Has progress counter (X/Y assets). Has memory sparkline. Missing: Gantt chart, per-asset duration display during execution, elapsed time counter.

---

### 4. Asset Detail Views

| Tool | What It Does |
|------|-------------|
| **Dagster** | Rich asset detail with tabs: Definition (code location, description, config), Lineage (upstream/downstream graph), Activity (materialization history with metadata, partition status), Checks (freshness/custom), Automation (sensors/schedules). Asset metadata display (last materialization time, partition status matrix). |
| **Airflow** | Task detail shows: task type, operator, trigger rule, dependencies, rendered template, XCom values, instance history (past runs of this task). |
| **Prefect** | Task run detail: status, duration, timestamps, logs, state transitions, result artifacts, tags. |
| **dbt Cloud** | Model detail: SQL/compiled SQL, schema, column-level lineage, test results, documentation, run history for that model. |

**Lattice Current State**: Asset detail page (`asset_detail.html`) shows: name, group, return type, description, dependencies, dependents, registered checks, and run history table with modal drill-down into logs/checks/assets per run. Solid foundation. Missing: live execution state when asset is currently running, partition status matrix.

---

### 5. Run History Presentation

| Tool | What It Does |
|------|-------------|
| **Dagster** | Runs page with filterable list (status, date range, tags). Run detail page with Gantt timeline, step list, structured logs, and run config. Asset-scoped run history on asset detail page. Partition-aware run history (shows which partitions have been materialized). |
| **Airflow** | Grid View is essentially a run history matrix (runs as columns, tasks as rows). Calendar view for historical run patterns. Run detail page with per-task breakdown. |
| **Prefect** | Flow runs page with filtering (state, date, flow name). Flow run detail with task run list, logs, state transitions. Dashboard cards showing run trends. |
| **dbt Cloud** | Run history list with model-level success/failure. Run detail with per-model timing. Environment-scoped history. |

**Lattice Current State**: History page (`history.html`) with: summary stats (total/passed/failed/rate), asset summary table, partition summary (last 7 days), recent runs list with status filter, and modal detail view with tabs (assets/checks/logs/lineage). Per-asset history accessible from `asset_detail.html`. This is already quite good.

---

## Feature Classification

### Table Stakes (Must Have -- Users Expect These)

| Feature | Complexity | Dependencies | Rationale |
|---------|-----------|-------------|-----------|
| **F1: Asset window shows live execution state** | Medium | WebSocket per-asset subscription | Every tool shows task/asset status during execution. Without this, the asset window is useless during the critical "watching it run" moment. |
| **F2: Log viewing per-asset (post-execution)** | Low | Existing -- already works via run history modal | All tools let you see logs after completion. Lattice already has this in the asset detail modal. |
| **F3: Success/failure status indication on asset window** | Low | F1 (needs WebSocket state) | Universal across all tools. A banner showing completed/failed with duration is minimum. |
| **F4: Asset metadata display (deps, type, checks)** | Low | Existing REST API | Already implemented in `asset_detail.html`. Needs to be replicated in the new window format. |
| **F5: Run history per-asset** | Low | Existing `/api/history/assets/` endpoint | Already works. Needs to be accessible from (or linkable to) the asset window. |
| **F6: Main graph stays functional during monitoring** | Low | Architecture -- no shared blocking state | Fundamental. If opening an asset window disrupts the graph, the feature is broken. Lattice's existing WebSocket broadcast model inherently supports this. |
| **F7: Node status colors on graph during execution** | Low | Existing -- already works | All tools do this. Lattice already has it. |

### Differentiators (Competitive Advantage)

| Feature | Complexity | Dependencies | Rationale |
|---------|-----------|-------------|-----------|
| **D1: Dedicated browser windows (not tabs/panels)** | Medium | `window.open()`, new HTML templates | No major tool does this. Genuine differentiator for users who want to arrange monitoring across multiple screens or tile windows alongside terminals. |
| **D2: Live log streaming during execution** | High | New WebSocket channel or message type for per-asset log entries, modification to `ExecutionLogHandler.emit()` to broadcast | Dagster and Prefect stream logs but within their SPA. Streaming logs to an independent window in real-time is novel and directly useful. |
| **D3: Zero-disruption monitoring (opening/closing windows has no execution side effects)** | Medium | Careful WebSocket lifecycle management | Most tools don't have this problem because they're SPAs. Lattice's multi-window approach makes this a feature: windows are purely observational, never affect execution. |
| **D4: Run history in its own window** | Medium | New template for windowed run history, `window.open()` from asset window | No tool does this natively. Allows side-by-side comparison of current execution vs past runs. |
| **D5: Window-to-window communication (refocus main graph)** | Low | `window.opener.focus()` or `BroadcastChannel` API | Nice UX polish. Quick way to get back to the graph from any child window. |
| **D6: Auto-transition from live logs to completion state** | Medium | D2 + F3, state machine in JS | When execution finishes, logs stop streaming and a summary banner appears. Dagster does this in their SPA but not across windows. |

### Anti-Features (Deliberately Do NOT Build)

| Feature | Rationale |
|---------|-----------|
| **iframe-based window management** | Explicitly ruled out by constraints. Browser windows are the chosen approach. iframes add complexity (cross-origin issues, styling conflicts, scroll management) without benefit for a local dev tool. |
| **Drag-and-drop window arrangement / tiling** | Explicitly out of scope. Let the OS window manager handle positioning. Building a tiling engine is massive complexity for a dev tool. |
| **Multi-user concurrent monitoring** | Out of scope. Lattice is a single-user tool. Adding user sessions, auth, and conflict resolution is scope creep. |
| **Mobile-responsive asset windows** | Out of scope. Desktop browser only. Optimizing for mobile adds CSS complexity and testing burden. |
| **Full SPA with client-side routing** | Lattice uses Jinja2 templates + vanilla JS. Converting to React/Vue/etc. would violate the tech stack constraint and is unnecessary for the scope. |
| **Persistent window layout memory** | Remembering where windows were positioned across sessions adds complexity (localStorage schema, window positioning API quirks across browsers) for minimal value. Let users just re-open what they need. |
| **Notification toasts in asset windows for OTHER assets** | Asset windows should be scoped to their asset. Showing notifications about unrelated assets adds noise. The main graph handles the global view. |
| **Real-time log search/filtering in asset window** | For v1, showing all logs for the asset is sufficient. Full-text search with highlighting across a streaming log is high complexity. Post-execution logs in run history can be searched later. |

---

## Dependency Map

```
F6 (Main graph stays functional)
 |
 +-- no deps, architectural -- existing design supports this

F7 (Node status colors) -- EXISTING
 |
 +-- no deps, already implemented

F4 (Asset metadata display) -- EXISTING
 |
 +-- no deps, existing REST API

F2 (Log viewing post-execution) -- EXISTING
 |
 +-- no deps, existing run history

D1 (Browser windows) -- FOUNDATION
 |
 +-- F4 (metadata shown in window)
 +-- F3 (status indication)
 +-- F1 (live execution state)
 |    |
 |    +-- D2 (live log streaming)
 |         |
 |         +-- D6 (auto-transition to completion)
 |
 +-- D5 (window-to-window communication)
 +-- D4 (run history window)
      |
      +-- F5 (run history per-asset) -- EXISTING

D3 (Zero-disruption monitoring)
 |
 +-- D1 (requires windows to exist)
 +-- F1 (requires WebSocket lifecycle to be clean)
```

**Critical path**: D1 (windows) -> F1 (live state) -> D2 (log streaming) -> D6 (auto-transition)

---

## Implementation Complexity Assessment

| Feature | Backend Changes | Frontend Changes | Estimated Effort |
|---------|----------------|-----------------|-----------------|
| D1: Browser windows | New route for asset window template | New `asset_window.html` template, `window.open()` in `graph.js` click handler | Medium -- mostly new template + JS glue |
| F1: Live execution state in window | Extend WebSocket to support asset-scoped subscriptions or filter client-side | WebSocket connection in asset window JS, state rendering | Medium -- WebSocket protocol extension |
| D2: Live log streaming | Modify `ExecutionLogHandler.emit()` to push log entries through `ExecutionManager.broadcast()`, or add per-asset log WebSocket channel | Log container in asset window with auto-scroll, append-only rendering | High -- touches log capture pipeline and WebSocket protocol |
| F3: Status banner | None (data already in WebSocket messages) | Banner component in asset window, show/hide logic | Low |
| D3: Zero-disruption | Ensure WebSocket connect/disconnect does not affect `ExecutionManager` state | Graceful WebSocket lifecycle in window open/close | Low-Medium -- mostly testing |
| D4: Run history window | None (existing API) | New `history_window.html` template or adapt existing | Low-Medium |
| D5: Window communication | None | `BroadcastChannel` or `window.opener` calls | Low |
| D6: Auto-transition | None (completion data already in WebSocket) | State machine: streaming -> complete, swap log view for summary | Medium |

---

## Recommendations for Implementation Order

1. **D1**: Build the window infrastructure (new templates, `window.open()` wiring, basic asset metadata)
2. **F1 + F3**: Add live execution state to the asset window (WebSocket connection, status display, success/failure banner)
3. **D2 + D6**: Add live log streaming and auto-transition (the high-value differentiator)
4. **D5**: Add window-to-window communication (refocus main graph)
5. **D4**: Add run history in its own window
6. **D3**: Verify and harden zero-disruption guarantees (mostly testing)

---

## Key Technical Decisions Needed

1. **WebSocket strategy for asset windows**: Should each asset window open its own WebSocket connection and filter messages client-side? Or should the server support asset-scoped WebSocket channels (e.g., `/ws/execution/{asset_key}`)? Client-side filtering is simpler but wastes bandwidth. Server-side filtering is cleaner but requires routing changes.

2. **Log streaming mechanism**: Should `ExecutionLogHandler.emit()` synchronously push log entries into an async broadcast queue? Or should there be a separate pub/sub mechanism? The current `emit()` is synchronous (standard Python logging), but `broadcast()` is async. A thread-safe queue bridging sync-to-async is needed.

3. **Window lifecycle management**: Should the main graph track which asset windows are open? Or should windows be fully independent? Tracking enables features like "close all windows" but adds state management complexity.

---

*Researched: 2026-02-06*
*Surveyed: Dagster (dagster-webserver UI), Apache Airflow (2.x Grid/Graph views), Prefect (Cloud + OSS UI), dbt Cloud (IDE + Run monitoring)*

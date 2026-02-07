# Phase 5: Run Monitoring & Live Logs - Research

**Researched:** 2026-02-07
**Domain:** WebSocket real-time UI, Jinja2 template creation/refactoring, FastAPI routing, server-side state bridging
**Confidence:** HIGH

## Summary

Phase 5 introduces three new/refactored pages within the sidebar layout: (1) an Active Runs page showing real-time per-asset execution status via WebSocket, (2) a refactored live logs page (full-page with sidebar and back button, replacing the popup-style layout), and (3) the existing history page re-parented into the sidebar layout (already done in Phase 4). The research focused on understanding the existing WebSocket infrastructure, the current template and routing patterns, the execution state model, and how to connect them into new full-page views.

The codebase already has all the server-side infrastructure needed: `ExecutionManager` broadcasts `asset_start`, `asset_complete`, `execution_complete`, and `memory_update` messages over `/ws/execution`. Per-asset log streaming exists over `/ws/asset/{key}` with replay buffers. The `GET /api/execution/status` endpoint provides the current `ExecutionStatusSchema` (including `is_running`, `asset_statuses`, `run_id`, counts). The `GET /api/history/runs` endpoint provides the last completed run data. No new Python dependencies or WebSocket endpoints are needed -- the phase is primarily about creating a new template (`runs.html`), adding a route (`/runs`), and refactoring `asset_live.html` to be a proper full page.

**Primary recommendation:** Create a `runs.html` template extending `base.html` that connects to the existing `/ws/execution` WebSocket for live updates and falls back to `GET /api/history/runs?limit=1` for showing the last completed run when idle. Refactor `asset_live.html` to replace the popup-style compact header with a proper full-page header including a back button to `/runs`. Add a `/runs` route in `routes.py` (or a new `routes_runs.py`) passing `current_page="runs"`.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Jinja2 | 3.1+ (installed) | Template inheritance, base.html extension | Already the project's template engine |
| FastAPI | 0.100+ (installed) | Route handlers, WebSocket endpoints | Already the web framework |
| WebSocket (existing) | N/A | Real-time execution status streaming | Already implemented in execution.py |
| Vanilla JavaScript | N/A | Client-side WebSocket connection, DOM updates | Project convention -- no JS frameworks |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None needed | - | - | No new dependencies required |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| WebSocket for active runs | REST polling | WebSocket already exists for execution updates; polling would duplicate infrastructure and add latency |
| Vanilla JS DOM updates | htmx or Alpine.js | Adds dependency; violates "no new dependencies" constraint |
| Server-side status rendering | Client-side only | Server-side can provide initial state (last completed run) but live updates must be WebSocket |

**Installation:**
```bash
# No new packages needed -- everything is already in the stack
```

## Architecture Patterns

### Recommended File Structure

```
src/lattice/web/
├── routes.py              # MODIFY: add /runs route
├── templates/
│   ├── base.html          # UNCHANGED: sidebar already has /runs link
│   ├── runs.html          # NEW: active runs page
│   ├── asset_live.html    # MODIFY: refactor to full page with back button
│   ├── index.html         # UNCHANGED
│   ├── history.html       # UNCHANGED (already re-parented in Phase 4)
│   └── asset_detail.html  # UNCHANGED
└── static/css/
    └── styles.css         # MODIFY: add runs-page-specific CSS (or inline in template)
```

### Pattern 1: Active Runs Page -- Dual-Mode Display (Live vs. Idle)

**What:** The active runs page has two visual modes: (1) when an execution is running, it shows a live-updating list of all assets with their real-time status (pending/running/completed/failed); (2) when no execution is running, it shows a summary of the last completed run.

**When to use:** This is the core pattern for the `/runs` page.

**How it works:**

1. **On page load:** Fetch `GET /api/execution/status` to check if an execution is currently running.
2. **If running (`is_running: true`):** Display the `asset_statuses` array in a live table, connect to `/ws/execution` for real-time updates.
3. **If not running (`is_running: false`):** Fetch `GET /api/history/runs?limit=1` to get the last completed run and display its summary.
4. **Transition handling:** When the WebSocket receives `execution_complete`, transition from live mode to idle mode showing the just-completed run.

**Key data flow:**
```
Page Load
  |
  +--> GET /api/execution/status
  |     |
  |     +--> is_running: true  --> Show live table + connect WS
  |     +--> is_running: false --> GET /api/history/runs?limit=1 --> Show last run summary
  |
  +--> WS /ws/execution (always connected for transitions)
        |
        +--> asset_start    --> Update asset row to "running"
        +--> asset_complete --> Update asset row to "completed" or "failed"
        +--> execution_complete --> Transition to idle mode
```

### Pattern 2: Reuse Existing WebSocket Infrastructure

**What:** The active runs page subscribes to the same `/ws/execution` WebSocket endpoint that the graph page already uses. The message types are identical:
- `asset_start` -- `{type: "asset_start", data: {asset_id: "..."}}`
- `asset_complete` -- `{type: "asset_complete", data: {asset_id: "...", status: "...", duration_ms: ..., error: "..."}}`
- `execution_complete` -- `{type: "execution_complete", data: {run_id: "...", status: "...", duration_ms: ..., completed_count: ..., failed_count: ..., total_dates: ...}}`
- `memory_update` -- `{type: "memory_update", data: {rss_mb: ..., vms_mb: ..., percent: ..., timestamp: "..."}}`
- `partition_start` -- `{type: "partition_start", data: {current_date: "...", current_date_index: ..., total_dates: ...}}`
- `partition_complete` -- `{type: "partition_complete", data: {date: "...", status: "...", duration_ms: ..., completed_count: ..., failed_count: ...}}`

**Key insight:** The `ExecutionManager` already supports multiple WebSocket clients via `self._websockets: set[WebSocket]`. Adding another subscriber (the runs page) requires zero server-side changes. The WebSocket endpoint at `/ws/execution` registers any connecting client via `manager.add_websocket(websocket)` and all connected clients receive all broadcast messages.

### Pattern 3: Live Logs as Full Page with Back Button

**What:** The existing `asset_live.html` is refactored from a popup-style layout to a proper full page within the sidebar layout. The key changes are:
1. Remove the fixed compact `.live-header` (it duplicates the sidebar navigation)
2. Add a back button/link to navigate back to `/runs`
3. Remove the "REFOCUS GRAPH" button (v1 popup concept)
4. Remove the "RUN HISTORY" button that opens a new tab (sidebar provides this)
5. Keep the WebSocket log streaming, state machine, and completion banner as-is

**When to use:** This refactoring satisfies requirement RECV-03.

### Pattern 4: Asset Click on Runs Page -> Navigate to Live Logs

**What:** On the active runs page, each asset row in the running state is a clickable link that navigates to `/asset/{key}/live`. This is standard `<a href>` navigation, not `window.open()`.

**When to use:** This satisfies requirement RUNS-03.

### Anti-Patterns to Avoid

- **Don't create a new WebSocket endpoint for the runs page:** The existing `/ws/execution` endpoint already broadcasts all the messages needed. Adding a separate endpoint would duplicate infrastructure.
- **Don't duplicate the execution state tracking on the server:** The `ExecutionManager` already tracks `_is_running`, `_executor.current_state`, etc. The runs page should read this via the existing REST endpoint, not maintain a separate state object.
- **Don't use innerHTML for user-provided data:** Follow the existing pattern from `asset_live.html` where `textContent` is used for user-provided strings (XSS safety). Asset names from the API are safe but maintain the discipline.
- **Don't add a header to base.html:** Phase 4 decided each page defines its own header inside `{% block content %}`. The runs page should follow this pattern.
- **Don't use SPA-style client routing:** The project uses standard `<a href>` navigation. Navigate between runs and live logs with regular page navigation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Real-time execution updates | Custom polling loop | Existing `/ws/execution` WebSocket | Already broadcasts all needed messages |
| Execution status check | Custom state store | Existing `GET /api/execution/status` endpoint | Returns full `ExecutionStatusSchema` |
| Last completed run | Custom "last run" tracker | `GET /api/history/runs?limit=1` | History store already ordered by start time descending |
| Per-asset log streaming | New WebSocket endpoint | Existing `/ws/asset/{key}` endpoint | Already handles replay buffer and live streaming |
| Template structure | Standalone HTML | `{% extends "base.html" %}` | Sidebar and shared structure already in base.html |
| Active page highlighting | JavaScript URL parsing | `current_page="runs"` template context | Established pattern from Phase 4 |

**Key insight:** Phase 5 is almost entirely a frontend/template effort. All the backend infrastructure exists. The only server-side change is adding a route handler for `/runs`.

## Common Pitfalls

### Pitfall 1: Race Condition Between REST Status Check and WebSocket Connection

**What goes wrong:** The page loads, calls `GET /api/execution/status` (which says `is_running: false`), switches to idle mode. But between the REST call and the WebSocket connection, an execution starts. The page misses the initial `asset_start` messages and shows stale "idle" state.

**Why it happens:** The REST status check and WebSocket connection are two separate operations with a time gap between them.

**How to avoid:** Connect the WebSocket FIRST, then check the REST status. If the REST says running, the WebSocket will already be receiving updates. If an execution starts between WebSocket connect and REST check, the WebSocket messages will trigger the live mode transition. The existing `asset_live.html` already uses this pattern: `checkInitialState().then(() => connectWebSocket())` -- but the inverse order is safer: connect WebSocket first, then check REST. Alternatively, keep the same order but handle `asset_start` messages even in "idle" mode by transitioning to "live" mode.

**Warning signs:** Runs page shows "no active execution" while the graph page shows execution in progress.

### Pitfall 2: WebSocket Reconnection on Page Navigation

**What goes wrong:** User navigates from `/runs` to `/asset/X/live` (live logs) and then clicks the back button to return to `/runs`. The runs page's WebSocket was closed when the user navigated away. On return, it needs to reconnect and re-check state.

**Why it happens:** Browser page navigation destroys the current page's JavaScript state, including WebSocket connections.

**How to avoid:** On every page load (including back-button navigation), the runs page should re-initialize: connect WebSocket, check REST status, and render accordingly. This is just the normal initialization flow. Since these are standard page navigations (not SPA), each load is a fresh start.

**Warning signs:** Runs page shows stale data after navigating back to it.

### Pitfall 3: Execution Completes While Viewing Live Logs

**What goes wrong:** User is on `/asset/X/live`, execution completes. The user clicks "Back" to `/runs`. The runs page should show the just-completed run summary, not a "no execution" state.

**Why it happens:** The runs page re-initializes on load. If it checks `is_running` (which is now `false`) and then fetches the last run, it works correctly -- the just-completed run is the last run.

**How to avoid:** This actually works naturally with the dual-mode pattern. When `is_running: false`, fetch `GET /api/history/runs?limit=1`, which returns the most recent run (the just-completed one). No special handling needed.

**Warning signs:** None expected -- this is the happy path.

### Pitfall 4: Refactoring asset_live.html Breaks Existing WebSocket Logic

**What goes wrong:** While removing the popup-style header and buttons, the developer accidentally removes or breaks the WebSocket connection logic, state machine, or completion banner.

**Why it happens:** The asset_live.html template has ~400 lines of inline JavaScript tightly coupled with the HTML structure.

**How to avoid:** The refactoring should be surgical: (1) replace the `.live-header` div with a simpler header that includes a back button, (2) remove the action buttons section (refocus + history), (3) keep the WebSocket connection, state machine, log rendering, and completion banner JavaScript completely untouched. The CSS can be simplified by removing popup-specific styles (`.live-header` positioning).

**Warning signs:** WebSocket connection fails, logs don't stream, completion banner doesn't show, state transitions broken.

### Pitfall 5: Asset Status List Out of Sync with Execution Plan

**What goes wrong:** The active runs page shows a list of assets, but during execution the actual plan may include assets not in the graph API response (if the plan was resolved with a target filter).

**Why it happens:** The `GET /api/execution/status` endpoint returns `asset_statuses` only for assets that have been processed so far. Assets not yet reached are not in the list.

**How to avoid:** Use the execution status `total_assets` count to show progress, but display only the assets that appear in `asset_statuses`. As execution progresses and `asset_start` messages arrive, new assets appear in the list. Alternatively, fetch `GET /api/plan` to get the full plan and show all assets as "pending" initially, then update as WebSocket messages arrive.

**Recommended approach:** Start with an empty list and add assets as `asset_start` messages arrive. This is simpler than trying to predict the plan. Show a progress counter (`completed + failed / total`) based on the execution status.

**Warning signs:** Missing assets in the list, incorrect progress count.

### Pitfall 6: History Page Already Working (RUNS-04 May Be Already Done)

**What goes wrong:** The planner creates tasks for RUNS-04 (run history page accessible via sidebar) that duplicate work already completed in Phase 4.

**Why it happens:** Phase 4 already migrated `history.html` to extend `base.html` and the sidebar already links to `/history`. The history page is already accessible via the sidebar.

**How to avoid:** RUNS-04 is effectively complete from Phase 4. The planner should verify this and not create duplicate tasks. The only possible remaining work would be if the history page needed additional modifications specific to Phase 5 (e.g., linking to the new active runs page). But the current history page renders correctly within the sidebar layout.

**Warning signs:** Duplicated effort on an already-working feature.

## Code Examples

### Example 1: Route Handler for /runs Page

```python
# In routes.py - create_router() (or new routes_runs.py)
@router.get("/runs", response_class=HTMLResponse)
async def runs_page(request: Request) -> HTMLResponse:
    """Serve the active runs / run monitoring page."""
    return templates.TemplateResponse(request, "runs.html", {"current_page": "runs"})
```

This follows the exact pattern established in Phase 4 for all other routes. The `current_page="runs"` variable drives the sidebar active-state highlighting in `base.html`.

### Example 2: Active Runs Page -- Dual Mode JavaScript

```javascript
// State management for the runs page
let currentMode = 'loading'; // 'loading' | 'live' | 'idle'
let ws = null;

async function initialize() {
    // 1. Connect WebSocket first (so we don't miss transitions)
    connectWebSocket();

    // 2. Check current execution state
    const status = await fetchJSON('/api/execution/status');

    if (status.is_running) {
        enterLiveMode(status);
    } else {
        enterIdleMode();
    }
}

function enterLiveMode(status) {
    currentMode = 'live';
    // Show live asset status table
    // Populate with status.asset_statuses
    updateLiveDisplay(status);
}

async function enterIdleMode() {
    currentMode = 'idle';
    // Fetch last completed run
    try {
        const data = await fetchJSON('/api/history/runs?limit=1');
        if (data.runs.length > 0) {
            showLastRunSummary(data.runs[0]);
        } else {
            showNoRunsMessage();
        }
    } catch (e) {
        showNoRunsMessage();
    }
}

// WebSocket message handler
function handleMessage(message) {
    switch (message.type) {
        case 'asset_start':
            if (currentMode !== 'live') enterLiveMode({asset_statuses: []});
            addOrUpdateAsset(message.data.asset_id, 'running');
            break;
        case 'asset_complete':
            addOrUpdateAsset(message.data.asset_id, message.data.status);
            break;
        case 'execution_complete':
            // Show completion, then transition to idle
            showCompletionSummary(message.data);
            // After a brief delay, reload as idle with last run
            setTimeout(() => enterIdleMode(), 2000);
            break;
    }
}
```

### Example 3: Runs Page Template Structure

```html
{% extends "base.html" %}
{% block title %}Active Runs{% endblock %}
{% block head_extra %}
<style>
    /* Page-specific styles */
    body { overflow: auto; }
    .runs-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 6rem 2rem 2rem;
    }
    /* Asset status rows, progress indicator, etc. */
</style>
{% endblock %}
{% block content %}
    <!-- Header (each page defines its own per Phase 4 decision) -->
    <header class="header fixed top-0 left-0 right-0 z-50 p-4 ...">
        <!-- LATTICE logo, title, theme toggle -->
    </header>

    <div class="runs-container">
        <!-- Live mode: visible during execution -->
        <div id="live-panel" style="display: none;">
            <h2 class="section-title">ACTIVE EXECUTION</h2>
            <!-- Progress bar / counter -->
            <!-- Asset status table with clickable rows -->
        </div>

        <!-- Idle mode: visible when no execution running -->
        <div id="idle-panel" style="display: none;">
            <h2 class="section-title">LAST COMPLETED RUN</h2>
            <!-- Last run summary card -->
        </div>

        <!-- Loading state -->
        <div id="loading-panel">
            <!-- Loading indicator -->
        </div>
    </div>
{% endblock %}
{% block scripts %}
<script>
    // Initialization, WebSocket connection, mode switching
</script>
{% endblock %}
```

### Example 4: Refactored asset_live.html Header (Back Button Pattern)

```html
<!-- BEFORE (popup-style): -->
<div class="live-header">
    <div class="live-header-left">
        <span class="live-header-title">LATTICE</span>
        <span class="live-header-separator">//</span>
        <span class="live-header-asset">{{ asset_key }}</span>
        <span class="live-badge">LIVE</span>
    </div>
    <!-- theme toggle -->
</div>

<!-- AFTER (full-page with back button): -->
<header class="header fixed top-0 left-0 right-0 z-50 p-4 flex items-center justify-between">
    <div class="flex items-center gap-4">
        <a href="/runs" class="back-link">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
            </svg>
            BACK TO RUNS
        </a>
        <div class="header-divider"></div>
        <span class="live-header-asset">{{ asset_key }}</span>
        <span class="live-badge">LIVE</span>
    </div>
    <div class="flex items-center gap-3">
        <!-- theme toggle button -->
    </div>
</header>
```

The `.back-link` class already exists in `asset_detail.html` with proper styling. Reuse it.

### Example 5: Clickable Asset Row on Runs Page (RUNS-03)

```javascript
function renderAssetRow(assetId, status) {
    const row = document.createElement('tr');
    row.className = `asset-row status-${status}`;

    // Make running assets clickable
    if (status === 'running' || status === 'completed' || status === 'failed') {
        row.style.cursor = 'pointer';
        row.addEventListener('click', () => {
            window.location.href = '/asset/' + encodeURIComponent(assetId) + '/live';
        });
    }

    // ... populate cells with status indicator, name, duration, etc.
    return row;
}
```

Note: All assets in any status could be clickable (to view their logs). The requirement says "clicking a running asset" but making all clickable is a better UX. The planner can decide.

### Example 6: Existing WebSocket Message Types (Reference)

```javascript
// Messages received from /ws/execution (ExecutionManager.broadcast):
// These are already being used by graph.js -- runs page uses the same messages.

// 1. Asset starts executing
{type: "asset_start", data: {asset_id: "group/name"}}

// 2. Asset finishes (success or failure)
{type: "asset_complete", data: {
    asset_id: "group/name",
    status: "completed" | "failed",
    duration_ms: 123.45,
    error: null | "Error message"
}}

// 3. Memory update (sent every 0.5s during execution)
{type: "memory_update", data: {
    rss_mb: 45.2,
    vms_mb: 120.5,
    percent: 2.1,
    timestamp: "2026-02-07T..."
}}

// 4. Partition starts (multi-date execution)
{type: "partition_start", data: {
    current_date: "2026-01-15",
    current_date_index: 1,
    total_dates: 5
}}

// 5. Partition completes
{type: "partition_complete", data: {
    date: "2026-01-15",
    status: "completed" | "failed",
    duration_ms: 1234.5,
    completed_count: 10,
    failed_count: 0
}}

// 6. Entire execution finishes
{type: "execution_complete", data: {
    run_id: "abc12345",
    status: "completed" | "failed",
    duration_ms: 5678.9,
    completed_count: 10,
    failed_count: 0,
    total_dates: 1
}}

// 7. Check results (broadcast after all checks run)
{type: "checks_complete", data: {
    total: 5,
    passed: 4,
    failed: 1,
    results: [...]
}}
```

## State of the Art

| Old Approach (v1) | Current Approach (v2) | When Changed | Impact |
|---|---|---|---|
| Popup windows for live monitoring | Full-page with sidebar navigation | v2.0 Phase 5 | Standard browser navigation, sidebar always available |
| Graph page as the only execution monitor | Dedicated Active Runs page | v2.0 Phase 5 | Clear separation of graph visualization vs execution monitoring |
| Refocus button on popup | Back button on full page | v2.0 Phase 5 | Standard navigation pattern, works with browser back/forward |
| No "last run" idle state | Active Runs page shows last completed run | v2.0 Phase 5 | Useful even when no execution is running |

**Deprecated/outdated (to be removed in Phase 7, not Phase 5):**
- The `window.open()` call in graph.js `openAssetWindow()` -- will be replaced with `window.location.href` in Phase 6
- The popup-blocked notice in graph.js -- no longer needed when navigating via links
- The refocus button in asset_live.html -- replaced by back button in Phase 5
- The `window.name = 'lattice_graph'` in graph.js -- popup window targeting concept

## Open Questions

1. **Should the runs page show the execution plan (all assets as "pending") before execution starts, or only show assets as they appear?**
   - What we know: `GET /api/execution/status` returns `asset_statuses` which only includes assets that have started. `GET /api/plan` returns the full execution plan.
   - What's unclear: Is it better UX to show all planned assets as "queued" from the start, or to have them appear dynamically as execution reaches them?
   - Recommendation: Start with only showing assets as they appear (via WebSocket messages). This is simpler and avoids the complexity of determining which plan is being executed. The progress counter (`completed/total`) from `ExecutionStatusSchema` already provides the overview. If all-assets-upfront is desired, a second plan could fetch `GET /api/plan` and merge with WebSocket updates.

2. **Should clicking any asset on the runs page navigate to live logs, or only running assets?**
   - What we know: RUNS-03 says "Clicking a running asset on the active runs page navigates to its live logs page."
   - What's unclear: Should completed/failed assets also be clickable?
   - Recommendation: Make all assets clickable. The live logs page already handles the `completed` and `failed` states (shows completion banner, logs are preserved in replay buffer). Restricting to only "running" assets is a worse UX.

3. **Where does the /runs route go -- routes.py or a new routes_runs.py?**
   - What we know: The current structure has `routes.py` (graph, asset routes) and `routes_history.py` (history routes).
   - What's unclear: Should the runs route be in routes.py (it's a simple single-route) or a new file for organizational clarity?
   - Recommendation: Add it to `routes.py` since it's a single route and closely related to the existing asset/execution routes. Creating a separate file for one route is overkill.

4. **What should the asset_live.html back button link to?**
   - What we know: RECV-03 says "back button." The user could arrive at asset_live from the runs page or potentially from other places.
   - What's unclear: Should it always link to `/runs`, use JavaScript `history.back()`, or be context-aware?
   - Recommendation: Always link to `/runs` (the active runs page). This is predictable and correct -- if the user was monitoring execution, they want to go back to the runs overview. Using `history.back()` is fragile (what if they navigated from a bookmark?). A static `/runs` link is simple and reliable.

## Sources

### Primary (HIGH confidence)

- **Codebase analysis** -- Read and analyzed all source files: `execution.py` (ExecutionManager, WebSocket endpoints, message types), `routes.py` (existing route patterns), `routes_history.py` (history API endpoints), `app.py` (app factory), `schemas_execution.py` (ExecutionStatusSchema, AssetStatusSchema), `executor.py` (ExecutionState, AssetStatus enum), all 5 HTML templates, `graph.js` (WebSocket client pattern), `styles.css` (sidebar CSS)
- **Phase 4 research and verification** -- Confirmed base.html structure, `current_page` pattern, sidebar CSS, template inheritance pattern
- **Planning documents** -- ROADMAP.md, REQUIREMENTS.md, STATE.md for requirements RUNS-01 through RUNS-04 and RECV-03

### Secondary (MEDIUM confidence)

- **WebSocket reconnection patterns** -- Standard approach (reconnect on close with backoff) used in both `graph.js` and `asset_live.html`
- **Dual-mode UI pattern** -- Common pattern for dashboards showing live vs historical data; verified against existing codebase patterns

### Tertiary (LOW confidence)

- None. All findings are based on direct codebase analysis.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Using existing Jinja2, FastAPI routes, WebSocket endpoints, no new dependencies
- Architecture: HIGH -- All backend infrastructure exists; this is primarily a frontend/template effort
- Pitfalls: HIGH -- Identified from direct analysis of existing WebSocket client code, execution state model, and template patterns

**Research date:** 2026-02-07
**Valid until:** 2026-03-07 (stable -- no external dependencies to go stale)

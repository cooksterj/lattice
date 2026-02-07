# Architecture: Sidebar Navigation, Full-Page Views, and Partial DAG Re-Execution

**Research Date:** 2026-02-07
**Dimension:** Architecture for v2.0 sidebar navigation, full-page views, and failed asset re-execution
**Status:** Complete
**Confidence:** HIGH (based on thorough codebase analysis; all integration points verified against source code)

---

## Executive Summary

This document defines the architecture for transforming Lattice's web UI from a popup-window model (v1.0) to a sidebar-navigation model (v2.0). The changes span three dimensions: (1) persistent sidebar navigation via Jinja2 template inheritance, (2) full-page views replacing popup windows, and (3) ExecutionManager extensions for partial DAG re-execution from a failed asset downstream. Every integration point is mapped against the existing codebase with explicit identification of what changes, what is new, and what remains untouched.

The existing WebSocket per-asset streaming infrastructure, log capture, and replay buffer all remain intact -- they simply deliver to in-page components instead of popup windows. The heaviest architectural change is introducing Jinja2 template inheritance (base template with sidebar) across all 4 existing templates, followed by a new ExecutionPlan.resolve_from_assets() capability for partial re-execution.

---

## Existing Architecture (v1.0 Baseline)

Before defining changes, here is the current component layout as verified from source code.

### Current Templates (All Standalone, No Inheritance)

| Template | Route | Purpose | Lines |
|----------|-------|---------|-------|
| `index.html` | `GET /` | D3.js graph with execution controls | 120 |
| `asset_live.html` | `GET /asset/{key}/live` | Popup window: live log streaming | 891 |
| `asset_detail.html` | `GET /asset/{key}` | Popup window: run history per asset | 878 |
| `history.html` | `GET /history` | Global run history page | 861 |

Each template is a complete standalone HTML document with its own `<head>`, header, corner decorations, theme toggle, and inline `<script>` blocks. There is massive duplication -- the header/nav, theme toggle, and corner decorations are copy-pasted across all 4 files.

### Current Navigation Model

- Header has two nav links: GRAPH (/) and HISTORY (/history)
- `index.html` has a right-slide sidebar (for asset details) -- this is the "ASSET DATA" panel that shows on node click, NOT a navigation sidebar
- `asset_live.html` opens via `window.open()` from `graph.js`
- `asset_detail.html` opens via link from `asset_live.html`
- No back button pattern; user manages windows manually

### Current Execution Model

- `ExecutionManager.run_execution()` accepts `target` (single asset key) and `include_downstream` (boolean)
- `ExecutionPlan.resolve()` builds the plan using `DependencyGraph.get_all_upstream()` or `get_all_downstream()`
- The `/api/execution/start` endpoint accepts `ExecutionStartRequest` with `target`, `include_downstream`, `execution_date`, `execution_date_end`
- Execution is single-instance: `if manager.is_running: raise HTTPException(409)`
- There is no concept of "re-run from this asset" or "run only these specific assets"

### Current WebSocket Infrastructure

- `/ws/execution` -- global broadcast to all connected clients (graph page)
- `/ws/asset/{key}` -- per-asset scoped streaming with replay buffer
- `ExecutionManager._asset_subscribers: dict[str, set[WebSocket]]` -- per-asset subscriber registry
- `ExecutionManager._replay_buffers: dict[str, deque[dict]]` -- 500-entry replay per asset
- `asyncio.Queue` bridge from sync logging thread to async WebSocket delivery

---

## Architecture Changes for v2.0

### Change Category Overview

| Category | Component | Change Type |
|----------|-----------|-------------|
| Template Inheritance | New `base.html` template | **NEW** |
| Template Inheritance | All 4 existing templates | **MODIFIED** (extend base) |
| Navigation Sidebar | Sidebar HTML/CSS/JS in base.html | **NEW** |
| Active Runs Page | `runs_active.html` template | **NEW** |
| Active Runs Page | `/runs/active` route | **NEW** |
| Active Runs API | `GET /api/execution/active` | **NEW** |
| Live Logs Full Page | `asset_live.html` | **MODIFIED** (remove popup chrome, add back button) |
| Graph Click Behavior | `graph.js` | **MODIFIED** (select/highlight, not window.open) |
| Partial Re-Execution | `ExecutionPlan` | **MODIFIED** (new resolve mode) |
| Partial Re-Execution | `ExecutionManager` | **MODIFIED** (support multi-asset target) |
| Partial Re-Execution | `ExecutionStartRequest` schema | **MODIFIED** (accept asset list) |
| Partial Re-Execution | Execute button in `graph.js` | **MODIFIED** (context-aware) |
| Cleanup | Remove popup code from `graph.js` | **MODIFIED** |
| Cleanup | Remove popup chrome from `asset_live.html` | **MODIFIED** |

---

## Component 1: Jinja2 Template Inheritance (Base Template with Sidebar)

### Problem

All 4 templates duplicate header, navigation, theme toggle, corner decorations, font imports, and CSS includes. Adding a persistent sidebar means adding it to all 4 (soon 5+) pages. Without template inheritance, this is unmaintainable.

### Solution: `base.html` Base Template

Create a base template that owns the common page shell. All pages extend it.

**File:** `src/lattice/web/templates/base.html`

**Blocks defined:**

| Block | Purpose | Default Content |
|-------|---------|-----------------|
| `{% block title %}` | Page title | `LATTICE` |
| `{% block head_extra %}` | Additional `<head>` content (per-page CSS) | Empty |
| `{% block content %}` | Main page content area | Empty |
| `{% block scripts %}` | Page-specific JavaScript | Empty |

**What the base template owns:**

1. `<!DOCTYPE html>`, `<html>`, `<head>` with shared CSS/font imports
2. The persistent navigation sidebar (left side, always visible)
3. The top header bar with logo, title, and theme toggle
4. Corner decorations
5. Theme toggle JavaScript
6. Shared utility functions (escapeHtml, formatDuration, formatDate)

### Navigation Sidebar Structure

The sidebar is a narrow vertical bar on the LEFT side of every page (not the existing right-side "ASSET DATA" panel on index.html, which is a detail panel for the selected node).

**Sidebar elements:**
- GRAPH icon/link (navigates to `/`)
- HISTORY icon/link (navigates to `/history`)
- ACTIVE RUNS icon/link (navigates to `/runs/active`) -- with a live indicator dot when execution is running
- The sidebar collapses to icon-only width (~60px) to maximize content area

**Active run indicator:** The sidebar needs to know if an execution is running. Two approaches:

1. **Server-side rendering:** Pass `is_running` to every template context. Requires modifying every route handler.
2. **Client-side polling:** A small JS snippet in `base.html` polls `GET /api/execution/status` every 2-3 seconds and updates the indicator.

**Recommendation:** Client-side polling. It decouples the sidebar from route handler changes, and the endpoint already exists. The poll is lightweight (the endpoint returns a small JSON object) and only needs to check `is_running` boolean.

### Template Migration Strategy

Each existing template converts from standalone to extending `base.html`:

**Before (standalone):**
```html
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <title>LATTICE // Asset Graph</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- ... all shared imports ... -->
    <link rel="stylesheet" href="/static/css/styles.css?v=9">
</head>
<body class="font-mono">
    <!-- header, nav, corner decorations, content, scripts -->
</body>
</html>
```

**After (extends base):**
```html
{% extends "base.html" %}

{% block title %}LATTICE // Asset Graph{% endblock %}

{% block head_extra %}
<!-- page-specific CSS if any -->
{% endblock %}

{% block content %}
<!-- just the page content, no header/nav/decorations -->
{% endblock %}

{% block scripts %}
<script src="/static/js/graph.js?v=17"></script>
{% endblock %}
```

### Impact on Existing Templates

| Template | Changes Required |
|----------|-----------------|
| `index.html` | Remove standalone HTML shell; keep graph container and sidebar detail panel as `{% block content %}`; move graph.js to `{% block scripts %}` |
| `asset_live.html` | Remove standalone HTML shell and popup-specific header; convert to full-page layout extending base; keep WebSocket logic in `{% block scripts %}` |
| `asset_detail.html` | Remove standalone HTML shell and header; convert to full-page layout extending base; keep history fetch logic in `{% block scripts %}` |
| `history.html` | Remove standalone HTML shell and header; convert to full-page layout extending base; keep summary/runs logic in `{% block scripts %}` |

### Layout Architecture

```
+----------------------------------------------------------+
|  [LOGO]  LATTICE  //  ASSET ORCHESTRATION    [theme btn]  |  <- header (in base.html)
+------+---------------------------------------------------+
|      |                                                    |
| ICON |                                                    |
| ICON |              {% block content %}                   |
| ICON |                                                    |
|      |              (page-specific content)                |
|      |                                                    |
|      |                                                    |
+------+---------------------------------------------------+
  ^                    ^
  |                    |
  Sidebar (base.html)  Content area (child template)
```

On the graph page specifically, the existing right-side "ASSET DATA" detail panel remains as part of `index.html`'s content block -- it is NOT the navigation sidebar.

---

## Component 2: Full-Page Views with Back Navigation

### Problem

v1.0 uses popup windows for asset live monitoring and asset detail/history. v2.0 replaces these with standard full-page navigation.

### Solution: Standard Page Navigation

Every view is a full page. Navigation uses standard `<a>` links and the browser back button. No popups, no modals for primary views.

### Page Hierarchy

```
/                          Main graph page
/asset/{key}/live          Asset live monitoring (full page)
/asset/{key}               Asset detail + run history (full page)
/history                   Global run history (full page)
/runs/active               Active/queued runs (full page) -- NEW
```

### Back Button Pattern

Each sub-page includes a "BACK TO GRAPH" link (already exists in `asset_detail.html` at line 524-529). This pattern extends to all sub-pages:

- `/asset/{key}/live` -> back to `/`
- `/asset/{key}` -> back to `/` (already exists)
- `/history` -> back to `/` (via nav sidebar)
- `/runs/active` -> back to `/` (via nav sidebar)

The sidebar provides persistent navigation regardless of depth, so the back link is supplementary.

### Changes to `asset_live.html`

Currently designed as a popup window with:
- Compact popup header (line 437-456)
- "REFOCUS GRAPH" button using `window.open('/#refocus', 'lattice_graph')` (line 486)
- "RUN HISTORY" button using `window.open('/asset/' + ASSET_KEY, '_blank')` (line 489)

**v2.0 changes:**
- Remove popup-specific compact header (replaced by base.html header + sidebar)
- Remove "REFOCUS GRAPH" button (no longer needed -- user navigates back via sidebar or back button)
- Change "RUN HISTORY" link to standard `<a href="/asset/{{ asset_key }}">` navigation
- Add "BACK TO GRAPH" link (same pattern as asset_detail.html)
- The WebSocket connection logic, log rendering, state machine, and completion banner all remain unchanged -- they work identically in a full page vs. a popup

---

## Component 3: Active Runs Page

### Problem

Users need a page showing what is currently running, what is queued, and what has completed in the current (or most recent) execution.

### Solution: New `/runs/active` Route and Template

**Route:** `GET /runs/active` -- serves `runs_active.html`
**API:** `GET /api/execution/active` -- returns detailed per-asset status with timing

### API Design: `GET /api/execution/active`

This extends the existing `GET /api/execution/status` endpoint which already returns:
```json
{
  "is_running": true,
  "run_id": "abc123",
  "started_at": "...",
  "current_asset": "data/transform",
  "total_assets": 10,
  "completed_count": 5,
  "failed_count": 1,
  "asset_statuses": [
    {"id": "data/raw", "status": "completed", "duration_ms": 123.4, ...},
    {"id": "data/transform", "status": "running", ...}
  ]
}
```

The existing endpoint already provides everything needed. Rather than creating a new endpoint, the active runs page can use `GET /api/execution/status` directly plus the existing `/ws/execution` WebSocket for real-time updates.

**When idle (no execution running):** The page shows the most recent completed run from history. This requires fetching `GET /api/history/runs?limit=1` to get the latest run, then `GET /api/history/runs/{run_id}` for details.

### Template Behavior

**During execution:**
- Table/list of all assets in the execution plan with status (pending/running/completed/failed/skipped)
- Running assets highlighted with animation
- Clicking a running/completed/failed asset navigates to `/asset/{key}/live`
- Real-time updates via `/ws/execution` WebSocket (same as graph page uses)
- Progress summary (X/Y completed, Z failed)

**When idle:**
- Shows the last completed run's asset results
- Each asset row is clickable, navigating to `/asset/{key}`

### File Impact

| File | Change |
|------|--------|
| `src/lattice/web/templates/runs_active.html` | **NEW** -- extends base.html |
| `src/lattice/web/routes.py` | **MODIFIED** -- add `GET /runs/active` route |

No new API endpoints required -- existing endpoints provide all necessary data.

---

## Component 4: Graph Click Behavior Change (Select/Highlight)

### Problem

Currently, clicking a graph node calls `this.openAssetWindow(d.id)` which opens a popup via `window.open()`. v2.0 changes this to select/highlight the node and update the Execute button to be context-aware.

### Current Code Path (graph.js lines 526-530)

```javascript
.on('click', (event, d) => {
    if (event.defaultPrevented) return;
    event.stopPropagation();
    this.openAssetWindow(d.id);
});
```

### New Click Behavior

**Click on node:**
1. Toggle selection state on the node (highlight it and its downstream dependencies)
2. Update the right-side "ASSET DATA" detail panel (existing `selectNode()` method at line 701)
3. Make the Execute button context-aware -- if a node is selected, Execute runs from that node downstream

**Visual feedback for selection:**
- Selected node gets a distinct border (`.node.selected rect` style already exists in CSS at line 681)
- Downstream nodes of the selected node get a subtle highlight (e.g., dashed border or opacity change)
- This helps the user see what will be re-executed

**Click on background (deselect):**
- Already handled at line 543: `this.svg.on('click', () => { ... })`

### Context-Aware Execute Button

**Current behavior:** Execute button always runs the full pipeline (or with a date parameter).

**New behavior:**
- If no node selected: Execute runs the full pipeline (unchanged)
- If a node is selected: Execute runs from that node + all downstream dependents
- The button label changes to indicate scope: "EXECUTE ALL" vs "EXECUTE FROM [asset_name]"
- If the selected node is a failed node from a previous run, the label says "RE-EXECUTE FROM [asset_name]"

### Changes to `startExecution()` (graph.js line 973)

Currently builds `requestBody` with optional date parameters. New logic:

```javascript
// If a node is selected, add it as the target with include_downstream=true
if (this.selectedNode) {
    requestBody.target = this.selectedNode.id;
    requestBody.include_downstream = true;
}
```

This uses the EXISTING `target` and `include_downstream` fields in `ExecutionStartRequest` (schemas_execution.py line 63-64). The existing `run_execution()` in ExecutionManager already passes these to `ExecutionPlan.resolve()`, which already supports `include_downstream=True` (plan.py line 102-107).

**This means partial re-execution from a selected node already works at the API level.** The only change needed is wiring the graph UI selection to pass `target` and `include_downstream` in the request body.

### Removed Code

The following methods/code in `graph.js` are removed:
- `openAssetWindow(assetId)` (lines 635-657) -- popup opening logic
- `showPopupBlockedNotice(url)` (lines 659-699) -- popup blocked fallback
- `this.assetWindows = new Map()` (line 27) -- window tracking
- `window.name = 'lattice_graph'` (line 28) -- named window for refocus

---

## Component 5: Partial DAG Re-Execution

### Problem

When an asset fails, users want to fix the issue and re-run from that asset downstream without re-running upstream assets that already succeeded.

### Existing Support Analysis

**Already works (verified from source code):**

1. `ExecutionPlan.resolve(registry, target="failed/asset", include_downstream=True)` (plan.py lines 102-107):
   - Gets all upstream dependencies of the target
   - Adds the target itself
   - Gets all downstream dependents
   - Filters topological sort to this subset

2. `ExecutionStartRequest` already has `target: str | None` and `include_downstream: bool` fields (schemas_execution.py lines 63-64)

3. `ExecutionManager.run_execution()` already passes `target` and `include_downstream` through to `ExecutionPlan.resolve()` (execution.py lines 325-327)

**The gap:** When `include_downstream=True`, the plan includes ALL upstream dependencies of the target plus the target plus all downstream. This means it re-runs upstream assets that already succeeded. For a true "re-execute from failure point", we want to run ONLY the failed asset and its downstream dependents, skipping upstream assets.

### Solution: New `include_upstream` Parameter

Add an `include_upstream: bool = True` parameter to `ExecutionPlan.resolve()`:

```python
# New behavior:
# include_upstream=True, include_downstream=False  -> target + all upstream (current default)
# include_upstream=True, include_downstream=True   -> target + upstream + downstream (current behavior)
# include_upstream=False, include_downstream=True  -> target + downstream ONLY (new: re-execute from failure)
# include_upstream=False, include_downstream=False -> target ONLY
```

**Implementation in `ExecutionPlan.resolve()` (plan.py):**

```python
if include_downstream and not include_upstream:
    # Re-execute from this asset: target + downstream only
    required = {target_key}
    required.update(graph.get_all_downstream(target_key))
elif include_downstream:
    # Full subgraph: upstream + target + downstream
    required = graph.get_all_upstream(target_key)
    required.add(target_key)
    required.update(graph.get_all_downstream(target_key))
else:
    # Target + upstream (existing default)
    required = graph.get_all_upstream(target_key)
    required.add(target_key)
```

**Important consideration:** When skipping upstream, the IOManager must already have the values for upstream assets from the previous execution. In the current architecture, `MemoryIOManager` is created fresh each execution in `run_execution()` (execution.py line 364). This means upstream assets' values are NOT available.

**Resolution options:**

1. **Option A: Re-run upstream but skip execution (fastest integration):** Include upstream assets in the plan but mark them to use cached results. This requires significant executor changes.

2. **Option B: Pre-load upstream values into IOManager (clean, recommended):** Before execution starts, load the outputs of upstream assets from the previous run's stored results into the IOManager. This requires the IOManager to be pre-seeded.

3. **Option C: Just re-run everything (simplest, good enough for v2.0):** Use the existing `include_downstream=True` behavior which re-runs upstream too. The user can accept this since upstream assets already succeeded and will succeed again quickly. This is what Dagster and Airflow do by default.

**Recommendation: Option C for v2.0.** The existing `include_downstream=True` already provides the correct behavior for "re-execute from this asset" -- it ensures all upstream dependencies are available. Re-running already-succeeded upstream assets is a minor cost compared to the architectural complexity of Options A or B. This can be optimized in a future version.

### API Changes

| File | Change |
|------|--------|
| `schemas_execution.py` | No change needed -- `target` and `include_downstream` already exist |
| `execution.py` | No change needed -- already passes through to `ExecutionPlan.resolve()` |
| `plan.py` | No change needed for v2.0 (Option C uses existing behavior) |
| `graph.js` | **MODIFIED** -- `startExecution()` passes `target` and `include_downstream` when a node is selected |

---

## Component 6: Active Run Indicator in Sidebar

### Problem

The navigation sidebar needs to show whether an execution is currently running (a pulsing indicator next to the "Active Runs" icon).

### Solution: Client-Side Status Polling in Base Template

A small JavaScript snippet in `base.html` polls `GET /api/execution/status` every 3 seconds:

```javascript
async function checkExecutionStatus() {
    try {
        const resp = await fetch('/api/execution/status');
        const data = await resp.json();
        const indicator = document.getElementById('sidebar-run-indicator');
        if (indicator) {
            indicator.classList.toggle('active', data.is_running);
        }
    } catch (e) { /* silently ignore */ }
}
setInterval(checkExecutionStatus, 3000);
checkExecutionStatus(); // immediate first check
```

**Why polling instead of WebSocket:** The sidebar indicator is a simple boolean (running or not). Adding a WebSocket connection to every page just for this would be overkill. The poll is ~100 bytes every 3 seconds. If the user is on the graph page, the graph page's WebSocket already provides real-time updates -- the poll is just for non-graph pages.

---

## Data Flow Diagrams

### Graph Click -> Selection -> Execute (v2.0)

```
User clicks asset node on graph
       |
       v
graph.js click handler:
  1. Toggle selection (highlight node + downstream)
  2. Show asset details in right panel (existing selectNode)
  3. Update Execute button label ("EXECUTE FROM [name]")
       |
User clicks Execute button
       |
       v
graph.js startExecution():
  1. Build request body with target=selectedNode.id, include_downstream=true
  2. POST /api/execution/start
       |
       v
Server: ExecutionManager.run_execution(registry, target, include_downstream=True)
  1. ExecutionPlan.resolve(registry, target, include_downstream=True)
  2. Plan includes: target's upstream + target + target's downstream
  3. Execute plan normally
  4. Broadcast status updates via /ws/execution
       |
       v
graph.js receives WebSocket updates:
  - Nodes update status (pending -> running -> completed/failed)
  - Execute button resets on completion
```

### Page Navigation (v2.0)

```
Any page (extends base.html)
       |
       +-- Sidebar: GRAPH icon -> GET / -> index.html
       |
       +-- Sidebar: HISTORY icon -> GET /history -> history.html
       |
       +-- Sidebar: ACTIVE icon -> GET /runs/active -> runs_active.html
       |
       +-- In-page link: "View Asset" -> GET /asset/{key} -> asset_detail.html
       |
       +-- In-page link: "View Live" -> GET /asset/{key}/live -> asset_live.html
       |
       +-- Browser back button -> previous page (standard navigation)
```

### Active Runs Page Data Flow

```
User navigates to /runs/active
       |
       v
Server: GET /runs/active -> render runs_active.html
       |
       v
Client JavaScript:
  1. Fetch GET /api/execution/status
  2. If is_running:
     a. Render asset status table from asset_statuses array
     b. Connect to /ws/execution WebSocket for real-time updates
     c. Update table as asset_start/asset_complete messages arrive
  3. If NOT is_running:
     a. Fetch GET /api/history/runs?limit=1 for latest run
     b. Fetch GET /api/history/runs/{run_id} for details
     c. Render last run's asset results
       |
User clicks an asset row
       |
       v
Navigate to:
  - If running/queued: /asset/{key}/live (live monitoring)
  - If completed/failed/idle: /asset/{key} (detail + history)
```

---

## File Impact Summary

### New Files

| File | Purpose |
|------|---------|
| `src/lattice/web/templates/base.html` | Base template with sidebar, header, theme toggle, shared CSS/JS |
| `src/lattice/web/templates/runs_active.html` | Active/queued runs page (extends base) |

### Modified Files

| File | Changes |
|------|---------|
| `src/lattice/web/templates/index.html` | Convert to extend base.html; remove duplicate header/nav/theme/decorations; keep graph content and right-side detail panel |
| `src/lattice/web/templates/asset_live.html` | Convert to extend base.html; remove popup header and refocus button; add back-to-graph link; keep WebSocket/log/state-machine logic |
| `src/lattice/web/templates/asset_detail.html` | Convert to extend base.html; remove duplicate header/nav/theme/decorations; keep asset info and history table |
| `src/lattice/web/templates/history.html` | Convert to extend base.html; remove duplicate header/nav/theme/decorations; keep summary/runs/modal logic |
| `src/lattice/web/static/js/graph.js` | (1) Change click handler from `openAssetWindow` to `selectNode` + highlight downstream; (2) Make Execute button context-aware (pass `target` + `include_downstream`); (3) Remove `openAssetWindow`, `showPopupBlockedNotice`, `assetWindows` Map, window.name |
| `src/lattice/web/static/css/styles.css` | Add sidebar navigation styles, active run indicator styles |
| `src/lattice/web/routes.py` | Add `GET /runs/active` route handler |
| `src/lattice/web/app.py` | No changes needed (new route added to existing router in routes.py) |

### Unchanged Files

| File | Why Unchanged |
|------|---------------|
| `src/lattice/executor.py` | Execution engine is callback-driven; no UI knowledge |
| `src/lattice/plan.py` | Existing `resolve(target, include_downstream=True)` already provides needed behavior |
| `src/lattice/graph.py` | Graph algorithms unchanged; `get_all_downstream` already exists |
| `src/lattice/web/execution.py` | ExecutionManager and WebSocket endpoints unchanged; existing `run_execution()` already supports target + include_downstream |
| `src/lattice/web/routes_history.py` | History API endpoints unchanged |
| `src/lattice/web/schemas.py` | No new graph/asset schemas needed |
| `src/lattice/web/schemas_execution.py` | ExecutionStartRequest already has `target` and `include_downstream` fields |
| `src/lattice/observability/log_capture.py` | Log capture infrastructure unchanged |
| All test files | Updated separately in testing phase |

---

## Design Decisions

### D1: Left Sidebar Navigation (Not Top Nav Expansion)

**Decision:** Persistent vertical sidebar on the left with icon links.

**Rationale:**
- The graph page uses the full viewport width for D3.js rendering; a top nav bar that takes more vertical space would reduce graph area
- The existing right-side "ASSET DATA" panel slides over the graph; a left sidebar keeps this asymmetric and avoids collision
- Vertical icon bars are standard in developer tools (VS Code, GitHub, Dagster)
- The sidebar is always visible, making navigation one-click from any page

**Alternative considered:** Expanding the existing top nav bar (currently has GRAPH and HISTORY links). Rejected because adding Active Runs and future pages would crowd the horizontal space, and the graph page header already has execution controls.

### D2: Client-Side Polling for Run Indicator (Not WebSocket Everywhere)

**Decision:** Poll `GET /api/execution/status` every 3 seconds in the base template.

**Rationale:**
- WebSocket on every page adds complexity and connection management overhead
- The poll payload is tiny (~100 bytes) and infrequent (every 3 seconds)
- On the graph page, the existing `/ws/execution` WebSocket already provides real-time updates -- the poll is a fallback for non-graph pages
- Simpler to implement and debug than managing WebSocket lifecycle in the base template

### D3: Re-Use Existing `include_downstream=True` for Partial Re-Execution (Not Custom Plan)

**Decision:** Use the existing `ExecutionPlan.resolve(target, include_downstream=True)` for re-executing from a failed asset.

**Rationale:**
- This re-runs upstream assets too, but they already succeeded and will succeed again quickly
- Avoids the complexity of IOManager pre-seeding or executor skip logic
- Matches behavior of Dagster's "Materialize Selection" and Airflow's "Clear Downstream"
- Can be optimized later (skip already-succeeded upstream) if performance becomes an issue

### D4: No New WebSocket Endpoints

**Decision:** Reuse existing `/ws/execution` and `/ws/asset/{key}` endpoints.

**Rationale:**
- The active runs page needs the same data as the graph page (asset_start, asset_complete events) -- `/ws/execution` provides this
- The live logs page needs the same per-asset streaming as the popup window -- `/ws/asset/{key}` provides this
- No new WebSocket protocol changes needed; the message format is identical

### D5: Template Inheritance with Inline Scripts (Not Separate JS Files)

**Decision:** Keep per-page JavaScript inline in `{% block scripts %}` rather than extracting to separate `.js` files.

**Rationale:**
- The existing codebase uses inline `<script>` blocks in all templates
- Extracting to separate files would require a module bundler or careful script ordering
- Jinja2 template variables (like `{{ asset_key }}`) are used directly in script blocks; separating requires a different injection mechanism
- For a development tool with ~5 pages, the simplicity of inline scripts outweighs the organizational benefit of separate files
- The shared utility functions (theme toggle, formatDate, etc.) DO move to base.html's script block, eliminating the worst duplication

---

## Build Order (Dependency Chain)

The following order reflects what must exist before each subsequent component can be built.

### Phase 1: Template Inheritance Foundation

**Build:** `base.html` base template with sidebar navigation + convert all 4 existing templates to extend it.

**Why first:** Every subsequent change (new pages, modified pages) depends on the template inheritance being in place. Building the sidebar first establishes the navigation framework.

**Deliverables:**
- `base.html` with sidebar, header, theme toggle, corner decorations, shared CSS/JS
- `index.html` converted to extend `base.html`
- `asset_detail.html` converted to extend `base.html`
- `history.html` converted to extend `base.html`
- `asset_live.html` converted to extend `base.html` (popup chrome removed)

**Risk:** This is the highest-risk phase because it touches all 4 existing templates. Careful CSS isolation needed to ensure the graph page layout (full viewport D3.js SVG) works correctly with the sidebar.

**Testing:** Visual inspection of all 4 pages; verify theme toggle works; verify navigation links work; verify graph page execution still functions.

### Phase 2: Graph Click Behavior + Context-Aware Execute

**Build:** Modify `graph.js` to select/highlight nodes on click and make Execute button context-aware.

**Why second:** This is the core UX change that replaces popup windows. It depends on Phase 1 (sidebar navigation must be in place so users can navigate to detail pages via sidebar instead of popups).

**Deliverables:**
- Click handler changed to `selectNode` + downstream highlighting
- Execute button becomes "EXECUTE FROM [name]" when a node is selected
- `startExecution()` passes `target` and `include_downstream` when applicable
- Remove `openAssetWindow`, `showPopupBlockedNotice`, window tracking code

**Testing:** Click a node, verify selection highlight; click Execute with selection, verify it runs from that node; click Execute without selection, verify full pipeline runs.

### Phase 3: Active Runs Page

**Build:** New `runs_active.html` template + route.

**Why third:** Depends on Phase 1 (template inheritance) and benefits from Phase 2 (execution infrastructure already working). The active runs page provides the "what's running now" view that the sidebar links to.

**Deliverables:**
- `runs_active.html` extending `base.html`
- `GET /runs/active` route in `routes.py`
- JavaScript for fetching execution status and rendering asset list
- WebSocket integration for real-time updates during execution
- Last-run fallback when idle

**Testing:** Navigate to /runs/active during execution, verify real-time updates; navigate when idle, verify last run display; click asset rows, verify navigation.

### Phase 4: Polish and Cleanup

**Build:** Remove remaining v1 popup artifacts; finalize sidebar active state indicators; CSS polish.

**Deliverables:**
- Client-side polling for run indicator in sidebar
- Active nav link highlighting (current page)
- Remove any remaining popup-related CSS/JS
- Cache buster version bumps on CSS and JS files

---

## CSS Strategy

### Sidebar Styles

The navigation sidebar requires new CSS in `styles.css`. Key considerations:

1. **Z-index management:** The sidebar must be above the graph SVG but below modals. Current z-index usage:
   - Corner decorations: z-20
   - Execution progress: z-40
   - Memory panel: z-40
   - Execution controls: z-40
   - Header: z-10 (in index.html), z-50 (in other pages)
   - Right-side detail sidebar: z-50
   - Loading overlay: z-100

   The navigation sidebar should be z-30 (above graph content, below execution controls).

2. **Width management:** The sidebar is narrow (icon-only, ~60px). The main content area uses `calc(100% - 60px)` or equivalent flex layout.

3. **Graph page special case:** The graph SVG currently fills the viewport. With the sidebar, it fills `viewport width - sidebar width`. The D3.js zoom and layout may need the viewport dimensions recalculated.

### Theme Compatibility

All new sidebar styles must support both dark and light themes using the existing CSS custom properties (`--bg-surface`, `--border-dim`, `--neon-cyan`, etc.).

---

## Testing Considerations

### What Can Break

1. **Graph layout dimensions:** Adding a sidebar changes the available width for D3.js. The `setupSVG()` method reads `container.clientWidth` -- this should automatically adjust if the container's CSS changes.

2. **WebSocket connections on page navigation:** When navigating from the graph page to another page, the graph page's WebSocket connection closes. This is expected and correct -- the execution continues on the server regardless.

3. **Execution state across navigation:** If a user starts execution on the graph page, then navigates to the active runs page, the active runs page must discover the running execution via `GET /api/execution/status`. This is already handled by the polling/fetch approach.

4. **Theme persistence:** Theme is stored in localStorage (`localStorage.getItem('theme')`). This persists across page navigations. The base template's theme toggle reads this on load.

5. **CSS specificity conflicts:** Moving styles from inline `<style>` blocks (in each template) to the shared `styles.css` may cause specificity conflicts. The existing templates have page-specific styles defined in inline `<style>` blocks -- these remain in `{% block head_extra %}` to maintain specificity.

---

## Capacity and Performance Notes

- Template inheritance adds no runtime cost (Jinja2 resolves blocks at render time)
- The sidebar polling adds one HTTP request every 3 seconds per open browser tab (~100 bytes)
- Removing popup windows reduces total WebSocket connections (no more per-popup connections when the user is just viewing the graph)
- Full-page navigation is standard browser behavior; no memory management concerns (unlike popups which accumulate)

---

*Architecture research complete: 2026-02-07*

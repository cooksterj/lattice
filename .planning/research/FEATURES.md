# Feature Research: Sidebar Navigation, Run Monitoring & Failure Recovery

**Domain:** DAG orchestration web UI -- sidebar navigation, active run monitoring, run history views, failure recovery / partial re-execution
**Researched:** 2026-02-07
**Confidence:** HIGH (patterns well-established across Dagster, Airflow, Prefect; codebase infrastructure verified by direct code inspection)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist once a sidebar + recovery UI is introduced. Missing these makes the product feel incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Persistent sidebar on all pages | Every orchestration tool (Dagster, Prefect) uses persistent navigation -- users expect to reach any view from any page without browser back | MEDIUM | Sidebar must render as a shared layout element across all templates. Existing pages (index, history, asset_live, asset_detail) currently have independent headers -- need a common layout wrapper or template includes |
| Icon-only collapsed sidebar | Users expect a narrow icon rail that does not steal horizontal space from the graph. Dagster moved to this pattern specifically to preserve visual space for DAGs | LOW | 2-3 icon buttons in a narrow (48-56px) vertical bar. Tooltips on hover for labels. No accordion/expand needed for just 2-3 icons |
| Active runs page showing live asset statuses | Users expect to see what is currently running. Dagster has an "Overview > Runs" page; Airflow has a Grid/Graph view with per-task status coloring. During execution, show running/queued/completed assets. When idle, show last completed run summary | HIGH | Requires a new full page + route. Must consume the existing WebSocket execution feed (already broadcasts `asset_start`, `asset_complete`, `execution_complete`). Needs new endpoint or client-side state to show "last completed run" when idle |
| Run history full page | Users expect a dedicated page listing past runs with status, duration, and drill-down. Existing `/history` page already does this. v2 moves it from top-nav into sidebar-navigated full page | LOW | The existing history.html template and /api/history/* endpoints are already complete. Main work is re-parenting the template to use the sidebar layout and removing the old top-nav |
| Full-page live logs (replace popup) | Users expect clicking a running asset navigates to a full page showing live streaming logs, not a popup window. Dagster, Prefect, and Airflow all use full-page log views | MEDIUM | The existing asset_live.html template (891 lines) already has the log streaming UI, WebSocket client, state machine, and completion banner. Main work is removing popup-specific code (refocus button, window.name targeting) and adding sidebar + back navigation |
| Back button / browser history support | Full-page navigation must work with browser back/forward. Users should never feel "trapped" on a page | LOW | Standard anchor tags (`<a href="...">`) and full-page loads. No SPA complexity. Each page has its own URL. Back button works naturally with server-rendered pages |
| Graph click = select/highlight (no popup) | Users expect clicking a graph node to select it (highlight node + downstream), not to open a window. Selection is a prerequisite for the "re-execute from here" flow | MEDIUM | Existing `graph.js` already has `highlightConnections()` and node selection state. Remove `openAssetWindow()` from click handler. Add persistent selection styling (outline, glow). Wire selected state to the Execute button |
| Remove v1 popup infrastructure | Once sidebar navigation replaces popups, leftover popup code confuses the codebase and creates dead code paths | LOW | Delete: `openAssetWindow()`, `showPopupBlockedNotice()`, `assetWindows` Map, `window.name = 'lattice_graph'`, refocus button handler. Clean removal of ~100 lines in graph.js |

### Differentiators (Competitive Advantage)

Features that set Lattice apart from typical DAG UIs. Not required for launch, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Failed asset re-execution with visual downstream highlighting | Click a failed asset on the graph to highlight it AND all downstream assets. Then click Execute to re-run from that point. Dagster has "re-execute from failure" but it operates on the whole run, not a visual graph selection. Airflow has "clear downstream" but requires navigating to a task detail page. Lattice can make this a single graph-click + Execute flow | HIGH | Backend: `ExecutionPlan.resolve()` already supports `include_downstream=True`. The `ExecutionStartRequest` already has `target` and `include_downstream` fields. Frontend: Need to compute downstream set from graph data (JS), visually highlight all selected nodes, and wire the Execute button to POST with `target=<failed_asset>&include_downstream=true` |
| Visual downstream propagation on graph | When a failed asset is selected, visually show the "blast radius" -- all downstream assets that would be re-executed get highlighted in a distinct color (e.g., amber). This gives users confidence about what will happen before clicking Execute | MEDIUM | Requires traversing the edge data in JS to find all transitive dependents. The server already has `DependencyGraph.get_all_downstream()` -- either replicate in JS or add an API endpoint `/api/graph/downstream/{key}` that returns the set |
| Active runs page dual mode (live vs last-completed) | When execution is running: show real-time asset status cards (running, queued, completed, failed). When idle: show the last completed run summary with per-asset results. Most tools just show "no active runs" when idle -- Lattice can provide useful context at all times | MEDIUM | Idle mode can reuse run history data from `/api/history/runs?limit=1`. Live mode uses WebSocket. The dual-mode behavior is a state machine: check `/api/execution/status` on page load to decide which mode to render |
| Clickable running assets navigate to live logs | From the active runs page, clicking a running (or recently completed) asset navigates to the full-page live log view. This creates a seamless monitoring workflow: sidebar > active runs > click asset > live logs | LOW | Simple anchor link from the active runs page to `/asset/{key}/live`. The live page already handles late-joining (replay buffer catches up missed logs) |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for a vanilla JS / Jinja2 codebase.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| SPA-style client-side routing | Smoother navigation without page reloads | Requires a JS framework (React/Vue) or a custom router. Lattice uses server-rendered Jinja2 templates + vanilla JS. Adding client-side routing means duplicating route logic, managing state across "pages" in JS, and fighting browser history. Massive complexity for minimal gain | Use full-page navigation with shared template includes for sidebar. Each page loads fast (no heavy JS bundle). Browser back/forward works natively |
| Expandable sidebar with text labels | Users might request a wide sidebar that expands to show "Run History", "Active Runs", "Settings" as text labels | For a tool with only 2-3 navigation items, an expanding sidebar is overkill and steals graph space. Dagster found the same issue and moved to a narrower approach. The graph needs maximum horizontal space | Icon-only sidebar rail with tooltips. 48-56px wide. Always visible, never expanding. Clear, recognizable icons for 2-3 destinations |
| In-page log streaming (embed in sidebar or panel) | Show live logs in a sidebar panel alongside the graph | The log container needs vertical space (hundreds of lines). Cramming it into a sidebar creates a tiny, unusable scrolling area. Also requires maintaining two WebSocket contexts (graph + logs) on one page | Navigate to a dedicated full-page live log view. Full screen height for logs. Dedicated WebSocket connection per page |
| Automatic retry on failure | Auto-retry failed assets without user intervention | Masks real failures, can cause infinite loops, and complicates the execution model. The current executor has no retry concept -- adding one means retry counts, backoff strategies, and a fundamentally different execution state machine | Manual re-execution: user clicks the failed asset, sees the blast radius, then consciously clicks Execute. Explicit is better than implicit |
| Real-time graph animation during execution | Animate edges/nodes with flowing particles or pulsing effects during execution | Performance killer with D3.js force-directed graphs. CSS animations on SVG elements cause layout thrashing. The existing `status-running` class with a subtle pulse is sufficient | Simple CSS class-based status coloring (already exists: `status-completed`, `status-failed`, `status-running`). Add `status-selected` for the re-execution highlight |
| Multi-select assets for partial execution | Shift+click to select multiple non-contiguous assets for re-execution | Breaks the DAG contract. If you select assets A and C but not B (where A -> B -> C), the execution plan is invalid. The only safe partial selections follow the DAG structure: "from X downstream" | Single-asset selection that automatically includes downstream. The DAG structure determines the execution subset, not arbitrary user selection |
| Modal overlays for run details from sidebar | Show run details in a modal overlay instead of navigating to a page | The existing history page already uses modals for run details. For v2, full-page views are the explicit design choice (per PROJECT.md). Modals fight with the sidebar layout and cannot be bookmarked or shared | Full-page run detail views. Navigable via sidebar, linkable, works with browser back button |

## Feature Dependencies

```
[Sidebar Layout]
    |
    |--requires--> [Template restructuring] (shared base template with sidebar includes)
    |
    |--enables--> [Active Runs Page] (navigable via sidebar icon)
    |                  |
    |                  |--enhances--> [Click-to-live-logs] (from active runs to /asset/{key}/live)
    |                  |
    |                  |--requires--> [WebSocket execution feed] (ALREADY EXISTS)
    |
    |--enables--> [Run History Page] (navigable via sidebar icon)
    |                  |
    |                  |--requires--> [History API] (ALREADY EXISTS)
    |
    |--enables--> [Full-page live logs] (navigable from active runs page)
                       |
                       |--requires--> [asset_live.html refactor] (remove popup code, add sidebar)
                       |
                       |--requires--> [WebSocket per-asset streaming] (ALREADY EXISTS)

[Graph Click = Select]
    |
    |--enables--> [Failed asset re-execution]
    |                  |
    |                  |--requires--> [Downstream highlight computation] (JS or API)
    |                  |
    |                  |--requires--> [Execute button wiring] (POST with target + include_downstream)
    |                  |
    |                  |--requires--> [ExecutionPlan.resolve(include_downstream=True)] (ALREADY EXISTS)
    |
    |--conflicts--> [v1 popup window.open] (must be removed before or alongside)

[Remove v1 popups]
    |
    |--requires--> [Sidebar Layout] (replacement must exist first)
    |--requires--> [Full-page live logs] (replacement must exist first)
```

### Dependency Notes

- **Sidebar Layout requires Template restructuring:** All existing templates (index.html, history.html, asset_live.html, asset_detail.html) have independent headers and no shared layout. A base template or Jinja2 include pattern is needed so the sidebar renders consistently across all pages.
- **Active Runs Page requires WebSocket execution feed:** The page consumes the existing `/ws/execution` WebSocket which already broadcasts `asset_start`, `asset_complete`, `execution_complete`, `memory_update`, and `partition_start/complete` messages. No new server-side work needed for the basic live view.
- **Failed asset re-execution requires Graph Click = Select:** The user must be able to click-select a failed asset on the graph before they can trigger downstream re-execution. These features are tightly coupled.
- **Failed asset re-execution requires Downstream highlight computation:** Before clicking Execute, the user needs to see which assets will be affected. This requires traversing the graph edges in JavaScript, or calling a new API endpoint like `/api/graph/downstream/{key}`.
- **Remove v1 popups conflicts with v1 popup behavior:** Cannot coexist -- the graph click handler either opens a window OR selects. Must replace, not extend.
- **Full-page live logs require sidebar:** The refactored asset_live.html must include the sidebar for consistent navigation. Otherwise users are stranded on the live log page with no way to navigate back except the browser back button.

## MVP Definition

### Launch With (v2.0)

Minimum viable product -- what is needed to validate the sidebar + recovery approach.

- [ ] Sidebar icon rail on all pages (3 icons: graph/home, active runs, run history) -- core navigation mechanism
- [ ] Active runs full page with real-time asset status during execution -- primary monitoring view
- [ ] Active runs idle state showing last completed run summary -- useful context when not executing
- [ ] Run history page accessible via sidebar (reuse existing template) -- already built, just re-parent
- [ ] Graph click = select/highlight (no popup) -- prerequisite for re-execution
- [ ] Failed asset click highlights asset + downstream on graph -- visual blast radius
- [ ] Execute button re-runs from selected failed asset downstream -- the recovery feature
- [ ] Full-page live logs (refactored asset_live.html with sidebar) -- replace popup with in-flow navigation
- [ ] Click running asset on active runs page navigates to live logs -- completes the monitoring flow
- [ ] Remove v1 popup infrastructure -- clean break from old approach

### Add After Validation (v2.x)

Features to add once core sidebar + recovery is working.

- [ ] Log search/filter in live log view -- v1 MILESTONES.md mentioned this as future; useful but not blocking
- [ ] Run comparison view (diff two runs side by side) -- advanced observability feature
- [ ] Keyboard shortcuts for sidebar navigation (1=graph, 2=active runs, 3=history) -- polish
- [ ] Graph minimap / overview panel -- useful when DAGs grow large, not critical for initial release

### Future Consideration (v3+)

Features to defer until the core experience is solid.

- [ ] Virtual scrolling for log entries -- only needed if users hit the 2000-entry DOM cap regularly
- [ ] Asset dependency tree sidebar panel -- sidebar real estate is limited; full page is better
- [ ] Notification/toast system for execution events -- useful for background awareness but adds complexity
- [ ] Persistent execution state across page reloads (localStorage) -- WebSocket replay buffer handles most cases
- [ ] Automatic retry with backoff -- fundamentally different execution model

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Sidebar icon rail on all pages | HIGH | MEDIUM | P1 |
| Active runs page (live mode) | HIGH | HIGH | P1 |
| Graph click = select/highlight | HIGH | MEDIUM | P1 |
| Failed asset downstream highlight | HIGH | MEDIUM | P1 |
| Execute from failed asset downstream | HIGH | LOW | P1 |
| Full-page live logs (remove popup) | HIGH | MEDIUM | P1 |
| Remove v1 popup infrastructure | MEDIUM | LOW | P1 |
| Active runs page (idle/last-run mode) | MEDIUM | LOW | P1 |
| Run history via sidebar | MEDIUM | LOW | P1 |
| Click running asset to live logs | MEDIUM | LOW | P1 |
| Log search/filter | MEDIUM | MEDIUM | P2 |
| Keyboard shortcuts | LOW | LOW | P3 |
| Graph minimap | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v2.0 launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Dagster | Airflow | Lattice v2 Approach |
|---------|---------|---------|---------------------|
| Navigation | Left sidebar with collapsible sections (Assets, Runs, Deployment, etc.). Recently moved from top-nav to sidebar. Discussion #21370 notes space constraints led to sidebar redesign | Top horizontal nav with dropdown menus (DAGs, Datasets, Admin, etc.) | Icon-only left sidebar rail (48-56px). 3 icons: graph (home), active runs, run history. Tooltips on hover. Minimal footprint to maximize graph space |
| Active run monitoring | "Runs" page shows all runs; individual run page shows per-asset/op status in real-time. Gantt chart timeline view | Grid View shows task instances with color-coded status per run. Task Duration view shows timeline | Dedicated "Active Runs" full page. Real-time per-asset status cards via WebSocket. Shows running, queued, completed, failed. Dual mode: live during execution, last-completed when idle |
| Run history | "Runs" page with filterable list (status, date range, tags). Run detail page with Gantt timeline, logs, config. Asset-scoped history on asset detail page | "Browse > DAG Runs" page with status filters. Grid View shows historical runs per task. Calendar view for patterns | Existing `/history` page with summary stats, asset breakdown, partition breakdown, and run detail modal with tabs (assets, checks, logs, lineage). Moves into sidebar-navigated layout |
| Failure recovery | "Re-execute from Failure" button in run details. Re-runs all failed steps + downstream. Issue #12423: cannot target individual failed assets within a multi-asset step | "Clear" action on failed task with "Downstream" checkbox. Resets task state so scheduler re-runs it | Visual graph-based approach: click failed asset on graph, see downstream highlight (blast radius), click Execute to re-run from that point. Uses existing `include_downstream=true` in ExecutionPlan |
| Live logs | Per-op/asset log streaming in run detail page. Structured log viewer with level filtering | Task Instance detail page shows logs. Real-time log tailing added in 2.6+. Logs fetched via REST with interval refresh | Full-page live log view per asset. WebSocket streaming with replay buffer for late joins. State machine (idle/running/completed/failed). DOM cap at 2000 entries with FIFO eviction |
| Graph interaction | Asset lineage view with click-to-select, right-click context menu for materialization | Graph View shows DAG structure. Click task to open side panel with details/actions | Click to select + highlight. Selected failed asset + downstream highlighted in distinct color. No context menu -- Execute button handles action. Cleaner than right-click menus |

## Existing Infrastructure Reuse

Critical for accurate complexity estimates -- what already exists and is verified by direct code inspection.

| Infrastructure | Location | Reusable For | Verified |
|----------------|----------|-------------|----------|
| WebSocket execution broadcast | `execution.py` -- `broadcast()`, message types: `asset_start`, `asset_complete`, `execution_complete`, `memory_update`, `partition_start`, `partition_complete` | Active runs page (live mode). No new server code needed | YES -- lines 141-156 |
| WebSocket per-asset streaming | `execution.py` -- `broadcast_to_asset()`, `add_asset_subscriber()`, replay buffer (500 entries) | Full-page live logs. Already works, just needs full-page container | YES -- lines 158-234 |
| `asset_live.html` template | 891-line template with WebSocket client, state machine (idle/running/completed/failed), log rendering with DOM cap, completion banner, theme toggle | Refactor for full-page: remove popup refs (refocus button, window.name), add sidebar include | YES -- verified all features |
| `history.html` template | Full history page with stats grid, asset summary table, partition summary, run list with filter, run detail modal with tabs (assets/checks/logs/lineage) | Re-parent into sidebar layout. Minimal changes | YES -- 861 lines |
| `ExecutionPlan.resolve(include_downstream=True)` | `plan.py` lines 43-123 | Backend for re-execute-from-failure. Already implements "target + all upstream + all downstream" | YES -- uses `get_all_upstream()` + `get_all_downstream()` |
| `ExecutionStartRequest.include_downstream` | `schemas_execution.py` line 64 | API already accepts `include_downstream` boolean flag | YES |
| `DependencyGraph.get_all_downstream()` | `graph.py` lines 227-255 | Server-side downstream computation. Could expose via API for JS consumption | YES -- BFS traversal of reverse_adjacency |
| `/api/graph` endpoint | `routes.py` lines 62-105 -- returns nodes and edges with dependency info | JS can compute downstream from edge data client-side (same traversal algorithm) | YES |
| `/api/execution/status` endpoint | `execution.py` lines 556-587 -- returns `is_running`, `run_id`, `current_asset`, `asset_statuses` | Active runs page can poll this for initial state on page load | YES |
| `/api/history/runs?limit=1` endpoint | `routes_history.py` lines 131-165 -- returns paginated run list | Active runs idle mode can fetch last completed run | YES |
| Node status CSS classes | `graph.js` -- `status-running`, `status-completed`, `status-failed` applied via `updateAssetStatus()` | Add `status-selected`, `status-downstream` for re-execution highlighting | YES -- lines 1145-1166 |
| `highlightConnections()` method | `graph.js` lines 583-613 -- highlights edges and dims unrelated nodes on hover | Extend pattern for persistent selection (currently only on hover). Need to add a click-based persistent version | YES |
| Node selection state | `graph.js` -- `this.selectedNode` property, `selectNode()` method for sidebar | Repurpose for persistent click selection instead of sidebar population | YES -- lines 701-792 |

## Sources

- [Dagster UI documentation](https://docs.dagster.io/concepts/webserver/ui) -- sidebar navigation structure, asset catalog, runs page (MEDIUM confidence -- official docs)
- [Dagster experimental UI navigation discussion](https://github.com/dagster-io/dagster/discussions/21370) -- sidebar vs top-nav tradeoffs, space constraints (MEDIUM confidence -- official GitHub)
- [Dagster re-execute from failure issue #12423](https://github.com/dagster-io/dagster/issues/12423) -- limitations of step-level vs asset-level re-execution (HIGH confidence -- official issue tracker)
- [Dagster new UI blog post](https://dagster.io/blog/introducing-the-new-dagster-plus-ui) -- sidebar navigation redesign rationale (MEDIUM confidence -- official blog)
- [Airflow re-run tasks (Astronomer)](https://docs.astronomer.io/learn/rerunning-dags) -- "Clear" action with downstream checkbox (MEDIUM confidence -- authoritative third party)
- [Airflow clear downstream issue #33014](https://github.com/apache/airflow/issues/33014) -- downstream clearing edge cases (HIGH confidence -- official issue tracker)
- [Airflow UI overview](https://airflow.apache.org/docs/apache-airflow/stable/ui.html) -- Grid View and Graph View for task monitoring (HIGH confidence -- official docs)
- [Prefect dashboard documentation](https://docs.prefect.io/orchestration/ui/dashboard.html) -- flow run monitoring patterns (MEDIUM confidence -- official docs)
- [Prefect React UI v2](https://deepwiki.com/PrefectHQ/prefect/2.2-react-ui-v2) -- sidebar layout with SidebarProvider (LOW confidence -- third party analysis)
- [shadcn/ui sidebar component](https://ui.shadcn.com/docs/components/radix/sidebar) -- collapsible sidebar patterns, icon-only rail best practices (HIGH confidence -- official docs)
- Lattice codebase: `src/lattice/web/` -- all existing routes, templates, WebSocket infrastructure, executor, graph module (HIGH confidence -- direct code inspection, all line numbers verified)

---
*Feature research for: Lattice v2.0 sidebar navigation, run monitoring, and failure recovery*
*Researched: 2026-02-07*

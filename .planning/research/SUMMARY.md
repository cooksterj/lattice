# Project Research Summary

**Project:** Lattice v2.0 - Sidebar Navigation, Full-Page Views, and Failure Recovery
**Domain:** DAG orchestration web UI refactoring
**Researched:** 2026-02-07
**Confidence:** HIGH

## Executive Summary

Lattice v2.0 transforms the popup-based navigation model into a professional sidebar-driven full-page architecture. The research confirms that **no new dependencies are needed** -- the existing stack (FastAPI, Jinja2, vanilla JS, D3.js, WebSocket, Tailwind CDN, SQLite) fully supports the upgrade. The core changes are structural: Jinja2 template inheritance for the persistent sidebar, removal of `window.open()` popup logic, and graph click behavior shifting from "open window" to "select and highlight for re-execution."

The recommended approach leverages existing infrastructure extensively. The WebSocket execution feed, per-asset log streaming, replay buffers, and ExecutionPlan resolution with `include_downstream=True` already exist and require no modification. The heaviest architectural work is establishing Jinja2 base template inheritance across 4 existing templates, followed by building a new Active Runs page and implementing visual downstream highlighting on the graph. The partial re-execution feature is already supported server-side -- the gap is purely UI wiring.

The key risk is template refactoring creating CSS regressions and WebSocket state loss on navigation. Mitigation: refactor templates one at a time starting with the simplest (history.html), use REST+WebSocket dual-layer for sidebar state resilience, and design downstream scope computation to include all necessary upstream dependencies (avoiding stale data pitfalls). The research identifies 6 critical pitfalls with specific prevention strategies, all addressable during phased implementation.

## Key Findings

### Recommended Stack

**No new dependencies required.** All v2.0 features are achievable with the existing stack. The changes are architectural (template structure, navigation patterns, graph interaction) rather than technological.

**Core technologies (unchanged):**
- **Jinja2 3.1.x (existing)** — Template inheritance (`{% extends %}` / `{% block %}`) provides sidebar-on-every-page pattern without duplication
- **Tailwind CSS CDN 3.x (existing)** — Already loaded; provides `fixed`, `flex`, `w-16`, `transition` utilities needed for sidebar layout
- **D3.js v7 (existing)** — All APIs for node selection, multi-node highlighting, and downstream traversal already available
- **FastAPI 0.115.x (existing)** — Route patterns support new full-page routes with no changes
- **WebSocket infrastructure (existing)** — `/ws/execution` and `/ws/asset/{key}` endpoints provide all necessary real-time data for sidebar and active runs page

**New patterns (zero-dependency):**
- **Inline SVG icons** — 3-4 hand-coded SVG icons for sidebar (graph, history, active runs, back arrow). No icon library needed; consistent with existing inline SVG pattern
- **History API** — Built-in browser API for back-button semantics (optional enhancement, not required for basic navigation)
- **ExecutionPlan.resolve() extension** — `include_downstream=True` already exists; partial re-execution is already supported

**Explicitly rejected:**
- Icon libraries (Lucide, Feather, FontAwesome) — overkill for 3-4 icons
- htmx or Alpine.js — introduces paradigm shift; vanilla JS is sufficient
- SPA routers (page.js, Navigo) — full-page server-rendered navigation is the correct pattern
- React/Vue/Svelte — prohibited by project constraints

### Expected Features

**Must have (table stakes):**
- **Persistent sidebar on all pages** — Every orchestration tool uses this pattern; users expect to reach any view without browser back
- **Icon-only collapsed sidebar** — Narrow rail (48-56px) preserves graph space; Dagster moved to this approach for the same reason
- **Active runs page showing live asset statuses** — During execution: running/queued/completed list. When idle: last completed run summary
- **Run history full page** — Already exists; needs sidebar integration
- **Full-page live logs (replace popup)** — Users expect full-page log streaming, not popup windows
- **Back button / browser history support** — Standard anchor tags; full-page loads work naturally
- **Graph click = select/highlight (no popup)** — Prerequisite for re-execute-from-here flow
- **Remove v1 popup infrastructure** — Clean removal of ~100 lines: `openAssetWindow()`, `showPopupBlockedNotice()`, `assetWindows` Map, window name tracking

**Should have (competitive advantage):**
- **Failed asset re-execution with visual downstream highlighting** — Click failed node, see blast radius (all downstream highlighted), click Execute to re-run from that point. Dagster has "re-execute from failure" but operates on whole run, not visual graph selection
- **Visual downstream propagation on graph** — Show "blast radius" in distinct color before execution
- **Active runs page dual mode** — Live during execution, last-completed when idle (most tools show "no active runs" when idle)
- **Clickable running assets navigate to live logs** — Seamless monitoring workflow from active runs page

**Defer (v2+):**
- Log search/filter in live view
- Run comparison view (diff two runs)
- Keyboard shortcuts for navigation
- Graph minimap/overview panel

### Architecture Approach

The architecture extends the existing template-per-page model with Jinja2 inheritance. A new `base.html` template owns the shared shell (sidebar, header, theme toggle, fonts, corner decorations). All pages extend it via `{% extends "base.html" %}` and override content blocks. The sidebar is pure CSS/Tailwind (no JavaScript needed for layout), with client-side polling for active run indicator.

**Major components:**

1. **Jinja2 Base Template (`base.html`)** — Shared shell with 4 blocks: `{% block title %}`, `{% block head_extra %}`, `{% block content %}`, `{% block scripts %}`. Sidebar defined once, inherited by all pages. Eliminates ~80 lines of duplicated boilerplate per template.

2. **Sidebar Navigation** — Narrow vertical icon rail (left side, always visible). Contains 3 icons: graph (home), run history, active runs. Active run indicator (pulsing dot) when execution is running, driven by polling `GET /api/execution/status` every 3 seconds. No WebSocket needed for sidebar (avoids connection churn on navigation).

3. **Active Runs Page (`/runs/active`)** — New full page + route. Consumes existing `/ws/execution` WebSocket for real-time updates during execution. When idle, fetches `GET /api/history/runs?limit=1` for last completed run. No new API endpoints needed.

4. **Graph Click Behavior** — Replace `this.openAssetWindow(d.id)` with `this.selectNodeForReexecution(d)`. Visually highlight selected node + downstream (yellow border + dashed border for downstream). Execute button becomes context-aware: "EXECUTE ALL" when nothing selected, "EXECUTE FROM [asset]" when node selected. Passes `target=selectedNodeId` + `include_downstream=true` to existing API.

5. **Partial Re-Execution** — Already supported. `ExecutionPlan.resolve(target, include_downstream=True)` includes target's upstream + target + target's downstream. Frontend just needs to wire graph selection to POST body. Backend requires no changes.

6. **Full-Page Navigation** — Standard `<a href="...">` links. Browser back button works naturally with server-rendered pages. Each view has unique URL. No SPA complexity, no History API required (optional for preserving graph selection state across back-button).

### Critical Pitfalls

1. **Stale Upstream Data During Partial Re-Execution** — When re-running from failed asset, `MemoryIOManager` is ephemeral (created fresh per execution). Upstream assets' outputs from prior run are unavailable. **Avoid by:** Using existing `include_downstream=True` which re-runs upstream too (ensures data availability). Accept this cost for v2.0; optimize later.

2. **Ambiguous Failed Asset Selection After Multiple Runs** — Graph shows mixed statuses from different runs. User cannot tell which failures are from which run. **Avoid by:** Clearing ALL asset statuses when starting partial execution, or dimming assets outside execution scope. Store execution scope client-side to differentiate "completed in this run" vs "prior run."

3. **WebSocket Connection Destroyed on Full-Page Navigation** — Every navigation reloads page, drops WebSocket, loses JavaScript state. Sidebar arrives in default state until reconnection. **Avoid by:** Using REST (`/api/execution/status`) for immediate sidebar state on load, WebSocket for live updates. Cache state in `sessionStorage` to eliminate flash-of-idle during navigation.

4. **Template Inheritance Block Conflicts** — Current templates are standalone with duplicated headers, CSS, and inline styles. Refactoring to extend base template risks CSS specificity conflicts and visual regressions. **Avoid by:** Refactoring one template at a time, starting with simplest (history.html). Extract shared CSS to `styles.css`, keep page-specific styles in `{% block head_extra %}`. Test visually after each template conversion.

5. **Downstream Scope Computation Errors (Diamond DAG)** — When re-executing from node B in a diamond dependency (A -> B -> D, A -> C -> D), the scope includes B + D (downstream of B) + A (upstream of B), but misses C. D depends on C, but C is outside the re-execution scope, causing missing data. **Avoid by:** For each downstream asset, include ALL its upstream deps (not just target's upstream). Verify with unit tests on diamond-shaped DAGs.

6. **Graph Click Behavior Breaks Drag Interaction** — D3 drag behavior conflicts with new click-to-select. Changing click handler risks triggering selection on drag-end or double-click. **Avoid by:** Preserving `if (event.defaultPrevented) return;` guard, keeping click handler synchronous (selection state updates immediately), debouncing rapid clicks.

## Implications for Roadmap

Based on research, the work naturally splits into 4 phases, ordered by dependency chain:

### Phase 1: Template Inheritance Foundation (Sidebar on All Pages)

**Rationale:** Every subsequent change depends on sidebar navigation existing. Building base template first establishes the framework. This is highest-risk phase (touches all 4 existing templates), so it must be completed before any feature work.

**Delivers:**
- `base.html` base template with sidebar, header, theme toggle, shared CSS/JS
- All 4 existing templates converted to extend base.html
- Sidebar icon rail with 3 navigation icons (graph, history, active runs)
- Client-side polling for active run indicator
- Removal of duplicated boilerplate (~80 lines per template)

**Addresses (from FEATURES.md):**
- Persistent sidebar on all pages (table stakes)
- Icon-only collapsed sidebar (table stakes)
- Back button / browser history support (table stakes)

**Avoids (from PITFALLS.md):**
- Pitfall 4: Template inheritance block conflicts (addressed by refactoring one template at a time)
- Pitfall 3: WebSocket state loss (mitigated by REST+polling for sidebar)

**Phase complexity:** MEDIUM-HIGH (template refactoring is delicate, CSS regressions likely)

---

### Phase 2: Graph Click Selection and Execute Context

**Rationale:** Core UX change that replaces popup windows. Must come after Phase 1 (sidebar navigation in place). Enables the failure recovery workflow. Lower risk than Phase 1 because graph.js is already well-tested.

**Delivers:**
- Graph click handler changed from `openAssetWindow()` to `selectNodeForReexecution()`
- Visual selection highlight on clicked node
- Downstream node highlighting (shows execution blast radius)
- Context-aware Execute button ("EXECUTE ALL" vs "EXECUTE FROM [asset]")
- `startExecution()` wiring to pass `target` + `include_downstream` when node selected
- Removal of v1 popup code (~100 lines: `openAssetWindow`, `showPopupBlockedNotice`, window tracking)

**Addresses (from FEATURES.md):**
- Graph click = select/highlight (table stakes)
- Failed asset re-execution with visual highlighting (differentiator)
- Visual downstream propagation on graph (differentiator)
- Remove v1 popup infrastructure (table stakes)

**Uses (from STACK.md):**
- D3.js node selection and CSS class application (already exists)
- Existing `ExecutionStartRequest.target` + `include_downstream` fields

**Implements (from ARCHITECTURE.md):**
- Component 4: Graph Click Behavior Change
- Component 5: Partial DAG Re-Execution (frontend wiring only; backend already works)

**Avoids (from PITFALLS.md):**
- Pitfall 6: Graph click breaks drag (preserve `event.defaultPrevented` guard)
- Pitfall 2: Ambiguous failed asset selection (clear selection state on new execution start)

**Phase complexity:** MEDIUM (well-defined, existing patterns, minimal backend)

---

### Phase 3: Active Runs Page and Live Logs Refactor

**Rationale:** Depends on Phases 1 (sidebar navigation) and 2 (execution infrastructure). Provides the "what's running now" view that sidebar links to. Completes the monitoring workflow.

**Delivers:**
- New `runs_active.html` template extending base.html
- `GET /runs/active` route in routes.py
- Real-time asset status list via `/ws/execution` WebSocket (reuses existing endpoint)
- Idle state showing last completed run (fetches from `/api/history/runs?limit=1`)
- Clickable assets navigate to live logs or detail pages
- `asset_live.html` refactored from popup to full-page (remove refocus button, add back link)

**Addresses (from FEATURES.md):**
- Active runs page showing live asset statuses (table stakes)
- Active runs idle/last-run mode (differentiator)
- Full-page live logs (table stakes)
- Clickable running assets navigate to live logs (differentiator)

**Uses (from STACK.md):**
- Existing `/ws/execution` WebSocket (no new endpoints)
- Existing `asset_live.html` template (891 lines of WebSocket/log logic stays intact)
- Existing history API endpoints

**Implements (from ARCHITECTURE.md):**
- Component 3: Active Runs Page
- Component 7: Live Logs Page Refactor

**Avoids (from PITFALLS.md):**
- Pitfall 3: WebSocket state loss on navigation (REST for initial load, WebSocket for updates)

**Phase complexity:** MEDIUM (leverages existing infrastructure, mostly template work)

---

### Phase 4: Polish, Cleanup, and Testing

**Rationale:** Final integration and removal of any remaining v1 artifacts. Ensures clean codebase before release.

**Delivers:**
- Remove any remaining popup-related CSS/JS
- Active nav link highlighting (current page indicator in sidebar)
- Cache buster version bumps on CSS and JS files
- Comprehensive testing on all navigation paths
- Visual regression testing on all pages
- Diamond DAG unit tests for partial re-execution scope

**Addresses (from FEATURES.md):**
- All cleanup tasks for table stakes features

**Implements (from ARCHITECTURE.md):**
- Component 6: Active Run Indicator in Sidebar (CSS polish)
- All testing considerations from architecture doc

**Avoids (from PITFALLS.md):**
- Pitfall 5: Downstream scope computation errors (unit tests for diamond DAGs)
- All "Looks Done But Isn't" checklist items

**Phase complexity:** LOW (integration and testing, no new features)

---

### Phase Ordering Rationale

- **Phase 1 first:** Template inheritance is foundational. Every subsequent feature depends on sidebar existing. Highest risk, so must be stabilized before proceeding.
- **Phase 2 before Phase 3:** Graph click selection is the core UX change. Active runs page can be built independently, but the execution flow (select -> execute) should be working first for better testing.
- **Phase 3 after sidebar + graph:** Active runs page consumes data from execution infrastructure. By Phase 3, both sidebar and graph are working, providing context for integration testing.
- **Phase 4 last:** Cleanup and polish after all features are integrated.

**Dependency chain verified:**
```
Phase 1 (base template)
    |
    +-- enables --> Phase 2 (graph selection)
    |                    |
    +-- enables --> Phase 3 (active runs page)
                         |
                         v
                    Phase 4 (polish)
```

### Research Flags

**Phases with standard patterns (skip deep research):**
- **Phase 1:** Jinja2 template inheritance is well-documented. All integration points verified in codebase. Standard patterns apply.
- **Phase 2:** D3.js selection and graph interaction are established patterns. Existing codebase has similar logic (`selectNode()`, `highlightConnections()`).
- **Phase 3:** WebSocket consumption and template rendering follow existing patterns from v1. Minimal novelty.

**Phases needing careful design (not research, but design validation):**
- **Phase 1:** Template refactoring requires visual regression testing after each template conversion. Consider screenshot diffing.
- **Phase 2:** Downstream scope computation needs unit tests on diamond DAGs before integration. Edge case validation.

**No phases need `/gsd:research-phase`** — all patterns are established, all integration points mapped.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations verified against existing codebase. No new dependencies needed. Every integration point checked. |
| Features | HIGH | Table stakes list validated against Dagster/Airflow/Prefect. Competitor analysis confirms expectations. Existing infrastructure verified (WebSocket, history API, ExecutionPlan). |
| Architecture | HIGH | All file paths, line numbers, and integration points verified via direct code inspection. Template inheritance pattern is standard Jinja2. WebSocket endpoints already exist and work. |
| Pitfalls | HIGH | All 6 critical pitfalls mapped to specific codebase patterns. Prevention strategies are concrete and testable. Sources include official issue trackers (Dagster, Airflow) documenting similar problems. |

**Overall confidence:** HIGH

### Gaps to Address

**Minor gaps (acceptable for v2.0):**

- **Downstream scope computation optimization:** Current approach re-runs upstream dependencies even when their outputs are available. This is correct but potentially inefficient for deep DAGs. **Handle during:** Phase 2 implementation. Accept the current behavior; flag for v2.1 optimization if users report performance issues.

- **Virtual scrolling for log entries:** The 2000-entry DOM cap is a known limitation. If users hit this regularly, virtual scrolling is needed. **Handle during:** Phase 3 testing. Monitor user feedback; add virtual scrolling in v2.x if needed.

- **CSS specificity conflicts during template refactoring:** Moving inline styles to shared stylesheet may cause specificity battles. **Handle during:** Phase 1 execution. Test each template conversion visually before proceeding to next template. Use browser DevTools to trace conflicts.

**No critical gaps.** All research areas have sufficient confidence for roadmap creation and implementation.

## Sources

### Primary (HIGH confidence)
- Lattice codebase: `src/lattice/web/` (all routes, templates, WebSocket infrastructure, executor, graph module) — direct code inspection, all line numbers verified
- [Jinja2 Template Inheritance Documentation](https://jinja.palletsprojects.com/en/stable/templates/) — official docs on extends, block, include
- [FastAPI Templates Documentation](https://fastapi.tiangolo.com/advanced/templates/) — official FastAPI Jinja2 integration
- [D3.js Selections](https://d3js.org/d3-selection/selecting) — D3 selection API for node highlighting
- [MDN History API](https://developer.mozilla.org/en-US/docs/Web/API/History_API/Working_with_the_History_API) — pushState/popstate reference

### Secondary (MEDIUM confidence)
- [Dagster UI documentation](https://docs.dagster.io/concepts/webserver/ui) — sidebar navigation structure, asset catalog, runs page
- [Dagster re-execute from failure issue #12423](https://github.com/dagster-io/dagster/issues/12423) — limitations of step-level vs asset-level re-execution
- [Dagster experimental UI navigation discussion](https://github.com/dagster-io/dagster/discussions/21370) — sidebar vs top-nav tradeoffs
- [Airflow re-run tasks (Astronomer)](https://docs.astronomer.io/learn/rerunning-dags) — "Clear" action with downstream checkbox
- [Airflow UI overview](https://airflow.apache.org/docs/apache-airflow/stable/ui.html) — Grid View and Graph View for task monitoring
- [Prefect dashboard documentation](https://docs.prefect.io/orchestration/ui/dashboard.html) — flow run monitoring patterns

### Tertiary (LOW confidence, informational only)
- [Tailwind CSS Sidebar Layouts](https://tailwindcss.com/plus/ui-blocks/application-ui/application-shells/sidebar) — official Tailwind sidebar patterns
- [WebSocket Reconnection Strategies](https://oneuptime.com/blog/post/2026-01-27-websocket-reconnection/view) — lifecycle and state recovery patterns
- [shadcn/ui sidebar component](https://ui.shadcn.com/docs/components/radix/sidebar) — collapsible sidebar patterns

---
*Research completed: 2026-02-07*
*Ready for roadmap: yes*

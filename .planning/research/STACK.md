# Stack Research: Sidebar Navigation, Full-Page Views, and Partial DAG Re-Execution

**Research Date:** 2026-02-07
**Dimension:** Frontend architecture changes for v2.0 sidebar-driven navigation and failure recovery
**Confidence:** HIGH (all recommendations use existing stack or zero-dependency additions)

---

## Executive Summary

v2.0 replaces the popup-window approach with persistent sidebar navigation and full-page views. The existing stack (FastAPI, Jinja2, vanilla JS, D3.js, WebSocket, Tailwind CDN, SQLite) is fully sufficient. **No new libraries or frameworks are needed.** The changes are structural -- Jinja2 template inheritance for the shared sidebar, inline SVG icons (no icon library), browser History API for back-button navigation, and backend extension of `ExecutionPlan.resolve()` for partial re-execution. The D3.js graph gets new selection/highlight behavior replacing `window.open()`.

---

## Recommended Stack

### No New Dependencies

| Category | Technology | Version | Status | Rationale |
|----------|-----------|---------|--------|-----------|
| Templates | Jinja2 | 3.1.x (existing) | No change | Template inheritance (`{% extends %}` / `{% block %}`) provides the sidebar-on-every-page pattern |
| CSS Utility | Tailwind CSS CDN | 3.x (existing) | No change | Already loaded via `cdn.tailwindcss.com` in all templates; provides `fixed`, `flex`, `w-16`, `transition` utilities for sidebar |
| CSS Custom | `styles.css` | existing | Extend | Add sidebar icon styles, active-page indicator, selection highlight styles |
| Graph | D3.js v7 | 7.x (existing) | No change | Already loaded via CDN; has all APIs needed for node selection, multi-node highlighting, and downstream traversal |
| Icons | Inline SVG | N/A | New pattern | Hand-coded SVG icons in Jinja2 templates. 3-4 icons total (graph, history, active runs, logs). No icon library needed. |
| Navigation | History API | Built-in | New pattern | `history.pushState()` + `popstate` event for back-button support on full-page views |
| Backend | FastAPI | 0.115.x (existing) | No change | Existing route patterns support new full-page routes |
| Execution | `ExecutionPlan` | existing | Extend | `include_downstream=True` already exists in `ExecutionPlan.resolve()` -- partial re-execution is already supported server-side |

### What NOT to Add (and Why)

| Technology | Why Not |
|------------|---------|
| **Icon library (Lucide, Feather, FontAwesome)** | Only 3-4 icons needed (graph, clock/history, play/active, chevron-back). Adding a library for 4 icons is needless dependency. Inline SVGs are smaller, faster, and already the pattern used in the codebase (see header buttons in `index.html`). |
| **htmx or Alpine.js** | The codebase uses vanilla JS with fetch/WebSocket. Adding a micro-framework for sidebar toggle and page transitions introduces a paradigm shift. The changes are simple DOM manipulation. |
| **CSS framework (Bootstrap, Bulma)** | Tailwind CDN is already loaded and used. Adding a second CSS framework creates conflicts. |
| **SPA router (page.js, Navigo)** | This is NOT becoming a SPA. Full-page navigation with Jinja2 server-rendered pages is the correct pattern. The History API is used only for back-button semantics, not client-side routing. |
| **React/Vue/Svelte** | Explicitly prohibited by project constraints. Vanilla JS is sufficient. |
| **Web Components** | Adds complexity without benefit. Jinja2 template inheritance already provides component reuse. |

---

## Integration Patterns

### 1. Jinja2 Template Inheritance for Persistent Sidebar

**Confidence: HIGH** -- Jinja2 template inheritance is a core feature, extensively documented, and the standard approach for shared layouts.

**Current state:** Each template (`index.html`, `asset_detail.html`, `asset_live.html`, `history.html`) is a standalone HTML document with duplicated header, corner decorations, theme toggle, and font imports.

**Target state:** A `base.html` template defines the shared shell (sidebar, header, fonts, theme toggle, corner decorations). Each page extends it and fills content blocks.

```
templates/
  base.html          -- Shared shell: sidebar, header, theme toggle, fonts, corner decorations
  index.html          -- {% extends "base.html" %} -- Graph page (overrides content block)
  history.html        -- {% extends "base.html" %} -- Run history full page
  active_runs.html    -- {% extends "base.html" %} -- Active/queued runs full page (NEW)
  asset_live.html     -- {% extends "base.html" %} -- Live log streaming full page (refactored)
  asset_detail.html   -- {% extends "base.html" %} -- Asset detail full page (refactored)
```

**Key blocks in `base.html`:**

```jinja2
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <title>LATTICE // {% block title %}{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    {# Fonts, shared CSS #}
    <link rel="stylesheet" href="/static/css/styles.css?v=...">
    {% block head_extra %}{% endblock %}
</head>
<body class="font-mono">
<div class="flex h-screen">
    {# Persistent sidebar -- identical on every page #}
    <nav class="sidebar-nav">
        {% block sidebar %}
        {% include "partials/_sidebar.html" %}
        {% endblock %}
    </nav>

    {# Main content area #}
    <main class="flex-1 overflow-auto">
        {% block content %}{% endblock %}
    </main>
</div>
{% block scripts %}{% endblock %}
</body>
</html>
```

**Why this pattern:**
- Eliminates ~80 lines of duplicated boilerplate per template (header, fonts, theme toggle, corner decorations).
- Sidebar is defined once and appears on every page automatically.
- Child templates only define their unique content.
- Jinja2 `{% include %}` for the sidebar partial keeps `base.html` clean.

**Migration path:** Refactor templates one at a time. Extract the shared shell into `base.html`, then convert each page to `{% extends "base.html" %}`. The sidebar partial can be developed independently.

### 2. Sidebar Design: Narrow Icon Rail

**Confidence: HIGH** -- Pure CSS/Tailwind, no JavaScript needed for the sidebar itself.

The sidebar is a narrow, persistent icon rail on the left side of every page. It does NOT slide or expand -- it is always visible with small icons.

**Sidebar layout (using Tailwind classes already available via CDN):**

```
+----+----------------------------------+
| SB |        MAIN CONTENT AREA         |
|    |                                  |
| [] |  (graph / history / active /     |
| [] |   asset detail / live logs)      |
| [] |                                  |
+----+----------------------------------+

SB = sidebar (fixed width ~56-64px)
[] = icon buttons (graph, history, active runs)
```

**Icon approach:** Inline SVG, same pattern as existing header buttons. The codebase already contains 15+ inline SVGs (theme toggle, relayout, close, back arrow, play icon). Adding 3-4 more for sidebar icons is consistent.

Example sidebar icons (all from simple SVG paths):
- **Graph** (grid/nodes icon -- reuse existing logo SVG scaled down)
- **History** (clock icon -- `<path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>`)
- **Active Runs** (play-circle or activity icon)

**Active page indicator:** CSS class on the current page's icon, using the existing `--neon-cyan` accent color and a left border or background highlight. The current page's icon gets the `.active` class, set via Jinja2 context variable:

```jinja2
{# In base.html, pass current_page to template context #}
<a href="/" class="sidebar-icon {% if current_page == 'graph' %}active{% endif %}">
    <svg>...</svg>
</a>
```

The FastAPI route handlers pass `current_page` in the template context:

```python
return templates.TemplateResponse(request, "index.html", {"current_page": "graph"})
```

### 3. Full-Page Navigation with Back Button

**Confidence: HIGH** -- Standard browser navigation. No JavaScript routing needed.

**Current state:** Node clicks open `window.open()` popups. Navigation between views is via popup windows.

**Target state:** All views are full pages served by FastAPI routes. Navigation is standard `<a href="...">` links. The browser's back button works naturally because each page is a real URL.

**Why the History API is NOT needed for basic navigation:**
Since every view is a server-rendered page at a unique URL, the browser back button works automatically. There is no SPA, no client-side routing, no `pushState()` needed for the basic navigation flow.

**Where History API IS useful (optional):**
If the graph page wants to preserve node selection state across back-button navigation (e.g., user clicks node -> navigates to detail page -> presses back -> graph should still show that node selected), the graph page can use `replaceState()` to store the selected node ID:

```javascript
// When user selects a node on the graph
history.replaceState({ selectedNode: nodeId }, '');

// On page load, restore selection
window.addEventListener('popstate', (e) => {
    if (e.state?.selectedNode) {
        this.selectNode(e.state.selectedNode);
    }
});
```

This is a nice-to-have, not a requirement. The primary navigation works without any History API usage.

**Route structure for full-page views:**

| URL | Page | Template | Purpose |
|-----|------|----------|---------|
| `/` | Graph | `index.html` | D3.js DAG with node click-to-select |
| `/history` | Run History | `history.html` | Already exists, add sidebar |
| `/active` | Active Runs | `active_runs.html` | NEW: Running/queued assets during execution, last completed run when idle |
| `/asset/{key}` | Asset Detail | `asset_detail.html` | Already exists, add sidebar |
| `/asset/{key}/live` | Live Logs | `asset_live.html` | Already exists, refactor from popup to full page with sidebar |

### 4. Graph Click Behavior Change: Select + Highlight

**Confidence: HIGH** -- D3.js already has all the needed APIs. The codebase already implements `highlightConnections()` and CSS classes for node selection.

**Current behavior (v1.0):**
```javascript
.on('click', (event, d) => {
    if (event.defaultPrevented) return;
    event.stopPropagation();
    this.openAssetWindow(d.id);  // Opens popup window
});
```

**New behavior (v2.0):**
```javascript
.on('click', (event, d) => {
    if (event.defaultPrevented) return;
    event.stopPropagation();
    this.selectNodeForReexecution(d);  // Select + highlight downstream
});
```

**What `selectNodeForReexecution()` does:**
1. Marks the clicked node as "selected" (yellow border -- CSS class `.selected` already exists in `styles.css`)
2. Uses `DependencyGraph.get_all_downstream()` logic (client-side, from the graph data already loaded) to identify all downstream nodes
3. Highlights the selected node + all downstream nodes with a distinct visual style (e.g., dashed border, muted color indicating "will re-run")
4. Shows an "Execute from here" button (floating near the selection, or in the existing execution controls area)
5. Clicking "Execute from here" calls `POST /api/execution/start` with `{ target: selectedNodeId, include_downstream: true }`

**Downstream traversal on the client side:**
The graph data (`/api/graph` response) includes `edges` (source -> target). Building a reverse adjacency map and doing BFS from the selected node is trivial in vanilla JS -- ~15 lines of code. The existing `highlightConnections()` method already does single-hop neighbor highlighting. Extending it to multi-hop downstream is straightforward.

**What to remove from `graph.js`:**
- `openAssetWindow()` method
- `showPopupBlockedNotice()` method
- `assetWindows` Map tracking
- `window.name = 'lattice_graph'` assignment
- All `BroadcastChannel` code (if any remains)

### 5. Partial DAG Re-Execution (Backend)

**Confidence: HIGH** -- The infrastructure already exists. `ExecutionPlan.resolve()` already accepts `include_downstream=True`.

**Current backend support:**

```python
# In plan.py - ExecutionPlan.resolve()
if include_downstream:
    required = graph.get_all_upstream(target_key)
    required.add(target_key)
    required.update(graph.get_all_downstream(target_key))
```

```python
# In execution.py - ExecutionStartRequest
class ExecutionStartRequest(BaseModel):
    target: str | None = None
    include_downstream: bool = False
    execution_date: date | None = None
    execution_date_end: date | None = None
```

```python
# In execution.py - run_execution() already passes include_downstream
plan = ExecutionPlan.resolve(
    registry, target=target, include_downstream=include_downstream
)
```

**What this means:** The "Execute from failed asset downstream" feature requires NO backend changes for the core execution path. The frontend needs to:
1. Know which asset failed (from the `execution_complete` or `asset_complete` WebSocket message)
2. Let the user click the failed node on the graph
3. Highlight it + downstream
4. Send `POST /api/execution/start` with `target=failedAssetId, include_downstream=true`

**Important nuance -- re-execution skips upstream:** When `include_downstream=True`, the plan includes the target's upstream dependencies AND downstream dependents. For a "re-run from failure" scenario, this means upstream assets that already succeeded will re-run too. This is actually correct behavior because the failed asset needs fresh input data.

If the user only wants to re-run the failed asset + downstream (assuming upstream outputs are still available in the IOManager), a new parameter like `skip_completed_upstream=True` could be added. However, this is an optimization for later -- the current behavior (re-run everything needed) is safe and correct.

**New API endpoint consideration:** An optional `GET /api/graph/downstream/{key}` endpoint could return the list of downstream asset IDs for a given key. This would let the frontend highlight downstream nodes without computing the graph traversal client-side. However, since the client already has the full graph data, client-side traversal is simpler and avoids an extra round-trip. Recommend client-side traversal.

### 6. Active Runs Page

**Confidence: HIGH** -- Leverages existing WebSocket infrastructure and REST endpoints.

The active runs page (`/active`) needs:
- **During execution:** Show list of running/queued/completed/failed assets in real-time, powered by the existing `/ws/execution` WebSocket (which already broadcasts `asset_start` and `asset_complete` events)
- **When idle:** Show the last completed run's results, fetched from the existing `/api/history/runs?limit=1` REST endpoint
- **Click running asset:** Navigate to `/asset/{key}/live` (standard link, not popup)

**No new WebSocket endpoints needed.** The existing `/ws/execution` WebSocket broadcasts all the data the active runs page needs. The page just renders it differently from how the graph page uses it (list view vs. node status updates).

### 7. Live Logs Page Refactor

**Confidence: HIGH** -- Template content stays ~90% the same, just wrapped in the new base layout.

The existing `asset_live.html` (891 lines) was designed as a popup window. For v2.0:
- **Keep:** WebSocket connection logic, state machine (idle/running/completed/failed), log entry rendering, completion banner, auto-scroll, DOM cap at 2000 entries
- **Remove:** "Refocus Graph" button, "Run History" popup button, `window.opener` usage, popup-specific header
- **Change:** Wrap in `{% extends "base.html" %}`, add back-link to graph or previous page
- **Add:** Standard sidebar (inherited from base.html)

The WebSocket endpoint `/ws/asset/{key}` remains unchanged. The only difference is the page is now a full-page view instead of a popup.

---

## CSS Changes Needed in `styles.css`

| Addition | Purpose | Complexity |
|----------|---------|------------|
| `.sidebar-nav` | Fixed-width left sidebar container | Low -- ~15 lines of CSS |
| `.sidebar-icon` | Icon button within sidebar | Low -- ~10 lines |
| `.sidebar-icon.active` | Active page indicator (left border + background) | Low -- ~5 lines |
| `.node.selected-for-reexec` | Node highlight for re-execution target | Low -- ~5 lines, similar to existing `.node.selected` |
| `.node.downstream-highlight` | Downstream node highlight (muted version of selected) | Low -- ~5 lines |
| `.reexec-controls` | Floating "Execute from here" button area | Low -- ~15 lines |

**All achievable with custom CSS in `styles.css`.** Tailwind utility classes handle the layout (flexbox, fixed positioning, widths). Custom CSS handles the Lattice-specific theming (neon colors, glow effects, clip-paths).

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Layout | Jinja2 `{% extends %}` | Duplicate sidebar HTML in each template | DRY violation, maintenance burden |
| Icons | Inline SVG | Lucide/Feather icon library | 3-4 icons do not justify a library; inline SVGs are already the codebase pattern |
| Icons | Inline SVG | CSS-only icons (css.gg) | CSS-only icons are clever but harder to customize colors/sizes with CSS variables |
| Navigation | Full-page server-rendered | Client-side SPA routing | Adds complexity, violates "no new frameworks" constraint, Jinja2 SSR is the existing pattern |
| Re-execution | Extend existing `include_downstream` | New "partial execution" mode | Existing parameter already does exactly what is needed |
| Active runs data | Existing `/ws/execution` WebSocket | New dedicated WebSocket endpoint | Existing endpoint already broadcasts all needed events |
| Downstream highlight | Client-side BFS on graph data | New `/api/graph/downstream/{key}` endpoint | Client already has full graph; avoid extra round-trip |

---

## Installation

No new packages to install. All changes are within the existing dependency tree.

```bash
# No changes needed
# Existing dependencies handle everything:
# - fastapi (routes, templates)
# - jinja2 (template inheritance)
# - uvicorn (ASGI server)
# - Tailwind CSS CDN (already in templates)
# - D3.js v7 CDN (already in templates)
```

---

## Sources

- [Jinja2 Template Inheritance Documentation](https://jinja.palletsprojects.com/en/stable/templates/) -- Official Jinja2 docs on `extends`, `block`, `include`
- [FastAPI Templates Documentation](https://fastapi.tiangolo.com/advanced/templates/) -- Official FastAPI Jinja2 integration
- [MDN History API](https://developer.mozilla.org/en-US/docs/Web/API/History_API/Working_with_the_History_API) -- pushState/popstate reference
- [MDN History.pushState()](https://developer.mozilla.org/en-US/docs/Web/API/History/pushState) -- Detailed API reference
- [Tailwind CSS Sidebar Layouts](https://tailwindcss.com/plus/ui-blocks/application-ui/application-shells/sidebar) -- Official Tailwind sidebar patterns
- [D3.js Selections](https://d3js.org/d3-selection/selecting) -- D3 selection API for node highlighting
- [CSS.GG Icon Library](https://css.gg/) -- Evaluated but not recommended (inline SVG preferred)
- Existing codebase: `src/lattice/web/templates/`, `src/lattice/web/static/`, `src/lattice/web/execution.py`, `src/lattice/plan.py`, `src/lattice/graph.py`

---

*Research completed: 2026-02-07*
*Supersedes: v1.0 STACK.md (multi-window popup approach, 2026-02-06)*

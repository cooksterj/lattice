# Pitfalls Research: Sidebar Navigation, Partial DAG Re-Execution, and Failure Recovery

**Domain:** Adding sidebar navigation, partial re-execution, and failure recovery to existing DAG orchestration web UI
**Researched:** 2026-02-07
**Confidence:** HIGH (based on direct codebase analysis and domain experience)

---

## Critical Pitfalls

### Pitfall 1: Stale Upstream Data During Partial Re-Execution

**What goes wrong:**
When re-executing from a failed asset downstream, the system must load the outputs of upstream assets that already completed successfully in the previous run. But the current `MemoryIOManager` is ephemeral -- it creates a fresh instance per execution (line 364 of `execution.py`: `base_io_manager = MemoryIOManager()`). After the first run completes, all intermediate results are garbage-collected. When the user triggers a partial re-execution starting from the failed asset, the executor needs the outputs of the successfully-completed upstream assets as inputs, but those outputs no longer exist.

The system has two paths to this failure: (1) the IOManager has no data, so `io_manager.load(dep_key)` raises a `KeyError`, and every asset in the partial run fails immediately; or (2) the IOManager happens to have stale data from a different run, producing silently incorrect results.

**Why it happens:**
The `Executor` and `AsyncExecutor` were designed for full-pipeline execution where every asset runs and produces its output before any downstream consumer reads it. Partial re-execution breaks this assumption -- it assumes some assets already have stored outputs from a prior run.

**How to avoid:**
1. For partial re-execution, the executor must first load the results of all upstream assets that are NOT being re-executed. This means either: (a) persisting intermediate results from the original run (e.g., keeping the `MemoryIOManager` instance alive between runs), or (b) re-executing all upstream dependencies before the failed asset even in "partial" mode (which is what `ExecutionPlan.resolve()` with `include_downstream=True` already does -- it includes upstream deps of the target).
2. The `ExecutionPlan.resolve(registry, target=failed_asset, include_downstream=True)` path already resolves the target's upstream dependencies PLUS all downstream. This is the correct approach -- it re-runs the failed asset's upstream deps to regenerate their outputs, then runs the failed asset and everything downstream. The partial saving is that assets which are NOT upstream or downstream of the failed asset are skipped.
3. Do NOT try to cache IOManager results between runs. The simpler and more correct approach is: re-execute upstream deps + failed asset + downstream. The user saves time by not re-running unrelated branches of the DAG.
4. Clearly communicate in the UI which assets will be re-executed (the full subgraph, not just "failed + downstream").

**Warning signs:**
- `KeyError` or missing data errors when loading dependencies during partial re-execution
- Assets complete instantly with wrong output values (loaded from stale cache)
- Test passes when running full pipeline but fails when running partial re-execution

**Phase to address:**
Must be designed in the phase that implements `ExecutionStartRequest` changes for partial re-execution. This is the foundational correctness issue.

---

### Pitfall 2: Ambiguous "Failed Asset" Selection on Graph After Multiple Runs

**What goes wrong:**
The graph currently shows asset status from the most recent execution via CSS classes (`status-running`, `status-completed`, `status-failed`). After an execution with failures, the user sees red (failed) nodes. But if the user runs a new partial execution from a failed asset and THAT also fails at a different asset, the graph now shows a mix of statuses from two different runs. The user cannot tell which failures are from which run, and clicking a "failed" asset may re-execute from a different failure point than intended.

Worse: if the partial re-execution succeeds for the originally-failed asset but fails at a downstream asset, the graph shows the originally-failed asset as "completed" (from the partial run) and a new downstream asset as "failed". The user may not realize the upstream asset was re-executed -- they see a different failure landscape than expected.

**Why it happens:**
The graph status visualization (`updateAssetStatus` in graph.js) overwrites per-asset statuses as they arrive via WebSocket, with no concept of "which run" a status belongs to. Each new execution clears statuses (line 995: `this.executionState.assetStatuses.clear()`) but only for assets that actually execute in the new run. Assets outside the partial execution scope retain their status from the previous run.

**How to avoid:**
1. When starting a partial re-execution, clear ALL asset statuses on the graph first, not just the ones in the current execution scope. Assets outside the execution scope should show "not part of this run" (neutral/default), not their status from a prior run.
2. Alternatively, visually distinguish "in scope" vs. "out of scope" assets during partial execution. Dim/gray-out assets that are not being re-executed, and only color-code the assets that are part of the current run.
3. Add a "run scope" indicator to the graph UI: when a partial execution is active, show which assets are included (highlighted border) vs. excluded (dimmed).
4. Store the execution scope (set of asset keys being re-executed) client-side so the graph can differentiate between "completed in this run" and "completed in a prior run".

**Warning signs:**
- User clicks "Execute from failed" but the wrong subgraph re-executes because they selected the wrong failed asset
- Graph shows green (completed) for assets that were NOT re-executed in the current run
- User confusion about which run produced which status

**Phase to address:**
Must be addressed in the phase that changes graph click behavior to select/highlight. The visual differentiation between "current run scope" and "prior run results" is essential for the re-execution UX.

---

### Pitfall 3: WebSocket Connection Destroyed on Every Full-Page Navigation

**What goes wrong:**
The current architecture uses separate HTML templates for each page (index.html, history.html, asset_detail.html, asset_live.html). Each page loads independently with its own `<script>` block. Navigating between pages causes a full page reload, which destroys:
- All JavaScript state (the `LatticeGraph` instance, execution state, WebSocket connections)
- The WebSocket connection to `/ws/execution`
- Any in-progress asset status tracking on the graph

When v2 introduces a persistent sidebar on ALL pages, the sidebar needs to show active run status and icons that reflect live execution state. But every time the user navigates to a different page (e.g., clicks "Run History" in the sidebar), the page reloads, the WebSocket drops, and the sidebar loses its live state. The sidebar arrives in its default "no execution" state until a new WebSocket connection is established and catches up.

**Why it happens:**
Jinja2 template inheritance gives shared HTML structure (sidebar, header), but JavaScript state does not survive full-page navigation. Each page gets a fresh JavaScript execution context. This is fundamentally different from SPA frameworks where navigation preserves state.

**How to avoid:**
1. Accept that WebSocket state is lost on navigation and design for rapid reconnection. Each page's JavaScript should: (a) check execution status via REST (`/api/execution/status`) immediately on load, (b) connect to WebSocket for live updates, (c) render the sidebar state based on the REST response while waiting for WebSocket to connect. This gives instant sidebar state without waiting for WebSocket.
2. Use `sessionStorage` or `localStorage` to cache the last-known execution state. On page load, read cached state to populate the sidebar immediately, then update when REST/WebSocket data arrives. This eliminates the flash of "idle" sidebar during page transitions.
3. Keep the sidebar JavaScript in a shared file (e.g., `sidebar.js`) loaded by the base template. This shared script handles WebSocket connection, sidebar rendering, and state caching. Page-specific scripts handle only page-specific behavior.
4. Do NOT try to prevent full-page navigation (e.g., with History API / SPA routing). The project constraint requires Jinja2 templates with full-page navigation. Fighting this constraint leads to fragile, half-SPA code.

**Warning signs:**
- Sidebar flickers or shows "no active run" briefly when navigating between pages during execution
- WebSocket reconnection takes 1-2 seconds after navigation, during which sidebar is stale
- Users report "execution stopped" when they navigate, even though execution continues server-side
- WebSocket connection count spikes on server during rapid navigation (connect/disconnect churn)

**Phase to address:**
Must be addressed in the first phase when implementing the sidebar and base template. The WebSocket + REST fallback pattern must be established before any page-specific features are built on top of it.

---

### Pitfall 4: Template Inheritance Block Conflicts When Adding Sidebar to Existing Pages

**What goes wrong:**
The current templates (index.html, history.html, asset_detail.html, asset_live.html) are completely independent HTML documents with no shared base template. Each has its own `<html>`, `<head>`, `<body>`, header, corner decorations, theme toggle, and inline `<style>` blocks. Introducing a base template with a shared sidebar requires refactoring ALL existing templates to extend the base.

The common mistake: defining the base template's blocks too coarsely (e.g., one giant `{% block content %}`) or too finely (dozens of tiny blocks). Too coarse means child templates cannot customize the sidebar or header per-page. Too fine means every child template must override many blocks, and forgetting one causes subtle layout breaks. Another mistake: duplicating the sidebar HTML in each template instead of using inheritance, leading to N copies that drift apart.

Additionally, the current inline `<style>` blocks in each template (e.g., asset_live.html has ~420 lines of inline CSS) will conflict with base template styles. CSS specificity battles between base and child template styles produce mysterious visual bugs.

**Why it happens:**
The v1 templates were designed as independent pages opened in separate windows. There was no need for shared structure because each page was a self-contained document. Adding shared structure after the fact requires careful refactoring.

**How to avoid:**
1. Define the base template with these specific blocks: `{% block title %}`, `{% block head_extra %}` (for page-specific CSS/meta), `{% block content %}` (main page area), `{% block scripts %}` (page-specific JS), and `{% block sidebar_extra %}` (for page-specific sidebar content, if any).
2. Extract all shared CSS into `styles.css` (already partially done) and move inline styles from each template into either the shared stylesheet or page-specific CSS files.
3. Move the duplicated header, theme toggle, and corner decoration markup into the base template. Each child template should only contain its page-specific content.
4. Refactor one template at a time, starting with the simplest (history.html), then asset_detail.html, then index.html (most complex due to D3 graph), then asset_live.html (being replaced with full-page view).
5. Test each template after refactoring before moving to the next. CSS regressions from specificity changes are the most common breakage.

**Warning signs:**
- Visual regression in existing pages after introducing the base template (elements shifted, colors wrong, fonts changed)
- Template renders but sidebar is missing on one page (forgot to extend base)
- JavaScript errors on page load because a script relies on DOM elements that moved to the base template
- `{% block %}` name collision between base and child template

**Phase to address:**
Must be the FIRST implementation task in the sidebar phase. All subsequent features (sidebar content, page-specific behavior) depend on the base template being correctly established.

---

### Pitfall 5: Downstream Propagation Scope Computation Errors in `ExecutionPlan.resolve()`

**What goes wrong:**
The `ExecutionPlan.resolve()` method with `include_downstream=True` includes: (1) all upstream dependencies of the target, (2) the target itself, and (3) all downstream dependents of the target. This is correct for "re-execute from this asset and everything downstream." But there are edge cases:

- **Diamond dependencies**: If asset D depends on both B and C, and B depends on A, re-executing from B should include B, C (only if C also depends on something being re-executed), and D. But `get_all_downstream(B)` returns {D} (correct), and `get_all_upstream(B)` returns {A} (correct). The plan executes A, B, D. But D also depends on C, and C's output is from the previous run (or missing). If the IOManager does not have C's output, D fails.
- **Shared upstream**: If the failed asset B has an upstream dep A that is also an upstream dep of unrelated asset E, re-executing from B will re-execute A. If A's output changes (e.g., reads live data), E's next full pipeline run will see different data than B's partial re-run saw. This is a consistency issue, not a crash, but it can be confusing.

**Why it happens:**
`get_all_downstream()` correctly traverses the reverse adjacency graph. But `get_all_upstream()` for the target only traverses the forward adjacency graph from the target upward. It does not account for OTHER upstream dependencies of downstream assets that are not in the re-execution scope.

**How to avoid:**
1. When computing the re-execution scope for "from failed asset + downstream", the correct algorithm is:
   - Start with the target (failed asset)
   - Add all downstream dependents of the target
   - For EACH asset in this set, add ALL of their upstream dependencies (not just the target's upstream)
   - This ensures that every asset in the scope has all its inputs available
2. The current `ExecutionPlan.resolve(target=X, include_downstream=True)` already does this: it unions `get_all_upstream(target)`, `{target}`, and `get_all_downstream(target)`. BUT it does NOT compute the upstream deps of the downstream assets. If a downstream asset depends on something outside the target's upstream tree, that dependency is missing from the plan.
3. Fix: after computing downstream set, iterate each downstream asset and add its upstream dependencies to the execution scope. Then topologically sort the full set.
4. Write explicit tests for diamond-shaped DAGs where the re-execution target is one branch of the diamond.

**Warning signs:**
- Partial re-execution fails with "dependency not found" for assets that depend on branches outside the re-execution scope
- Test DAGs with linear chains pass, but diamond-shaped DAGs fail
- Inconsistent asset outputs when partial re-runs produce different upstream data than the original run

**Phase to address:**
Must be addressed in the phase that implements the partial re-execution backend. Requires unit tests with diamond-shaped DAGs before integration.

---

### Pitfall 6: Graph Click Behavior Change Breaks Drag Interaction

**What goes wrong:**
The current graph.js has click handlers on nodes (line 526-529) that call `this.openAssetWindow(d.id)`. This is being replaced with select/highlight behavior. D3's drag behavior also uses click-like events. The current code already handles this with `if (event.defaultPrevented) return;` on line 527 to distinguish drags from clicks. But changing the click handler to "select and show execution controls" introduces a new interaction: the user must be able to (1) drag nodes, (2) single-click to select/highlight for re-execution, and (3) click empty space to deselect.

The pitfall: if the new click handler performs any asynchronous work (e.g., fetching asset details for the sidebar info panel), the handler may fire twice on double-click, or the selection state may become inconsistent if the user clicks a different node before the first click's async work completes. Additionally, the existing sidebar (right-side asset detail panel in index.html, lines 87-105) already has open/close behavior tied to node clicks via `selectNode()`. The new "select for re-execution" behavior must coexist with or replace this.

**Why it happens:**
The v1 click handler was simple: open a window (synchronous, fire-and-forget). The v2 click handler must manage selection state, update sidebar content, and potentially update the Execute button context -- all of which involve state transitions that can conflict with rapid clicking or drag interactions.

**How to avoid:**
1. Keep the click handler synchronous. Selection state (which node is selected) should update immediately on click. Any async work (fetching details, updating sidebar) happens after the synchronous state update.
2. Use a single `selectedAsset` state variable on the `LatticeGraph` instance. Clicking a node sets it; clicking empty space clears it. The Execute button reads this state to determine "full pipeline" vs. "from selected asset".
3. Remove the v1 `openAssetWindow()` call entirely. Replace with `this.selectAsset(d.id)` that updates visual highlighting and the Execute button label.
4. Debounce or guard against rapid clicks: if the user clicks node A then immediately clicks node B, the selection should switch cleanly to B without intermediate states from A's async operations leaking through.
5. Explicitly handle the interaction between drag-end and click. The current `event.defaultPrevented` check works, but verify it still works after changing the click handler.

**Warning signs:**
- Dragging a node also selects it (drag-end triggers click handler)
- Double-clicking a node causes two selection state changes
- Clicking rapidly between nodes shows details for the wrong asset
- The Execute button shows stale context after clicking a different node

**Phase to address:**
Must be addressed in the phase that changes graph click behavior from window.open to select/highlight.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Duplicating sidebar HTML in each template instead of using base template inheritance | Faster initial implementation, no refactoring of existing templates | N copies drift apart; sidebar changes require editing every template | Never -- template inheritance is the correct approach from the start |
| Using `localStorage` as the only source of sidebar execution state | No WebSocket needed for sidebar on non-graph pages | Stale state if another tab modifies execution state; localStorage is synchronous and blocks rendering | Only as a cache layer on top of REST + WebSocket, never as sole source |
| Re-executing the entire pipeline instead of implementing proper partial execution | Simpler implementation, no scope computation issues | User frustration with unnecessary re-execution; defeats the purpose of the feature | Acceptable for MVP if partial execution scope computation is flagged as follow-up |
| Keeping v1 popup window code alongside v2 sidebar code during migration | Both approaches work during transition | Two navigation paradigms confuse users; duplicated WebSocket connection patterns | Only during a single migration phase; must be removed before phase completion |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Jinja2 base template + D3 graph page | Putting D3 initialization in the base template script block, causing it to run on non-graph pages | Keep D3 initialization in a page-specific `{% block scripts %}` that only index.html overrides |
| Sidebar WebSocket + execution WebSocket | Creating two WebSocket connections on the graph page (one for sidebar, one for execution graph updates) | Use a single WebSocket connection on the graph page that feeds both the sidebar and the graph; other pages use only the sidebar WebSocket |
| `/api/execution/start` with `target` + `include_downstream` | Sending `target=assetId` without `include_downstream=True`, causing only upstream + target to execute (missing downstream) | Always send `include_downstream=True` when executing from a failed asset; the API already supports this parameter |
| Existing `selectNode()` sidebar + new selection behavior | Calling `selectNode()` (which opens the right sidebar with asset details) AND the new select-for-execution behavior on the same click | Replace `selectNode()` entirely; the v2 click handler should update execution context (sidebar icon badge, Execute button label) without opening a detail panel |
| Cache buster on `graph.js` | Forgetting to bump the `?v=N` parameter in index.html when modifying graph.js | Move to a hash-based cache buster or increment on every change; the MEMORY.md already documents this as a lesson learned from v1 |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Sidebar WebSocket polling on every page | Every page load creates a WebSocket connection for sidebar state; rapid navigation creates connect/disconnect churn | Use REST for initial state, WebSocket only if user stays on page >1 second | >10 page navigations per minute during active execution |
| Re-executing all upstream assets on partial re-run with deep DAG | Partial re-execution from leaf node re-executes entire pipeline because everything is upstream | Show the re-execution scope in UI before user confirms; let user understand what will run | DAGs with >20 assets where failed asset is deep in the graph |
| DOM updates for sidebar run history during execution | Sidebar shows live list of running/completed assets, updated on every WebSocket message; DOM thrashing during rapid asset completion | Batch sidebar updates on `requestAnimationFrame`; update at most 2x per second | >10 assets completing per second in parallel execution |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Execute button always says "EXECUTE" regardless of selection state | User cannot tell if clicking Execute will run full pipeline or partial re-execution | Context-aware label: "EXECUTE ALL" when nothing selected, "EXECUTE FROM [asset]" when failed asset selected |
| No confirmation before partial re-execution | User accidentally re-executes from wrong asset, running a large portion of the pipeline unnecessarily | Show a confirmation with the list of assets that will be re-executed (the scope), let user confirm or cancel |
| Sidebar navigation loses scroll position | User scrolling through run history in sidebar, clicks an entry, navigates to detail page, hits back -- sidebar scroll position is lost | Use `sessionStorage` to save sidebar scroll position per page; restore on navigation |
| Active runs page shows nothing when idle | User navigates to Active Runs page when no execution is running, sees empty page with no context | Show the last completed run's results when idle, with clear "IDLE -- LAST RUN:" header; transition to live view when execution starts |
| Failed asset not visually distinct enough for re-execution | User cannot easily find which asset(s) failed after a run | Add persistent failure indicators (red border, icon) that survive WebSocket disconnect; combine with filter/search if many assets |

## "Looks Done But Isn't" Checklist

- [ ] **Sidebar on all pages:** Verify sidebar appears on index.html, history.html, asset_detail.html, and any new full-page views. Common miss: forgetting to extend the base template on one page.
- [ ] **WebSocket reconnection after navigation:** Navigate away from graph page during execution, navigate back. Verify WebSocket reconnects and graph shows current execution state (not stale or empty).
- [ ] **Partial re-execution with diamond DAG:** Test re-execution from a node that has downstream dependents with OTHER upstream dependencies outside the re-execution scope. Verify those other upstream deps are included in the scope.
- [ ] **Execute button context after deselection:** Select a failed asset, verify Execute button says "EXECUTE FROM [asset]". Click empty space to deselect. Verify Execute button reverts to "EXECUTE ALL".
- [ ] **Sidebar state during execution:** Start execution, navigate to history page, verify sidebar shows active run icon/indicator. Navigate back to graph, verify graph shows current execution progress.
- [ ] **v1 popup code fully removed:** Search codebase for `window.open`, `assetWindows`, `openAssetWindow`, `showPopupBlockedNotice`, `refocusMainWindow`, `lattice_graph` window name. All should be removed or repurposed.
- [ ] **Existing WebSocket endpoints still work:** Verify `/ws/execution` and `/ws/asset/{key}` endpoints still function correctly after refactoring. These are consumed by the new sidebar and full-page views.
- [ ] **Theme toggle works on all pages:** After introducing base template, verify dark/light toggle works consistently across all pages (localStorage theme is read on load, toggle updates all pages).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Stale upstream data in partial re-execution | LOW | Fall back to full pipeline re-execution; add logging that clearly shows which assets were re-executed vs. skipped |
| Template inheritance CSS regressions | MEDIUM | Diff screenshots before/after refactoring; use browser DevTools to trace specificity conflicts; fix one template at a time |
| WebSocket state loss on navigation | LOW | REST endpoint provides ground truth; WebSocket is optimization layer. If WebSocket fails, sidebar shows state from last REST poll |
| Diamond DAG scope computation bug | HIGH | If users encounter this, the partial re-execution produces wrong results. Must fix the scope computation algorithm and re-test all DAG shapes |
| Graph click behavior regression (drag vs. click) | LOW | Revert to v1 click handler if v2 handler breaks drag; the `event.defaultPrevented` guard is the key mechanism to preserve |
| Execute button fires wrong execution type | MEDIUM | Add server-side validation: if `target` is specified, verify it exists and is in a valid state (failed or completed from prior run) before starting execution |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| P1: Stale upstream data in partial re-execution | Backend re-execution phase | Unit test: partial re-execution on linear and diamond DAGs |
| P2: Ambiguous failed asset selection | Graph click behavior change phase | Manual test: run, fail, partial re-run, verify visual state is clear |
| P3: WebSocket destroyed on navigation | Sidebar + base template phase | Navigate during execution, verify sidebar state on every page |
| P4: Template inheritance block conflicts | Sidebar + base template phase (FIRST task) | Visual regression test on all 4 existing pages after base template extraction |
| P5: Downstream scope computation errors | Backend re-execution phase | Unit tests with diamond, fan-out, and fan-in DAG topologies |
| P6: Graph click behavior breaks drag | Graph click behavior change phase | Manual test: drag node, click node, drag-then-release, double-click |

## Sources

- Direct codebase analysis: `src/lattice/web/execution.py`, `src/lattice/executor.py`, `src/lattice/plan.py`, `src/lattice/graph.py`, `src/lattice/web/static/js/graph.js`, all templates
- [Dagster re-run from failure issue #12423](https://github.com/dagster-io/dagster/issues/12423) -- documents edge cases with partial re-execution in DAG frameworks
- [Dagster failed runs re-execution issue #11883](https://github.com/dagster-io/dagster/issues/11883) -- reconciliation sensor failed runs cannot be re-executed
- [WebSocket Reconnection Strategies](https://oneuptime.com/blog/post/2026-01-27-websocket-reconnection/view) -- lifecycle and state recovery patterns
- [How to Handle WebSocket Reconnection Logic](https://oneuptime.com/blog/post/2026-01-24-websocket-reconnection-logic/view) -- exponential backoff and state restoration
- [Jinja2 Template Inheritance Documentation](https://jinja.palletsprojects.com/en/stable/templates/) -- block scoping, super(), and child template patterns
- [Jinja2 Template Inheritance API](https://tedboy.github.io/jinja2/templ9.html) -- block variable scoping pitfalls
- v1.0 pitfalls analysis (prior `.planning/research/PITFALLS.md`) -- P4 (replay buffer), P7 (per-asset WebSocket), P9 (sync-to-async bridge) all still relevant but already solved in v1

---
*Pitfalls research for: Lattice v2.0 Sidebar Navigation, Partial DAG Re-Execution, and Failure Recovery*
*Researched: 2026-02-07*

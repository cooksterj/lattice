# Phase 6: Graph Selection & Failure Recovery - Research

**Researched:** 2026-02-07
**Domain:** D3.js graph interaction, JavaScript state management, FastAPI execution API wiring
**Confidence:** HIGH

## Summary

Phase 6 replaces the current graph click behavior (which opens popup windows via `window.open`) with a click-to-select/highlight pattern, and makes the Execute button context-aware so users can re-execute from a failed asset plus all downstream dependents. This is almost entirely a frontend change -- the backend already fully supports partial re-execution via the existing `target` and `include_downstream` parameters in `ExecutionStartRequest`, `ExecutionManager.run_execution()`, and `ExecutionPlan.resolve()`.

The research found that no new backend code, no new API endpoints, no new dependencies, and no new database changes are needed. The work is concentrated in `graph.js` (change click handler, add selection state, update Execute button wiring) and `styles.css` (add selected-node visual styles). The existing right-side detail sidebar in `index.html` (which already has `selectNode()` and open/close logic) will be repurposed for selected-asset details.

**Primary recommendation:** Wire graph click to `selectNode()` (already exists), persist selection state in `this.selectedNode`, update Execute button label dynamically, and pass `target` + `include_downstream=true` in the POST body when a node is selected. Remove `openAssetWindow` and popup infrastructure but DO NOT remove `window.name`/`assetWindows` tracking yet -- that cleanup belongs to Phase 7.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| D3.js | v7 | Graph rendering, node interaction, drag/zoom | Already loaded in index.html via CDN |
| Vanilla JS | ES6+ | Selection state, DOM manipulation, fetch API | Project constraint: no frameworks |
| FastAPI | existing | REST API for execution start | Backend already wired |
| CSS | existing | Node highlight/selection styling | Existing status styles to extend |

### Supporting

No new libraries needed. All functionality is achieved with existing D3.js and vanilla JS.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual DOM class toggling for selection | D3 selection state library | Overkill for single-selection; D3's `.classed()` already sufficient |
| Client-side downstream computation (BFS) | Server API endpoint for downstream | Server endpoint adds latency; graph data is already client-side. But for v2.0, avoid client-side graph traversal -- just highlight the selected node, not the blast radius (BLAST-01 is out of scope) |
| New `include_upstream=false` plan mode | Existing `include_downstream=true` | Re-running upstream is acceptable for v2.0 (Dagster/Airflow default behavior); avoids IOManager pre-seeding complexity |

## Architecture Patterns

### Current Click Handler (to be replaced)

```javascript
// graph.js line 526-530 -- CURRENT behavior (Phase 3 / v1.0)
.on('click', (event, d) => {
    if (event.defaultPrevented) return; // Ignore drag-end clicks
    event.stopPropagation();
    this.openAssetWindow(d.id);  // Opens popup window
});
```

### New Click Handler (Phase 6)

```javascript
// graph.js -- NEW behavior
.on('click', (event, d) => {
    if (event.defaultPrevented) return; // Ignore drag-end clicks
    event.stopPropagation();
    this.handleNodeClick(d);
});

handleNodeClick(d) {
    // Toggle selection: clicking the already-selected node deselects it
    if (this.selectedNode && this.selectedNode.id === d.id) {
        this.deselectNode();
        return;
    }
    this.selectNodeForExecution(d);
}

selectNodeForExecution(d) {
    this.selectedNode = d;

    // Highlight selected node visually
    this.nodeElements.classed('selected', n => n.id === d.id);

    // Update execute button label
    this.updateExecuteButtonLabel();
}

deselectNode() {
    this.selectedNode = null;
    this.nodeElements.classed('selected', false);
    this.updateExecuteButtonLabel();
}
```

### Execute Button Context-Awareness

```javascript
updateExecuteButtonLabel() {
    const btn = document.getElementById('execute-btn');
    const span = btn.querySelector('span');

    if (this.selectedNode) {
        const name = this.selectedNode.name || this.selectedNode.id;
        const status = this.executionState.assetStatuses.get(this.selectedNode.id);

        if (status === 'failed') {
            span.textContent = `RE-EXECUTE FROM ${name.toUpperCase()}`;
        } else {
            span.textContent = `EXECUTE FROM ${name.toUpperCase()}`;
        }
    } else {
        span.textContent = 'EXECUTE';
    }
}
```

### Execution Start Wiring

```javascript
// In startExecution() -- extend existing requestBody construction
const requestBody = {};

// Date parameters (existing)
if (this.dateState.mode === 'single' && this.dateState.startDate) {
    requestBody.execution_date = this.dateState.startDate;
} else if (this.dateState.mode === 'range' && ...) {
    requestBody.execution_date = this.dateState.startDate;
    requestBody.execution_date_end = this.dateState.endDate;
}

// NEW: Targeted execution when a node is selected
if (this.selectedNode) {
    requestBody.target = this.selectedNode.id;
    requestBody.include_downstream = true;
}
```

### Deselection Patterns

```javascript
// Click graph background -> deselect
this.svg.on('click', () => {
    this.deselectNode();
});

// Escape key -> deselect
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        this.deselectNode();
    }
});
```

### CSS for Selected Node

```css
/* Already exists in styles.css line 681-685 */
.node.selected rect {
    stroke: var(--neon-yellow) !important;
    stroke-width: 3px;
    filter: drop-shadow(0 0 12px rgba(184, 158, 74, 0.4));
}
```

The `.node.selected` style already exists and uses the yellow highlight. No new CSS needed for the basic selection visual.

### Recommended File Changes

```
Modified files:
src/lattice/web/static/js/graph.js
  - Replace click handler: openAssetWindow -> handleNodeClick
  - Add handleNodeClick(), selectNodeForExecution(), deselectNode(), updateExecuteButtonLabel()
  - Modify startExecution() to include target + include_downstream
  - Add Escape key listener for deselection
  - Modify SVG background click to deselect (repurpose existing)
  - Modify stopExecution() to reset button label via updateExecuteButtonLabel()
  - Update progress display to show targeted asset count (not total nodes)

src/lattice/web/static/css/styles.css
  - Possibly add subtle transition for selection state (optional polish)

src/lattice/web/templates/index.html
  - Bump graph.js cache buster (?v=N)
```

### Anti-Patterns to Avoid

- **Do not compute downstream blast radius client-side for v2.0:** BLAST-01 is explicitly out of scope. Selection just highlights the single clicked node. Downstream highlighting is a v2.x feature.
- **Do not prevent selection of non-failed nodes:** The success criteria say "Clicking any asset node on the graph selects and highlights it" -- selection works for ALL nodes, not just failed ones. The Execute button adapts its label based on the selected node's status.
- **Do not open the right-side detail sidebar on click:** Per the v2 decisions, graph click selects/highlights only (no popup, no sidebar open). The right-side sidebar from the original codebase was used for asset details, but the success criteria explicitly say "no popup opens". The existing `selectNode()` method that populates the right sidebar should NOT be called on click -- only `selectNodeForExecution()` which just toggles the CSS class and updates the button.
- **Do not navigate on click:** Graph click is purely a selection action. Navigation is handled by the sidebar rail.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Partial DAG re-execution | Custom execution plan builder | Existing `ExecutionPlan.resolve(target, include_downstream=True)` | Already tested, handles topological sort, upstream deps |
| Targeted execution API | New endpoint or schema | Existing `ExecutionStartRequest.target` + `include_downstream` fields | Schema, route, and manager all already support it |
| Node selection highlighting | Custom SVG attribute manipulation | D3's `.classed('selected', predicate)` | Standard D3 pattern, already used for status classes |
| Downstream computation | Client-side BFS/DFS on graph data | Skip for v2.0 (out of scope per BLAST-01) | Server-side `get_all_downstream()` exists for future use |

**Key insight:** The entire backend infrastructure for targeted re-execution already exists. This phase is purely about wiring the graph UI to use it. The only "new" behavior is the JavaScript selection state and button label update.

## Common Pitfalls

### Pitfall 1: Click vs. Drag Confusion
**What goes wrong:** User drags a node and the click handler fires on mouse-up, selecting the node unintentionally.
**Why it happens:** D3's drag behavior and click events can conflict. A drag-end triggers a click event.
**How to avoid:** Check `event.defaultPrevented` at the top of the click handler. D3's drag behavior calls `event.preventDefault()` during drag, so `event.defaultPrevented` is `true` after a drag. This pattern already exists in the current codebase (line 527).
**Warning signs:** Nodes get selected whenever you try to move them.

### Pitfall 2: Stale Selection After Execution
**What goes wrong:** User selects a failed node, executes, the node succeeds, but the button still says "RE-EXECUTE FROM X".
**Why it happens:** The button label is set at selection time based on `executionState.assetStatuses`, but status updates come via WebSocket during/after execution.
**How to avoid:** Call `updateExecuteButtonLabel()` whenever `updateAssetStatus()` fires. If the selected node's status changes (e.g., from 'failed' to 'completed'), the button label updates in real time.
**Warning signs:** Button label doesn't update during execution.

### Pitfall 3: Selection Persists Across Executions
**What goes wrong:** User selects node A, runs execution, execution completes, but node A is still selected. Next "Execute" click unexpectedly targets node A again.
**Why it happens:** `stopExecution()` doesn't clear the selection.
**How to avoid:** In `stopExecution()`, call `this.deselectNode()` to clear selection and reset the button label. Or alternatively, leave selection in place so the user can immediately re-execute if the fix didn't work -- this is a UX decision.
**Recommendation:** Clear selection after successful completion, keep selection on failure (so user can re-try).

### Pitfall 4: SVG Click Bubbles Through Nodes
**What goes wrong:** Clicking a node also triggers the SVG background click handler, immediately deselecting the node.
**Why it happens:** Click events bubble from node to SVG. The SVG handler deselects.
**How to avoid:** Call `event.stopPropagation()` in the node click handler (already present in current code, line 528). This prevents the event from reaching the SVG handler.
**Warning signs:** Selection appears to flash on and immediately off.

### Pitfall 5: Progress Count Shows Total Nodes Instead of Targeted Subset
**What goes wrong:** When executing a subset (e.g., 3 of 15 assets), the progress bar shows "0/15" instead of "0/3".
**Why it happens:** `startExecution()` currently sets total to `this.nodes.length` (line 886/999).
**How to avoid:** After the execution start response, the WebSocket broadcasts asset_start/asset_complete events only for the targeted assets. The progress total should be updated when the first `asset_start` or `execution_complete` message arrives, or alternatively, fetch the plan count from the server before starting.
**Simplest approach:** Let the progress counter increment naturally from WebSocket events, and set the total from the `execution_complete` message. Or, if the selection is known, compute the count client-side (selectedNode + downstream).
**Pragmatic approach:** Use the `execution_complete.data.completed_count + data.failed_count` as the authoritative total (already done in `showExecutionComplete`). The initial total can be set to "..." or "?" during targeted execution.

### Pitfall 6: MemoryIOManager Is Ephemeral
**What goes wrong:** When re-executing from a failed asset with `include_downstream=True`, upstream assets re-run because `MemoryIOManager` is created fresh each time in `run_execution()` (execution.py line 364).
**Why it happens:** The IOManager doesn't persist between executions. Upstream assets that already succeeded have no stored output.
**How to avoid:** Accept this for v2.0. The existing `include_downstream=True` already re-runs upstream assets to ensure their outputs are available. This is the same approach Dagster and Airflow use by default. Optimization (skip upstream, pre-seed IOManager) is a future consideration.
**Warning signs:** Upstream assets re-execute even though they previously succeeded. This is expected behavior for v2.0.

### Pitfall 7: Cache Buster Not Bumped
**What goes wrong:** After deploying graph.js changes, browsers serve the old cached version. Click handler still opens popups instead of selecting.
**Why it happens:** `index.html` loads `graph.js?v=16` and browsers aggressively cache JS files.
**How to avoid:** Bump the version number in `index.html` line 104: `graph.js?v=17` (or higher).
**Warning signs:** Changes work in incognito but not in regular browser.

## Code Examples

### Example 1: Complete Click Handler Replacement

```javascript
// Source: Verified from codebase analysis of graph.js lines 502-530

// BEFORE (v1.0 popup behavior):
.on('click', (event, d) => {
    if (event.defaultPrevented) return;
    event.stopPropagation();
    this.openAssetWindow(d.id);
});

// AFTER (v2.0 selection behavior):
.on('click', (event, d) => {
    if (event.defaultPrevented) return;
    event.stopPropagation();
    this.handleNodeClick(d);
});
```

### Example 2: Existing Backend Support (No Changes Needed)

```python
# Source: schemas_execution.py lines 58-65
class ExecutionStartRequest(BaseModel):
    target: str | None = None
    include_downstream: bool = False
    execution_date: date | None = None
    execution_date_end: date | None = None

# Source: execution.py lines 601-617 (start_execution endpoint)
async def start_execution(request: ExecutionStartRequest, ...):
    background_tasks.add_task(
        manager.run_execution,
        registry,
        request.target,           # Already wired
        request.include_downstream,  # Already wired
        request.execution_date,
        request.execution_date_end,
    )

# Source: plan.py lines 102-112 (include_downstream support)
if include_downstream:
    required = graph.get_all_upstream(target_key)
    required.add(target_key)
    required.update(graph.get_all_downstream(target_key))
```

### Example 3: Existing CSS Selection Style

```css
/* Source: styles.css lines 681-685 -- already exists */
.node.selected rect {
    stroke: var(--neon-yellow) !important;
    stroke-width: 3px;
    filter: drop-shadow(0 0 12px rgba(184, 158, 74, 0.4));
}
```

### Example 4: Existing SVG Background Click Pattern

```javascript
// Source: graph.js lines 543-550 -- already deselects on background click
this.svg.on('click', () => {
    sidebar.classList.add('translate-x-full');
    this.selectedNode = null;
    this.nodeElements.classed('selected', false);
    const execControls = document.querySelector('.execution-controls');
    if (execControls) execControls.classList.remove('sidebar-open');
});
```

This existing handler already clears selection on background click. Phase 6 repurposes this by adding `updateExecuteButtonLabel()` and removing the sidebar-related logic (or keeping it for the right panel if desired).

### Example 5: Escape Key Deselection

```javascript
// Standard pattern for escape-to-deselect
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && this.selectedNode) {
        this.deselectNode();
    }
});
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Graph click opens popup window | Graph click selects/highlights node | v2.0 (this phase) | Simpler UX, no popup blocker issues |
| Execute always runs full DAG | Execute is context-aware (full or targeted) | v2.0 (this phase) | Enables failure recovery workflow |
| Re-execution requires CLI or API | Re-execution from graph UI | v2.0 (this phase) | Self-service failure recovery |

## Key Facts From Codebase Analysis

### What Already Exists (No Changes Needed)

1. **`ExecutionStartRequest`** (schemas_execution.py) -- has `target: str | None` and `include_downstream: bool = False`
2. **`start_execution` endpoint** (execution.py) -- passes `target` and `include_downstream` to `run_execution()`
3. **`ExecutionManager.run_execution()`** (execution.py) -- passes to `ExecutionPlan.resolve()`
4. **`ExecutionPlan.resolve()`** (plan.py) -- supports `include_downstream=True`, uses `get_all_upstream()` + `get_all_downstream()`
5. **`DependencyGraph.get_all_downstream()`** (graph.py) -- BFS traversal of reverse adjacency
6. **`.node.selected rect` CSS** (styles.css) -- yellow highlight with glow for selected nodes
7. **`event.defaultPrevented` check** (graph.js) -- prevents click after drag
8. **`event.stopPropagation()`** (graph.js) -- prevents SVG background click from firing
9. **SVG background click handler** (graph.js) -- clears selection
10. **`this.selectedNode` property** (graph.js constructor) -- initialized to null

### What Must Change

1. **Node click handler** (graph.js line 529): Change from `this.openAssetWindow(d.id)` to `this.handleNodeClick(d)`
2. **Execute button label**: Dynamically update between "EXECUTE" and "EXECUTE FROM [name]"
3. **`startExecution()` request body** (graph.js line 1014-1028): Add `target` and `include_downstream` when `this.selectedNode` is set
4. **Escape key listener**: Add keydown event listener for deselection
5. **`stopExecution()` button reset**: Call `updateExecuteButtonLabel()` instead of hardcoded 'EXECUTE'
6. **Progress total**: Handle dynamic total for targeted execution
7. **Cache buster**: Bump `graph.js?v=N` in index.html

### What to Remove (Defer to Phase 7)

The popup infrastructure (`openAssetWindow`, `showPopupBlockedNotice`, `assetWindows` Map, `window.name`) should be removed in Phase 7 (Popup Cleanup), NOT in this phase. Phase 6 focuses on making the new selection behavior work; Phase 7 handles deletion of the old code. However, since Phase 6 replaces the click handler, the `openAssetWindow` method becomes dead code after this phase.

**Recommendation:** Remove `openAssetWindow` call from the click handler but leave the method definition intact for Phase 7 to clean up. OR, remove it now since it's dead code and Phase 7 won't need to find it. The safer choice is to remove it now (less dead code to maintain) and let Phase 7 focus on the remaining popup artifacts (popup blocked notice, window name, assetWindows map).

## Open Questions

1. **Should selection persist after execution completes?**
   - What we know: Success criteria don't specify this. Prior research recommends clearing on success, keeping on failure.
   - What's unclear: User preference.
   - Recommendation: Clear selection after execution completes (both success and failure). User can re-select if needed. Simpler implementation and avoids confusion.

2. **Should the right-side detail sidebar open on node selection?**
   - What we know: The v2 decisions say "Graph click selects/highlights only (no navigation, no popup)". The success criteria say "no popup opens". The existing `selectNode()` method opens a right-side panel with asset details.
   - What's unclear: Whether "no popup" also means "no sidebar panel".
   - Recommendation: Do NOT open the right-side detail sidebar on click for this phase. Selection is purely visual (highlight + button label). This keeps the interaction minimal and focused. The detail sidebar can be used later if needed.

3. **Should the progress total show the targeted subset count?**
   - What we know: Currently shows `this.nodes.length` as total. For targeted execution, only a subset runs.
   - What's unclear: Best UX for displaying partial execution progress.
   - Recommendation: Set initial total to the full node count, but let `showExecutionComplete()` correct it (already does this on lines 1141-1142). The user sees progress increment and then gets the final accurate count. Alternatively, fetch `/api/plan?target=X` before starting to get the exact count, but this adds latency.

## Sources

### Primary (HIGH confidence)
- `src/lattice/web/static/js/graph.js` - Complete D3.js graph implementation, click handlers, execution UI
- `src/lattice/web/execution.py` - ExecutionManager, start_execution endpoint, WebSocket routes
- `src/lattice/plan.py` - ExecutionPlan.resolve() with include_downstream support
- `src/lattice/graph.py` - DependencyGraph with get_all_downstream()
- `src/lattice/web/schemas_execution.py` - ExecutionStartRequest with target + include_downstream
- `src/lattice/web/static/css/styles.css` - Existing .node.selected and status styles
- `src/lattice/web/templates/index.html` - Template structure, cache buster
- `.planning/research/ARCHITECTURE.md` - Prior v2 research with detailed component analysis
- `.planning/STATE.md` - Key v2 decisions (graph click = select only)
- `.planning/REQUIREMENTS.md` - RECV-01, RECV-02 specifications

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` - Prior analysis of MemoryIOManager ephemerality and diamond dependency issues
- `.planning/research/STACK.md` - Stack analysis confirming no new dependencies needed
- `tests/test_web.py` - Existing test patterns for execution endpoints and WebSocket
- `tests/test_plan.py` - Test patterns for ExecutionPlan.resolve()

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All tools and libraries already in codebase, verified from source
- Architecture: HIGH - Backend is unchanged, frontend patterns verified from existing graph.js
- Pitfalls: HIGH - All pitfalls identified from direct codebase analysis, not hypothetical
- Code examples: HIGH - All examples derived from actual source code with line references

**Research date:** 2026-02-07
**Valid until:** 2026-03-07 (stable -- no external dependencies, all internal code)

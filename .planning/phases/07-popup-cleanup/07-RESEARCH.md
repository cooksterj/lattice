# Phase 7: Popup Cleanup - Research

**Researched:** 2026-02-07
**Domain:** Dead code removal (JavaScript, CSS)
**Confidence:** HIGH

## Summary

Phase 7 is a pure cleanup phase. All v1 popup infrastructure in `graph.js` is dead code -- no handler calls it, no template references it, and no Python route depends on it. The scope is precisely defined: remove 4 code artifacts from `graph.js` (2 constructor lines, 2 method definitions) and bump the cache buster in `index.html`. There are zero dependencies on external libraries, zero new features, and zero backend changes.

Phase 5 already removed all popup-related code from `asset_live.html` (refocus button, `refocusMainWindow()`, `openRunHistory()`, action buttons). Phase 6 replaced the node click handler to call `handleNodeClick()` instead of `openAssetWindow()`. The only remaining popup code lives in `graph.js`.

**Primary recommendation:** Delete the 4 dead code artifacts from `graph.js`, bump the cache buster in `index.html`, run the existing test suite, and verify via grep that no popup references remain.

## Standard Stack

No new libraries or dependencies. This phase only removes code.

### Core
| Library | Version | Purpose | Relevance |
|---------|---------|---------|-----------|
| N/A | -- | -- | Pure deletion -- no libraries involved |

## Architecture Patterns

### What Stays (DO NOT TOUCH)
The following code in `graph.js` must remain intact -- it is actively used:

- `handleNodeClick(d)` (line 791) -- current click handler
- `selectNodeForExecution(d)` (line 800) -- selection logic
- `deselectNode()` (line 810) -- deselection logic
- `updateExecuteButtonLabel()` (line 822) -- button label management
- `startExecution()` (line 1021) -- execution trigger with `target` + `include_downstream`
- `connectExecutionWebSocket()` (line 1100) -- WebSocket connection
- `selectNode(node)` (line 698) -- sidebar detail panel (called from dep-badge clicks)
- All node highlighting (`highlightConnections`, `clearHighlights`)
- All execution state management, memory display, sparkline, date selection

### What Gets Removed

**4 discrete artifacts, all in `graph.js`:**

| # | What | Location | Lines | Why Dead |
|---|------|----------|-------|----------|
| 1 | `this.assetWindows = new Map()` | Constructor, line 27 | 1 line | Only read/written by `openAssetWindow()` which is dead |
| 2 | `window.name = 'lattice_graph'` | Constructor, line 28 | 1 line | Named window targeting for refocus; `asset_live.html` no longer has refocus button |
| 3 | `openAssetWindow(assetId)` method | Lines 632-654 | 23 lines | Was called from click handler; Phase 6 replaced with `handleNodeClick()` |
| 4 | `showPopupBlockedNotice(url)` method | Lines 656-696 | 41 lines | Only called by `openAssetWindow()` which is dead |

**Also remove:** The `// Window tracking for asset live monitoring (GRAF-02)` comment on line 26.

**Total removal:** ~68 lines of JavaScript.

### What Was Already Removed (by prior phases)

| Artifact | Removed In | Confirmation |
|----------|-----------|--------------|
| `refocusMainWindow()` function in `asset_live.html` | Phase 5 | Grep confirms no matches in templates |
| `openRunHistory()` function in `asset_live.html` | Phase 5 | Grep confirms no matches in templates |
| "REFOCUS GRAPH" button in `asset_live.html` | Phase 5 | Grep confirms no matches in templates |
| "RUN HISTORY" button in `asset_live.html` | Phase 5 | Grep confirms no matches in templates |
| `window.opener` references in `asset_live.html` | Phase 5 | Grep confirms no matches in templates |
| `this.openAssetWindow(d.id)` call in click handler | Phase 6 | Line 529 now calls `this.handleNodeClick(d)` |

### Post-Removal: Cache Buster Bump

`index.html` line 104 currently loads:
```html
<script src="/static/js/graph.js?v=17"></script>
```
After modifying `graph.js`, bump to `?v=18` to ensure browsers fetch the updated file.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| N/A | -- | -- | This is deletion, not construction |

**Key insight:** The entire phase is removal of dead code. There is nothing to build.

## Common Pitfalls

### Pitfall 1: Accidentally Removing Live Code
**What goes wrong:** Removing methods or properties that are still referenced elsewhere, causing runtime errors.
**Why it happens:** Insufficient grep verification before deletion.
**How to avoid:** After deletion, grep the entire `src/` tree for every removed identifier: `openAssetWindow`, `showPopupBlockedNotice`, `assetWindows`, `lattice_graph`, `popup-blocked-notice`, `GRAF-02`. All should return zero results.
**Warning signs:** Any grep match outside of planning docs.

### Pitfall 2: Forgetting the Cache Buster
**What goes wrong:** Browsers serve the old `graph.js` from cache. The dead code is still there from the user's perspective (invisible but harmless), or worse, a stale version with mismatched method references.
**Why it happens:** The `?v=N` cache buster in `index.html` is easy to overlook.
**How to avoid:** Always bump `?v=N` in `index.html` when modifying `graph.js`. Currently at `v=17`, bump to `v=18`.
**Warning signs:** Changes to `graph.js` without corresponding bump in `index.html`.

### Pitfall 3: Removing Constructor Lines Without Preserving Structure
**What goes wrong:** Removing lines 26-28 (comment + assetWindows + window.name) but leaving an awkward blank gap or breaking the constructor flow.
**Why it happens:** Mechanical deletion without reading the surrounding code.
**How to avoid:** After removing the 3 lines (comment + 2 assignments), verify the constructor still reads cleanly -- `this.selectedNode` assignment (line 22) should flow directly into `this.executionState` (line 31).
**Warning signs:** Consecutive blank lines or orphaned comments in the constructor.

### Pitfall 4: Breaking Existing Tests
**What goes wrong:** Removing code that a test somehow references or depends on.
**Why it happens:** Tests may reference popup infrastructure indirectly.
**How to avoid:** Run the full test suite (`python -m pytest tests/ -v`) after deletion. Current tests do NOT reference any popup code (verified: `test_web.py` has no `window.open`, `popup`, `openAssetWindow`, or `assetWindows` references).
**Warning signs:** Test failures after code removal.

## Code Examples

### Exact Lines to Remove from graph.js

**Constructor (lines 26-28):**
```javascript
        // Window tracking for asset live monitoring (GRAF-02)
        this.assetWindows = new Map();
        window.name = 'lattice_graph';
```

**openAssetWindow method (lines 632-654):**
```javascript
    openAssetWindow(assetId) {
        // Check if window is already open (GRAF-02: duplicate prevention)
        const existing = this.assetWindows.get(assetId);
        if (existing && !existing.closed) {
            existing.focus();
            return;
        }

        // MUST be synchronous in click handler -- no await before this line
        const url = '/asset/' + encodeURIComponent(assetId) + '/live';
        const windowName = 'lattice_asset_' + assetId.replace(/[^a-zA-Z0-9_]/g, '_');
        const features = 'width=900,height=700';
        const windowRef = window.open(url, windowName, features);

        if (!windowRef) {
            // Popup was blocked by browser
            this.showPopupBlockedNotice(url);
            return;
        }

        windowRef.focus();
        this.assetWindows.set(assetId, windowRef);
    }
```

**showPopupBlockedNotice method (lines 656-696):**
```javascript
    showPopupBlockedNotice(url) {
        // Remove any existing notice
        const existing = document.querySelector('.popup-blocked-notice');
        if (existing) existing.remove();

        const notice = document.createElement('div');
        notice.className = 'popup-blocked-notice';
        notice.innerHTML = `
            <span style="color: var(--neon-pink, #ff2a6d); font-family: Orbitron, sans-serif;
                  font-size: 0.75rem; letter-spacing: 0.1em;">
                POPUP BLOCKED
            </span>
            <a href="${encodeURI(url)}" target="_blank" rel="noopener"
               style="color: var(--neon-cyan, #05d9e8); text-decoration: underline;
                      font-size: 0.8rem; margin-left: 0.5rem;">
                Open manually
            </a>
            <button onclick="this.parentElement.remove()"
                    style="margin-left: 0.5rem; color: var(--text-secondary, #8282a0);
                           background: none; border: none; cursor: pointer;
                           font-size: 0.8rem;">
                dismiss
            </button>
        `;
        Object.assign(notice.style, {
            position: 'fixed',
            bottom: '1rem',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: '1000',
            padding: '0.75rem 1.5rem',
            background: 'rgba(18, 18, 26, 0.95)',
            border: '1px solid var(--neon-pink, #ff2a6d)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
        });

        document.body.appendChild(notice);
        setTimeout(() => { if (notice.parentElement) notice.remove(); }, 8000);
    }
```

### Cache Buster Bump in index.html (line 104)
```html
<!-- Before -->
<script src="/static/js/graph.js?v=17"></script>
<!-- After -->
<script src="/static/js/graph.js?v=18"></script>
```

## State of the Art

| Old Approach (v1.0) | Current Approach (v2.0) | When Changed | Impact |
|---------------------|-------------------------|--------------|--------|
| Graph click opens popup via `window.open()` | Graph click selects node, updates Execute button | Phase 6 | Click handler already changed; `openAssetWindow` is dead code |
| Popup blocked notice as fallback | No popups = no blocker issues | Phase 6 | `showPopupBlockedNotice` is dead code |
| `window.name = 'lattice_graph'` for refocus targeting | Full-page navigation via sidebar | Phase 4-5 | Named window targeting is dead code |
| `assetWindows` Map for dedup tracking | No popup windows to track | Phase 6 | Map is dead code |
| Refocus button in asset_live.html | Back button navigating to /runs | Phase 5 | Already removed |

## Verification Checklist

After removal, the following greps against `src/` must all return zero matches:

| Search Term | Expected Matches |
|-------------|-----------------|
| `window.open` | 0 |
| `openAssetWindow` | 0 |
| `showPopupBlockedNotice` | 0 |
| `assetWindows` | 0 |
| `popup-blocked-notice` | 0 |
| `popup.blocked` or `popup blocked` | 0 |
| `lattice_graph` (as window name) | 0 |
| `lattice_asset_` (as window name prefix) | 0 |
| `GRAF-02` | 0 |
| `refocusMainWindow` | 0 |
| `window.name` (in graph.js) | 0 |
| `window.opener` (in all src/) | 0 |

Existing test suite must pass: `.venv/bin/python -m pytest tests/ -v`

Functional verification: graph page loads, nodes render, click selects, Execute button works, sidebar navigation works, live logs page works.

## Open Questions

None. The scope is fully defined -- this is pure dead code removal with zero ambiguity.

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `src/lattice/web/static/js/graph.js` (1301 lines) -- verified all popup artifacts and their call sites
- Direct code inspection of `src/lattice/web/templates/asset_live.html` -- confirmed no popup/refocus code remains
- Direct code inspection of `src/lattice/web/templates/index.html` -- confirmed cache buster at `?v=17`
- Direct code inspection of `src/lattice/web/static/css/styles.css` -- confirmed no popup-related CSS rules
- Direct code inspection of `tests/test_web.py` -- confirmed no popup-related test dependencies
- `.planning/phases/06-graph-selection-failure-recovery/06-01-SUMMARY.md` -- confirmed `openAssetWindow` kept as dead code for Phase 7
- `.planning/phases/05-run-monitoring-live-logs/05-02-SUMMARY.md` -- confirmed refocus button and action buttons removed
- `.planning/research/PITFALLS.md` line 226 -- verification checklist for popup removal

### Secondary (MEDIUM confidence)
- None needed -- all findings from direct code inspection

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no libraries involved (pure deletion)
- Architecture: HIGH -- dead code paths verified via grep and call-site analysis
- Pitfalls: HIGH -- all pitfalls are standard code-removal concerns, verified against actual codebase

**Research date:** 2026-02-07
**Valid until:** indefinite (dead code removal does not expire)

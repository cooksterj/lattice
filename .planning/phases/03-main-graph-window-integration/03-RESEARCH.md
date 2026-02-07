# Phase 3: Main Graph Window Integration - Research

**Researched:** 2026-02-06
**Domain:** Browser window.open() API, popup blocker handling, window tracking/deduplication, D3.js click-vs-drag disambiguation
**Confidence:** HIGH

## Summary

This research investigates the implementation of Phase 3: modifying the main graph page's click handler to open asset monitoring in new browser windows (instead of navigating away), tracking open windows to prevent duplicates, and handling popup blockers gracefully. Phase 1 delivered WebSocket streaming infrastructure; Phase 2 delivered the `/asset/{key}/live` page. Phase 3 is purely client-side JavaScript changes to `graph.js` -- no new server-side code, no new templates, no new routes.

The scope is narrow and well-bounded: (1) change one line in the click handler from `window.location.href` to `window.open()`, (2) add a `Map` to track open window references by asset key, (3) add popup blocker detection with a fallback UI. The entire implementation lives in `src/lattice/web/static/js/graph.js`. The critical technical nuance is that `window.open()` must be called synchronously within the click handler (not after any `await`) to avoid popup blockers, and the click handler must distinguish real clicks from drag-end events using `event.defaultPrevented`.

The main graph window's existing WebSocket connection (`/ws/execution`) continues operating independently of any asset windows opened. The execution status updates flow through the existing broadcast mechanism and are unaffected by opening or closing asset windows.

**Primary recommendation:** Modify the existing `.on('click')` handler in `graph.js` to call `window.open()` synchronously with a deterministic window name per asset. Track window references in a `Map<string, Window>`. Check for popup blockers by testing the return value of `window.open()`. No new dependencies or server-side changes needed.

## Standard Stack

### Core

| Library/Module | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| `window.open()` | Browser native | Open new browser window for asset live page | Standard browser API; the project constraint specifies `window.open()` not iframes |
| `window.focus()` | Browser native | Focus existing window when re-clicking same asset | Standard browser API; works reliably on windows you created via `window.open()` |
| D3.js v7 | CDN (already loaded) | Click handler on graph nodes via `.on('click', ...)` | Already used for all graph interactions |

### Supporting

| Library/Module | Version | Purpose | When to Use |
|----------------|---------|---------|-------------|
| `Map` | ES6 native | Track `assetKey -> WindowReference` for deduplication | Used in `LatticeGraph` class to store open window references |
| `Window.closed` | Browser native | Check if a previously-opened window has been closed by user | Checked before attempting `.focus()` on a tracked window |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| JavaScript `Map` for window tracking | Plain object `{}` | `Map` is semantically correct for key-value tracking and supports any key type; slight preference but either works |
| `window.open()` with named target | `window.open()` with `_blank` + manual tracking | Named target (`window.open(url, name)`) provides browser-level deduplication, but calling it with the same name navigates (reloads) the existing window. Manual tracking with `.focus()` avoids reload. Use manual tracking. |
| Inline notification for popup blocked | Modal dialog | Inline notification is less intrusive for a dev tool; a modal would block interaction |

**Installation:** No new packages needed. All APIs are browser-native.

## Architecture Patterns

### Recommended File Structure (changes only)

```
src/lattice/web/
    static/js/
        graph.js            # MODIFY: Click handler + window tracking
```

No new files. No server-side changes. One file modified.

### Pattern 1: Synchronous window.open() in Click Handler

**What:** Call `window.open()` directly and synchronously inside the D3 click handler. Never call it after an `await`, `setTimeout`, or any async callback.

**When to use:** Always. This is not optional -- browsers block `window.open()` calls that are not in the synchronous call stack of a user-initiated event.

**Example:**
```javascript
// Source: MDN Window.open() documentation + existing graph.js click handler pattern
.on('click', (event, d) => {
    if (event.defaultPrevented) return; // Ignore drag-end clicks (D3 pattern)
    event.stopPropagation();

    // MUST be synchronous -- no await before this line
    const url = '/asset/' + encodeURIComponent(d.id) + '/live';
    const windowName = 'lattice-asset-' + d.id.replace(/[^a-zA-Z0-9_]/g, '_');
    const windowRef = window.open(url, windowName, 'width=900,height=700');

    if (!windowRef) {
        // Popup was blocked -- show fallback
        this.showPopupBlockedNotice(url);
        return;
    }

    windowRef.focus();
})
```

**Confidence: HIGH** -- MDN documentation explicitly states that `window.open()` must be called in the synchronous call stack of a user-initiated event. The existing click handler already calls `window.location.href` synchronously, so the change is a direct replacement.

### Pattern 2: Window Tracking with Map for Duplicate Prevention

**What:** Store `window.open()` return values in a `Map<assetKey, WindowReference>`. Before opening a new window, check if a tracked window exists and is still open (`.closed === false`). If so, focus it instead of opening a new one.

**When to use:** For GRAF-02 (re-clicking focuses existing window).

**Example:**
```javascript
// Source: MDN Window.open() documentation, Pattern from javascript.info/popup-windows

constructor(container) {
    // ... existing constructor ...
    this.assetWindows = new Map(); // Track open asset windows
}

openAssetWindow(assetId) {
    const existing = this.assetWindows.get(assetId);
    if (existing && !existing.closed) {
        existing.focus();
        return;
    }

    const url = '/asset/' + encodeURIComponent(assetId) + '/live';
    const windowName = 'lattice-asset-' + assetId.replace(/[^a-zA-Z0-9_]/g, '_');
    const windowRef = window.open(url, windowName, 'width=900,height=700');

    if (!windowRef) {
        this.showPopupBlockedNotice(url);
        return;
    }

    windowRef.focus();
    this.assetWindows.set(assetId, windowRef);
}
```

**Why manual tracking instead of relying on window name alone:** Calling `window.open(url, name)` when a window with that `name` already exists will navigate (reload) the existing window to the URL. This is undesirable -- the asset live page maintains WebSocket connection state, log entries, and execution state that would be lost on reload. Manual tracking via the `Map` lets us call `.focus()` directly without re-navigating.

**Confidence: HIGH** -- MDN documentation confirms that `window.open()` with an existing target name reloads the URL in that window. The `.closed` property check is a standard browser API.

### Pattern 3: D3 Click-vs-Drag Disambiguation

**What:** D3's drag behavior suppresses the click event after a drag operation by setting `event.defaultPrevented = true`. The click handler must check `event.defaultPrevented` to avoid opening a window when the user is finishing a drag.

**When to use:** Always, since the graph nodes have both drag and click handlers.

**Example:**
```javascript
// Source: D3 Observable "Click vs Drag" example (https://observablehq.com/@d3/click-vs-drag)
.on('click', (event, d) => {
    if (event.defaultPrevented) return; // Dragged, not clicked
    event.stopPropagation();
    this.openAssetWindow(d.id);
})
```

**Current state of the code:** The existing click handler at line 522-525 of `graph.js` does NOT check `event.defaultPrevented`. It calls `event.stopPropagation()` and navigates. This means drag-end currently triggers navigation -- a pre-existing bug. The Phase 3 change should add the `event.defaultPrevented` guard.

**Confidence: HIGH** -- D3 v7 official documentation and Observable examples explicitly recommend this pattern.

### Pattern 4: Popup Blocker Detection and Fallback

**What:** `window.open()` returns `null` when the popup is blocked by the browser. Detect this and show a user-friendly message with a direct link.

**When to use:** Whenever `window.open()` is called.

**Example:**
```javascript
// Source: MDN Window.open() documentation
showPopupBlockedNotice(url) {
    // Show a temporary inline notification near the graph
    const notice = document.createElement('div');
    notice.className = 'popup-blocked-notice';
    notice.innerHTML = `
        <span>Popup blocked by browser.</span>
        <a href="${url}" target="_blank" rel="noopener">Open manually</a>
        <button onclick="this.parentElement.remove()">Dismiss</button>
    `;
    document.body.appendChild(notice);

    // Auto-dismiss after 8 seconds
    setTimeout(() => notice.remove(), 8000);
}
```

**Confidence: HIGH** -- MDN documentation explicitly states `window.open()` returns `null` when blocked.

### Anti-Patterns to Avoid

- **Using window name as the sole deduplication mechanism:** `window.open(url, name)` with an existing name reloads the URL in that window, losing WebSocket state. Use manual tracking + `.focus()` instead.
- **Calling `window.open()` after an `await`:** Browsers will block it as a popup. The URL is known statically -- no async operation needed before opening.
- **Using `noopener` in the window features:** `noopener` sets `window.opener` to `null` in the child window, which would break the "Refocus Graph" button in the asset live page (`window.opener.focus()`).
- **Using `_blank` as the target name:** `_blank` always opens a new window, defeating deduplication. Use a deterministic name per asset OR use manual tracking (we use manual tracking).
- **Opening windows from D3 drag-end events:** Always check `event.defaultPrevented` first.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Window deduplication | Custom broadcast/polling between windows | `Map<key, WindowRef>` + `.closed` check | Simple, reliable, browser-native |
| Popup blocker detection | Try-catch around `window.open()` | Check return value for `null` | `window.open()` does not throw; it returns `null` when blocked |
| Click vs drag disambiguation | Custom mouse distance tracking | `event.defaultPrevented` check | D3 v7 sets this automatically after drag operations |
| Window sizing | Pixel-perfect calculations | Static `width=900,height=700` string | Good enough for a dev tool; OS handles DPI scaling |

**Key insight:** Phase 3 is the simplest phase. It modifies a single file (`graph.js`) with well-understood browser APIs. The main risk is not technical complexity but subtle browser behavior (popup blockers, drag-click conflicts).

## Common Pitfalls

### Pitfall 1: Popup Blocker Triggered by Async window.open()

**What goes wrong:** `window.open()` is called after an `await` or inside a `setTimeout`, and the browser blocks it as an unsolicited popup.
**Why it happens:** Browsers require `window.open()` to be in the synchronous call stack of a user gesture (click). Any async boundary breaks this requirement.
**How to avoid:** Call `window.open()` directly in the click handler, before any `await`. The URL (`/asset/{key}/live`) is known statically from the node data -- no server call is needed.
**Warning signs:** `window.open()` returns `null` even though the user clicked a node. Console may show "Popup blocked" messages.

### Pitfall 2: window.open() with Named Target Reloads Existing Window

**What goes wrong:** Using `window.open(url, 'asset-name')` when a window with that name is already open causes the browser to reload the URL in that window, destroying WebSocket state, log entries, and completion banners.
**Why it happens:** The browser spec says that if a window with the target name exists, the URL is loaded into it.
**How to avoid:** Use manual tracking with a `Map`. Before opening, check if the stored `WindowReference` is still open (`.closed === false`). If open, call `.focus()` directly without calling `window.open()`.
**Warning signs:** Re-clicking an asset causes the live page to reload, losing all accumulated state.

### Pitfall 3: Drag-End Triggers Click Handler

**What goes wrong:** After dragging a node, the mouseup event fires a click, which opens a window unintentionally.
**Why it happens:** D3 drag and click events both fire on mouseup. D3 v7 suppresses the click event after a drag by setting `event.defaultPrevented = true`, but the handler must check this.
**How to avoid:** Add `if (event.defaultPrevented) return;` as the first line of the click handler.
**Warning signs:** Dragging a node opens a new browser window.

### Pitfall 4: window.opener Lost with noopener

**What goes wrong:** The "Refocus Graph" button in the asset live page (`window.opener.focus()`) fails because `window.opener` is `null`.
**Why it happens:** If `window.open()` is called with `noopener` in the features string, the child window's `window.opener` reference is set to `null`.
**How to avoid:** Do NOT include `noopener` in the window features. The live page and the graph are same-origin, and the opener reference is needed for the refocus button.
**Warning signs:** The "Refocus Graph" button in the asset live page opens a new tab instead of focusing the main window.

### Pitfall 5: window.focus() Doesn't Work on Tabs

**What goes wrong:** Calling `.focus()` on a tracked window reference does nothing -- the window does not come to the front.
**Why it happens:** If the browser opens the "popup" as a tab instead of a separate window, `.focus()` may not bring it to the foreground. This happens when no window features (dimensions) are specified.
**How to avoid:** Specify `width=` and `height=` in the window features string. This signals to the browser that a separate window (not a tab) is desired. Most browsers will open a popup-style window when dimensions are specified.
**Warning signs:** Re-clicking an asset does not bring the existing window to the front.

### Pitfall 6: Window Name with Special Characters

**What goes wrong:** Asset IDs like `analytics/stats` contain `/` which is not valid in window names. The window may not be created or the name may be mangled.
**Why it happens:** The window name (second parameter of `window.open()`) has restrictions -- it cannot contain spaces and some browsers reject special characters.
**How to avoid:** Sanitize the asset ID for use as a window name: replace non-alphanumeric characters with underscores. Use the original `d.id` as the key in the tracking `Map`.
**Warning signs:** Windows with group-scoped asset IDs (containing `/`) fail to open or tracking fails.

## Code Examples

### Example 1: Complete Click Handler Replacement

```javascript
// Source: Replacing graph.js lines 522-525
// Before:
.on('click', (event, d) => {
    event.stopPropagation();
    window.location.href = '/asset/' + encodeURIComponent(d.id);
})

// After:
.on('click', (event, d) => {
    if (event.defaultPrevented) return; // Ignore drag-end (D3 pattern)
    event.stopPropagation();
    this.openAssetWindow(d.id);
})
```

### Example 2: openAssetWindow Method

```javascript
// Source: MDN Window.open() + manual tracking pattern
openAssetWindow(assetId) {
    // Check if window is already open
    const existing = this.assetWindows.get(assetId);
    if (existing && !existing.closed) {
        existing.focus();
        return;
    }

    const url = '/asset/' + encodeURIComponent(assetId) + '/live';
    const windowName = 'lattice_asset_' + assetId.replace(/[^a-zA-Z0-9_]/g, '_');
    const features = 'width=900,height=700';
    const windowRef = window.open(url, windowName, features);

    if (!windowRef) {
        // Popup was blocked
        this.showPopupBlockedNotice(url);
        return;
    }

    windowRef.focus();
    this.assetWindows.set(assetId, windowRef);
}
```

### Example 3: Popup Blocked Notice

```javascript
// Source: Graceful fallback when popup is blocked
showPopupBlockedNotice(url) {
    // Remove any existing notice
    const existing = document.querySelector('.popup-blocked-notice');
    if (existing) existing.remove();

    const notice = document.createElement('div');
    notice.className = 'popup-blocked-notice';
    // Use textContent for the message, innerHTML only for the link structure
    notice.innerHTML = `
        <span style="color: var(--neon-pink); font-family: Orbitron, sans-serif;
              font-size: 0.75rem; letter-spacing: 0.1em;">
            POPUP BLOCKED
        </span>
        <a href="${encodeURI(url)}" target="_blank" rel="noopener"
           style="color: var(--neon-cyan); text-decoration: underline;
                  font-size: 0.8rem; margin-left: 0.5rem;">
            Open manually
        </a>
        <button onclick="this.parentElement.remove()"
                style="margin-left: 0.5rem; color: var(--text-secondary);
                       background: none; border: none; cursor: pointer;
                       font-size: 0.8rem;">
            dismiss
        </button>
    `;
    // Position at bottom of viewport
    Object.assign(notice.style, {
        position: 'fixed',
        bottom: '1rem',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: '1000',
        padding: '0.75rem 1.5rem',
        background: 'rgba(18, 18, 26, 0.95)',
        border: '1px solid var(--neon-pink)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
    });

    document.body.appendChild(notice);
    setTimeout(() => { if (notice.parentElement) notice.remove(); }, 8000);
}
```

### Example 4: Constructor Addition

```javascript
// Source: Add to LatticeGraph constructor (graph.js line ~25)
constructor(container) {
    // ... existing properties ...

    // Window tracking for duplicate prevention (GRAF-02)
    this.assetWindows = new Map();

    this.init();
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `window.location.href` navigation | `window.open()` for new windows | This phase | Users stay on graph while viewing assets |
| No window tracking | `Map<assetKey, WindowRef>` tracking | This phase | Prevents duplicate windows |
| No drag-click disambiguation | `event.defaultPrevented` check | This phase | Prevents accidental window opens on drag |

**Deprecated/outdated:**
- `d3.event` (D3 v5 and earlier): The project uses D3 v7 where the event is passed as the first parameter to handlers. No need for `d3.event`.
- `window.open()` with `popup=yes` feature: Modern browsers ignore most feature flags. Specifying `width` and `height` is sufficient to hint popup behavior.

## Open Questions

1. **Window size preferences (900x700)**
   - What we know: The asset live page was designed as a monitoring popup with a compact header. 900x700 provides reasonable space for the log container and asset info panel.
   - What's unclear: Whether users on smaller screens would prefer different dimensions.
   - Recommendation: Use `width=900,height=700` as a reasonable default. The window is resizable by the user. This can be adjusted later based on feedback.

2. **Should the main graph track closed windows and clean up the Map?**
   - What we know: The `Map` will accumulate entries over time as users open windows for different assets. Checking `.closed` before `.focus()` already handles stale entries functionally.
   - What's unclear: Whether a large `Map` with many stale entries causes issues.
   - Recommendation: No active cleanup needed. The `Map` is keyed by asset ID, so it grows at most to the number of assets (typically 10-50). Checking `.closed` is cheap. Let entries accumulate.

3. **Should `noopener` be used for security?**
   - What we know: `noopener` prevents the child window from accessing `window.opener`. This is a security best practice for untrusted third-party links. However, the asset live page explicitly uses `window.opener.focus()` for the "Refocus Graph" button.
   - Recommendation: Do NOT use `noopener`. Both windows are same-origin (same Lattice server), and the opener reference is a required feature (AWIN-03 refocus button). There is no security risk since this is a local development tool.

## Sources

### Primary (HIGH confidence)
- **MDN Window.open()** -- https://developer.mozilla.org/en-US/docs/Web/API/Window/open -- Authoritative documentation on parameters, return values, popup behavior, and target names
- **D3 Observable "Click vs Drag"** -- https://observablehq.com/@d3/click-vs-drag -- Official D3 example for disambiguating click and drag events using `event.defaultPrevented`
- **javascript.info Popup Windows** -- https://javascript.info/popup-windows -- Comprehensive guide on `window.open()`, `.focus()`, `.closed`, and window name behavior
- **Existing codebase analysis** -- Direct reading of:
  - `src/lattice/web/static/js/graph.js` -- Current click handler (line 522-525), drag handler (line 467-483), constructor, event listeners
  - `src/lattice/web/templates/asset_live.html` -- Target page, uses `window.opener.focus()` (line 869-873)
  - `src/lattice/web/routes.py` -- `/asset/{key}/live` route already exists (Phase 2 delivered)
  - `.planning/research/ARCHITECTURE.md` -- Component 5 spec (graph.js modifications)
  - `.planning/STATE.md` -- Research flag about synchronous popup blocker handling

### Secondary (MEDIUM confidence)
- **Mike Palmer blog on popup blockers** -- https://www.mikepalmer.dev/blog/open-a-new-window-without-triggering-pop-up-blockers -- Practical guide on the "open first, navigate later" pattern for async operations
- **Ryan Thomson on async window.open()** -- https://www.ryanthomson.net/articles/you-shouldnt-call-window-open-asynchronously/ -- Explains why async calls trigger popup blockers
- **MDN Window.focus()** -- https://developer.mozilla.org/en-US/docs/Web/API/Window/focus -- Documents browser restrictions on focus stealing

### Tertiary (LOW confidence, needs validation during implementation)
- **window.focus() reliability across browsers** -- Works reliably on windows created via `window.open()` with dimension features, but may not work if the browser opens as a tab instead. Validated by multiple sources but browser-specific behavior may vary.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All browser-native APIs, no new dependencies, well-documented
- Architecture: HIGH -- Single file modification (`graph.js`), pattern is straightforward
- Pitfalls: HIGH -- Each pitfall is documented in MDN or official D3 resources with clear avoidance strategies
- Code examples: HIGH -- Based on MDN documentation and direct analysis of existing graph.js code

**Research date:** 2026-02-06
**Valid until:** 2026-06-06 (very stable -- browser APIs do not change frequently)

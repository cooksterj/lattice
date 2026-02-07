# Phase 2: Asset Live Monitoring Page - Research

**Researched:** 2026-02-06
**Domain:** Jinja2 template + vanilla JavaScript WebSocket client for real-time log rendering
**Confidence:** HIGH

## Summary

This research investigates the implementation of Phase 2: a dedicated browser page at `/asset/{key}/live` that shows live execution logs, completion status, and asset details for a single asset. Phase 1 has already built all server-side infrastructure -- the per-asset WebSocket endpoint at `/ws/asset/{key}`, the subscriber registry, replay buffer delivery, and message types (`asset_log`, `asset_start`, `asset_complete`, `replay`). Phase 2 is purely a client-side consumer of this existing infrastructure, plus one new FastAPI route.

The standard approach is a new Jinja2 template (`asset_live.html`) with inline JavaScript that connects to the existing WebSocket endpoint and renders log entries into a scrollable container. The template follows the exact same patterns as the existing `asset_detail.html` and `history.html` -- Tailwind CSS CDN, Orbitron/Space Mono fonts, the "dimmed mission control" design system from `styles.css`, and vanilla JavaScript with `fetch()` for REST and `WebSocket` for streaming. No new server-side dependencies are needed; no new npm packages; no frontend build step.

The key technical elements are: (1) a WebSocket client that handles `replay`, `asset_log`, `asset_start`, and `asset_complete` message types, (2) a state machine with three states (idle, running, completed/failed) that determines what the user sees, and (3) two cross-window interactions (`window.opener.focus()` for refocus and `window.open()` for run history).

**Primary recommendation:** Create one new template (`asset_live.html`), one new route (`/asset/{key}/live`), and inline JavaScript for WebSocket connection and log rendering. Follow existing template patterns exactly. No new dependencies.

## Standard Stack

### Core

| Library/Module | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| FastAPI route | 0.115+ (installed) | New `GET /asset/{key}/live` route | Existing `create_router()` pattern in `routes.py` |
| Jinja2 template | 3.1+ (installed) | `asset_live.html` page template | Same as `asset_detail.html`, `history.html`, `index.html` |
| Browser `WebSocket` API | Native | Connect to `/ws/asset/{key}` | No library needed; same approach as `graph.js` WebSocket usage |
| Browser `fetch()` API | Native | Load asset details from `/api/assets/{key}` | Same pattern as `asset_detail.html` JavaScript |
| Tailwind CSS CDN | CDN (no install) | Utility classes for layout | Already used by all existing templates |
| Orbitron + Space Mono | Google Fonts CDN | Typography | Already used by all existing templates |
| `styles.css` | Local | Design system variables (neon colors, borders, clips) | Shared CSS with all pages |

### Supporting

| Library/Module | Version | Purpose | When to Use |
|----------------|---------|---------|-------------|
| `Element.scrollIntoView()` | Native DOM | Auto-scroll log container to latest entry | Called after each log entry append; use `{behavior: 'smooth'}` only if user is at bottom |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inline `<script>` in template | Separate `asset_live.js` file | Separate file is cleaner for large JS but adds a cache-busting concern; existing `asset_detail.html` uses inline JS (700+ lines). Follow existing pattern. |
| Manual DOM manipulation | Template literals + `innerHTML` | The existing codebase consistently uses `innerHTML` with template literals for dynamic content (see `asset_detail.html` lines 651-697, `history.html` lines 647-656). Follow existing pattern. |
| `requestAnimationFrame` batching | Direct DOM appends per log entry | Batch only if >100 entries/second cause visible jank. Start simple. |

**Installation:** No new packages needed. All required modules are either browser-native or already in the project's dependency list.

## Architecture Patterns

### Recommended File Structure (changes only)

```
src/lattice/web/
    routes.py               # MODIFY: Add GET /asset/{key}/live route
    templates/
        asset_live.html     # NEW: Live monitoring page template with inline JS
```

### Pattern 1: Route Registration Following Existing Convention

**What:** Add the `/asset/{key}/live` route to the existing `create_router()` function in `routes.py`, following the same pattern as `/asset/{key}`.

**When to use:** When adding a new page route that serves a Jinja2 template.

**Example:**
```python
# Source: Existing pattern in routes.py (lines 52-55)
@router.get("/asset/{key:path}", response_class=HTMLResponse)
async def asset_detail(request: Request, key: str) -> HTMLResponse:
    """Serve the asset detail page with run history."""
    return templates.TemplateResponse(request, "asset_detail.html", {"asset_key": key})

# NEW: Following the same pattern
@router.get("/asset/{key:path}/live", response_class=HTMLResponse)
async def asset_live(request: Request, key: str) -> HTMLResponse:
    """Serve the asset live monitoring page."""
    return templates.TemplateResponse(request, "asset_live.html", {"asset_key": key})
```

**Confidence: HIGH** -- Direct extension of existing pattern.

**CRITICAL: Route ordering matters.** FastAPI evaluates routes in registration order. The `/asset/{key:path}/live` route must be registered BEFORE `/asset/{key:path}` because `:path` is greedy and would match `key=group/name/live` otherwise. Alternatively, the `/live` route can be placed after but FastAPI's path matching should handle the more-specific path first. However, since both use `:path` capture, the safest approach is to register `/asset/{key:path}/live` first. Verify with a test.

### Pattern 2: WebSocket State Machine (Client-Side)

**What:** A three-state model (`idle`, `running`, `completed`/`failed`) that determines what the page displays, driven by WebSocket messages.

**When to use:** When the page needs to show different UI based on whether an asset is currently executing.

**States and transitions:**
```
IDLE (default on page load)
  |- Receives `asset_start` message -> RUNNING
  |- Shows: asset details panel, "No execution in progress" status

RUNNING
  |- Receives `asset_log` messages -> append log entries
  |- Receives `asset_complete` with status=completed -> COMPLETED
  |- Receives `asset_complete` with status=failed -> FAILED
  |- Shows: streaming log entries, running indicator

COMPLETED / FAILED
  |- Receives `asset_start` message -> RUNNING (new execution started)
  |- Shows: success/failure banner with duration, final log entries
```

**On WebSocket connect (any state):**
1. If `replay` message received with entries, process each entry as if live (this catches up late connections)
2. If replay includes an `asset_complete` message, transition to COMPLETED/FAILED immediately
3. If replay includes `asset_start` but no `asset_complete`, transition to RUNNING

**Confidence: HIGH** -- Derived from the Phase 1 message types: `asset_start`, `asset_log`, `asset_complete`, `replay`.

### Pattern 3: Log Entry Rendering with Auto-Scroll

**What:** Append log entries to a scrollable container, auto-scrolling to the bottom only when the user is already at the bottom (not when they have scrolled up to read earlier entries).

**When to use:** For any streaming log display.

**Example:**
```javascript
// Source: Common pattern for streaming log UIs
function appendLogEntry(data) {
    const container = document.getElementById('log-container');
    const isAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 50;

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <span class="log-level ${data.level}">${data.level}</span>
        <span class="log-timestamp">${formatTime(data.timestamp)}</span>
        <span class="log-message">${escapeHtml(data.message)}</span>
    `;
    container.appendChild(entry);

    if (isAtBottom) {
        entry.scrollIntoView({ behavior: 'smooth' });
    }
}
```

**Confidence: HIGH** -- Standard pattern for streaming log UIs. The existing codebase uses similar log entry styling in `asset_detail.html` (lines 361-388) and `history.html` (lines 344-371).

### Pattern 4: Cross-Window Communication

**What:** The live monitoring page provides two cross-window interactions: refocusing the main graph window and opening run history.

**Refocus main window:**
```javascript
// If opened via window.open() from graph.js, window.opener is the main graph window
function refocusMainWindow() {
    if (window.opener && !window.opener.closed) {
        window.opener.focus();
    } else {
        // Fallback: open graph in new tab
        window.open('/', '_blank');
    }
}
```

**Open run history:**
```javascript
// Open the existing asset detail page (run history) in a new browser window
function openRunHistory(assetKey) {
    window.open(`/asset/${encodeURIComponent(assetKey)}`, '_blank');
}
```

**Confidence: HIGH** -- `window.opener` is a standard browser API. Since the page opens in a new window (via `window.open` from Phase 3), `window.opener` will reference the main graph window. If the page is opened directly (typed URL), `window.opener` will be `null`, which the fallback handles.

### Pattern 5: Template Structure Following Existing Conventions

**What:** The `asset_live.html` template follows the exact structure of existing templates.

**Existing template structure (from `asset_detail.html` and `history.html`):**
1. `<!DOCTYPE html>` with `<html lang="en" class="dark">`
2. `<head>` with Tailwind CDN, Google Fonts, `styles.css?v=N` link
3. Page-specific `<style>` block (inline CSS for page-specific styles)
4. `<body class="font-mono">`
5. `<header>` with Lattice logo, nav links, theme toggle
6. Main content container with max-width
7. Corner decorations divs
8. `<script>` block with theme toggle + page logic
9. `const ASSET_KEY = "{{ asset_key }}"` for Jinja2 variable injection

**Confidence: HIGH** -- Direct replication of existing template structure.

### Anti-Patterns to Avoid

- **Using a frontend framework (React/Vue/etc.):** The project explicitly constrains to Jinja2 + vanilla JS. All existing pages use this pattern. Do not introduce a build step.
- **Creating a SPA with client-side routing:** Explicitly out of scope per REQUIREMENTS.md.
- **Sharing WebSocket connections between windows:** Already decided against (STATE.md). Each window gets its own connection.
- **Modifying the existing `/ws/execution` endpoint:** The global broadcast endpoint stays unchanged. Asset windows use `/ws/asset/{key}`.
- **Adding unnecessary REST endpoints:** The existing `/api/assets/{key}` already returns all needed asset details (name, group, dependencies, dependents, return_type, checks). No new API endpoints required.
- **Using `setInterval` for polling execution status:** WebSocket already pushes status changes. No polling needed.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML escaping for log messages | Manual regex replace | `textContent` instead of `innerHTML` for message text | XSS prevention; `textContent` auto-escapes |
| Scroll position detection | Custom scroll math | `scrollHeight - scrollTop <= clientHeight + threshold` | Standard DOM API; well-tested pattern |
| WebSocket reconnection | Custom retry logic | Simple `setTimeout` + reconnect in `onclose` handler | The existing `graph.js` uses this pattern (line 988-991); keep it simple for dev tool |
| Theme persistence | Custom storage | `localStorage.getItem('theme')` + class toggle | Already implemented in all existing templates |
| Duration formatting | Custom function | Reuse the `formatDuration(ms)` pattern from existing templates | Identical function exists in `asset_detail.html` (line 642-645) and `history.html` (line 623-626) |

**Key insight:** Phase 2 is almost entirely client-side work consuming Phase 1's server infrastructure. The server changes are minimal (one new route). All UI patterns exist in the codebase already -- the challenge is assembling them into a cohesive live monitoring experience.

## Common Pitfalls

### Pitfall 1: Route Ordering with Path Parameters

**What goes wrong:** The new `/asset/{key:path}/live` route and the existing `/asset/{key:path}` route both use `:path` capture. If the new route is registered after the existing one, FastAPI might match `key = "group/name/live"` instead of routing to the live endpoint.
**Why it happens:** FastAPI's `:path` converter is greedy and matches everything including slashes.
**How to avoid:** Register the `/asset/{key:path}/live` route BEFORE the `/asset/{key:path}` route in the `create_router()` function. Write a test that confirms `GET /asset/data/my_asset/live` returns the live template, not the detail template.
**Warning signs:** Visiting `/asset/some_key/live` renders the asset detail page instead of the live page.

### Pitfall 2: Replay Buffer Contains Mixed Message Types

**What goes wrong:** The replay buffer (`get_replay_buffer()`) returns a list of messages. These are `asset_log` messages. But `asset_start` and `asset_complete` messages are also broadcast to asset subscribers (via `broadcast_to_asset` in `_broadcast_asset_start` and `_broadcast_asset_complete`). However, only `asset_log` messages are stored in the replay buffer (see `_route_log_entry` at line 229-234 of `execution.py`). The `asset_start` and `asset_complete` events are NOT in the replay buffer.
**Why it happens:** The replay buffer was designed for log catch-up, not status catch-up.
**How to avoid:** On WebSocket connect, the client should also check execution status via the REST API (`/api/execution/status`) to determine initial state. If `is_running` is true and the current asset matches, set state to RUNNING. The replay buffer then provides the log catch-up. If `is_running` is false, set state to IDLE.
**Warning signs:** Client connects during execution but shows IDLE state because no `asset_start` message was in the replay.

### Pitfall 3: Stale WebSocket After Execution Ends

**What goes wrong:** The WebSocket connection stays open after execution completes. If a new execution starts later, the client receives messages from the new execution without a clean state reset.
**Why it happens:** The WebSocket connection at `/ws/asset/{key}` is persistent -- it does not close when execution ends.
**How to avoid:** When receiving `asset_complete`, transition to COMPLETED/FAILED state and clear the "running" indicator. When receiving a new `asset_start`, clear the log container and reset to RUNNING state. The WebSocket stays open, which is correct (it allows the page to monitor multiple execution cycles without refresh).
**Warning signs:** Logs from a previous execution remain visible when a new execution starts.

### Pitfall 4: window.opener is null When Page is Opened Directly

**What goes wrong:** The "Refocus Main Window" button calls `window.opener.focus()`, but `window.opener` is null if the user navigated to `/asset/{key}/live` directly (typed URL or bookmark) rather than via `window.open()` from the graph.
**Why it happens:** `window.opener` is only set when a window is opened via `window.open()` from another page.
**How to avoid:** Always check `window.opener && !window.opener.closed` before calling `focus()`. Provide a fallback: navigate to `/` or open the graph in a new tab. Disable/hide the refocus button when `window.opener` is not available.
**Warning signs:** JavaScript error `Cannot read properties of null (reading 'focus')` in console.

### Pitfall 5: Log Container Grows Without Bound

**What goes wrong:** If an asset produces thousands of log entries, appending DOM nodes for each one degrades browser performance.
**Why it happens:** No virtual scrolling or DOM node limit implemented.
**How to avoid:** For v1, add a simple cap: keep only the last N (e.g., 2000) DOM entries in the log container, removing the oldest when the cap is exceeded. This matches the server-side replay buffer concept (500 entries). Virtual scrolling (AWIN-08) is explicitly deferred to v2.
**Warning signs:** Browser becomes sluggish during long-running executions with verbose logging.

### Pitfall 6: XSS via Log Messages

**What goes wrong:** Log messages could contain HTML characters (`<`, `>`, `&`). If inserted via `innerHTML`, they could break rendering or introduce XSS.
**Why it happens:** Asset functions may log arbitrary strings including file paths, URLs, or error messages with angle brackets.
**How to avoid:** Use `textContent` for the message body, not `innerHTML`. For the structured parts (level badge, timestamp), `innerHTML` with template literals is fine because those values come from the server and are controlled strings.
**Warning signs:** Log entries with `<` in them cause broken HTML rendering.

## Code Examples

### Example 1: WebSocket Connection and Message Handling

```javascript
// Source: Pattern derived from existing graph.js WebSocket (lines 970-1001)
// and Phase 1 message types (asset_log, asset_start, asset_complete, replay)

class AssetLiveMonitor {
    constructor(assetKey) {
        this.assetKey = assetKey;
        this.state = 'idle'; // 'idle' | 'running' | 'completed' | 'failed'
        this.ws = null;
        this.logCount = 0;
        this.MAX_LOG_ENTRIES = 2000;
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/asset/${this.assetKey}`;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this.updateConnectionStatus('connected');
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };

        this.ws.onclose = () => {
            this.updateConnectionStatus('disconnected');
            // Reconnect after delay
            setTimeout(() => this.connect(), 2000);
        };

        this.ws.onerror = () => {
            this.updateConnectionStatus('error');
        };
    }

    handleMessage(message) {
        switch (message.type) {
            case 'replay':
                // Process buffered entries on connect
                for (const entry of message.data.entries) {
                    this.handleMessage(entry);
                }
                break;

            case 'asset_start':
                this.setState('running');
                this.clearLogContainer();
                break;

            case 'asset_log':
                if (this.state !== 'running') {
                    this.setState('running');
                }
                this.appendLogEntry(message.data);
                break;

            case 'asset_complete':
                this.setState(message.data.status); // 'completed' or 'failed'
                this.showCompletionBanner(message.data);
                break;
        }
    }

    // ... rendering methods
}
```

### Example 2: Completion Banner Rendering

```javascript
// Source: Pattern derived from existing status-badge CSS classes
// in asset_detail.html and history.html

function showCompletionBanner(data) {
    const banner = document.getElementById('completion-banner');
    const isSuccess = data.status === 'completed';

    banner.className = `completion-banner ${isSuccess ? 'success' : 'failure'}`;
    banner.innerHTML = `
        <span class="banner-icon">${isSuccess ? '&check;' : '&cross;'}</span>
        <span class="banner-status">${data.status.toUpperCase()}</span>
        <span class="banner-duration">${formatDuration(data.duration_ms)}</span>
    `;
    banner.style.display = 'flex';
}
```

### Example 3: Execution Status Check on Page Load

```javascript
// Source: Uses existing /api/execution/status endpoint

async function checkExecutionStatus() {
    try {
        const status = await fetchJSON('/api/execution/status');
        if (status.is_running) {
            // Check if our asset is in the running state
            const assetStatus = (status.asset_statuses || [])
                .find(a => a.id === ASSET_KEY);
            if (assetStatus) {
                if (assetStatus.status === 'running') {
                    setState('running');
                } else if (assetStatus.status === 'completed' || assetStatus.status === 'failed') {
                    setState(assetStatus.status);
                }
            } else {
                // Execution is running but our asset hasn't started yet
                setState('idle');
            }
        }
    } catch (e) {
        // Execution status unavailable; stay in idle
        console.error('Failed to check execution status:', e);
    }
}
```

### Example 4: Route Registration with Correct Ordering

```python
# Source: Modified create_router() in routes.py
# CRITICAL: /live route must be registered BEFORE the greedy :path route

@router.get("/asset/{key:path}/live", response_class=HTMLResponse)
async def asset_live(request: Request, key: str) -> HTMLResponse:
    """Serve the asset live monitoring page."""
    return templates.TemplateResponse(request, "asset_live.html", {"asset_key": key})

@router.get("/asset/{key:path}", response_class=HTMLResponse)
async def asset_detail(request: Request, key: str) -> HTMLResponse:
    """Serve the asset detail page with run history."""
    return templates.TemplateResponse(request, "asset_detail.html", {"asset_key": key})
```

### Example 5: Template Page Structure

```html
<!-- Source: Following exact structure of asset_detail.html -->
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LATTICE // LIVE // {{ asset_key }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/styles.css?v=9">
    <style>
        body { overflow: auto; }
        /* Page-specific styles here */
    </style>
</head>
<body class="font-mono">
    <!-- Header with LATTICE logo, nav, theme toggle -->
    <!-- Status banner area (hidden by default) -->
    <!-- Asset info panel -->
    <!-- Log stream container (scrollable) -->
    <!-- Action buttons (refocus, run history) -->
    <!-- Corner decorations -->
    <script>
        const ASSET_KEY = "{{ asset_key }}";
        // Theme toggle (same as other pages)
        // WebSocket connection + message handling
        // Asset info loading via fetch
        // Log rendering
    </script>
</body>
</html>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling `/api/execution/status` for log updates | WebSocket push via `/ws/asset/{key}` | Phase 1 (just built) | Real-time delivery, no polling overhead |
| Single page with both live and history | Separate `/asset/{key}/live` and `/asset/{key}` routes | Architecture decision | Clean separation of concerns |
| Global broadcast with client-side filtering | Per-asset server-side filtering | Phase 1 decision | Only relevant messages sent to each window |

**Deprecated/outdated:**
- No deprecated patterns relevant to this phase. All browser APIs used (WebSocket, fetch, DOM manipulation) are stable and current.

## Open Questions

1. **Should the log container cap be 2000 or match the server replay buffer (500)?**
   - What we know: The server replay buffer is 500 entries per asset. But a long execution might produce more entries during a single live viewing session. The browser can handle more DOM nodes than the server buffers.
   - What's unclear: Typical log volume per asset in real-world usage.
   - Recommendation: Start with 2000 entries in the DOM container. This is generous for a monitoring tool. If performance issues arise, reduce or add virtual scrolling (v2).

2. **Should the live page show a stripped-down header or the full Lattice header?**
   - What we know: Existing pages (`asset_detail.html`, `history.html`) all have the full header with logo, nav, and theme toggle. The live page opens in a separate window (smaller), so screen real estate matters.
   - What's unclear: Whether the full header is too heavy for a monitoring popup window.
   - Recommendation: Use a compact header -- keep the LATTICE logo and asset name but drop the full nav bar. Include the theme toggle. This differentiates the live window from the main pages while keeping brand consistency.

3. **Initial state when no execution is running**
   - What we know: AWIN-05 says "When no execution is running, user sees asset details including dependencies, type, and group."
   - What's unclear: Whether to show a full asset info panel (like the existing `asset_detail.html` header) or a condensed version.
   - Recommendation: Show a focused asset info panel with: name, group, return type, dependencies list, and dependents list. Fetch from the existing `/api/assets/{key}` endpoint. The log area shows an empty state message like "AWAITING EXECUTION..."

4. **WebSocket reconnection strategy**
   - What we know: The existing `graph.js` reconnects after 1 second on close (line 988-991). The live page should reconnect as well.
   - Recommendation: Reconnect after 2 seconds with the same pattern. No exponential backoff needed for a local dev tool. On reconnect, the replay buffer provides catch-up.

## Sources

### Primary (HIGH confidence)
- **Existing codebase analysis** -- All source files read and analyzed:
  - `src/lattice/web/routes.py` -- Route registration pattern, `create_router()`, path parameters
  - `src/lattice/web/app.py` -- Application factory, router registration
  - `src/lattice/web/execution.py` -- ExecutionManager with subscriber registry, WebSocket endpoints, message types, replay buffer
  - `src/lattice/web/templates/asset_detail.html` -- Template structure, inline JS patterns, CSS conventions
  - `src/lattice/web/templates/history.html` -- Template structure, theme toggle, fetch helpers
  - `src/lattice/web/templates/index.html` -- Main page template structure
  - `src/lattice/web/static/js/graph.js` -- WebSocket connection pattern, execution state handling
  - `src/lattice/web/static/css/styles.css` -- Full design system with CSS variables
  - `src/lattice/web/schemas.py` -- AssetDetailSchema response format
  - `src/lattice/web/schemas_execution.py` -- ExecutionStatusSchema for status checking
  - `src/lattice/observability/log_capture.py` -- Log entry callback pattern (already built in Phase 1)
  - `tests/test_web.py` -- Test patterns with TestClient
- **Phase 1 research and implementation** -- `.planning/phases/01-streaming-infrastructure-and-websocket/01-RESEARCH.md`
- **Architecture research** -- `.planning/research/ARCHITECTURE.md` (Component 4 spec, data flow, window lifecycle)
- **Requirements** -- `.planning/REQUIREMENTS.md` (AWIN-01 through AWIN-05)
- **Project state** -- `.planning/STATE.md` (prior decisions, blockers)
- **Roadmap** -- `.planning/ROADMAP.md` (Phase 2 plan structure, success criteria)

### Secondary (MEDIUM confidence)
- **Browser WebSocket API** -- Standard browser API, well-documented and stable. Behavior verified against existing usage in `graph.js`.
- **FastAPI route ordering with :path** -- FastAPI routes are matched in registration order. Verified by reading FastAPI/Starlette source behavior with path converters.

### Tertiary (LOW confidence, needs validation during implementation)
- **DOM performance with 2000+ log entry nodes** -- The 2000-node cap is an estimate. Actual performance depends on browser, DOM complexity per entry, and rendering pipeline. Should be validated with a test producing high log volume.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- No new dependencies; all patterns exist in codebase
- Architecture: HIGH -- Component 4 was already designed in ARCHITECTURE.md; Phase 1 infrastructure is built and verified
- Pitfalls: HIGH -- Derived from concrete analysis of route ordering behavior, WebSocket message types, and replay buffer contents
- Code examples: HIGH -- Based on direct reading of existing template and JavaScript patterns with minimal extension

**Research date:** 2026-02-06
**Valid until:** 2026-03-06 (stable -- all dependencies are browser-native or pinned project deps)

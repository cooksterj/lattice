# Stack Research: Multi-Window Browser UI with Real-Time WebSocket Streaming

**Research Date:** 2026-02-06
**Dimension:** Frontend Browser APIs for Multi-Window Architecture
**Confidence:** High (all APIs are Baseline Widely Available unless noted)

---

## Executive Summary

Lattice needs to open dedicated browser windows for individual asset monitoring (live log streaming, asset details, run history) without disrupting the main DAG graph window or pipeline execution. The existing stack (FastAPI, Jinja2, vanilla JS, WebSocket) is fully sufficient. No new frameworks or libraries are needed. The solution uses four browser APIs: `window.open()` for window creation, `BroadcastChannel` for cross-window coordination, per-window `WebSocket` connections for real-time data, and `Page Visibility API` for connection optimization.

---

## 1. Window Creation: `window.open()`

### Recommendation: Use `window.open()` with named windows and `popup` feature flag
**Confidence: HIGH**

### What to Use

```javascript
// Open asset window from main graph
const assetWindow = window.open(
    `/asset/${encodeURIComponent(assetId)}/live`,
    `lattice-asset-${assetId}`,          // Named window (reuse on re-click)
    'popup,width=800,height=600'         // Force separate window, not tab
);
if (assetWindow) assetWindow.focus();
```

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Window vs. tab | Window (`popup` feature) | PROJECT.md explicitly requires "new browser window (not tab, not navigation)". The `popup` feature flag in modern browsers requests a separate window rather than a tab. |
| Named windows | `lattice-asset-${assetId}` | Prevents duplicate windows for the same asset. Re-clicking the same asset in the DAG will focus the existing window instead of spawning a new one. `window.open()` with an existing name reuses the browsing context. |
| `noopener` | DO NOT USE | We need `window.opener` to remain set so the child window can call `window.opener.focus()` for the "back to main window" button. Same-origin context means no security risk. |
| Popup blockers | Call from click handler only | `window.open()` must be called synchronously within a user gesture (click event). Calling it from an async callback or timer will be blocked. The current `graph.js` already handles node clicks -- the `window.open()` call replaces the existing `window.location.href` navigation. |
| Window sizing | `width=800,height=600` | Reasonable default for a log viewer. Users can resize freely. No need to specify `left`/`top` -- let the OS position subsequent windows. |

### Pattern: Window Reference Tracking

The main window should track opened windows to enable coordination and prevent duplicates.

```javascript
// In the main LatticeGraph class
this.assetWindows = new Map();  // assetId -> WindowProxy

openAssetWindow(assetId) {
    const existing = this.assetWindows.get(assetId);
    if (existing && !existing.closed) {
        existing.focus();
        return;
    }
    const win = window.open(
        `/asset/${encodeURIComponent(assetId)}/live`,
        `lattice-asset-${assetId}`,
        'popup,width=800,height=600'
    );
    if (win) {
        this.assetWindows.set(assetId, win);
    }
}
```

### What NOT to Use

- **iframes**: PROJECT.md constraint explicitly excludes iframes. They also create layout complexity and shared DOM issues.
- **`target="_blank"` links**: Opens tabs, not windows. No control over window features.
- **Modal dialogs (`showModal()`)**: Blocks the parent window. Cannot position independently on screen.

---

## 2. Cross-Window Communication: `BroadcastChannel` API

### Recommendation: Use `BroadcastChannel` as the primary cross-window coordination mechanism
**Confidence: HIGH**

### Why BroadcastChannel over Alternatives

| Option | Verdict | Rationale |
|--------|---------|-----------|
| **BroadcastChannel** | USE THIS | Baseline Widely Available since March 2022. Fire-and-forget pub/sub. No need to hold window references. Works even if windows open/close independently. Perfect for "main window tells all asset windows that execution started." |
| **window.postMessage()** | USE SPARINGLY | Requires holding a reference to the target window. Good for direct parent-child communication (e.g., the "back to main window" button), but BroadcastChannel is simpler for broadcast scenarios. |
| **window.opener** | USE FOR BACK-BUTTON ONLY | The child window needs `window.opener.focus()` for the "refocus main window" button. This is the simplest approach for a single targeted action. |
| **SharedWorker** | DO NOT USE | NOT Baseline. Limited browser support. Adds complexity. Overkill for this use case. |
| **localStorage events** | DO NOT USE | Hacky workaround from the pre-BroadcastChannel era. Only fires on *other* windows (not the one that wrote). Requires serialization overhead. No structured message format. |

### Channel Architecture

Define two named channels for clear separation of concerns:

```javascript
// Channel 1: Execution lifecycle events (main -> asset windows)
const executionChannel = new BroadcastChannel('lattice-execution');

// Channel 2: Window coordination (any window -> any window)
const windowChannel = new BroadcastChannel('lattice-windows');
```

### Message Protocol

All messages use a consistent envelope format:

```javascript
// Sending
executionChannel.postMessage({
    type: 'execution_started',
    payload: { target: 'asset_name', runId: 'abc-123' }
});

executionChannel.postMessage({
    type: 'execution_complete',
    payload: { runId: 'abc-123', status: 'completed', failedCount: 0 }
});

// Receiving (in asset window)
executionChannel.onmessage = (event) => {
    const { type, payload } = event.data;
    switch (type) {
        case 'execution_started':
            // Switch from detail view to live log view
            break;
        case 'execution_complete':
            // Show completion banner, stop expecting logs
            break;
    }
};
```

### Message Types

| Channel | Message Type | Sender | Receivers | Purpose |
|---------|-------------|--------|-----------|---------|
| `lattice-execution` | `execution_started` | Main window | All asset windows | Signal to switch to live log mode |
| `lattice-execution` | `execution_complete` | Main window | All asset windows | Signal to show completion banner |
| `lattice-execution` | `asset_started` | Main window | Specific asset window | Indicate this asset is now executing |
| `lattice-execution` | `asset_complete` | Main window | Specific asset window | Indicate this asset finished (success/fail) |
| `lattice-windows` | `window_opened` | Any child window | Main window | Register new window (optional, for cleanup) |
| `lattice-windows` | `window_closing` | Any child window | Main window | Notify main that window is closing |

### Lifecycle Management

```javascript
// In every window, clean up on unload
window.addEventListener('beforeunload', () => {
    windowChannel.postMessage({
        type: 'window_closing',
        payload: { windowType: 'asset', assetId: ASSET_KEY }
    });
    executionChannel.close();
    windowChannel.close();
});
```

### What NOT to Use for Cross-Window Communication

- **Polling `localStorage`**: Inefficient and unreliable. BroadcastChannel exists specifically to replace this pattern.
- **SharedWorker as message bus**: Adds a third process. BroadcastChannel does this natively.
- **window.opener chaining**: Fragile. If the main window reloads, all `opener` references become stale. BroadcastChannel survives page reloads because it is name-based.

---

## 3. WebSocket Connection Strategy: Per-Window Connections

### Recommendation: Each window opens its own WebSocket connection with asset-scoped filtering
**Confidence: HIGH**

### Architecture Decision: Per-Window WebSocket vs. Shared WebSocket

| Approach | Verdict | Rationale |
|----------|---------|-----------|
| **Per-window WebSocket** | USE THIS | Each window connects to the same FastAPI WebSocket endpoint but sends a subscription message to filter for its asset. Simple, stateless from the client side, robust against window lifecycle changes. |
| **SharedWorker WebSocket** | DO NOT USE | SharedWorker has limited browser support. Adds complexity. The server already handles multiple WebSocket connections efficiently. |
| **Main window relays via BroadcastChannel** | DO NOT USE | Creates a single point of failure. If the main window is busy or the user navigates it, all child windows lose their data stream. Adds latency. |
| **Server-Sent Events (SSE)** | DO NOT USE | Uni-directional only. The existing infrastructure is WebSocket. SSE would require building a parallel streaming system. |

### WebSocket Endpoint Design (Server Side)

The current server has a single `/ws/execution` endpoint that broadcasts to all clients. The enhancement adds a new asset-scoped endpoint:

```
/ws/asset/{asset_key}/logs    -- Per-asset live log stream
```

This is cleaner than having clients filter on the existing broadcast endpoint because:
1. The server can efficiently route only relevant log entries per connection.
2. No wasted bandwidth sending all-asset updates to a window that only cares about one asset.
3. The existing `/ws/execution` endpoint remains unchanged (backward compatible per PROJECT.md constraint).

### Client-Side WebSocket Pattern

```javascript
class AssetLogStream {
    constructor(assetKey) {
        this.assetKey = assetKey;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
    }

    connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}/ws/asset/${encodeURIComponent(this.assetKey)}/logs`;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            // Optionally send subscription confirmation
        };

        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            this.handleMessage(msg);
        };

        this.ws.onclose = (event) => {
            if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                setTimeout(() => this.connect(), this.reconnectDelay * this.reconnectAttempts);
            }
        };

        this.ws.onerror = () => {
            // Error triggers close event, reconnect handled there
        };
    }

    handleMessage(msg) {
        switch (msg.type) {
            case 'log_entry':
                // Append to log viewer DOM
                break;
            case 'asset_started':
                // Show "executing" state
                break;
            case 'asset_complete':
                // Show completion banner
                break;
        }
    }

    disconnect() {
        if (this.ws) {
            this.ws.close(1000, 'Window closing');
            this.ws = null;
        }
    }
}
```

### Reconnection Strategy

- **Exponential backoff**: Start at 1 second, cap at 5 attempts (1s, 2s, 3s, 4s, 5s).
- **Reset on success**: When `onopen` fires, reset the attempt counter.
- **No reconnect after clean close**: If `event.wasClean` is true (server intentionally closed), do not reconnect.
- **Page Visibility integration**: Disconnect when window is hidden (minimized/background tab), reconnect when visible again. This prevents zombie connections.

### Connection Count Consideration

With N asset windows open, the server handles N+1 WebSocket connections (1 main + N asset streams). For Lattice's use case (single-user, local network, <50 assets), this is negligible. Uvicorn handles thousands of concurrent WebSocket connections without issue.

---

## 4. Page Visibility API: Connection Optimization

### Recommendation: Use `visibilitychange` to pause/resume WebSocket connections in background windows
**Confidence: HIGH**

### Why This Matters

Browsers throttle timers and may reduce resources for background tabs/windows. However, WebSocket connections are NOT throttled (MDN explicitly exempts them). The concern is not browser behavior but resource efficiency -- if a user has 10 asset windows open but is only looking at 2, the other 8 are consuming server connections and bandwidth for data the user is not seeing.

### Pattern

```javascript
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        // Window is in background -- disconnect to save resources
        this.logStream.disconnect();
    } else {
        // Window is visible again -- reconnect
        this.logStream.connect();
    }
});
```

### When NOT to Optimize

If the asset window is receiving logs during active execution and the user just briefly switches windows, disconnecting loses log entries. Two strategies:

1. **Aggressive (recommended for Lattice)**: Always disconnect when hidden. When reconnecting, the server sends any missed log entries since the last seen sequence number. This requires the server to buffer recent logs per asset (which it already does via `LogCapture`).

2. **Conservative**: Keep the connection alive during execution, disconnect only when idle. Simpler but wastes resources.

The aggressive approach is better because the server-side `LogCapture` already stores all log entries in memory during execution. The reconnecting client can request a replay.

---

## 5. Window Lifecycle and the "Back to Main" Button

### Recommendation: Use `window.opener.focus()` for the back-to-main button
**Confidence: HIGH**

### Pattern

```javascript
// In asset window template
document.getElementById('back-to-main').addEventListener('click', () => {
    if (window.opener && !window.opener.closed) {
        window.opener.focus();
    } else {
        // Opener was closed or reloaded -- navigate instead
        window.open('/', '_blank');
    }
});
```

### Why `window.opener` Works Here

- Same-origin context (all windows serve from the same FastAPI server).
- We intentionally DO NOT set `noopener` when calling `window.open()`.
- The main window opened the asset window, so `window.opener` is set.
- `focus()` is always accessible even cross-origin, so this is robust.

### Fallback When Opener Is Lost

If the user refreshes the main window, `window.opener` in child windows becomes `null` (the browsing context changed). The fallback opens a new main window via `window.open('/', '_blank')`. This is acceptable because:
- Lattice is a single-user development tool.
- The BroadcastChannel communication still works after a main window reload (channels are name-based, not reference-based).

---

## 6. Run History Window

### Recommendation: Use the same `window.open()` pattern with a dedicated route
**Confidence: HIGH**

The "Run History" link in the asset window opens a third window type:

```javascript
// In asset window
document.getElementById('run-history-btn').addEventListener('click', () => {
    window.open(
        `/asset/${encodeURIComponent(ASSET_KEY)}/history`,
        `lattice-history-${ASSET_KEY}`,
        'popup,width=900,height=700'
    );
});
```

The history window is simpler than the live log window:
- No WebSocket connection needed (history is static data from REST API).
- No BroadcastChannel subscription needed (historical data does not change during viewing).
- Standard fetch from `/api/history/assets/{key}` on page load.
- The existing `asset_detail.html` template already has all the run history UI -- it can be adapted or a new template created.

---

## 7. Server-Side Requirements (Brief)

This research is frontend-focused, but the server must support:

| Requirement | Current State | Change Needed |
|-------------|--------------|---------------|
| WebSocket broadcast to all clients | Exists (`/ws/execution`) | Keep as-is |
| Per-asset WebSocket endpoint | Does not exist | Add `/ws/asset/{key}/logs` |
| Per-asset log streaming during execution | `LogCapture` captures per-asset | Route captured logs to asset-scoped WebSocket |
| Asset live view route | Does not exist | Add `/asset/{key}/live` serving new template |
| Asset history window route | Partially exists (`/asset/{key}`) | Add `/asset/{key}/history` or reuse existing |
| Log replay on reconnect | Does not exist | Add sequence numbering to log entries, support replay |

---

## 8. Anti-Patterns to Avoid

| Anti-Pattern | Why It Fails for Lattice |
|-------------|------------------------|
| **Single WebSocket shared via SharedWorker** | SharedWorker has limited browser support. Adds complexity with no benefit for a single-user tool. |
| **iframe-based window management** | Shares the parent DOM. Complex sizing/scrolling. Cannot arrange independently on screen. Violates project constraint. |
| **React/Vue for child windows** | Violates tech stack constraint. Vanilla JS is more than sufficient for a log viewer and detail panel. |
| **Polling REST endpoints instead of WebSocket** | Adds latency. Lattice already has WebSocket infrastructure. Polling for real-time logs is fundamentally wrong. |
| **BroadcastChannel as the log transport** | BroadcastChannel is for coordination signals, not high-volume data streams. Log entries should flow over WebSocket. BroadcastChannel messages are fire-and-forget with no delivery guarantee. |
| **`window.name` for data passing** | Deprecated pattern. Use URL query parameters or BroadcastChannel instead. |
| **Storing window state in `localStorage`** | Synchronous, blocks the main thread. Not designed for real-time coordination. Use BroadcastChannel. |

---

## 9. Browser Compatibility Summary

| API | Baseline Status | Since | Notes |
|-----|----------------|-------|-------|
| `window.open()` | Widely Available | Always | Core web platform |
| `BroadcastChannel` | Widely Available | March 2022 | All modern browsers |
| `WebSocket` | Widely Available | Always | Core web platform |
| `Page Visibility API` | Widely Available | July 2015 | All modern browsers |
| `window.opener` | Widely Available | Always | Core web platform |
| `window.postMessage()` | Widely Available | July 2015 | Fallback for direct messaging |
| `SharedWorker` | NOT Baseline | N/A | EXCLUDED -- limited support |

All recommended APIs are Baseline Widely Available and safe for production use in 2025/2026.

---

## 10. Recommended Architecture Diagram

```
+---------------------------+     BroadcastChannel      +---------------------------+
|    MAIN WINDOW (/)        | <-- 'lattice-execution' ->|  ASSET WINDOW             |
|                           |     'lattice-windows'     |  (/asset/{key}/live)      |
|  - D3.js DAG graph        |                           |                           |
|  - Execution controls     |     window.opener         |  - Live log viewer        |
|  - WebSocket /ws/execution| <-------------------------+  - Asset details          |
|  - Node click handler     |     .focus()              |  - Completion banner      |
|    calls window.open()    |                           |  - "Back to Main" button  |
|                           |                           |  - "Run History" button   |
|  Tracks: assetWindows Map |                           |                           |
+---------------------------+                           |  WebSocket:               |
                                                        |  /ws/asset/{key}/logs     |
                                                        +-------------+-------------+
                                                                      |
                                                            window.open()
                                                                      |
                                                        +-------------v-------------+
                                                        |  HISTORY WINDOW           |
                                                        |  (/asset/{key}/history)   |
                                                        |                           |
                                                        |  - Run history table      |
                                                        |  - Run detail modal       |
                                                        |  - REST API only (no WS)  |
                                                        +---------------------------+
```

---

## 11. Integration with Existing Codebase

### Files That Change

| File | Change Type | Description |
|------|------------|-------------|
| `src/lattice/web/static/js/graph.js` | Modify | Replace `window.location.href` in node click handler with `window.open()`. Add `assetWindows` Map tracking. |
| `src/lattice/web/routes.py` | Modify | Add routes for `/asset/{key}/live` and `/asset/{key}/history`. |
| `src/lattice/web/execution.py` | Modify | Add per-asset WebSocket endpoint `/ws/asset/{key}/logs`. Extend `ExecutionManager` to route log entries to asset-scoped connections. |
| `src/lattice/web/templates/asset_live.html` | New | Template for the live log streaming asset window. |
| `src/lattice/web/templates/asset_history.html` | New | Template for the standalone history window (derived from existing `asset_detail.html`). |
| `src/lattice/web/static/js/asset_live.js` | New | JS for the live log window: WebSocket connection, BroadcastChannel listener, log rendering. |
| `src/lattice/observability/log_capture.py` | Modify | Add sequence numbering to log entries for replay support. |

### Files That Do NOT Change

| File | Reason |
|------|--------|
| `src/lattice/web/templates/index.html` | Template structure unchanged. JS changes are in `graph.js`. |
| `src/lattice/web/templates/asset_detail.html` | Existing asset detail page remains for direct navigation. |
| `src/lattice/executor.py` | Execution engine is decoupled from web layer. |
| `src/lattice/web/app.py` | Only needs to mount new routers (minimal change). |

---

*Research completed: 2026-02-06*
*Sources: MDN Web Docs (BroadcastChannel, window.open, postMessage, WebSocket, Page Visibility API, SharedWorker, window.opener, window.name), existing Lattice codebase analysis*

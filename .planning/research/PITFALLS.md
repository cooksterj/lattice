# Pitfalls: Multi-Window Asset Monitoring with WebSocket Streaming

**Project:** Lattice Web UI -- Multi-Window Asset Monitoring
**Analysis Date:** 2026-02-06
**Dimension:** Technical pitfalls for real-time multi-window web UI with WebSocket streaming

---

## P1: Popup Blockers Silently Swallow `window.open()` Calls

**What goes wrong:** Modern browsers block `window.open()` unless it is called synchronously inside a direct user-gesture handler (e.g., a `click` event). If the call is deferred -- wrapped in `await`, placed inside a `setTimeout`, or triggered after an async fetch -- the browser treats it as a programmatic popup and blocks it silently. The call returns `null` instead of a window reference, and no error is thrown. The user clicks an asset node and nothing visible happens.

**Warning signs:**
- `window.open()` returns `null` in testing on Chrome or Firefox but works in Safari (Safari is more permissive)
- The feature works locally but fails for users who have stricter popup settings
- Opening works on first click but fails on second click (some browsers allow one popup per gesture)
- Works when DevTools is open (some browsers relax popup rules during development)

**Why this matters for Lattice specifically:** The current `graph.js` click handler on nodes (`line 522-524`) does `window.location.href = '/asset/' + ...` synchronously, which works fine. Switching to `window.open()` in the same synchronous handler will work. But if the implementation first fetches asset data or checks execution status before opening the window, the async gap will trigger the blocker.

**Prevention strategy:**
1. Call `window.open()` synchronously inside the D3 node click handler, before any async operations
2. Always capture and check the return value: `const win = window.open(...); if (!win) { /* show fallback UI */ }`
3. Provide a visible fallback when blocked: display a toast notification with a direct link the user can click, or open in the current tab with a "back to graph" button
4. Store the window reference in a `Map<assetId, Window>` so subsequent clicks can focus an existing window (`win.focus()`) rather than opening duplicates
5. Test with Chrome's built-in popup blocker enabled (Settings > Privacy > Site Settings > Pop-ups and redirects)

**Phase mapping:** Must be addressed in the first implementation phase when converting the click handler from navigation to window.open. This is a gating issue -- if window.open fails silently, the entire feature appears broken.

---

## P2: WebSocket Connections Accumulate Without Cleanup Across Window Lifecycle

**What goes wrong:** Each asset window opens its own WebSocket connection to `/ws/execution`. When the user closes a window, the browser initiates a TCP close handshake, but the server-side `execution_websocket()` function (line 531-556 of `execution.py`) only removes the socket from the set when `WebSocketDisconnect` is raised during the `while True` loop's `asyncio.sleep(0.5)`. There is a race window: if the window is closed between a successful `send_json` and the next sleep cycle, the dead socket persists in `_websockets` until the next broadcast attempt fails. Meanwhile, the server-side coroutine keeps running, consuming an asyncio task slot.

**Warning signs:**
- `len(self._websockets)` grows over time even after windows are closed (observable via the debug logs already in place)
- asyncio task count increases monotonically during a session
- Server becomes sluggish after opening and closing many asset windows
- `RuntimeError: WebSocket is already closed` appears in server logs during broadcast

**Why this matters for Lattice specifically:** The current code has exactly one WebSocket connection (from the main graph page). Adding N asset windows means N+1 connections. A user monitoring 5-8 assets during a pipeline run is realistic. If they close and reopen windows during a long execution, orphaned connections accumulate. The `broadcast()` method (line 132-147) iterates all sockets, so dead ones cause failed sends and get cleaned up reactively -- but only on the next broadcast, and only for sockets that raise exceptions (not for those that silently buffer).

**Prevention strategy:**
1. Add a `beforeunload` handler in each asset window's JavaScript that sends a WebSocket close frame before the page unloads: `window.addEventListener('beforeunload', () => ws.close(1000, 'window_closed'));`
2. On the server side, add a heartbeat mechanism: if the WebSocket loop does not receive a pong within 10 seconds, forcibly close and remove the socket
3. Track open connections with metadata (asset_id, opened_at) so they can be inspected and debugged
4. Add a maximum connection limit per client (e.g., 20 WebSocket connections total) to prevent runaway accumulation
5. Close the server-side coroutine explicitly when `WebSocketDisconnect` occurs (the current code does this with the `finally` block, but verify the asyncio task is actually cancelled)

**Phase mapping:** Must be designed into the WebSocket endpoint from the start. The `beforeunload` handler should be in the first implementation. Server-side heartbeat can be a follow-up hardening task.

---

## P3: Memory Leak from Unbounded Log Entry Accumulation in ExecutionLogHandler

**What goes wrong:** The `ExecutionLogHandler` (in `log_capture.py`) stores every log entry in `self._entries` as a Python list that grows without bound during execution. When log entries are broadcast to asset windows via WebSocket, the entries are serialized to JSON and sent. But the handler itself keeps all entries in memory for the duration of the `capture_logs()` context manager (which spans the entire execution). For a pipeline with many assets producing verbose logs during a date-range backfill (e.g., 30 days x 10 assets x 50 log lines = 15,000 entries), this list consumes significant memory and slows down iteration when building the `RunResult`.

**Warning signs:**
- Server RSS grows proportionally to execution duration and log volume
- Memory panel on the graph page shows steadily increasing RSS that does not flatten after assets complete
- Backfill runs (date ranges) show dramatically higher memory than single-date runs
- `handler.entries` property (line 74) calls `.copy()` which doubles memory at the point of use

**Why this matters for Lattice specifically:** The current implementation stores logs only for post-mortem (after execution, logs go into SQLite). Adding real-time log streaming means logs must flow through two paths: (1) WebSocket to the browser for live display, and (2) the list for eventual persistence. If both paths accumulate independently, memory doubles. Furthermore, the `_entries.copy()` call on line 74 means every time logs are accessed (e.g., for each partition in a date range), a full copy is made.

**Prevention strategy:**
1. Stream log entries to WebSocket consumers immediately upon capture (extend `emit()` to also enqueue to an async broadcast queue)
2. For persistence, write log entries to SQLite in batches during execution rather than accumulating the entire list
3. If the full list must be kept, impose a cap (e.g., last 10,000 entries per execution) and drop oldest entries with a warning
4. Remove the `.copy()` in the `entries` property -- return a read-only view or the list directly if callers do not mutate it
5. For date-range backfills, clear the handler between partitions (the current code already creates a fresh `capture_logs()` context per partition via the `with` statement on line 278 of `execution.py`, but verify this is preserved when adding streaming)

**Phase mapping:** Must be addressed when implementing the real-time log streaming feature. The decision about whether to stream-then-discard vs. accumulate-and-stream affects the entire log pipeline architecture.

---

## P4: Race Condition Between Window Opening and Execution State

**What goes wrong:** A user clicks an asset node to open its window. The window opens, connects via WebSocket, and requests the current state. But between the click and the WebSocket connection completing (which involves a TCP handshake, HTTP upgrade, and server accept), the asset may transition from "running" to "completed". The window misses the `asset_start` and `asset_complete` messages that were broadcast before it connected. The user sees an empty log view with no indication that the asset already finished.

**Warning signs:**
- Asset window shows "waiting for execution" even though the asset has already completed
- Log entries from before the WebSocket connection are missing from the live view
- The main graph shows an asset as completed (green) but its window shows it as idle
- Intermittent: sometimes works (slow assets), sometimes misses (fast assets)

**Why this matters for Lattice specifically:** The current `ExecutionManager.broadcast()` is fire-and-forget to currently-connected sockets. There is no replay mechanism. The `/api/execution/status` endpoint returns current state but not historical log entries for a specific asset. A user opening a window for an asset that is currently executing will miss all log entries emitted before the WebSocket connected.

**Prevention strategy:**
1. When a new asset window WebSocket connects, send the current execution state as the first message ("state snapshot"): which asset is running, what its status is, and the last N log entries for the requested asset
2. Add an asset-scoped log buffer on the server: `dict[AssetKey, deque[LogEntry]]` with a max size (e.g., 500 entries per asset). New WebSocket connections for that asset receive the buffered entries immediately
3. Include a sequence number in each WebSocket message so the client can detect if it missed messages
4. The client should fetch `/api/execution/status` via REST on connect and reconcile with subsequent WebSocket messages
5. Consider a two-phase connection: (a) REST fetch for current state + recent logs, then (b) WebSocket for live updates going forward

**Phase mapping:** Must be designed into the WebSocket protocol from the start. The server-side log buffer should be implemented alongside the per-asset WebSocket endpoint. Retrofitting replay is significantly harder than building it in.

---

## P5: Cross-Window Reference Management Creates Zombie Windows

**What goes wrong:** The main window stores references to opened asset windows via `window.open()`. If the main window navigates away (e.g., user clicks "HISTORY" nav link on line 43 of `index.html`), reloads, or crashes, all stored window references are lost. The asset windows remain open but the main window can no longer find them. The next time the user clicks the same asset, a duplicate window opens. Now two windows compete for the same WebSocket messages (if keyed by asset), or the user has orphaned windows consuming resources.

**Warning signs:**
- Multiple windows open for the same asset after navigating away and back
- `window.open()` with the same window name parameter opens a new window instead of focusing the existing one (because the reference was lost)
- Users report "too many windows" after extended use
- WebSocket connection count on server keeps growing

**Why this matters for Lattice specifically:** The main graph page at `/` is a full SPA-style page. Navigating to `/history` or `/asset/{key}` causes a full page reload (these are separate Jinja2 templates, not SPA routes). Any JavaScript state in `graph.js` -- including the `LatticeGraph` instance and any window references stored on it -- is destroyed on navigation.

**Prevention strategy:**
1. Use the `name` parameter of `window.open(url, name)` with a deterministic name derived from the asset ID (e.g., `lattice_asset_${assetId.replace(/\//g, '_')}`). Browsers will reuse an existing window with the same name instead of creating a new one
2. On the asset window side, detect if the opener window is gone (`window.opener === null || window.opener.closed`) and show a "main window closed" indicator instead of breaking
3. Store the set of open asset window names in `localStorage` so that after navigation, the main window can reclaim references using `window.open('', existingName)`
4. Add a `beforeunload` handler on the main window that either closes all child windows or warns the user
5. In the asset window's WebSocket handler, if the connection drops, show a reconnection UI rather than leaving a stale window

**Phase mapping:** The `window.open()` name parameter should be used from the first implementation. The localStorage tracking of open windows is a follow-up improvement. The opener detection in asset windows should be part of the initial asset window template.

---

## P6: High-Volume Log Output Overwhelms the Browser DOM

**What goes wrong:** During execution, an asset might produce hundreds of log entries per second (e.g., a data processing asset logging each batch). Each log entry arrives via WebSocket and gets appended to the DOM. At ~50 entries/second, after 60 seconds the DOM has 3,000 new elements. The browser spends increasing time on layout recalculation, repainting, and garbage collection. Scrolling becomes janky. Eventually the tab becomes unresponsive or the browser suggests killing it.

**Warning signs:**
- Asset window becomes sluggish after ~30 seconds of log streaming
- Chrome DevTools Performance tab shows long "Recalculate Style" and "Layout" tasks
- Memory usage of the browser tab grows linearly without bound
- Scroll position jumps erratically when new entries are appended
- CPU usage spikes on the client machine

**Why this matters for Lattice specifically:** The existing `asset_detail.html` renders logs as individual `<div class="log-entry">` elements (lines 361-388). This pattern works for historical logs (finite, loaded once) but will fail for live streaming. The demo assets in the examples directory may produce moderate log volumes, but real-world assets (which this framework is modeled after) routinely produce thousands of log lines during execution.

**Prevention strategy:**
1. Implement a virtual scrolling / windowed rendering approach: only render the visible log entries plus a small buffer above and below. Libraries like this can be implemented in vanilla JS with ~100 lines
2. Cap the in-browser log buffer at a fixed size (e.g., 5,000 entries). When the cap is hit, discard the oldest entries and show a "N earlier entries truncated" indicator
3. Batch DOM updates: instead of appending each log entry as it arrives, collect entries in a JavaScript array and flush to the DOM on a `requestAnimationFrame` cadence (max 60 updates/second regardless of message rate)
4. Use `DocumentFragment` for batch insertions to minimize reflows
5. Add a pause/resume button that stops auto-scrolling and DOM updates while the user is reading, with a badge showing "N new entries" that arrived while paused
6. Consider auto-scroll behavior: only auto-scroll to bottom if the user is already at the bottom. If they have scrolled up to read, hold position and show a "jump to bottom" indicator

**Phase mapping:** The batched rendering and DOM cap should be part of the initial log streaming implementation. Virtual scrolling can be a follow-up optimization if the cap proves insufficient. The pause/resume and scroll behavior should be designed upfront even if implemented incrementally.

---

## P7: Per-Asset WebSocket Multiplexing vs. Separate Connections

**What goes wrong:** Two common approaches exist: (A) one WebSocket per asset window, each connecting to `/ws/asset/{asset_id}`, or (B) a single shared WebSocket connection with message routing by asset ID. Both have distinct failure modes.

Approach A (separate connections): Each window has its own connection. The server must manage N+1 WebSocket connections (1 main + N asset windows). Browser limits vary but most allow 6 concurrent WebSocket connections per origin (in older browsers) or ~256 in modern browsers. With many open asset windows, connection limits could be hit. Each connection also has its own TCP overhead and keepalive cost. The server's `_websockets` set grows linearly.

Approach B (shared connection via BroadcastChannel or SharedWorker): More efficient but significantly more complex. Cross-window communication via `BroadcastChannel` API requires all windows to be on the same origin (true here) and the same browser (true). But if the main window's WebSocket drops, all asset windows lose their data source. The single point of failure is the main window.

**Warning signs:**
- With Approach A: server logs show many concurrent WebSocket connections; asyncio event loop becomes saturated with send tasks
- With Approach B: closing the main window kills log streaming in all asset windows; `BroadcastChannel` messages arrive out of order under load

**Why this matters for Lattice specifically:** The current server architecture has a single `_websockets: set[WebSocket]` that broadcasts all messages to all connections. There is no per-asset filtering. If N asset windows connect, each receives every asset's updates and must filter client-side. This is wasteful: a window for asset A receives log entries for assets B, C, D, etc.

**Prevention strategy:**
1. Recommended approach: separate WebSocket per asset window, with server-side filtering. Create a new endpoint `/ws/asset/{asset_id}` that only sends messages relevant to that asset. This keeps the architecture simple and each window independent
2. On the server side, maintain a mapping: `dict[str, set[WebSocket]]` keyed by asset ID. The broadcast method checks which asset the message is about and sends only to subscribed sockets
3. Keep the existing `/ws/execution` endpoint for the main graph window (broadcasts all asset status changes, memory updates)
4. Set a reasonable limit (e.g., 50 concurrent WebSocket connections) and return HTTP 503 if exceeded
5. Document in the UI that each asset window maintains its own connection; closing a window frees a connection slot

**Phase mapping:** The decision between Approach A and B must be made before implementation begins -- it affects the WebSocket endpoint design, the JavaScript client architecture, and the server-side connection management. Recommend deciding during roadmap/architecture phase.

---

## P8: WebSocket Reconnection Storms After Server Restart

**What goes wrong:** The existing `connectExecutionWebSocket()` in `graph.js` (line 986-990) has an unconditional reconnect: if the WebSocket closes while `isRunning` is true, it retries after 1 second. When the server restarts (e.g., during development with `--reload`, or a crash), all N+1 WebSocket connections drop simultaneously. Every window attempts to reconnect at the same time. The server, still starting up, may reject connections or accept them and immediately drop them. All clients retry again, creating a thundering herd. The server's asyncio event loop is flooded with connection accept/reject cycles.

**Warning signs:**
- Server logs show rapid-fire "WebSocket client connected" / "WebSocket client disconnected" messages
- Uvicorn reload takes noticeably longer when many windows are open
- CPU spike on server during restart with multiple clients
- Clients all reconnect at the exact same moment (visible in browser DevTools network tab)

**Why this matters for Lattice specifically:** During development, `uvicorn --reload` restarts the server on every file change. With 5+ asset windows open, each restart triggers 6+ simultaneous reconnection attempts. The current 1-second fixed retry in `graph.js` means all clients are synchronized.

**Prevention strategy:**
1. Use exponential backoff with jitter for WebSocket reconnection: start at 1 second, double each retry, cap at 30 seconds, add random jitter of 0-1 seconds
2. Limit maximum reconnection attempts (e.g., 10 attempts) and then show a "connection lost -- click to reconnect" UI instead of retrying forever
3. Each asset window should independently manage its reconnection, not coordinate with the main window
4. On the server side, add a connection rate limiter: if more than 20 new WebSocket connections arrive within 2 seconds, queue them with a brief delay
5. During reconnection, show a visible "reconnecting..." indicator in each window so the user knows the system is recovering

**Phase mapping:** Reconnection logic should be built into the JavaScript WebSocket client from the start. Exponential backoff with jitter is a one-time implementation that prevents problems throughout the lifecycle.

---

## P9: Log Streaming Interferes with Asset Execution Performance

**What goes wrong:** The `ExecutionLogHandler.emit()` method is called synchronously from within the asset function's thread. If `emit()` is extended to broadcast log entries via WebSocket (which is an async operation), there are two risks: (1) blocking the asset function's execution thread while waiting for the async broadcast, or (2) if using `asyncio.create_task()` to avoid blocking, creating a backlog of unsent messages that consumes memory.

The current `execution.py` broadcasts asset status changes from async callbacks (`_broadcast_asset_start`, `_broadcast_asset_complete`). But log entries are captured by a synchronous logging handler. Bridging sync logging to async WebSocket sends requires careful thread/async boundary management.

**Warning signs:**
- Asset execution times increase when log streaming is enabled vs. disabled
- `asyncio.Queue` grows without bound when log production rate exceeds WebSocket send rate
- `RuntimeWarning: coroutine was never awaited` in server logs
- Dead WebSocket connections cause `broadcast()` to block on failed sends, which backs up the log queue

**Why this matters for Lattice specifically:** The `AsyncExecutor` runs asset functions via `asyncio.to_thread()` for sync assets (line implied by the executor architecture). The logging handler's `emit()` is called in that thread. Calling `await broadcast()` from a non-async context requires `asyncio.run_coroutine_threadsafe()` or a queue-based approach. Getting this wrong either blocks execution or loses log entries.

**Prevention strategy:**
1. Use an `asyncio.Queue` as the bridge: `emit()` puts log entries onto the queue (thread-safe via `loop.call_soon_threadsafe(queue.put_nowait, entry)`). A separate async task reads from the queue and broadcasts to relevant WebSocket connections
2. Set a maximum queue size (e.g., 10,000 entries). If the queue is full, drop the oldest entry and increment a "dropped logs" counter that is periodically sent to clients
3. Never call `await` from within the logging handler -- it runs in the executor's worker thread, not the asyncio event loop thread
4. Batch log broadcasts: instead of one WebSocket message per log entry, collect entries for 100ms and send them as an array. This reduces WebSocket frame overhead and browser message handling
5. Add a configuration flag to disable log streaming (keep only file/SQLite capture) for performance-sensitive deployments

**Phase mapping:** This is the core technical challenge of the log streaming feature. The sync-to-async bridge design must be settled before any implementation begins. Recommend prototyping the queue-based approach in isolation before integrating with the full system.

---

## P10: Browser Tab Throttling Delays WebSocket Messages in Background Windows

**What goes wrong:** Modern browsers aggressively throttle background tabs and windows. When an asset window is not focused (the user is looking at the main graph or another asset window), the browser may: (1) reduce `setTimeout`/`setInterval` frequency to once per second, (2) defer `requestAnimationFrame` callbacks entirely, (3) throttle WebSocket message processing, and (4) suspend the page entirely after 5 minutes of inactivity (Chrome's "Tab Freeze" feature).

When the user switches back to a throttled asset window, the WebSocket receive buffer may have accumulated hundreds of messages. The client suddenly processes them all at once, causing a visible lag and a burst of DOM updates.

**Warning signs:**
- Asset window shows a burst of log entries when the user switches to it, rather than a smooth stream
- Timestamps on displayed log entries are clustered instead of evenly spaced
- The "auto-scroll to bottom" behavior jumps erratically when the window regains focus
- WebSocket `onmessage` handler logs show message timestamps bunched together

**Why this matters for Lattice specifically:** The entire use case is multi-window monitoring. By definition, only one window is focused at a time. Every other window is in the background and subject to throttling. If the user opens 5 asset windows, 4 are always throttled.

**Prevention strategy:**
1. Design the client to tolerate message batches: when processing received messages, do not perform DOM updates for each individual message. Instead, accumulate messages and render on the next `requestAnimationFrame`
2. Include server-side timestamps in each message (not client-side). When rendering, use the server timestamp for ordering and display, not the client receive time
3. Add a "catch-up" mode: when a window regains focus (detected via `document.visibilitychange` event), fetch any missed state from the REST API and reconcile
4. Accept that background windows will have delayed updates. Do not try to fight browser throttling -- design the UX around it (e.g., show a "last updated X seconds ago" indicator)
5. Consider using `Web Workers` for WebSocket management if real-time updates in background windows are critical -- Workers are not subject to the same throttling as the main thread

**Phase mapping:** The `requestAnimationFrame`-based rendering and visibility change handling should be in the initial implementation. Web Worker optimization is an advanced follow-up only if background accuracy is critical.

---

## P11: Shared ExecutionManager State Corruption with Per-Asset WebSocket Endpoints

**What goes wrong:** The current `ExecutionManager` has a single `_websockets: set[WebSocket]` and a single `broadcast()` method. Adding per-asset WebSocket endpoints means the manager must track which WebSocket belongs to which asset. If this mapping is implemented as a `dict[str, set[WebSocket]]`, concurrent modifications (connections arriving and leaving while broadcasts are in progress) can cause `RuntimeError: Set changed size during iteration` or, worse, silently skip sockets.

The existing broadcast already handles dead sockets by collecting them in a separate set and removing after iteration (lines 139-147). But with multiple dictionaries being modified concurrently by different asyncio tasks, the single-threaded-but-interleaved nature of asyncio means a `broadcast()` to asset A can be interrupted by a new connection arriving for asset B, modifying the shared data structure.

**Warning signs:**
- Intermittent `RuntimeError: dictionary changed size during iteration` errors during high-connection-churn periods
- Some asset windows stop receiving updates while others continue working
- Adding a new WebSocket connection causes a brief pause in message delivery to other connections

**Why this matters for Lattice specifically:** All WebSocket handling runs on the single asyncio event loop. There is no threading concern, but `await` points in the broadcast loop (the `await ws.send_json()` call) yield control, allowing other coroutines to modify the connection registry.

**Prevention strategy:**
1. Take a snapshot of the connection set before iterating: `sockets = set(self._asset_websockets.get(asset_id, ()))` then iterate the snapshot
2. Alternatively, use `asyncio.Lock` around connection registry modifications and broadcast iterations (not around individual sends, which would serialize all sends)
3. Keep the per-asset socket registry as a separate class (`AssetConnectionManager`) to encapsulate the concurrency logic away from the execution broadcast logic
4. Write explicit tests that simulate concurrent connect/disconnect/broadcast operations using `asyncio.gather()`

**Phase mapping:** Must be addressed in the WebSocket endpoint implementation phase. The connection registry design is foundational and cannot be safely retrofitted.

---

## Summary by Implementation Phase

| Phase | Pitfalls to Address | Priority |
|-------|---------------------|----------|
| **Architecture/Design** | P7 (multiplexing decision), P9 (sync-to-async bridge design), P4 (replay protocol) | Critical -- these are architectural decisions that cannot be deferred |
| **Window Management** | P1 (popup blockers), P5 (cross-window references), P8 (reconnection storms) | High -- user-facing failures |
| **WebSocket Infrastructure** | P2 (connection cleanup), P11 (state corruption), P4 (state replay) | High -- reliability |
| **Log Streaming** | P3 (memory leaks), P6 (DOM performance), P9 (execution interference) | High -- the core feature |
| **Polish/Hardening** | P10 (background throttling), P8 (reconnection backoff) | Medium -- quality of experience |

---

*Analysis based on: existing codebase at `src/lattice/web/`, `src/lattice/observability/`, and PROJECT.md requirements*

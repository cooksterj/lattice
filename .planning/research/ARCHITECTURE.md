# Architecture: Multi-Window Real-Time Asset Monitoring

**Research Date:** 2026-02-06
**Dimension:** Architecture for multi-window real-time monitoring web UI
**Status:** Complete

---

## Executive Summary

This document defines the component architecture, data flow, and build order for adding multi-window asset monitoring to the Lattice web UI. The design extends the existing ExecutionManager/WebSocket broadcast infrastructure with asset-scoped subscription channels and real-time log streaming. Each component boundary is explicit, and the build order reflects dependency chains between server-side and client-side pieces.

---

## Component Map

### Component 1: Asset Log Streaming Service (Server-Side)

**Purpose:** Capture log entries during asset execution and make them available for real-time streaming to subscribing clients.

**Boundary:** Lives in the observability layer (`src/lattice/observability/`). Extends the existing `ExecutionLogHandler` to emit log entries in real time rather than only collecting them in a list for post-execution storage.

**Interfaces:**
- **Input:** Python `logging.LogRecord` objects emitted during asset execution (same source as existing `ExecutionLogHandler`)
- **Output:** Callable callback `on_log_entry(entry: LogEntry) -> None` invoked synchronously each time a log is captured. The callback is set by the ExecutionManager before execution starts.

**What it owns:**
- A new `StreamingLogHandler` class (or an enhancement to `ExecutionLogHandler`) that, in addition to appending to its internal list, invokes a registered callback per log entry
- The `set_current_asset()` context tracking (already exists)
- The `LogEntry` creation with `asset_key` tagging (already exists)

**What it does NOT own:**
- WebSocket connections (those belong to ExecutionManager)
- Filtering logic for which client gets which log (that belongs to the subscription router)
- Historical log storage (unchanged, belongs to `RunRecord` / history store)

---

### Component 2: Subscription-Aware WebSocket Router (Server-Side)

**Purpose:** Manage WebSocket connections that are scoped to specific assets, filtering broadcast messages so each asset window receives only relevant updates.

**Boundary:** Lives in the web layer (`src/lattice/web/`). This is a new WebSocket endpoint or an enhancement to the existing `/ws/execution` endpoint.

**Interfaces:**
- **Input from client:** WebSocket connection request with a query parameter or initial subscription message specifying the `asset_key` (e.g., `ws://host/ws/asset/{asset_key}` or `ws://host/ws/execution?subscribe=asset_key`)
- **Input from server:** Log entries and asset status updates from ExecutionManager
- **Output to client:** JSON messages filtered to the subscribed asset: `{type: "asset_log", data: {asset_key, level, message, timestamp}}`, `{type: "asset_start", data: {...}}`, `{type: "asset_complete", data: {...}}`

**What it owns:**
- A mapping of `asset_key -> set[WebSocket]` for per-asset subscriptions
- Connection lifecycle management (accept, register subscription, remove on disconnect)
- The filtering logic that routes log entries and status updates to the correct subscriber set
- Dead connection cleanup (extend existing pattern from `ExecutionManager.broadcast`)

**What it does NOT own:**
- The log capture itself (belongs to Streaming Log Handler)
- The execution lifecycle (belongs to ExecutionManager)
- The main graph WebSocket broadcast (the existing `/ws/execution` continues unchanged)

**Design Decision -- New Endpoint vs. Enhanced Existing:**

Recommended: **New dedicated endpoint** `/ws/asset/{asset_key}` rather than modifying the existing `/ws/execution`.

Rationale:
1. The existing `/ws/execution` serves the main graph page with broadcast semantics (all clients get all messages). Changing its protocol would break backward compatibility.
2. A path-parameter-based endpoint (`/ws/asset/{asset_key}`) makes the subscription explicit at the URL level, requiring no handshake protocol change.
3. The asset key is available at connection time (from the URL), so the server immediately knows which subscription set to add the client to.
4. The main graph page continues using `/ws/execution` unmodified. Asset windows use `/ws/asset/{key}`.

---

### Component 3: ExecutionManager Extensions (Server-Side)

**Purpose:** Wire the streaming log handler and subscription router into the existing execution lifecycle.

**Boundary:** Modifications to the existing `ExecutionManager` class in `src/lattice/web/execution.py`.

**Interfaces:**
- **New property:** `_asset_subscribers: dict[str, set[WebSocket]]` -- per-asset WebSocket sets
- **New method:** `add_asset_subscriber(asset_key: str, ws: WebSocket) -> None`
- **New method:** `remove_asset_subscriber(asset_key: str, ws: WebSocket) -> None`
- **New method:** `broadcast_to_asset(asset_key: str, message: dict) -> None` -- sends to all subscribers of a specific asset
- **New callback:** `_on_log_entry(entry: LogEntry) -> None` -- invoked by streaming log handler, routes to `broadcast_to_asset`

**What it owns:**
- The per-asset subscriber registry (dict of sets)
- The wiring between log capture callback and WebSocket delivery
- The lifecycle of asset-scoped broadcasts during execution

**What it does NOT own:**
- The global broadcast to all clients (existing `broadcast()` method, unchanged)
- The WebSocket endpoint routing (belongs to Component 2)
- The log capture mechanism (belongs to Component 1)

**Integration with existing execution flow:**

The `run_execution` method currently creates a `capture_logs()` context manager and an `ExecutionLogHandler`. The enhancement will:
1. Create a `StreamingLogHandler` that invokes `self._on_log_entry` for each entry
2. The `_on_log_entry` method extracts the `asset_key` from the `LogEntry`, looks up subscribers, and calls `broadcast_to_asset`
3. The existing post-execution log storage (`handler.entries`) remains unchanged

---

### Component 4: Asset Window Page & Template (Client-Side)

**Purpose:** Dedicated browser window for viewing a single asset's live execution logs and static details.

**Boundary:** New Jinja2 template and associated JavaScript. Lives in `src/lattice/web/templates/` and `src/lattice/web/static/js/`.

**Interfaces:**
- **URL:** `/asset/{key}/live` (new route, distinct from existing `/asset/{key}` which shows run history)
- **Template context:** `asset_key` (string, injected by Jinja2)
- **WebSocket connection:** Connects to `/ws/asset/{asset_key}` on load
- **REST API calls:** `GET /api/assets/{key}` for static asset details (existing endpoint)

**What it owns:**
- The HTML structure for the asset monitoring window (log stream area, status banner, asset info panel)
- WebSocket connection management (connect, reconnect on drop, handle messages)
- Log rendering (append new log entries to a scrolling container)
- Status display (idle, running, completed, failed) based on WebSocket messages
- Window-to-opener communication (button to refocus main window via `window.opener.focus()`)
- Link to open run history in a separate window

**What it does NOT own:**
- Asset data fetching logic (uses existing REST endpoints)
- D3.js graph rendering (that stays in the main window)
- Execution control (start/stop execution remains on the main graph page)

---

### Component 5: Main Graph Window Modifications (Client-Side)

**Purpose:** Change the main graph page click behavior to open asset windows as separate browser windows instead of navigating away.

**Boundary:** Modifications to existing `src/lattice/web/static/js/graph.js`.

**Interfaces:**
- **Changed behavior:** Click handler on graph nodes calls `window.open('/asset/{key}/live', ...)` instead of `window.location.href = '/asset/' + key`
- **Window tracking:** Optional `Map<assetKey, WindowReference>` to reuse existing windows if already open
- **No new WebSocket connections:** The main window continues using `/ws/execution` as before

**What it owns:**
- The node click handler modification
- Window size/position parameters for `window.open()`
- Optional tracking of opened windows to prevent duplicates (focus existing window if already open)

**What it does NOT own:**
- Anything inside the asset window (that is Component 4)
- Execution control logic (unchanged)
- WebSocket protocol changes (the main window's WebSocket is unaffected)

---

### Component 6: Asset Window REST Routes (Server-Side)

**Purpose:** Serve the asset live monitoring page and provide any additional API endpoints needed for the asset window.

**Boundary:** New or extended routes in `src/lattice/web/routes.py`.

**Interfaces:**
- **New route:** `GET /asset/{key}/live` -- serves the `asset_live.html` template with `asset_key` context
- **Existing route reuse:** `GET /api/assets/{key}` -- already provides asset metadata (no changes needed)
- **Existing route reuse:** `GET /api/history/assets/{key}` -- already provides per-asset run history

**What it owns:**
- The route handler for the live monitoring page
- Template context preparation

**What it does NOT own:**
- The template rendering logic (Jinja2 handles this)
- The WebSocket endpoint (belongs to Component 2)

---

## Data Flow

### Log Data: From Asset Execution to Browser Window

```
Asset Function Executes
       |
       v
Python logging.Logger.info("Processing 1000 rows")
       |
       v
StreamingLogHandler.emit(record)
       |
       +---> [1] Append to self._entries (existing behavior, for post-run storage)
       |
       +---> [2] Create LogEntry(asset_key=current_asset, level, message, timestamp)
       |
       v
callback: ExecutionManager._on_log_entry(entry)
       |
       v
ExecutionManager.broadcast_to_asset(asset_key, {
    type: "asset_log",
    data: {asset_key, level, message, timestamp}
})
       |
       v
For each ws in self._asset_subscribers[asset_key]:
    await ws.send_json(message)
       |
       v
Browser WebSocket.onmessage handler in asset_live.html
       |
       v
Append <div class="log-entry"> to log container DOM
```

### Asset Status: From Executor to Browser Window

```
AsyncExecutor._execute_asset(asset_def) starts
       |
       v
ExecutionManager._broadcast_asset_start(key)
       |
       +---> [1] broadcast({type: "asset_start", ...}) to ALL clients (existing, main graph)
       |
       +---> [2] broadcast_to_asset(key, {type: "asset_start", ...}) to SUBSCRIBED clients (new)
       |
       v
[... asset executes ...]
       |
       v
ExecutionManager._broadcast_asset_complete(result)
       |
       +---> [1] broadcast({type: "asset_complete", ...}) to ALL clients (existing)
       |
       +---> [2] broadcast_to_asset(key, {type: "asset_complete", ...}) to SUBSCRIBED clients (new)
```

### Window Lifecycle

```
User clicks asset node on main graph (index.html)
       |
       v
graph.js: window.open('/asset/{key}/live', 'lattice-asset-{key}', 'width=700,height=800')
       |
       v
Server: GET /asset/{key}/live -> render asset_live.html with asset_key context
       |
       v
Browser: asset_live.js loads:
    1. Fetch GET /api/assets/{key} -> render asset info panel
    2. Connect WebSocket to /ws/asset/{key}
    3. If execution is running: receive live logs
    4. If execution is not running: show "IDLE" status with asset details
       |
       v
On execution start (triggered from main window):
    - Server broadcasts asset_start to subscriber
    - Log entries stream in real-time
    - Status shows "RUNNING"
       |
       v
On asset completion:
    - Server broadcasts asset_complete with status/duration
    - Status shows "COMPLETED" or "FAILED" banner
    - Log streaming stops for this asset
       |
       v
On window close:
    - WebSocket disconnects
    - Server removes from _asset_subscribers[key] (cleanup in finally block)
    - No effect on execution (purely observational)
```

---

## Component Interaction Diagram

```
+------------------------------------------+
|            MAIN BROWSER WINDOW           |
|  (index.html + graph.js)                 |
|                                          |
|  [D3 Graph] --click--> window.open()     |
|  [Execute Btn] --POST--> /api/exec/start |
|  [WS: /ws/execution] <-- broadcast all   |
+----+-------------------------------------+
     |
     | window.open('/asset/{key}/live')
     v
+------------------------------------------+
|         ASSET BROWSER WINDOW             |
|  (asset_live.html + asset_live.js)       |
|                                          |
|  [Asset Info] <-- GET /api/assets/{key}  |
|  [Log Stream] <-- WS: /ws/asset/{key}   |
|  [Status Bar] <-- asset_start/complete   |
|  [History Btn] --> window.open('/asset/{key}') |
|  [Focus Main] --> window.opener.focus()  |
+----+-------------------------------------+
     |
     | WebSocket connection
     v
+------------------------------------------+
|        FASTAPI SERVER                    |
|                                          |
|  ExecutionManager                        |
|    ._websockets: set[WS]     (broadcast) |
|    ._asset_subscribers: dict  (per-asset)|
|                                          |
|  /ws/execution     (global broadcast)    |
|  /ws/asset/{key}   (asset-scoped)        |
|                                          |
|  StreamingLogHandler                     |
|    .emit() --> callback -->              |
|      ExecutionManager._on_log_entry()    |
|        --> broadcast_to_asset()          |
+------------------------------------------+
```

---

## Design Decisions

### Per-Window WebSocket (Not Shared)

**Decision:** Each asset window opens its own WebSocket connection to `/ws/asset/{key}`.

**Rationale:**
- Browser windows cannot share WebSocket connections (each window is an independent browsing context)
- `SharedWorker` or `BroadcastChannel` API could theoretically share a single connection, but adds significant complexity for no benefit in a local development tool
- Per-window connections are simpler, more reliable, and align with how the existing main window already works
- The server already handles multiple WebSocket clients in `ExecutionManager._websockets`; the per-asset pattern is structurally identical

**Alternative considered:** Single WebSocket with client-side filtering (main window broadcasts to child windows via `postMessage`). Rejected because: requires the main window to stay open and be the single point of WebSocket connectivity, creating fragility. If the main window refreshes, all child windows lose updates.

### Server-Side Filtering (Not Client-Side)

**Decision:** The server filters messages per-asset before sending, rather than broadcasting everything and letting clients filter.

**Rationale:**
- In a pipeline with 50+ assets, broadcasting all logs to all windows wastes bandwidth
- Server-side filtering is O(subscribers_for_asset) per log entry, which is typically 0-1
- Client-side filtering would require every window to process every message, then discard most
- The subscription model is simpler to reason about: each WebSocket connection is explicitly scoped

### Separate Live View Route (Not Merged with Asset Detail)

**Decision:** New route `/asset/{key}/live` for the monitoring window, keeping existing `/asset/{key}` for run history.

**Rationale:**
- The live monitoring window and the historical run detail page serve fundamentally different purposes
- The live window needs WebSocket connectivity and a streaming log container; the history page needs pagination and modal dialogs
- Merging them would create a complex page that does too many things
- Users can open the history page from the live window via a dedicated link/button
- Separation allows the live window to be lightweight and focused

### Callback-Based Log Streaming (Not Polling)

**Decision:** The log handler invokes a callback per entry rather than having the WebSocket endpoint poll for new entries.

**Rationale:**
- Polling introduces latency (at minimum, the poll interval) and wastes CPU
- The existing `ExecutionLogHandler.emit()` is called synchronously in the logging path, so adding a callback is a natural extension
- The callback can safely schedule an async broadcast because `emit()` runs in the executor's async context (via `asyncio.to_thread` for sync assets, or directly for async assets)

**Important implementation detail:** The `emit()` method is synchronous (required by Python's `logging.Handler`). The callback must not be `await`ed directly. Instead, it should use `asyncio.get_event_loop().call_soon_threadsafe()` to schedule the async `broadcast_to_asset` on the event loop. This is necessary because sync asset functions run in a thread pool via `asyncio.to_thread()`, and the logging handler's `emit()` will be called from that thread.

---

## Build Order (Dependency Chain)

The following order reflects what must exist before each subsequent component can function.

### Phase 1: Server-Side Log Streaming Infrastructure

**Build:** Component 1 (StreamingLogHandler) + Component 3 (ExecutionManager extensions for per-asset subscriber registry)

**Why first:** All downstream components depend on the server being able to capture logs in real time and route them to per-asset channels. Without this, the WebSocket endpoint has nothing to send and the client has nothing to display.

**Deliverables:**
- `StreamingLogHandler` class with callback support
- `ExecutionManager._asset_subscribers` dict
- `ExecutionManager.add_asset_subscriber()` / `remove_asset_subscriber()` / `broadcast_to_asset()`
- `ExecutionManager._on_log_entry()` callback wired into the streaming handler
- Integration of streaming handler into `run_execution()` method

**Can be tested:** Unit tests with mock WebSockets verifying that log entries reach the correct subscriber set.

---

### Phase 2: Asset-Scoped WebSocket Endpoint

**Build:** Component 2 (WebSocket router for `/ws/asset/{key}`)

**Depends on:** Phase 1 (needs `ExecutionManager.add_asset_subscriber` etc. to exist)

**Deliverables:**
- New `create_asset_websocket_router(manager)` function in `src/lattice/web/execution.py`
- WebSocket endpoint at `/ws/asset/{asset_key}`
- On connect: accept, extract `asset_key` from path, call `manager.add_asset_subscriber(key, ws)`
- On disconnect: call `manager.remove_asset_subscriber(key, ws)`
- Keep-alive loop (similar to existing `/ws/execution` endpoint)
- Registration of router in `create_app()`

**Can be tested:** Integration test connecting a WebSocket client to `/ws/asset/some_key`, running an execution, and verifying log messages arrive.

---

### Phase 3: Asset Live Monitoring Page

**Build:** Component 4 (asset_live.html template + JavaScript) + Component 6 (REST route)

**Depends on:** Phase 2 (needs the WebSocket endpoint to connect to)

**Deliverables:**
- New template `src/lattice/web/templates/asset_live.html`
- New JavaScript (inline or `src/lattice/web/static/js/asset_live.js`)
- New route `GET /asset/{key}/live` in `src/lattice/web/routes.py`
- Asset info panel (populated via `GET /api/assets/{key}`)
- Live log stream container (populated via WebSocket)
- Status banner (idle / running / completed / failed)
- "Focus Main Window" button
- "View Run History" link (opens `/asset/{key}` in new window)

**Can be tested:** Manual testing by opening the URL, starting execution from the main window, and verifying logs stream in.

---

### Phase 4: Main Graph Window Integration

**Build:** Component 5 (modify graph.js click handler)

**Depends on:** Phase 3 (the `/asset/{key}/live` page must exist for `window.open` to load)

**Deliverables:**
- Modified click handler in `graph.js`: `window.open('/asset/' + key + '/live', ...)` instead of `window.location.href = '/asset/' + key`
- Window tracking map to reuse/focus existing windows
- Window sizing parameters

**Can be tested:** Click an asset node on the main graph, verify a new window opens with the live monitoring page.

---

## File Impact Summary

### New Files

| File | Purpose |
|------|---------|
| `src/lattice/web/templates/asset_live.html` | Jinja2 template for asset monitoring window |
| `src/lattice/web/static/js/asset_live.js` | JavaScript for WebSocket connection and log rendering (optional; can be inline in template) |

### Modified Files

| File | Changes |
|------|---------|
| `src/lattice/observability/log_capture.py` | Add callback support to `ExecutionLogHandler` or create `StreamingLogHandler` subclass |
| `src/lattice/web/execution.py` | Add `_asset_subscribers` dict, `add/remove_asset_subscriber()`, `broadcast_to_asset()`, `_on_log_entry()` to `ExecutionManager`; add `create_asset_websocket_router()` |
| `src/lattice/web/routes.py` | Add `GET /asset/{key}/live` route handler |
| `src/lattice/web/app.py` | Register the new asset WebSocket router via `create_asset_websocket_router()` |
| `src/lattice/web/static/js/graph.js` | Change node click handler from navigation to `window.open()` |

### Unchanged Files

| File | Why unchanged |
|------|---------------|
| `src/lattice/executor.py` | Execution engine has no knowledge of WebSocket; callbacks are injected |
| `src/lattice/web/schemas.py` | No new REST response schemas needed (existing schemas suffice) |
| `src/lattice/web/schemas_execution.py` | WebSocket messages are unstructured dicts, not Pydantic responses |
| `src/lattice/web/routes_history.py` | Run history endpoints unchanged |
| `src/lattice/web/templates/index.html` | HTML structure unchanged; behavior changes are in graph.js |
| `src/lattice/web/templates/asset_detail.html` | Existing asset detail / run history page unchanged |
| `src/lattice/observability/models.py` | `LogEntry` model already has all needed fields |

---

## Threading and Async Considerations

### Critical: Log Emit from Thread Pool

The `AsyncExecutor` runs synchronous asset functions via `asyncio.to_thread()`. This means:

1. The asset function runs in a worker thread
2. Python logging calls within that function invoke `StreamingLogHandler.emit()` in the worker thread
3. `emit()` is synchronous, but `broadcast_to_asset()` is async (sends to WebSockets)

**Solution:** The callback registered on the handler must bridge the thread-async gap:

```
def _on_log_entry_sync(self, entry: LogEntry) -> None:
    """Synchronous callback safe to call from any thread."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.call_soon_threadsafe(
            asyncio.ensure_future,
            self.broadcast_to_asset(str(entry.asset_key), {...})
        )
```

Alternatively, use an `asyncio.Queue` that the WebSocket keep-alive loop drains:

```
# In emit():
self._log_queue.put_nowait(entry)

# In WebSocket loop (already has await asyncio.sleep(0.5)):
while not self._log_queue.empty():
    entry = self._log_queue.get_nowait()
    await self.broadcast_to_asset(...)
```

The queue approach is simpler and avoids cross-thread async scheduling. It introduces up to 0.5 seconds of latency (the sleep interval), which is acceptable for a monitoring tool. The interval can be reduced to 0.1 seconds for near-real-time feel.

### WebSocket Connection Lifecycle

WebSocket connections are managed by FastAPI/Starlette's ASGI server (uvicorn). Each connection runs as an independent async task. The `_asset_subscribers` dict is accessed from:

1. The WebSocket endpoint handler (on connect/disconnect) -- runs in the ASGI event loop
2. The `broadcast_to_asset()` method -- also runs in the ASGI event loop (either directly or via `call_soon_threadsafe`)

Since both run on the same event loop and Python's GIL prevents concurrent dict mutation, no explicit locking is needed for the single-server deployment model. This matches the existing pattern for `_websockets: set[WebSocket]`.

---

## Capacity Notes

- Each asset window adds one WebSocket connection to the server
- In a typical session, a user might have 3-5 asset windows open simultaneously
- The existing `ExecutionManager` already handles multiple WebSocket clients; the per-asset pattern adds negligible overhead
- Log entries are typically 10-50 per asset execution (INFO level); at DEBUG level this could be 100-500
- At 50 log entries per second across all assets, and 5 subscribing windows, the server sends approximately 50 messages/second total -- well within uvicorn's capacity

---

*Architecture research complete: 2026-02-06*

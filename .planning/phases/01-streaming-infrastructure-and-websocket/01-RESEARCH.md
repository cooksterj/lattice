# Phase 1: Streaming Infrastructure and WebSocket - Research

**Researched:** 2026-02-06
**Domain:** Python logging handler extension, asyncio sync-to-async bridging, FastAPI WebSocket per-asset streaming
**Confidence:** HIGH

## Summary

This research investigates the implementation details for Phase 1: building the server-side log streaming infrastructure and per-asset WebSocket endpoint. The phase extends two existing components -- `ExecutionLogHandler` in `src/lattice/observability/log_capture.py` and `ExecutionManager` in `src/lattice/web/execution.py` -- to capture log entries in real-time and route them to subscribing WebSocket clients at `/ws/asset/{key}`.

The standard approach uses Python's `logging.Handler` callback pattern extended with a synchronous callback, an `asyncio.Queue` as the sync-to-async bridge (decided in prior research), and a per-asset subscriber registry (`dict[str, set[WebSocket]]`) on the ExecutionManager. A replay buffer (`collections.deque` with maxlen) provides catch-up for late-connecting clients. No new dependencies are needed -- everything uses Python stdlib (`asyncio`, `logging`, `collections`) and existing FastAPI WebSocket support.

The key technical challenge is the sync-to-async boundary: asset functions run in thread pools via `asyncio.to_thread()`, their log `emit()` calls are synchronous, but WebSocket sends are async. The `asyncio.Queue` pattern with `loop.call_soon_threadsafe(queue.put_nowait, entry)` solves this cleanly. A dedicated async drain task reads from the queue and broadcasts to subscribers.

**Primary recommendation:** Extend `ExecutionLogHandler` with a callback in `emit()`, use `asyncio.Queue` as the sync-to-async bridge, add per-asset subscriber registry to `ExecutionManager`, and implement `/ws/asset/{key}` endpoint with replay buffer. All patterns are well-established and verified against the existing codebase.

## Standard Stack

### Core

| Library/Module | Version | Purpose | Why Standard |
|----------------|---------|---------|--------------|
| Python `logging` | stdlib (3.11) | Log handler extension | Already used by `ExecutionLogHandler`; `Handler.emit()` is the standard extension point |
| `asyncio.Queue` | stdlib (3.11) | Sync-to-async bridge | Thread-safe `put_nowait()` via `call_soon_threadsafe`; standard pattern for bridging sync logging to async consumers |
| `collections.deque` | stdlib (3.11) | Replay buffer with maxlen | O(1) append/popleft, automatic eviction when maxlen reached; standard bounded buffer |
| FastAPI `WebSocket` | 0.128.0 (installed) | Per-asset WebSocket endpoint | Already used by existing `/ws/execution` endpoint; `@router.websocket("/ws/asset/{key}")` pattern |
| Pydantic `BaseModel` | 2.12+ (installed) | Log entry serialization | Already used for `LogEntry` model in observability.models |

### Supporting

| Library/Module | Version | Purpose | When to Use |
|----------------|---------|---------|-------------|
| `asyncio.Lock` | stdlib | Protect subscriber registry during concurrent modification | Only if testing reveals race conditions; single event loop means dict access is typically safe between await points |
| `threading.get_ident` | stdlib | Detect if `emit()` is called from worker thread vs event loop thread | For debug logging to verify the sync-to-async bridge is working correctly |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.Queue` | `loop.call_soon_threadsafe(asyncio.ensure_future, broadcast_coro)` | Simpler but creates unbounded async tasks; Queue provides backpressure and batching opportunity |
| `collections.deque` | `list` with manual slicing | deque is O(1) for bounded buffer eviction; list would require manual len check + del/pop |
| Extending `ExecutionLogHandler` | New `StreamingLogHandler` subclass | Subclass is cleaner but requires updating all `ExecutionLogHandler` references; extending existing class is simpler since callback is optional (None = no-op) |

**Installation:** No new packages needed. All required modules are either Python stdlib or already in the project's dependency list.

## Architecture Patterns

### Recommended File Structure (changes only)

```
src/lattice/
    observability/
        log_capture.py          # MODIFY: Add callback support to ExecutionLogHandler
    web/
        execution.py            # MODIFY: Add subscriber registry, broadcast_to_asset,
                                #         _on_log_entry, drain task, /ws/asset/{key} endpoint
        app.py                  # MODIFY: Register asset WebSocket router
tests/
    test_observability/
        test_log_capture.py     # MODIFY: Add tests for callback-based streaming
    test_web.py                 # MODIFY: Add tests for WebSocket endpoint and subscriber registry
```

### Pattern 1: Callback-Extended Log Handler

**What:** Add an optional `on_entry` callback to `ExecutionLogHandler.emit()` that fires synchronously for each captured log entry, in addition to appending to the internal list.

**When to use:** When log entries need to be consumed in real-time by external subscribers during execution.

**Why this pattern:** The existing `emit()` already creates a `LogEntry` and appends it. Adding a callback is a single line extension. The callback is synchronous (matching `emit()`'s contract), and the caller is responsible for bridging to async if needed.

**Example:**
```python
# Source: Extending existing ExecutionLogHandler in log_capture.py
class ExecutionLogHandler(logging.Handler):
    def __init__(
        self,
        on_entry: Callable[[LogEntry], None] | None = None,
    ) -> None:
        super().__init__()
        self._entries: list[LogEntry] = []
        self._current_asset: AssetKey | None = None
        self._on_entry = on_entry

    def emit(self, record: logging.LogRecord) -> None:
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created),
            level=record.levelname,
            logger_name=record.name,
            message=self.format(record),
            asset_key=self._current_asset,
        )
        self._entries.append(entry)
        # NEW: Fire callback for real-time consumers
        if self._on_entry is not None:
            self._on_entry(entry)
```

**Confidence: HIGH** -- This is a minimal extension of the standard `logging.Handler` pattern. The existing test suite for `ExecutionLogHandler` verifies `emit()` behavior; new tests only need to verify callback invocation.

### Pattern 2: asyncio.Queue as Sync-to-Async Bridge

**What:** Use `asyncio.Queue` to safely transfer `LogEntry` objects from synchronous logging threads to the async event loop for WebSocket broadcasting.

**When to use:** When `emit()` is called from a worker thread (via `asyncio.to_thread()` in `AsyncExecutor._execute_asset()`) and the consumer needs to do async work (WebSocket sends).

**Why this pattern:** `asyncio.Queue.put_nowait()` is not thread-safe on its own, but `loop.call_soon_threadsafe(queue.put_nowait, entry)` safely schedules the put on the event loop. A dedicated async drain task then reads entries and broadcasts them.

**Critical detail:** The `emit()` callback must never block. `call_soon_threadsafe` is non-blocking -- it schedules work on the event loop and returns immediately.

**Example:**
```python
# Source: Sync-to-async bridge in ExecutionManager (execution.py)
class ExecutionManager:
    def __init__(self, ...) -> None:
        ...
        self._asset_subscribers: dict[str, set[WebSocket]] = {}
        self._log_queue: asyncio.Queue[LogEntry] | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._replay_buffers: dict[str, deque[dict[str, Any]]] = {}

    def _on_log_entry_sync(self, entry: LogEntry) -> None:
        """Synchronous callback invoked by StreamingLogHandler.emit().

        Safe to call from any thread. Enqueues the entry onto the
        asyncio event loop for async processing.
        """
        if self._log_queue is None:
            return
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(self._log_queue.put_nowait, entry)

    async def _drain_log_queue(self) -> None:
        """Async task that drains the log queue and broadcasts to subscribers."""
        assert self._log_queue is not None
        while True:
            entry = await self._log_queue.get()
            if entry is None:
                break  # Sentinel to stop draining
            await self._route_log_entry(entry)

    async def _route_log_entry(self, entry: LogEntry) -> None:
        """Route a log entry to the correct asset subscribers and replay buffer."""
        if entry.asset_key is None:
            return
        asset_key_str = str(entry.asset_key)
        message = {
            "type": "asset_log",
            "data": {
                "asset_key": asset_key_str,
                "level": entry.level,
                "message": entry.message,
                "timestamp": entry.timestamp.isoformat(),
                "logger_name": entry.logger_name,
            },
        }
        # Store in replay buffer
        if asset_key_str not in self._replay_buffers:
            self._replay_buffers[asset_key_str] = deque(maxlen=500)
        self._replay_buffers[asset_key_str].append(message)
        # Send to subscribers
        await self.broadcast_to_asset(asset_key_str, message)
```

**Confidence: HIGH** -- `asyncio.Queue` with `call_soon_threadsafe` is the documented pattern for sync-to-async bridging in Python. The existing codebase already uses `asyncio.to_thread()` for sync asset execution (line 654 of `executor.py`), confirming that log `emit()` calls do happen from worker threads.

### Pattern 3: Per-Asset Subscriber Registry

**What:** A `dict[str, set[WebSocket]]` mapping asset key strings to the set of WebSocket connections subscribing to that asset's updates.

**When to use:** To efficiently route log entries and status messages to only the relevant asset windows, rather than broadcasting to all connected clients.

**Why this pattern:** The existing `_websockets: set[WebSocket]` broadcasts to all clients. Per-asset filtering at the server prevents wasted bandwidth and simplifies client code.

**Example:**
```python
# Source: Subscriber registry methods in ExecutionManager (execution.py)
def add_asset_subscriber(self, asset_key: str, ws: WebSocket) -> None:
    """Register a WebSocket client for a specific asset."""
    if asset_key not in self._asset_subscribers:
        self._asset_subscribers[asset_key] = set()
    self._asset_subscribers[asset_key].add(ws)

def remove_asset_subscriber(self, asset_key: str, ws: WebSocket) -> None:
    """Unregister a WebSocket client from a specific asset."""
    if asset_key in self._asset_subscribers:
        self._asset_subscribers[asset_key].discard(ws)
        if not self._asset_subscribers[asset_key]:
            del self._asset_subscribers[asset_key]

async def broadcast_to_asset(self, asset_key: str, message: dict[str, Any]) -> None:
    """Send a message to all subscribers of a specific asset."""
    subscribers = set(self._asset_subscribers.get(asset_key, ()))  # Snapshot
    dead_sockets: set[WebSocket] = set()
    for ws in subscribers:
        try:
            await ws.send_json(message)
        except Exception:
            dead_sockets.add(ws)
    # Clean up dead sockets
    if dead_sockets and asset_key in self._asset_subscribers:
        self._asset_subscribers[asset_key] -= dead_sockets
```

**Confidence: HIGH** -- This mirrors the existing `broadcast()` pattern (lines 132-147 of `execution.py`) which takes a snapshot via iteration, catches exceptions on dead sockets, and cleans up afterward. The per-asset version adds only the dict lookup.

### Pattern 4: WebSocket Endpoint with Replay Buffer

**What:** A new endpoint at `/ws/asset/{key}` that, on connection, sends buffered recent log entries (catch-up replay) and then streams live entries as they arrive.

**When to use:** When clients may connect after execution has already started and need to see recent history.

**Example:**
```python
# Source: New asset WebSocket endpoint in execution.py
@router.websocket("/ws/asset/{key:path}")
async def asset_websocket(websocket: WebSocket, key: str) -> None:
    await websocket.accept()
    manager.add_asset_subscriber(key, websocket)

    # Send replay buffer (catch-up for late connectors)
    replay = list(manager.get_replay_buffer(key))
    if replay:
        await websocket.send_json({
            "type": "replay",
            "data": {"entries": replay},
        })

    # Send current execution state if running
    if manager.is_running:
        state = manager.get_asset_execution_state(key)
        if state:
            await websocket.send_json({
                "type": "asset_state",
                "data": state,
            })

    try:
        while True:
            # Keep connection alive; client doesn't send data
            # Use receive_text to detect disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.remove_asset_subscriber(key, websocket)
```

**Confidence: HIGH** -- The existing `/ws/execution` endpoint (lines 531-556 of `execution.py`) uses the same accept/loop/disconnect/finally pattern. The replay buffer adds an initial send before entering the keep-alive loop.

### Anti-Patterns to Avoid

- **Awaiting in `emit()`:** Python's `logging.Handler.emit()` is synchronous. Calling `await` inside it (or using `asyncio.run()`) will either fail or block the asset function's thread. Use `call_soon_threadsafe` to schedule async work instead.
- **Unbounded Queue without sentinel:** The drain task needs a clean shutdown mechanism. Use `queue.put_nowait(None)` as a sentinel to signal the drain task to exit after execution completes.
- **Broadcasting from `emit()` thread directly:** Using `asyncio.run_coroutine_threadsafe()` and waiting on the future would block the asset's execution thread while the WebSocket send completes. The Queue pattern decouples production from consumption.
- **Modifying `_asset_subscribers` dict during iteration:** `broadcast_to_asset` must snapshot the subscriber set before iterating (as shown in Pattern 3) because `await ws.send_json()` yields control, allowing other coroutines to modify the dict.
- **Storing replay buffer entries as `LogEntry` Pydantic models:** Serialize to dict once when creating the entry, store dicts in the deque, send dicts directly. Avoids repeated serialization for each new subscriber.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bounded buffer with automatic eviction | Manual list + len check + del | `collections.deque(maxlen=N)` | deque handles eviction automatically; O(1) append; thread-safe for single-writer |
| Thread-safe event loop scheduling | Manual threading.Lock + event loop reference | `loop.call_soon_threadsafe(fn, *args)` | Built-in asyncio primitive; handles GIL edge cases correctly |
| Async task lifecycle management | Manual coroutine tracking | `asyncio.create_task()` + try/finally cancel | Standard pattern; task cleanup on execution end |
| WebSocket connection health detection | Manual ping/pong implementation | FastAPI/Starlette built-in exception handling on `send_json()` | Existing `broadcast()` pattern already handles this via exception catching |
| JSON serialization of LogEntry | Custom dict builder | `LogEntry.model_dump()` or pre-built dict | Pydantic v2 serialization is efficient; but pre-building dict in emit avoids repeated work |

**Key insight:** Every component in this phase uses Python stdlib or existing FastAPI primitives. The complexity is in the wiring between components, not in any individual piece.

## Common Pitfalls

### Pitfall 1: emit() Called from Worker Thread

**What goes wrong:** `ExecutionLogHandler.emit()` is called from the worker thread where `asyncio.to_thread()` runs the sync asset function. Directly accessing `asyncio.Queue.put_nowait()` from a non-event-loop thread is not thread-safe.
**Why it happens:** The `AsyncExecutor._execute_asset()` method (line 650-654 of `executor.py`) runs sync asset functions via `asyncio.to_thread()`. Any `logger.info()` call within the asset function triggers `emit()` in that thread.
**How to avoid:** Use `loop.call_soon_threadsafe(queue.put_nowait, entry)` which schedules the `put_nowait` call on the event loop thread. `call_soon_threadsafe` is the only safe way to interact with asyncio primitives from non-event-loop threads.
**Warning signs:** `RuntimeError: Non-thread-safe operation invoked on an event loop running in another thread` or silently lost log entries.

### Pitfall 2: Drain Task Not Started/Stopped Correctly

**What goes wrong:** The async drain task that reads from the queue must be created before execution starts and cancelled after execution ends. If not started, log entries accumulate in the queue forever. If not stopped, the task blocks on `queue.get()` indefinitely.
**Why it happens:** The drain task lifecycle is tied to execution, not to the application lifecycle.
**How to avoid:** Start the drain task at the beginning of `run_execution()` (before creating the executor). Send a `None` sentinel to the queue in the `finally` block of `run_execution()` to signal the drain task to exit. Await the drain task to ensure it has processed all remaining entries.
**Warning signs:** Log entries arriving after execution completes, or the drain task appearing in asyncio debug output as "pending".

### Pitfall 3: Replay Buffer Shared Across Executions

**What goes wrong:** If the replay buffer (`_replay_buffers` dict) is not cleared between executions, a new execution's log entries mix with the previous execution's entries. A client connecting to see the current run gets stale entries from a prior run.
**Why it happens:** `ExecutionManager` persists across runs; only `_is_running` and `_executor` are reset in `stop_execution()`.
**How to avoid:** Clear `_replay_buffers` at the start of `run_execution()` (alongside `_memory_timeline` and `_peak_rss_mb` which are already cleared on line 241-242 of `execution.py`).
**Warning signs:** WebSocket clients receive log entries with timestamps from a previous execution run.

### Pitfall 4: WebSocket Endpoint Using Blocking receive_text() Loop

**What goes wrong:** The standard WebSocket keep-alive pattern (`while True: await websocket.receive_text()`) blocks the coroutine until the client sends a message. Since asset windows do not send messages (they only receive), this effectively creates a long-lived coroutine that only exits on disconnect. This is correct behavior for a receiver-only endpoint, but it means the coroutine must handle `WebSocketDisconnect` to clean up properly.
**Why it happens:** FastAPI/Starlette WebSocket requires an active receive loop to detect disconnects.
**How to avoid:** Use the same `try/except WebSocketDisconnect/finally` pattern as the existing `/ws/execution` endpoint. The `finally` block must call `remove_asset_subscriber()`.
**Warning signs:** Orphaned subscriber entries after window close.

### Pitfall 5: Existing capture_logs() Context Manager and the New Callback

**What goes wrong:** The `capture_logs()` context manager in `log_capture.py` (lines 83-129) creates its own `ExecutionLogHandler` instance. The `run_execution()` method in `execution.py` (line 278) uses this context manager. If we need the handler to have a callback, we must pass the callback through `capture_logs()` or create the handler separately.
**Why it happens:** `capture_logs()` encapsulates handler creation. The callback is set by `ExecutionManager`, which is outside the observability module.
**How to avoid:** Add an optional `on_entry` parameter to `capture_logs()` that is forwarded to the `ExecutionLogHandler` constructor. This preserves the existing context manager pattern while enabling the callback.
**Warning signs:** N/A -- this is a design decision, not a runtime failure.

## Code Examples

### Example 1: Complete Sync-to-Async Bridge Wiring

Shows how the pieces connect in `run_execution()`:

```python
# In ExecutionManager.run_execution() -- modified execution flow
# (This replaces the relevant section of the existing method)

# 1. Create the async queue and start the drain task
self._log_queue = asyncio.Queue()
self._replay_buffers = {}  # Clear for new execution
self._drain_task = asyncio.create_task(self._drain_log_queue())

try:
    # ... existing date range loop ...
    for date_index, partition_date in enumerate(execution_dates):
        # 2. Create log handler WITH callback
        with capture_logs("lattice", on_entry=self._on_log_entry_sync) as log_handler:
            # ... existing executor creation and execution ...
            async def on_asset_start_with_tracking(
                key: AssetKey,
                tracker: LineageTracker = lineage_tracker,
                handler: ExecutionLogHandler = log_handler,
            ) -> None:
                tracker.set_current_asset(key)
                handler.set_current_asset(key)
                await self._broadcast_asset_start(key)
                # NEW: Also broadcast to asset-specific subscribers
                await self.broadcast_to_asset(str(key), {
                    "type": "asset_start",
                    "data": {"asset_key": str(key)},
                })

            # ... existing executor setup and result processing ...
finally:
    # 3. Signal drain task to stop and wait for completion
    if self._log_queue is not None:
        self._log_queue.put_nowait(None)  # Sentinel
    if self._drain_task is not None:
        await self._drain_task
    self._log_queue = None
    self._drain_task = None
    self.stop_execution()
```

### Example 2: capture_logs() with Callback Support

```python
# Modified capture_logs in log_capture.py
@contextmanager
def capture_logs(
    logger_name: str = "lattice",
    level: int = logging.DEBUG,
    on_entry: Callable[[LogEntry], None] | None = None,
) -> Generator[ExecutionLogHandler, None, None]:
    logger = logging.getLogger(logger_name)
    handler = ExecutionLogHandler(on_entry=on_entry)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))

    original_level = logger.level
    if logger.level > level:
        logger.setLevel(level)

    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
```

### Example 3: WebSocket Endpoint Registration in create_app()

```python
# In app.py -- add to create_app()
from lattice.web.execution import create_asset_websocket_router

# ... existing router registrations ...

# Add asset-scoped WebSocket route
asset_ws_router = create_asset_websocket_router(execution_manager)
app.include_router(asset_ws_router)
```

### Example 4: Test Pattern for WebSocket Subscriber

```python
# Test pattern using existing test infrastructure
@pytest.mark.asyncio
async def test_log_entry_reaches_subscriber(self, registry: AssetRegistry) -> None:
    """Log entries during execution are broadcast to asset subscribers."""
    received: list[dict] = []

    @asset(registry=registry)
    def my_asset() -> str:
        import logging
        logging.getLogger("lattice").info("Hello from asset")
        return "done"

    manager = ExecutionManager()

    # Create a mock WebSocket
    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock(side_effect=lambda msg: received.append(msg))

    # Subscribe to the asset
    manager.add_asset_subscriber("my_asset", mock_ws)

    # Run execution
    await manager.run_execution(registry, target="my_asset")

    # Verify log entries were received
    log_messages = [m for m in received if m.get("type") == "asset_log"]
    assert len(log_messages) > 0
    assert any("Hello from asset" in m["data"]["message"] for m in log_messages)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling-based log tailing | WebSocket streaming | Standard since FastAPI/ASGI | Real-time delivery, no polling overhead |
| `threading.Queue` for sync-async bridge | `asyncio.Queue` with `call_soon_threadsafe` | Python 3.4+ | More idiomatic, integrates with event loop natively |
| `asyncio.get_event_loop()` | `asyncio.get_running_loop()` | Python 3.10+ recommended | More explicit; but 3.11 still supports `get_event_loop()` from running context |

**Note on `get_event_loop()` vs `get_running_loop()`:** In the `emit()` callback (called from a worker thread), we need the main event loop reference. `asyncio.get_event_loop()` works in Python 3.11 when called from a thread where an event loop is set. However, the safest pattern is to capture the loop reference when setting up the handler (on the event loop thread) and pass it to the callback via closure. This avoids relying on implicit loop resolution in worker threads.

**Deprecated/outdated:**
- `@asyncio.coroutine` decorator: Use `async def` instead (already the pattern in this codebase)
- `loop.create_task()` from non-running loop: Use `asyncio.create_task()` from within async context

## Open Questions

1. **Replay buffer size: 500 entries per asset or configurable?**
   - What we know: The architecture research suggested 500 entries per asset. For a typical asset producing 50 lines, this covers ~10 full executions of catch-up.
   - What's unclear: Whether 500 is the right balance between memory usage and catch-up completeness for verbose assets.
   - Recommendation: Start with 500 as a constant. Make it a class-level attribute on ExecutionManager so it can be adjusted easily later. Not worth making a constructor parameter initially.

2. **Should `broadcast_to_asset` also forward `asset_start` and `asset_complete` events?**
   - What we know: The existing `_broadcast_asset_start` and `_broadcast_asset_complete` broadcast to ALL clients via `self.broadcast()`. Asset window subscribers need these events too.
   - What's unclear: Whether to (a) also call `broadcast_to_asset()` from within `_broadcast_asset_start`/`_broadcast_asset_complete`, or (b) have the new WebSocket endpoint read from both the global broadcast and the asset-specific channel.
   - Recommendation: Option (a) -- add `broadcast_to_asset()` calls to the existing callbacks. This keeps the asset WebSocket endpoint clean (it receives everything it needs on one channel) and the global broadcast unmodified.

3. **Should the drain task batch entries before broadcasting?**
   - What we know: Batching (collect entries for 50-100ms, send as array) reduces WebSocket frame overhead. But it adds latency.
   - What's unclear: Whether the overhead is meaningful for the expected log volume (10-50 entries per asset execution).
   - Recommendation: Start without batching (send each entry individually). Add batching as an optimization if profiling shows WebSocket send overhead is significant. The architecture supports adding batching later by modifying only `_drain_log_queue()`.

4. **Event loop reference in `_on_log_entry_sync`: capture at setup or resolve at call time?**
   - What we know: `asyncio.get_event_loop()` from a worker thread in Python 3.11 returns the running loop if one was set on that thread, or the main thread's loop. Behavior can be surprising.
   - What's unclear: Whether `asyncio.get_event_loop()` reliably returns the right loop from `asyncio.to_thread()` worker threads.
   - Recommendation: Capture the event loop reference at drain task creation time (`self._loop = asyncio.get_running_loop()`) and use `self._loop.call_soon_threadsafe(...)` in the callback. This is explicit and guaranteed to reference the correct loop.

## Sources

### Primary (HIGH confidence)
- **Existing codebase analysis** -- `src/lattice/observability/log_capture.py` (ExecutionLogHandler, capture_logs), `src/lattice/web/execution.py` (ExecutionManager, broadcast, run_execution, WebSocket endpoint), `src/lattice/executor.py` (AsyncExecutor.to_thread usage), `src/lattice/observability/models.py` (LogEntry model), `tests/test_observability/test_log_capture.py` (test patterns), `tests/test_web.py` (WebSocket and ExecutionManager test patterns)
- **Python 3.11 asyncio documentation** -- `asyncio.Queue`, `loop.call_soon_threadsafe`, `asyncio.create_task`, `asyncio.to_thread` threading behavior
- **Project research** -- `.planning/research/ARCHITECTURE.md` (component map, data flow, build order), `.planning/research/PITFALLS.md` (P2, P3, P4, P9, P11), `.planning/research/STACK.md` (WebSocket endpoint design), `.planning/research/SUMMARY.md` (phase decomposition rationale)

### Secondary (MEDIUM confidence)
- **FastAPI WebSocket documentation** -- WebSocket endpoint patterns, path parameters, disconnect handling. Verified against existing `/ws/execution` endpoint in the codebase.
- **Prior decisions from STATE.md** -- Per-window WebSocket with server-side filtering, asyncio.Queue as sync-to-async bridge. These are locked decisions.

### Tertiary (LOW confidence, needs validation during implementation)
- **`asyncio.get_event_loop()` behavior from worker threads** -- Python docs describe this but behavior can vary by runtime context. Recommend explicit loop capture pattern instead.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All stdlib or already-installed; patterns verified in existing codebase
- Architecture: HIGH -- Extends existing ExecutionManager/LogHandler patterns; component boundaries match prior research
- Pitfalls: HIGH -- Derived from concrete analysis of existing `emit()` call path and `asyncio.to_thread()` usage in executor
- Code examples: HIGH -- Based on direct reading of existing implementation with minimal extension

**Research date:** 2026-02-06
**Valid until:** 2026-03-06 (stable -- all dependencies are stdlib or pinned)

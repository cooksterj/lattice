# Project Research Summary

**Project:** Lattice Multi-Window Real-Time Asset Monitoring
**Domain:** DAG Orchestration Web UI (Multi-Window Browser Architecture)
**Researched:** 2026-02-06
**Confidence:** HIGH

## Executive Summary

This project adds dedicated browser windows for real-time asset monitoring to Lattice's existing DAG orchestration UI. Users can click any asset node on the main graph to open a separate window showing live log streaming, asset details, and run history without navigating away from the graph or disrupting pipeline execution. The multi-window approach is genuinely novel in the DAG orchestration space — major tools like Dagster, Airflow, and Prefect use single-page application patterns with panels/sidebars, making Lattice's approach a legitimate differentiator for users who want multi-screen monitoring.

The recommended implementation leverages four browser APIs that are all Baseline Widely Available: `window.open()` for window creation, `BroadcastChannel` for cross-window coordination, per-window `WebSocket` connections for real-time data, and the Page Visibility API for connection optimization. The existing stack (FastAPI, Jinja2, vanilla JavaScript, WebSocket) is fully sufficient — no new frameworks or libraries are needed. The architecture extends Lattice's existing ExecutionManager/WebSocket broadcast infrastructure with asset-scoped subscription channels and a streaming log handler that routes log entries to subscribing windows in real time.

The critical risks are: (1) popup blockers silently swallowing `window.open()` calls if not invoked synchronously in click handlers, (2) WebSocket connections accumulating without cleanup across window lifecycle, (3) memory leaks from unbounded log accumulation during long executions, and (4) race conditions where windows miss execution state if they connect after an asset completes. All four have clear prevention strategies and must be addressed in initial implementation phases, not retrofitted later.

## Key Findings

### Recommended Stack

The existing Lattice stack is fully capable of supporting multi-window asset monitoring. No new technologies are required. The solution uses four browser APIs that are Baseline Widely Available and safe for production use in 2026.

**Core technologies:**
- **window.open() with named windows**: Window creation with `popup` feature flag and asset-scoped names (`lattice-asset-{assetId}`) to prevent duplicates and reuse existing windows
- **BroadcastChannel API**: Cross-window coordination for execution lifecycle events (started, complete) without requiring window reference tracking. Baseline since March 2022.
- **Per-window WebSocket connections**: Each asset window connects to `/ws/asset/{asset_key}` for asset-scoped log streaming. Server-side filtering prevents wasted bandwidth.
- **Page Visibility API**: Optimize resources by disconnecting WebSocket when windows are minimized or in background, reconnecting when visible again.

**Explicitly rejected alternatives:**
- SharedWorker (limited browser support, adds complexity for no benefit in single-user tool)
- iframe-based windows (violates project constraint, adds DOM complexity)
- React/Vue for child windows (violates tech stack constraint, unnecessary for log viewer)
- localStorage polling for coordination (inefficient hack from pre-BroadcastChannel era)

**Critical decision:** Per-window WebSocket with server-side filtering. Each window maintains its own connection to `/ws/asset/{key}`. The server routes log entries only to relevant subscribers. This is simpler and more robust than a shared WebSocket with client-side filtering or a SharedWorker-based message bus.

### Expected Features

Research surveyed Dagster, Apache Airflow, Prefect, and dbt Cloud to identify table stakes vs. competitive differentiators. None of the major tools provide native multi-window monitoring — all use SPA patterns with panels/sidebars.

**Must have (table stakes):**
- Asset window shows live execution state during runs (WebSocket subscription)
- Log viewing per-asset post-execution (already exists via run history modal)
- Success/failure status indication on asset window (banner with duration)
- Asset metadata display (dependencies, type, checks — already exists in asset_detail.html)
- Run history per-asset (already exists via `/api/history/assets/` endpoint)
- Main graph stays functional during monitoring (no shared blocking state)
- Node status colors on graph during execution (already implemented)

**Should have (competitive differentiators):**
- Dedicated browser windows (not tabs/panels) — no major tool does this natively
- Live log streaming during execution to independent windows — Dagster/Prefect stream logs but within their SPA, not across windows
- Zero-disruption monitoring (opening/closing windows has no execution side effects) — unique benefit of multi-window architecture
- Run history in its own window (side-by-side comparison of current vs past runs)
- Window-to-window communication ("refocus main graph" button via `window.opener.focus()`)
- Auto-transition from live logs to completion state (state machine: streaming -> complete)

**Explicitly excluded (anti-features):**
- Drag-and-drop window arrangement (let OS window manager handle positioning)
- Multi-user concurrent monitoring (out of scope for single-user dev tool)
- Mobile-responsive asset windows (desktop browser only)
- Full SPA with client-side routing (violates Jinja2+vanilla JS constraint)
- Persistent window layout memory (adds complexity for minimal value)
- Real-time log search/filtering in asset window (defer to v2)

**Feature dependency chain:**
Browser windows (foundation) -> Live execution state -> Live log streaming -> Auto-transition to completion

### Architecture Approach

The design extends the existing ExecutionManager/WebSocket broadcast infrastructure with asset-scoped subscription channels and real-time log streaming. The architecture maintains clean separation between server-side log capture, subscription routing, and client-side rendering.

**Major components:**
1. **Asset Log Streaming Service** (server-side) — Extends ExecutionLogHandler to invoke callback per log entry. Captures logs in real time and makes them available for streaming. Integrates with existing log capture pipeline.
2. **Subscription-Aware WebSocket Router** (server-side) — New endpoint `/ws/asset/{asset_key}` that maintains `dict[str, set[WebSocket]]` mapping assets to subscribers. Filters broadcast messages so each window receives only relevant updates.
3. **ExecutionManager Extensions** (server-side) — Wires streaming log handler and subscription router into execution lifecycle. Adds `add_asset_subscriber()`, `broadcast_to_asset()`, and `_on_log_entry()` callback.
4. **Asset Window Page & Template** (client-side) — New route `/asset/{key}/live` with Jinja2 template and JavaScript. WebSocket connection management, log rendering, status display, refocus main window button.
5. **Main Graph Window Modifications** (client-side) — Change click handler from navigation (`window.location.href`) to `window.open()`. Optional window reference tracking to reuse existing windows.
6. **Asset Window REST Routes** (server-side) — Serve live monitoring page, reuse existing `/api/assets/{key}` and `/api/history/assets/{key}` endpoints.

**Build order (dependency chain):**
1. Server-side log streaming infrastructure (StreamingLogHandler + ExecutionManager subscriber registry)
2. Asset-scoped WebSocket endpoint (`/ws/asset/{key}`)
3. Asset live monitoring page (template + JavaScript + route)
4. Main graph window integration (modify graph.js click handler)

**Critical design decisions:**
- Per-window WebSocket (not shared) — browser windows cannot share connections, per-window is simpler and more reliable
- Server-side filtering (not client-side) — prevents wasting bandwidth broadcasting all logs to all windows
- Separate live view route (`/asset/{key}/live`) — distinct from historical run detail page (`/asset/{key}`)
- Callback-based log streaming (not polling) — natural extension of existing `emit()` synchronous path

**Threading/async considerations:**
`ExecutionLogHandler.emit()` is synchronous (called from asset function's thread). Bridging to async WebSocket broadcast requires `asyncio.Queue` as sync-to-async bridge. `emit()` enqueues via `loop.call_soon_threadsafe()`, separate async task drains queue and broadcasts. This prevents blocking asset execution while sending WebSocket messages.

### Critical Pitfalls

Research identified 11 pitfalls across architecture, window management, WebSocket infrastructure, log streaming, and UX polish. Top 5 by criticality:

1. **Popup blockers silently swallow window.open() calls** — Modern browsers block `window.open()` unless called synchronously in user-gesture handler. Deferred calls (after await, setTimeout, async fetch) return null with no error. Prevention: Call `window.open()` synchronously in D3 node click handler before any async operations. Capture and check return value, provide visible fallback when blocked. Phase: Must address in first implementation phase.

2. **WebSocket connections accumulate without cleanup** — When user closes window, dead socket may persist in `_websockets` until next broadcast attempt fails. Race window between window close and WebSocket disconnect handling. Prevention: Add `beforeunload` handler in each window to send close frame. Add server-side heartbeat mechanism. Track connections with metadata for debugging. Phase: Must be designed into WebSocket endpoint from the start.

3. **Memory leak from unbounded log entry accumulation** — `ExecutionLogHandler` stores all log entries in `self._entries` list that grows without bound. For verbose assets during backfills (30 days x 10 assets x 50 lines = 15,000 entries), memory consumption is significant. Prevention: Stream log entries to WebSocket immediately, write to SQLite in batches during execution, impose cap (last 10,000 entries) with warning if needed. Phase: Must address when implementing real-time log streaming.

4. **Race condition between window opening and execution state** — User opens window after asset starts executing. Window connects via WebSocket but misses `asset_start` and earlier log entries that were broadcast before connection established. Prevention: Server-side log buffer per asset (`dict[AssetKey, deque[LogEntry]]` with max 500 entries). New connections receive buffered entries immediately. Include sequence numbers in messages for gap detection. Phase: Must be designed into WebSocket protocol from the start.

5. **High-volume log output overwhelms browser DOM** — Assets producing hundreds of log entries per second cause browser tab to become sluggish/unresponsive as DOM grows (3,000+ elements after 60 seconds at 50 entries/sec). Prevention: Cap in-browser log buffer at 5,000 entries, discard oldest. Batch DOM updates via `requestAnimationFrame` (max 60 updates/sec). Use `DocumentFragment` for insertions. Add pause/resume button. Virtual scrolling as follow-up if needed. Phase: Must be part of initial log streaming implementation.

**Additional notable pitfalls:**
- Cross-window reference management (main window reload loses window references — use named windows with `window.open(url, name)` for reuse)
- Per-asset WebSocket multiplexing decision (separate connections with server-side filtering recommended over shared connection with client-side filtering)
- WebSocket reconnection storms after server restart (exponential backoff with jitter, not fixed 1-second retry)
- Log streaming interferes with execution performance (use `asyncio.Queue` as sync-to-async bridge, never await in logging handler)
- Browser tab throttling delays messages in background windows (design for batches, use server timestamps, show "last updated X seconds ago")
- Shared ExecutionManager state corruption (take snapshot of connection set before iterating to avoid RuntimeError during concurrent modifications)

## Implications for Roadmap

Based on research, the implementation naturally decomposes into four phases following the dependency chain identified in architecture analysis. The build order reflects what must exist before each subsequent component can function.

### Phase 1: Server-Side Log Streaming Infrastructure
**Rationale:** All downstream components depend on the server being able to capture logs in real time and route them to per-asset channels. Without this foundation, the WebSocket endpoint has nothing to send and the client has nothing to display.

**Delivers:**
- `StreamingLogHandler` class with callback support for real-time log entry emission
- `ExecutionManager._asset_subscribers: dict[str, set[WebSocket]]` registry
- `ExecutionManager.add_asset_subscriber()`, `remove_asset_subscriber()`, `broadcast_to_asset()` methods
- `ExecutionManager._on_log_entry()` callback wired into streaming handler
- Integration of streaming handler into `run_execution()` method

**Addresses:**
- Foundation for feature D2 (live log streaming)
- Prevents pitfall P3 (memory leaks) by designing stream-then-store instead of accumulate-and-stream
- Prevents pitfall P9 (execution interference) by implementing asyncio.Queue as sync-to-async bridge

**Avoids:**
- P9 (log streaming interfering with execution) — asyncio.Queue bridge ensures emit() never blocks on WebSocket sends
- P3 (unbounded memory growth) — design decision point for streaming vs accumulation

**Stack elements:** Python logging, asyncio.Queue, existing ExecutionLogHandler foundation

**Research flags:** None (standard patterns, well-understood async bridging)

---

### Phase 2: Asset-Scoped WebSocket Endpoint
**Rationale:** With log streaming infrastructure in place, need WebSocket endpoint that subscribing clients can connect to. Server-side filtering prevents wasting bandwidth broadcasting all logs to all windows.

**Delivers:**
- New endpoint `/ws/asset/{asset_key}` with path-parameter-based subscription
- `create_asset_websocket_router(manager)` function in execution.py
- On connect: extract asset_key from path, call `manager.add_asset_subscriber(key, ws)`
- On disconnect: call `manager.remove_asset_subscriber(key, ws)` in finally block
- Keep-alive loop similar to existing `/ws/execution` endpoint
- Registration of router in `create_app()`

**Addresses:**
- Feature F1 (live execution state in window) — foundation for receiving status updates
- Feature D2 (live log streaming) — transport layer for log entries
- Prevents pitfall P4 (race condition) by implementing log replay buffer
- Prevents pitfall P2 (connection cleanup) by adding explicit disconnect handling

**Avoids:**
- P2 (connection accumulation) — beforeunload handler + server-side disconnect handling
- P4 (missed execution state) — server-side log buffer with replay on connect
- P11 (state corruption) — snapshot connection set before iterating during broadcast

**Stack elements:** FastAPI WebSocket, existing ExecutionManager pattern, BroadcastChannel (client coordination, next phase)

**Research flags:** Moderate (replay buffer implementation needs careful testing)

---

### Phase 3: Asset Live Monitoring Page
**Rationale:** With WebSocket endpoint available, build the client-side window that connects to it. This is where users actually see live logs and execution state.

**Delivers:**
- New template `src/lattice/web/templates/asset_live.html`
- New JavaScript (inline or `asset_live.js`) with WebSocket connection management
- New route `GET /asset/{key}/live` in routes.py
- Asset info panel (populated via existing `GET /api/assets/{key}`)
- Live log stream container with scrolling behavior
- Status banner (idle / running / completed / failed)
- "Focus Main Window" button (via `window.opener.focus()`)
- "View Run History" link (opens `/asset/{key}` in new window)

**Addresses:**
- Feature F1 (live execution state) — WebSocket connection and state rendering
- Feature D2 (live log streaming) — log container with append-only rendering
- Feature F3 (status banner) — completion indicator with duration
- Feature D6 (auto-transition) — state machine: streaming -> complete
- Feature D5 (window communication) — refocus main graph button
- Feature D4 (run history window) — link to open history in separate window

**Avoids:**
- P6 (DOM overwhelm) — cap log buffer at 5,000 entries, batch DOM updates via requestAnimationFrame
- P10 (background throttling) — use server timestamps, design for message batches
- P1 (popup blockers) — for history link, same synchronous pattern as main window

**Stack elements:** Jinja2 templates, vanilla JavaScript, WebSocket API, Page Visibility API

**Research flags:** High (log rendering performance needs careful implementation and testing)

---

### Phase 4: Main Graph Window Integration
**Rationale:** With live monitoring page functional, wire it into the existing graph UI by changing node click behavior from navigation to window.open().

**Delivers:**
- Modified click handler in `graph.js`: `window.open('/asset/' + key + '/live', 'lattice-asset-' + key, 'popup,width=800,height=600')`
- Window tracking map: `this.assetWindows = new Map()` to reuse/focus existing windows
- Check if window already open: if exists and not closed, focus it instead of opening new
- Window sizing parameters (reasonable defaults, user can resize)

**Addresses:**
- Feature D1 (dedicated browser windows) — the core multi-window paradigm
- Feature D3 (zero-disruption monitoring) — windows are purely observational
- Feature F6 (main graph stays functional) — no navigation, graph remains active

**Avoids:**
- P1 (popup blockers) — synchronous call in click handler, before any async operations
- P5 (zombie windows) — named windows with asset-scoped names for reuse
- P8 (reconnection storms) — each window manages own connection independently

**Stack elements:** window.open() API, existing D3.js graph infrastructure

**Research flags:** None (straightforward browser API usage)

---

### Phase Ordering Rationale

The four-phase structure reflects hard dependencies between components:
- Phase 1 must complete before Phase 2 (WebSocket endpoint needs streaming infrastructure to have data to send)
- Phase 2 must complete before Phase 3 (client window needs endpoint to connect to)
- Phase 3 must complete before Phase 4 (main graph needs live monitoring page to exist for window.open to load)

This order naturally addresses critical pitfalls at the correct architectural layer:
- P9 (execution interference) and P3 (memory leaks) are addressed in Phase 1's log streaming design
- P2 (connection cleanup), P4 (race conditions), P11 (state corruption) are addressed in Phase 2's WebSocket endpoint
- P6 (DOM overwhelm), P10 (background throttling) are addressed in Phase 3's client-side rendering
- P1 (popup blockers), P5 (zombie windows) are addressed in Phase 4's window management

The grouping also allows incremental testing:
- Phase 1 can be unit tested with mock WebSockets
- Phase 2 can be integration tested by connecting a test client
- Phase 3 can be manually tested by directly opening the URL
- Phase 4 completes the user-facing feature flow

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 2 (WebSocket endpoint):** Replay buffer implementation is moderately complex. Needs design decisions around buffer size, sequence numbering, and catch-up protocol. Recommend prototyping the replay mechanism in isolation before integrating.
- **Phase 3 (Asset window):** Log rendering performance is the highest-risk area. Recommend researching/testing virtual scrolling libraries or windowed rendering approaches if initial cap-and-batch implementation proves insufficient under high log volumes.

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Log streaming):** asyncio.Queue as sync-to-async bridge is well-documented pattern. Callback-based handler extension is straightforward Python logging API usage.
- **Phase 4 (Graph integration):** window.open() is basic browser API. Named windows pattern is well-established.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommended browser APIs are Baseline Widely Available. FastAPI/WebSocket patterns already proven in existing codebase. No new frameworks or libraries required. |
| Features | HIGH | Surveyed 4 major DAG orchestration tools (Dagster, Airflow, Prefect, dbt Cloud). Clear table stakes vs differentiators. Multi-window approach is genuinely novel in this space. |
| Architecture | HIGH | Component boundaries align with existing codebase structure. Build order reflects hard dependencies. Server-side patterns extend existing ExecutionManager design. Client-side uses proven browser APIs. |
| Pitfalls | HIGH | Analyzed 11 pitfalls across 5 categories. Each has clear warning signs, prevention strategies, and phase mapping. Pitfalls are drawn from real-world WebSocket/multi-window experience and browser constraints. |

**Overall confidence:** HIGH

Research is comprehensive and actionable. Stack decisions are validated against browser compatibility data (MDN, Baseline Widely Available). Architecture extends existing patterns rather than introducing new paradigms. Feature analysis is grounded in competitive tool survey. Pitfalls are specific and mapped to implementation phases.

### Gaps to Address

**Gap 1: Log replay protocol details** — Research identifies the need for a replay buffer with sequence numbering but does not specify the exact protocol. During Phase 2 planning, need to decide: (1) JSON schema for sequence-numbered messages, (2) client request format for "give me entries since sequence N", (3) buffer eviction policy when cap is reached. Recommend prototyping the protocol before full implementation.

**Gap 2: Virtual scrolling threshold** — Research recommends cap-and-batch rendering initially, with virtual scrolling as follow-up optimization if needed. Need to establish actual performance threshold (e.g., "if profiling shows >100ms render time or >500MB browser memory, implement virtual scrolling"). This can only be determined through load testing during Phase 3.

**Gap 3: BroadcastChannel message protocol** — STACK.md defines channel names and message types but not the full protocol (e.g., when should asset windows post to the window coordination channel? What should main window do when it receives window_opened messages?). During Phase 3 planning, need to specify the full message exchange protocol and lifecycle hooks.

**Gap 4: Connection limit enforcement** — PITFALLS.md mentions setting a limit (e.g., 50 concurrent WebSocket connections) but does not specify where to enforce it (server-wide? per-client IP? per-session?) or how to communicate the limit to users. During Phase 2 implementation, need to decide enforcement level and error response (HTTP 503? WebSocket close with reason code?).

## Sources

### Primary (HIGH confidence)
- **MDN Web Docs (BroadcastChannel, window.open, postMessage, WebSocket, Page Visibility API, SharedWorker, window.opener, window.name)** — Browser API specifications and Baseline Widely Available status. All recommended APIs confirmed as Baseline since March 2022 or earlier.
- **Existing Lattice codebase analysis** — Reviewed `src/lattice/web/execution.py` (ExecutionManager, WebSocket broadcast pattern), `src/lattice/observability/log_capture.py` (ExecutionLogHandler), `src/lattice/web/static/js/graph.js` (node click handlers), `src/lattice/web/templates/` (Jinja2 template structure). Existing patterns directly inform extension points.
- **Dagster webserver UI, Apache Airflow 2.x Grid/Graph views, Prefect Cloud + OSS UI, dbt Cloud IDE + Run monitoring** — Surveyed feature sets for table stakes vs differentiators. Confirmed none offer native multi-window monitoring.

### Secondary (MEDIUM confidence)
- **AsyncIO threading patterns** — sync-to-async bridge via asyncio.Queue and call_soon_threadsafe is documented pattern but implementation details need verification during Phase 1.
- **Browser popup blocker behavior** — Behavior varies slightly across browsers (Safari more permissive than Chrome/Firefox) but synchronous-call-in-gesture-handler is universally safe approach.

### Tertiary (LOW confidence, needs validation)
- **Connection limits** — Browser WebSocket connection limits vary (older browsers: 6 per origin, modern: 256+). Exact limits need testing during Phase 2. Recommend establishing conservative limit (50 connections) to be safe.

---
*Research completed: 2026-02-06*
*Ready for roadmap: yes*

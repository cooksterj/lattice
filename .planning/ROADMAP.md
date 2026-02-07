# Roadmap: Lattice Multi-Window Asset Monitoring

## Overview

This roadmap delivers multi-window asset monitoring for Lattice's web UI across three phases following the dependency chain: server-side streaming infrastructure first, then the asset monitoring page, then wiring it into the main graph. Each phase produces a verifiable capability that the next phase builds on. The result is a complete workflow where users click any asset on the DAG graph to open an independent browser window showing live logs, completion status, and asset details -- all without disrupting pipeline execution.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Streaming Infrastructure and WebSocket** - Server-side log streaming with per-asset WebSocket subscriptions
- [ ] **Phase 2: Asset Live Monitoring Page** - Dedicated browser page for real-time log viewing and asset details
- [ ] **Phase 3: Main Graph Window Integration** - Wire asset monitoring into DAG graph via window.open()

## Phase Details

### Phase 1: Streaming Infrastructure and WebSocket
**Goal**: Server can capture asset logs in real-time and stream them to subscribing WebSocket clients without affecting execution
**Depends on**: Nothing (first phase)
**Requirements**: EXEC-01, EXEC-02
**Success Criteria** (what must be TRUE):
  1. A StreamingLogHandler captures per-asset log entries in real-time during execution and makes them available via callback
  2. A WebSocket client connected to `/ws/asset/{key}` receives log entries as they are emitted during asset execution
  3. A WebSocket client connecting after execution has started receives buffered recent log entries (replay catch-up)
  4. Downstream assets continue executing at the same pace whether or not WebSocket clients are connected
  5. Opening and closing WebSocket connections during execution has no effect on execution state
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md -- Callback-extended log handler and per-asset subscriber registry
- [x] 01-02-PLAN.md -- Asset-scoped WebSocket endpoint with replay buffer delivery
- [x] 01-03-PLAN.md -- Async bridge (sync-to-async log routing) and execution isolation verification

### Phase 2: Asset Live Monitoring Page
**Goal**: Users can open a dedicated page showing live execution logs, completion status, and asset details
**Depends on**: Phase 1
**Requirements**: AWIN-01, AWIN-02, AWIN-03, AWIN-04, AWIN-05
**Success Criteria** (what must be TRUE):
  1. User visiting `/asset/{key}/live` sees live log entries appearing in real-time during asset execution
  2. When execution completes, a success or failure banner with duration appears and log streaming stops
  3. User can click a button to refocus the main graph window
  4. User can click a link to open run history in a separate browser window
  5. When no execution is running, user sees asset details including dependencies, type, and group
**Plans**: TBD

Plans:
- [ ] 02-01: Asset live route and Jinja2 template with asset details panel
- [ ] 02-02: WebSocket client JavaScript for live log rendering and state management
- [ ] 02-03: Completion banner, refocus button, and run history link

### Phase 3: Main Graph Window Integration
**Goal**: Users can click any asset on the main DAG graph to open asset monitoring in a new browser window without leaving the graph
**Depends on**: Phase 2
**Requirements**: GRAF-01, GRAF-02, GRAF-03
**Success Criteria** (what must be TRUE):
  1. Clicking an asset node on the graph opens a new browser window with the asset live monitoring page
  2. Clicking the same asset again focuses the existing window instead of opening a duplicate
  3. Main graph window continues updating execution status while asset windows are open
**Plans**: TBD

Plans:
- [ ] 03-01: Graph click handler change from navigation to window.open()
- [ ] 03-02: Window tracking, duplicate prevention, and popup blocker handling

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Streaming Infrastructure and WebSocket | 3/3 | Complete | 2026-02-06 |
| 2. Asset Live Monitoring Page | 0/3 | Not started | - |
| 3. Main Graph Window Integration | 0/2 | Not started | - |

# Roadmap: Lattice Web UI

## Milestones

- [x] **v1.0 Multi-Window Asset Monitoring** - Phases 1-3 (shipped 2026-02-06)
- [x] **v2.0 Sidebar Navigation & Failed Asset Recovery** - Phases 4-7 (shipped 2026-02-08)

## Phases

<details>
<summary>v1.0 Multi-Window Asset Monitoring (Phases 1-3) - SHIPPED 2026-02-06</summary>

### Phase 1: Streaming Infrastructure
**Goal**: Real-time per-asset log streaming via WebSocket with replay buffer
**Plans**: 3 plans (complete)

Plans:
- [x] 01-01: WebSocket subscriber registry and per-asset log capture
- [x] 01-02: Execution isolation and replay buffer
- [x] 01-03: REST endpoint for asset details

### Phase 2: Asset Live Monitoring Page
**Goal**: Dedicated live page with state machine, completion banner, and navigation
**Plans**: 2 plans (complete)

Plans:
- [x] 02-01: Live monitoring template with WebSocket client and state machine
- [x] 02-02: Completion banner, refocus button, and run history link

### Phase 3: Main Graph Window Integration
**Goal**: Graph click opens asset window with dedup, popup fallback, and refocus
**Plans**: 2 plans (complete)

Plans:
- [x] 03-01: Window.open click handler with tracking and popup fallback
- [x] 03-02: Named window targeting for reliable refocus

</details>

<details>
<summary>v2.0 Sidebar Navigation & Failed Asset Recovery (Phases 4-7) - SHIPPED 2026-02-08</summary>

- [x] Phase 4: Template Foundation & Sidebar (2/2 plans) — completed 2026-02-07
- [x] Phase 5: Run Monitoring & Live Logs (2/2 plans) — completed 2026-02-07
- [x] Phase 6: Graph Selection & Failure Recovery (1/1 plan) — completed 2026-02-08
- [x] Phase 7: Popup Cleanup (1/1 plan) — completed 2026-02-08

See `.planning/milestones/v2.0-ROADMAP.md` for full phase details.

</details>

## Progress

**Execution Order:** Phase 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Streaming Infrastructure | v1.0 | 3/3 | Complete | 2026-02-06 |
| 2. Asset Live Monitoring | v1.0 | 2/2 | Complete | 2026-02-06 |
| 3. Graph Window Integration | v1.0 | 2/2 | Complete | 2026-02-06 |
| 4. Template Foundation & Sidebar | v2.0 | 2/2 | Complete | 2026-02-07 |
| 5. Run Monitoring & Live Logs | v2.0 | 2/2 | Complete | 2026-02-07 |
| 6. Graph Selection & Failure Recovery | v2.0 | 1/1 | Complete | 2026-02-08 |
| 7. Popup Cleanup | v2.0 | 1/1 | Complete | 2026-02-08 |

# Roadmap: Lattice Web UI

## Milestones

- [x] **v1.0 Multi-Window Asset Monitoring** - Phases 1-3 (shipped 2026-02-06)
- [ ] **v2.0 Sidebar Navigation & Failed Asset Recovery** - Phases 4-7 (in progress)

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

## v2.0 Sidebar Navigation & Failed Asset Recovery

**Milestone Goal:** Replace popup windows with sidebar-driven full-page navigation and add failed asset re-execution with downstream propagation.

- [x] **Phase 4: Template Foundation & Sidebar** - Base template with persistent sidebar on all pages
- [x] **Phase 5: Run Monitoring & Live Logs** - Active runs page, history re-parenting, live logs as full page
- [x] **Phase 6: Graph Selection & Failure Recovery** - Click-to-select on graph, context-aware Execute for re-runs
- [ ] **Phase 7: Popup Cleanup** - Remove all v1 popup infrastructure

## Phase Details

### Phase 4: Template Foundation & Sidebar
**Goal**: Users see a persistent sidebar on every page and can navigate between all views without browser back
**Depends on**: v1.0 complete (Phases 1-3)
**Requirements**: SIDE-01, SIDE-02, SIDE-03
**Success Criteria** (what must be TRUE):
  1. Every page displays a narrow icon rail sidebar on the left with icons for graph, active runs, and run history
  2. Clicking any sidebar icon navigates to the corresponding full page (not a popup, not a modal)
  3. The icon for the current page is visually highlighted so the user always knows where they are
  4. Browser back and forward buttons work correctly between all pages
**Plans**: 2 plans

Plans:
- [x] 04-01-PLAN.md — Create base.html with sidebar, sidebar CSS, and current_page route context
- [x] 04-02-PLAN.md — Migrate all 4 templates to extend base.html + visual verification

### Phase 5: Run Monitoring & Live Logs
**Goal**: Users can monitor active execution progress and view live logs as full pages within the sidebar layout
**Depends on**: Phase 4 (sidebar and base template)
**Requirements**: RUNS-01, RUNS-02, RUNS-03, RUNS-04, RECV-03
**Success Criteria** (what must be TRUE):
  1. Active runs page shows real-time per-asset status (running/queued/completed/failed) updating live during execution via WebSocket
  2. When no execution is running, the active runs page shows a summary of the last completed run
  3. Clicking a running asset on the active runs page navigates to its live logs as a full page with sidebar and back button
  4. Run history page is accessible via the sidebar and displays within the sidebar layout (not a standalone page)
  5. Live logs page has the sidebar, a back button, and streams logs in real time (no popup, no refocus button)
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md — Active Runs page with dual-mode display (live WebSocket + idle REST)
- [x] 05-02-PLAN.md — Refactor asset_live.html to full-page layout with back button + visual verification

### Phase 6: Graph Selection & Failure Recovery
**Goal**: Users can select a failed asset on the graph and re-execute it plus all downstream assets
**Depends on**: Phase 4 (sidebar layout), Phase 5 (live logs for monitoring re-execution)
**Requirements**: RECV-01, RECV-02
**Success Criteria** (what must be TRUE):
  1. Clicking an asset node on the graph selects and highlights it visually (no popup opens)
  2. When a failed asset is selected, the Execute button label changes to indicate re-execution from that asset
  3. Clicking Execute with a failed asset selected runs that asset plus all its downstream dependencies
  4. Clicking the graph background or pressing Escape deselects the current selection
**Plans**: 1 plan

Plans:
- [x] 06-01-PLAN.md — Graph click-to-select, context-aware Execute button, targeted re-execution wiring

### Phase 7: Popup Cleanup
**Goal**: All v1 popup infrastructure is removed and the codebase contains no window.open, popup fallback, or named window targeting code
**Depends on**: Phase 4, Phase 5, Phase 6 (all popup replacements complete)
**Requirements**: CLEN-01
**Success Criteria** (what must be TRUE):
  1. No window.open calls exist anywhere in the JavaScript codebase
  2. The popup blocked notice, refocus button, and named window targeting code are all removed
  3. All existing functionality (graph, monitoring, history, live logs) continues to work after removal
**Plans**: 1 plan

Plans:
- [ ] 07-01-PLAN.md — Remove popup dead code from graph.js and verify zero popup references

## Progress

**Execution Order:** Phase 4 -> 5 -> 6 -> 7

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Streaming Infrastructure | v1.0 | 3/3 | Complete | 2026-02-06 |
| 2. Asset Live Monitoring | v1.0 | 2/2 | Complete | 2026-02-06 |
| 3. Graph Window Integration | v1.0 | 2/2 | Complete | 2026-02-06 |
| 4. Template Foundation & Sidebar | v2.0 | 2/2 | Complete | 2026-02-07 |
| 5. Run Monitoring & Live Logs | v2.0 | 2/2 | Complete | 2026-02-07 |
| 6. Graph Selection & Failure Recovery | v2.0 | 1/1 | Complete | 2026-02-08 |
| 7. Popup Cleanup | v2.0 | 0/TBD | Not started | - |

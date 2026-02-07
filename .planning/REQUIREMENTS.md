# Requirements: Lattice Multi-Window Asset Monitoring

**Defined:** 2026-02-06
**Core Value:** Users can monitor individual asset execution in real-time without losing visibility of the overall pipeline or disrupting downstream execution.

## v1 Requirements

### Asset Window

- [ ] **AWIN-01**: User can see live log entries streaming in real-time as an asset executes
- [ ] **AWIN-02**: User sees a success/failure banner with duration when an asset completes execution
- [ ] **AWIN-03**: User can click a button to refocus the main graph window
- [ ] **AWIN-04**: User can click a link to open run history in a separate browser window
- [ ] **AWIN-05**: User can see asset details (dependencies, type, group) when no execution is running

### Graph Integration

- [ ] **GRAF-01**: User can click an asset node on the graph to open a new browser window (not navigate away)
- [ ] **GRAF-02**: Re-clicking an already-opened asset focuses the existing window instead of opening a duplicate
- [ ] **GRAF-03**: Main graph window remains functional and updating while asset windows are open

### Execution Continuity

- [x] **EXEC-01**: Downstream assets continue executing while user views any asset window
- [x] **EXEC-02**: Opening or closing asset windows has no effect on execution state

## v2 Requirements

### Asset Window Enhancements

- **AWIN-06**: User can search/filter log entries in the asset window
- **AWIN-07**: User can pause and resume live log streaming
- **AWIN-08**: Virtual scrolling for high-volume log output (>5000 entries)

### Window Management

- **WMAN-01**: User can see a count of open asset windows from the main graph
- **WMAN-02**: Window positions and sizes persist across sessions

## Out of Scope

| Feature | Reason |
|---------|--------|
| Drag-and-drop window arrangement | OS window manager handles positioning |
| Multi-user concurrent monitoring | Single-user development tool |
| Mobile-responsive asset windows | Desktop browser only |
| SPA with client-side routing | Violates Jinja2 + vanilla JS constraint |
| Real-time log search/filtering | Deferred to v2 |
| Authentication for web UI | Framework assumes local/trusted network |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AWIN-01 | Phase 2 | Pending |
| AWIN-02 | Phase 2 | Pending |
| AWIN-03 | Phase 2 | Pending |
| AWIN-04 | Phase 2 | Pending |
| AWIN-05 | Phase 2 | Pending |
| GRAF-01 | Phase 3 | Pending |
| GRAF-02 | Phase 3 | Pending |
| GRAF-03 | Phase 3 | Pending |
| EXEC-01 | Phase 1 | Done |
| EXEC-02 | Phase 1 | Done |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0

---
*Requirements defined: 2026-02-06*
*Last updated: 2026-02-06 after Phase 1 completion*

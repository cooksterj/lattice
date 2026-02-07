# Requirements: Lattice v2.0 Sidebar Navigation & Failed Asset Recovery

**Defined:** 2026-02-07
**Core Value:** Users can monitor execution, view logs, and recover from failures without leaving the main workflow or dealing with popup windows.

## v2.0 Requirements

### Sidebar Navigation

- [ ] **SIDE-01**: Persistent icon rail sidebar on all pages with 3 icons (graph/home, active runs, run history) — ~48-56px wide with tooltips
- [ ] **SIDE-02**: Active page icon is visually highlighted in the sidebar
- [ ] **SIDE-03**: All views are full-page navigation with browser back/forward support

### Run Monitoring

- [ ] **RUNS-01**: Active runs page shows real-time per-asset status (running/queued/completed/failed) during execution via WebSocket
- [ ] **RUNS-02**: Active runs page shows last completed run summary when no execution is running
- [ ] **RUNS-03**: Clicking a running asset on the active runs page navigates to its live logs page
- [ ] **RUNS-04**: Run history page accessible via sidebar (existing history template re-parented into sidebar layout)

### Failure Recovery

- [ ] **RECV-01**: Clicking any asset on the graph selects/highlights it (no popup)
- [ ] **RECV-02**: Execute button is context-aware — when a failed asset is selected, re-runs that asset plus all downstream
- [ ] **RECV-03**: Full-page live logs view with sidebar and back button (refactored from popup)

### Cleanup

- [ ] **CLEN-01**: Remove v1 popup infrastructure (window.open, popup fallback, refocus button, named window targeting)

## Future Requirements

### v2.x (After Validation)

- **SRCH-01**: Log search/filter in live log view
- **COMP-01**: Run comparison view (diff two runs side by side)
- **KEYS-01**: Keyboard shortcuts for sidebar navigation (1=graph, 2=active runs, 3=history)
- **MINI-01**: Graph minimap / overview panel for large DAGs
- **BLAST-01**: Visual downstream blast radius highlighting when selecting failed asset

### v3+ (Future Consideration)

- **VSCR-01**: Virtual scrolling for log entries
- **NOTF-01**: Notification/toast system for execution events
- **RTRY-01**: Automatic retry with backoff

## Out of Scope

| Feature | Reason |
|---------|--------|
| SPA client-side routing | Requires JS framework, violates stack constraint |
| Expandable sidebar with text labels | Overkill for 3 nav items, steals graph space |
| In-page log streaming panel | Log container needs full vertical space, cramped in sidebar |
| Multi-select non-contiguous assets | Breaks DAG contract — only "from X downstream" is safe |
| Automatic retry on failure | Masks real failures, complicates execution model |
| Modal overlays for run details | Full-page views are the explicit design choice |
| Real-time graph animation | Performance killer with D3.js force-directed graphs |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SIDE-01 | — | Pending |
| SIDE-02 | — | Pending |
| SIDE-03 | — | Pending |
| RUNS-01 | — | Pending |
| RUNS-02 | — | Pending |
| RUNS-03 | — | Pending |
| RUNS-04 | — | Pending |
| RECV-01 | — | Pending |
| RECV-02 | — | Pending |
| RECV-03 | — | Pending |
| CLEN-01 | — | Pending |

**Coverage:**
- v2.0 requirements: 11 total
- Mapped to phases: 0
- Unmapped: 11 (pending roadmap creation)

---
*Requirements defined: 2026-02-07*
*Last updated: 2026-02-07 after initial definition*

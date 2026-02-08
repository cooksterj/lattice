# Project Milestones: Lattice Web UI

## v2.0 Sidebar Navigation & Failed Asset Recovery (Shipped: 2026-02-08)

**Delivered:** Replaced popup-based monitoring with persistent sidebar navigation, added active runs monitoring, full-page live logs, graph click-to-select with targeted re-execution, and removed all v1 popup infrastructure.

**Phases completed:** 4-7 (6 plans total)

**Key accomplishments:**
- Jinja2 template inheritance with 52px icon rail sidebar on all pages
- Dual-mode active runs page with real-time WebSocket updates during execution and REST idle summary
- Full-page live logs view with sidebar and back navigation (replaces popup)
- Graph click-to-select with context-aware Execute button for targeted re-execution from failed assets
- Complete removal of v1 popup infrastructure (68 lines of dead code cleaned)

**Stats:**
- 32 files created/modified
- 6,751 lines added / 2,432 lines removed (net +4,319)
- 4 phases, 6 plans
- 1 day (2026-02-07 to 2026-02-08)

**Git range:** `470e10a` (feat(04-01)) -> `7a4ac8c` (feat(07-01))

**What's next:** Project feature-complete for v2.0. Future enhancements available: log search/filter, keyboard shortcuts, graph minimap, blast radius highlighting.

---

## v1.0 Multi-Window Asset Monitoring (Shipped: 2026-02-06)

**Delivered:** Complete multi-window asset monitoring — users click any asset on the DAG graph to open independent browser windows showing live logs, completion status, and asset details, all without disrupting pipeline execution.

**Phases completed:** 1-3 (7 plans total)

**Key accomplishments:**
- Real-time per-asset log streaming via WebSocket with replay buffer for late-joining clients
- Dedicated live monitoring page with state machine (idle/running/completed/failed)
- Completion banner with success/failure styling and formatted duration
- Graph click-to-window integration with duplicate prevention and popup blocker fallback
- Named window targeting for reliable cross-window refocus
- Full execution isolation — windows never affect pipeline state

**Stats:**
- 9 source files created/modified
- 1,607 lines of Python/JS/HTML added
- 3 phases, 7 plans
- 1 day from start to ship

**Git range:** `e8a1b66` → `39d4eb2`

**What's next:** Project complete (v1.0 MVP shipped). v2 features (log search/filter, virtual scrolling, window management) available if needed.

---

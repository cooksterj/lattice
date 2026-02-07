---
phase: 05-run-monitoring-live-logs
plan: 01
subsystem: ui
tags: [runs-page, websocket, dual-mode, jinja2, css, real-time]

# Dependency graph
requires:
  - phase: 04-template-foundation-sidebar
    provides: base.html sidebar layout, current_page context, sidebar-rail CSS
provides:
  - /runs route with active runs monitoring page
  - runs.html template with WebSocket-driven live mode and REST-driven idle mode
  - Runs-page CSS classes and statusPulse animation in styles.css
affects: [05-02 asset live page refactor, 06 graph integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-mode page: live WebSocket updates vs idle REST summary"
    - "Connect WebSocket first, then check REST status (avoid race condition)"
    - "textContent for all user-provided strings (XSS safety)"
    - "Auto-transition from idle to live on asset_start message"

key-files:
  created:
    - src/lattice/web/templates/runs.html
  modified:
    - src/lattice/web/routes.py
    - src/lattice/web/static/css/styles.css

key-decisions:
  - "statusPulse keyframe animation added to styles.css (was only inline in asset_live.html)"
  - "1.5s delay before transitioning to idle after execution_complete (lets user see final state)"
  - "Asset rows are anchor elements linking to /asset/{key}/live for seamless navigation"
  - "body overflow-auto set via block body_class (page needs scrolling for long asset lists)"

# Metrics
duration: 2min
completed: 2026-02-07
---

# Phase 5 Plan 01: Active Runs Page Summary

**Dual-mode /runs page with WebSocket live monitoring and REST idle summary, zero new endpoints**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~2.5min |
| Tasks | 1/1 |
| Test suite | 276 passed |
| Lint | Clean |

## Accomplishments

1. **Added `/runs` route** in `routes.py` returning `runs.html` with `current_page="runs"` for sidebar highlighting
2. **Created `runs.html` template** extending `base.html` with three visual panels: loading, live, and idle
3. **Live mode**: Connects to existing `/ws/execution` WebSocket; handles `asset_start`, `asset_complete`, and `execution_complete` messages to render a real-time per-asset status table with progress bar
4. **Idle mode**: Fetches `GET /api/history/runs?limit=1` to render a summary card of the last completed run with run ID, duration, asset counts, and status
5. **Auto-transitions**: Page transitions from idle to live when `asset_start` arrives; transitions from live to idle on `execution_complete` after a 1.5s delay
6. **Runs-page CSS**: Added complete CSS section with `runs-page`, `runs-header`, `runs-mode-badge`, `runs-progress-*`, `runs-asset-row`, `status-badge`, `runs-last-run`, `runs-idle-message`, and `runs-loading` classes
7. **Shared `statusPulse` animation**: Moved from inline-only in `asset_live.html` to `styles.css` as a shared keyframe

## Task Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add /runs route and create runs.html with dual-mode JS | 4d26b1c | routes.py, runs.html, styles.css |

## Files Created/Modified

### Created
- `src/lattice/web/templates/runs.html` -- Active runs page template (290 lines)

### Modified
- `src/lattice/web/routes.py` -- Added `/runs` route handler before `/asset/{key}/live`
- `src/lattice/web/static/css/styles.css` -- Added runs-page CSS section and statusPulse animation (~200 lines)

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| statusPulse in styles.css | Was only inline in asset_live.html; runs page also needs it; centralizing avoids duplication |
| 1.5s idle transition delay | Lets users see the final completed/failed state before the summary card replaces the asset list |
| Anchor elements for asset rows | Direct navigation to /asset/{key}/live; no JavaScript click handlers needed |
| body overflow-auto via block | Runs page needs vertical scroll for long asset lists; graph page uses overflow-hidden |

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- **Ready for 05-02**: The `/runs` page is complete and functional. Plan 02 (asset live page refactor) can proceed independently.
- **No blockers**: All existing tests pass (276/276). No new server-side endpoints were needed.
- **Integration notes**: The sidebar already links to `/runs` (set up in Phase 4). The route now returns a working page instead of 404.

## Self-Check: PASSED

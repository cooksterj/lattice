---
phase: 02-asset-live-monitoring-page
plan: 01
subsystem: ui
tags: [fastapi, jinja2, html, css, route-ordering, live-monitoring]

# Dependency graph
requires:
  - phase: 01-streaming-infrastructure-and-websocket
    provides: "Per-asset WebSocket endpoint (/ws/asset/{key}), subscriber registry, replay buffer"
provides:
  - "GET /asset/{key}/live route serving live monitoring template"
  - "asset_live.html template with asset details panel and design system compliance"
  - "Route ordering tests proving live and detail routes coexist"
  - "Placeholder sections for WebSocket streaming (Plan 02) and action buttons (Plan 03)"
affects: [02-02-PLAN, 02-03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Compact popup header (no full nav bar) for secondary windows"
    - "XSS-safe rendering with escapeHtml() helper for dynamic content"
    - "Route ordering: specific routes registered before greedy :path routes"

key-files:
  created:
    - "src/lattice/web/templates/asset_live.html"
  modified:
    - "src/lattice/web/routes.py"
    - "tests/test_web.py"

key-decisions:
  - "Live route registered BEFORE greedy detail route to prevent path capture conflict"
  - "Compact header (logo + asset key + LIVE badge) instead of full nav bar for popup window"
  - "escapeHtml() used for all dynamic content to prevent XSS from asset names/descriptions"

patterns-established:
  - "Popup window template pattern: compact header, no full navigation"
  - "Route ordering test pattern: verify both routes coexist with greedy path parameters"

# Metrics
duration: 3min
completed: 2026-02-07
---

# Phase 2 Plan 1: Live Monitoring Page Route and Template Summary

**FastAPI route at /asset/{key}/live with 542-line Jinja2 template following Lattice dimmed mission control design system, asset info panel loading from REST API, and placeholder sections for WebSocket streaming and action buttons**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-07T02:09:11Z
- **Completed:** 2026-02-07T02:12:23Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Route `/asset/{key}/live` registered before greedy `/asset/{key}` to prevent path capture conflict
- Full template with asset info panel that fetches name, group, return type, dependencies, and dependents from `/api/assets/{key}`
- 4 new tests proving route ordering correctness with both simple and grouped (slashed) asset keys
- Template includes all structural placeholders for Plans 02 (WebSocket) and 03 (action buttons, completion banner)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add /asset/{key}/live route with correct ordering and test** - `3bf4bf2` (feat)
2. **Task 2: Create asset_live.html template with asset details panel** - `e25f9c2` (feat)

## Files Created/Modified
- `src/lattice/web/templates/asset_live.html` - Live monitoring page template (542 lines) with asset details panel, log container, status bar, and Plan 02/03 placeholders
- `src/lattice/web/routes.py` - Added GET /asset/{key:path}/live route before greedy /asset/{key:path} detail route
- `tests/test_web.py` - Added TestAssetLivePage class with 4 tests for route ordering and template rendering

## Decisions Made
- **Route ordering:** Registered `/asset/{key:path}/live` on line 52 before `/asset/{key:path}` on line 57 to prevent FastAPI's greedy `:path` converter from capturing `/live` as part of the key
- **Compact header:** Used a streamlined header (LATTICE // asset_key LIVE badge + theme toggle) rather than the full nav bar, since this page opens in a popup window with limited screen space
- **XSS protection:** All dynamic content rendered through `escapeHtml()` helper using `textContent` assignment pattern, preventing XSS from asset names or descriptions containing HTML characters

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-commit hook (ruff-format) reformatted test file on first commit attempt; re-staged and committed successfully on second try

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Template structure is ready for Plan 02 to add WebSocket connection code in the clearly marked placeholder section
- Log container, status bar, and completion banner elements are present and wired with CSS classes for state transitions
- Plan 03 can add action buttons in the marked placeholder div and completion banner logic

## Self-Check: PASSED

---
*Phase: 02-asset-live-monitoring-page*
*Completed: 2026-02-07*

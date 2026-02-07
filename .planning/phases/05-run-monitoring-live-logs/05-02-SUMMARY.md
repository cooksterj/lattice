---
phase: 05-run-monitoring-live-logs
plan: 02
subsystem: ui
tags: [asset-live, sidebar, back-button, refactor, jinja2, css]

# Dependency graph
requires:
  - phase: 04-template-foundation-sidebar
    provides: base.html sidebar layout, current_page context
  - plan: 05-01
    provides: /runs route for back-button navigation target
provides:
  - Refactored asset_live.html as full-page view with sidebar and back button
  - Popup-era chrome (fixed header, action buttons, refocus/history JS) removed
affects: [06 graph integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sub-page header pattern: back-btn + title + separator + context (no sidebar icon highlighted)"
    - "Theme toggle stays in per-page header, not in base.html"

key-files:
  created: []
  modified:
    - src/lattice/web/templates/asset_live.html

key-decisions:
  - "Back button navigates to /runs via standard anchor href (no JS needed)"
  - "No sidebar icon highlighted for live page (it's a sub-page, not top-level nav)"
  - "Theme toggle preserved in page header (same pattern as asset_detail.html)"
  - "Container padding changed from 6rem to 0 top (fixed header removed)"

# Metrics
duration: 1min
completed: 2026-02-07
---

# Phase 5 Plan 02: Asset Live Page Refactor Summary

**Refactored asset_live.html from popup-style layout to full-page sidebar view with back button to /runs**

## Performance

| Metric | Value |
|--------|-------|
| Duration | ~1min |
| Tasks | 1/1 (auto) + 1 checkpoint |
| Test suite | 276 passed |
| Lint | Clean |

## Accomplishments

1. **Removed popup-style fixed header** (`.live-header`): The `position: fixed` header with "LATTICE // asset_key LIVE" badge was designed for a popup window and conflicted with the sidebar layout. Replaced with an inline `.live-page-header`.
2. **Added back button to /runs**: Inline header now includes a `< RUNS` back button linking to the Active Runs page via standard anchor `href="/runs"`.
3. **Removed action buttons**: The "REFOCUS GRAPH" and "RUN HISTORY" buttons (`.action-buttons` div) were popup-era controls. Removed along with their JavaScript functions (`refocusMainWindow()`, `openRunHistory()`).
4. **Cleaned up CSS**: Removed 11 CSS rules for `.live-header`, `.live-header-left`, `.live-header-title`, `.live-header-separator`, `.live-header-asset`, `.live-badge`, `.action-buttons`, `.action-btn` (including `.light`, `:hover`, `.primary`, `:disabled` variants). Added 7 new rules for `.live-page-header`, `.back-btn`, `.live-page-title`, `.live-page-separator`, `.live-page-asset`.
5. **Preserved all functional logic**: WebSocket connection, state machine (idle/running/completed/failed), log streaming with DOM capping at 2000 entries, completion banner, initial state REST check, theme toggle -- all untouched.

## Task Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Refactor asset_live.html from popup-style to full-page layout | 1b8d8c9 | asset_live.html |

## Files Created/Modified

### Modified
- `src/lattice/web/templates/asset_live.html` -- Removed 127 lines (popup header CSS, action buttons CSS/HTML/JS), added 56 lines (page header CSS/HTML with back button)

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Back button as anchor href to /runs | Simple, no JS needed; standard navigation pattern; /runs page created in 05-01 |
| No sidebar icon highlighted | Live page is a sub-page accessed from /runs, not a top-level nav item |
| Theme toggle kept in page header | Consistent with asset_detail.html pattern; base.html only initializes theme, doesn't render toggle |
| Padding 6rem to 0 top | Fixed header removed; content now flows naturally after inline header |

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- **Phase 5 complete**: Both plans (05-01 Active Runs page, 05-02 Asset Live refactor) are done. RECV-03 is satisfied.
- **Ready for Phase 6**: Graph integration can proceed. The sidebar navigation is complete with all three pages (graph, runs, history placeholder).
- **No blockers**: All 276 tests pass. No new dependencies added.

## Self-Check: PASSED

---
phase: 04-template-foundation-sidebar
plan: 01
subsystem: ui
tags: [jinja2, css, sidebar, navigation, template-inheritance]

# Dependency graph
requires:
  - phase: none
    provides: existing standalone HTML templates and CSS design system
provides:
  - Jinja2 base template (base.html) with sidebar, block zones, theme init
  - Sidebar rail CSS with icon styles, active state, and tooltips
  - current_page context variable in all route handlers
affects: [04-02 child template refactor, 05 active runs page, 06 graph refactor]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Jinja2 template inheritance with {% extends 'base.html' %}"
    - "Server-side current_page context for sidebar active highlighting"
    - "CSS-only tooltips via ::after pseudo-element with attr(title)"

key-files:
  created:
    - src/lattice/web/templates/base.html
  modified:
    - src/lattice/web/static/css/styles.css
    - src/lattice/web/routes.py
    - src/lattice/web/routes_history.py

key-decisions:
  - "No header in base.html -- each page defines its own header inside {% block content %}"
  - "Theme init only reads localStorage (no toggle button) -- button stays in per-page headers"
  - "Left corner decorations shifted to left:62px to clear sidebar"
  - "/runs link included now even though Active Runs page does not exist until Phase 5"

patterns-established:
  - "Template inheritance: all pages extend base.html via {% extends %}"
  - "Active page: routes pass current_page string, sidebar uses Jinja2 conditional"
  - "Sidebar icon rail: 52px fixed-left nav with CSS clip-path matching design language"

# Metrics
duration: 3min
completed: 2026-02-07
---

# Phase 4 Plan 01: Template Foundation & Sidebar Summary

**Jinja2 base template with 52px icon rail sidebar, CSS-only tooltips, and server-side active-page highlighting via current_page context**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-07T15:17:09Z
- **Completed:** 2026-02-07T15:20:12Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Created base.html with 6 Jinja2 block zones (title, head_extra, body_class, main_class, content, scripts)
- Built sidebar rail with 3 icon links (Graph, Active Runs, Run History) using inline SVGs from research doc
- Added current_page context to all 4 TemplateResponse calls across routes.py and routes_history.py
- CSS-only hover tooltips on sidebar icons using ::after pseudo-element

## Task Commits

Each task was committed atomically:

1. **Task 1: Create base.html with sidebar and shared structure** - `470e10a` (feat)
2. **Task 2: Add sidebar CSS to styles.css** - `ab0e836` (feat)
3. **Task 3: Add current_page to all route handlers** - `edc98b5` (feat)

## Files Created/Modified
- `src/lattice/web/templates/base.html` - Jinja2 base template with sidebar nav, block zones, corner decorations, theme init
- `src/lattice/web/static/css/styles.css` - Sidebar rail CSS (fixed nav, icon styles, active state, tooltips, main-content offset, corner decor adjustment)
- `src/lattice/web/routes.py` - Added current_page to index, asset_live, and asset_detail TemplateResponse calls
- `src/lattice/web/routes_history.py` - Added current_page to history_page TemplateResponse call

## Decisions Made
- **No shared header in base.html:** Headers vary too much between pages (index has node count + relayout, history has a different layout, asset_live has a compact header). Each page defines its own header in `{% block content %}`.
- **Theme initialization only (no toggle button):** The toggle button is part of each page's header, which varies per page. base.html only reads localStorage and sets the class.
- **Corner decoration offset:** Left corners shifted from `left: 10px` to `left: 62px` (sidebar width + 10px gap) to avoid being hidden behind the sidebar.
- **/runs link goes to `/runs`:** The Active Runs page does not exist yet (Phase 5), but the sidebar icon links to `/runs` now so the 3-icon layout is established. It will 404 until Phase 5.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed line-too-long lint errors in routes.py**
- **Found during:** Task 3 (Add current_page to routes)
- **Issue:** Adding current_page to asset_live and asset_detail TemplateResponse calls pushed lines beyond 100-char limit
- **Fix:** Wrapped the return statements across multiple lines
- **Files modified:** src/lattice/web/routes.py
- **Verification:** `ruff check` passes
- **Committed in:** edc98b5 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minor formatting fix required for lint compliance. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- base.html is ready for child templates to extend via `{% extends "base.html" %}`
- Plan 04-02 will refactor index.html, history.html, asset_detail.html, and asset_live.html to use template inheritance
- The sidebar is fully styled and will render correctly once child templates extend base.html
- All 276 existing tests pass with no regressions

## Self-Check: PASSED

---
*Phase: 04-template-foundation-sidebar*
*Completed: 2026-02-07*

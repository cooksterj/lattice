---
phase: 06-graph-selection-failure-recovery
plan: 01
subsystem: frontend-graph
tags: [d3, javascript, graph-selection, targeted-execution, failure-recovery]

requires:
  - phase: 03
    provides: graph click-to-open-popup infrastructure
  - phase: 04
    provides: sidebar navigation and Execute button
provides:
  - Click-to-select node highlighting on graph
  - Context-aware Execute button (EXECUTE / EXECUTE FROM X / RE-EXECUTE FROM X)
  - Targeted execution wiring (target + include_downstream sent to API)
  - Deselection via background click, Escape key, sidebar close
affects:
  - phase: 07 (popup cleanup -- openAssetWindow is now dead code)

tech-stack:
  added: []
  patterns:
    - "Toggle selection pattern (click selected node to deselect)"
    - "Context-aware button label driven by selection state + execution status"
    - "Targeted execution via existing backend API parameters"

key-files:
  created: []
  modified:
    - src/lattice/web/static/js/graph.js
    - src/lattice/web/templates/index.html

key-decisions:
  - "Clear selection after execution completes (both success and failure) for simplicity"
  - "Do NOT open right-side detail sidebar on node click -- selection is purely visual"
  - "Progress total shows '...' during targeted execution, corrected by showExecutionComplete"
  - "Keep openAssetWindow method definition (dead code) for Phase 7 cleanup"

duration: 2min
completed: 2026-02-08
---

# Phase 6 Plan 01: Graph Selection & Context-Aware Execute Button Summary

**Click-to-select node highlighting with context-aware Execute button for targeted re-execution via existing backend API**

## Performance
- **Duration:** 2min
- **Started:** 2026-02-08T00:17:36Z
- **Completed:** 2026-02-08T00:20:16Z
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments
- Replaced graph node click handler from popup-open to toggle-select pattern
- Added 4 new methods: handleNodeClick, selectNodeForExecution, deselectNode, updateExecuteButtonLabel
- Execute button dynamically shows EXECUTE, EXECUTE FROM [NAME], or RE-EXECUTE FROM [NAME] based on selection and asset status
- Wired startExecution to pass target + include_downstream=true to backend when a node is selected
- Multiple deselection paths: background click, Escape key, sidebar close button, execution completion
- Button label updates in real-time during execution as selected node status changes (e.g., failed -> running)
- Progress total shows '...' for targeted execution to avoid misleading count
- Cache buster bumped to v=17

## Task Commits
1. **Task 1: Implement graph selection and context-aware Execute button** - `888aeff` (feat)
2. **Task 2: Bump cache buster and run lint** - `9c4802d` (chore)

## Files Created/Modified
- `src/lattice/web/static/js/graph.js` - Replaced click handler, added selection state management (handleNodeClick, selectNodeForExecution, deselectNode, updateExecuteButtonLabel), targeted execution wiring, Escape key listener, real-time button label updates during execution
- `src/lattice/web/templates/index.html` - Bumped graph.js cache buster from v=16 to v=17

## Decisions Made
1. **Clear selection after execution completes** - Both success and failure clear selection for simplicity. User can re-select if needed.
2. **No sidebar on click** - Selection is purely visual (highlight + button label). Right-side detail sidebar stays closed.
3. **Progress total '...' during targeted execution** - Avoids misleading "0/15" when only 3 assets run. showExecutionComplete corrects with actual count.
4. **Keep openAssetWindow as dead code** - Method definition preserved for Phase 7 popup cleanup. Only the click handler call was removed.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None

## Next Phase Readiness
Phase 6 Plan 01 is complete. The graph selection and targeted execution wiring is fully functional. The backend already supports `target` + `include_downstream` parameters, so no backend changes were needed. Phase 7 (popup cleanup) can now safely remove the dead `openAssetWindow`, `showPopupBlockedNotice`, `assetWindows`, and `window.name` code since it is no longer called from any handler.

## Self-Check: PASSED

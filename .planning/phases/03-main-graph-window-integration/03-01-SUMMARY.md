---
phase: 03-main-graph-window-integration
plan: 01
status: complete
commits:
  - 38f5c24: "feat(03-01): implement window.open click handler with tracking and popup fallback"
  - 39d4eb2: "fix: Use named window targeting for reliable refocus across browsers"
files_modified:
  - src/lattice/web/static/js/graph.js
  - src/lattice/web/templates/asset_live.html
  - src/lattice/web/templates/index.html
---

# Plan 03-01 Summary: Click handler, window tracking, duplicate prevention, and popup blocker fallback

## What was built

Modified `graph.js` to wire asset node clicks to open independent browser windows with the asset live monitoring page. Added window tracking, duplicate prevention, click-vs-drag disambiguation, and popup blocker fallback.

### Key artifacts

- **`openAssetWindow(assetId)`** — Opens `/asset/{key}/live` in a new browser window via `window.open()`. Tracks window references in `this.assetWindows` Map. Checks `.closed` to detect manually closed windows.
- **`showPopupBlockedNotice(url)`** — Fixed-position notification with "POPUP BLOCKED" label, direct link, dismiss button, and 8s auto-dismiss.
- **`this.assetWindows = new Map()`** — Constructor-initialized Map for deduplication tracking (GRAF-02).
- **`window.name = 'lattice_graph'`** — Named window for reliable refocus from child windows.
- **Click handler** — `event.defaultPrevented` guard for click-vs-drag disambiguation (D3 pattern). Arrow function preserves `this` binding.

### Deviations from plan

1. **Refocus mechanism changed** — Plan specified `window.opener.focus()`. During human verification, discovered this doesn't work in modern browsers (macOS/Chrome restrict `window.focus()` outside direct user gestures). Fixed by using `window.open('/#refocus', 'lattice_graph')` — targeting a named window from a click handler IS treated as a user gesture. Required:
   - `window.name = 'lattice_graph'` in graph.js constructor
   - `refocusMainWindow()` in asset_live.html rewritten to use named window targeting
   - Cache buster bumped from v=13 to v=16 in index.html

### Human verification results

All 6 test scenarios passed:
1. GRAF-01: New window opens on click (after cache buster fix)
2. GRAF-02: Duplicate prevention — re-click focuses existing window
3. GRAF-03: Main graph keeps updating while asset windows open
4. Click-vs-drag disambiguation — drag does not open window
5. Refocus button works (after named window fix)
6. Close and reopen — new window opens for closed assets

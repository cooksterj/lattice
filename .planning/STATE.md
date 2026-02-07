# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** Users can monitor individual asset execution in real-time without losing visibility of the overall pipeline or disrupting downstream execution.
**Current focus:** MILESTONE COMPLETE

## Current Position

Phase: 3 of 3 (Main Graph Window Integration)
Plan: 1 of 1 in current phase
Status: Complete (all phases done)
Last activity: 2026-02-06 -- Phase 3 complete (verified)

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: -
- Total execution time: -

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |
| 2 | 3 | 8min | 2.7min |
| 3 | 1 | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 3-phase structure following dependency chain (streaming infra -> live page -> graph integration)
- [Roadmap]: EXEC-01/EXEC-02 mapped to Phase 1 as architectural invariants verified at infrastructure layer
- [Research]: Per-window WebSocket with server-side filtering (not shared connection with client-side filtering)
- [Research]: asyncio.Queue as sync-to-async bridge for log streaming (emit() never blocks execution)
- [Phase 1]: Fixed capture_logs to use getEffectiveLevel() instead of logger.level for proper level detection
- [Phase 1]: Replay buffer uses collections.deque(maxlen=500) per asset, cleared at each execution start
- [Phase 1]: asyncio.sleep(0) before sentinel ensures all call_soon_threadsafe callbacks are processed
- [Phase 2-01]: Live route registered BEFORE greedy detail route to prevent path capture conflict
- [Phase 2-01]: Compact header for popup window (no full nav bar)
- [Phase 2-01]: escapeHtml() used for all dynamic content to prevent XSS
- [Phase 2-02]: textContent used for log message rendering (XSS safety)
- [Phase 2-02]: checkInitialState() before connectWebSocket() for mid-execution page loads
- [Phase 2-02]: Replay messages recursively processed through handleMessage() for uniform handling
- [Phase 2-02]: DOM capped at 2000 entries (MAX_LOG_ENTRIES) with FIFO eviction
- [Phase 2-03]: Green (#22c55e) success / red (#ef4444) failure banner colors distinct from cyan/pink palette
- [Phase 2-03]: formatDuration handles three ranges: ms (<1s), seconds (<60s), minutes (>=60s)
- [Phase 2-03]: Action buttons always visible (not gated by execution state) for immediate access
- [Phase 3-01]: window.open() must be synchronous in click handler to avoid popup blockers
- [Phase 3-01]: event.defaultPrevented guard for D3 click-vs-drag disambiguation
- [Phase 3-01]: No noopener in window.open features (preserves window.opener for compatibility)
- [Phase 3-01]: Named window targeting (window.name = 'lattice_graph') for reliable refocus — window.opener.focus() unreliable in modern browsers

### Pending Todos

None.

### Blockers/Concerns

- [Resolved]: Log replay protocol -- implemented as deque buffer with "replay" message on connect
- [Resolved]: Popup blocker handling -- synchronous window.open() in click handler with fallback notification
- [Resolved]: Refocus button -- window.opener.focus() unreliable, switched to named window targeting
- [Research Gap]: Virtual scrolling threshold unknown until load testing

## Session Continuity

Last session: 2026-02-06
Stopped at: Milestone complete (all 3 phases done)
Resume file: None

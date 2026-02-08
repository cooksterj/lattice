---
status: complete
phase: 06-graph-selection-failure-recovery
source: [06-01-SUMMARY.md]
started: 2026-02-08T00:35:00Z
updated: 2026-02-08T00:50:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Click node selects with yellow glow
expected: Click any asset node on the graph. The node gets a yellow glow border (no popup opens). The Execute button label changes to "EXECUTE FROM [NAME]".
result: pass

### 2. Click selected node deselects
expected: Click the same node again. The yellow glow disappears and the Execute button resets to "EXECUTE".
result: pass

### 3. Click SVG background deselects
expected: Select a node, then click the empty graph background. The selection clears and button resets to "EXECUTE".
result: pass

### 4. Escape key deselects
expected: Select a node, then press Escape. The selection clears and button resets to "EXECUTE".
result: pass

### 5. Failed asset shows RE-EXECUTE label
expected: After a run with a failure (use web_demo_failures.py), click the failed (red) node. The button reads "RE-EXECUTE FROM [NAME]".
result: issue
reported: "The node isn't red, it blinks. Button label works correctly."
severity: cosmetic

### 6. Non-failed asset shows EXECUTE FROM label
expected: After a run, click a completed (non-failed) node. The button reads "EXECUTE FROM [NAME]" (not RE-EXECUTE).
result: pass

### 7. Targeted re-execution runs only target + downstream
expected: Select the failed cleaned_orders node and click RE-EXECUTE. Only cleaned_orders and its downstream assets run. Upstream assets (raw_orders, raw_users, etc.) do NOT re-run.
result: pass

### 8. Selection clears after execution completes
expected: After the re-execution finishes, the selection is cleared and the button resets to "EXECUTE".
result: pass

### 9. Failed dependency skips downstream immediately
expected: On first execution (web_demo_failures.py), when cleaned_orders fails, all downstream assets gray out immediately. No intermediate assets blink/animate as "running" before being skipped.
result: pass

### 10. Button label updates during execution
expected: Select a failed node and re-execute. While the selected asset is running, observe the button label updates in real-time (e.g., from "RE-EXECUTE FROM X" to "EXECUTE FROM X" as the asset transitions from failed to running/completed).
result: pass

## Summary

total: 10
passed: 9
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Failed node displays with solid red/pink styling"
  status: failed
  reason: "User reported: The node isn't red, it blinks"
  severity: cosmetic
  test: 5
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

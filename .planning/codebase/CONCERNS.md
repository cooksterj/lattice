# Codebase Concerns

**Analysis Date:** 2026-02-06

## Tech Debt

**Bare exception handling in type hint extraction:**
- Issue: Overly broad `except Exception` in `_extract_return_type` catches all exceptions including system exits
- Files: `src/lattice/asset.py:96-99`
- Impact: Silent failures in type hint extraction; bugs in type annotation processing go undetected
- Fix approach: Catch specific exceptions (`TypeError`, `NameError`, `AttributeError`) that `get_type_hints()` can raise; log the failure for debugging

**Global mutable state in check registry:**
- Issue: Lazy-initialized global check registry with `global` keyword; no thread-safety mechanisms
- Files: `src/lattice/observability/checks.py:103-118`
- Impact: In multi-threaded environments (WSGI servers, concurrent requests), concurrent registry modifications can cause race conditions and data corruption
- Fix approach: Use `threading.Lock` in `get_global_check_registry()`; consider thread-local registries for web requests

**Global mutable state in asset registry:**
- Issue: Global singleton registry (`_global_registry`) in `src/lattice/registry.py:120` has no locking mechanism
- Files: `src/lattice/registry.py:25-116, 120-132`
- Impact: Concurrent asset registration from multiple threads (e.g., multi-threaded web server) can corrupt the registry; duplicate registration checks may fail under race conditions
- Fix approach: Add `threading.RLock()` to `AssetRegistry.__init__()` and use it in `register()`, `get()`, and iteration methods

**Inefficient memory usage in graph level tracking:**
- Issue: Temporary `AssetRegistry` created during execution just for graph construction
- Files: `src/lattice/executor.py:482-490`
- Impact: In large asset graphs (1000+ assets), creates unnecessary registry copy and intermediate objects during each execution
- Fix approach: Pass `DependencyGraph` directly to executor instead of reconstructing it; cache graph in ExecutionPlan

**WebSocket connection leak risk:**
- Issue: Dead socket connections tracked but not immediately closed/cleaned; set-based cleanup on broadcast failure
- Files: `src/lattice/web/execution.py:139-157`
- Impact: Long-running web servers with many client disconnects accumulate zombie WebSocket references; memory leak if broadcast fails
- Fix approach: Close sockets immediately on disconnect in `remove_websocket()`; add periodic cleanup task for dead connections

## Known Bugs

**Broad exception handling masks real errors:**
- Symptoms: Type hint extraction silently fails; asset return type is None for malformed annotations
- Files: `src/lattice/asset.py:96-99`
- Trigger: Using `get_type_hints()` on functions with forward references or unresolvable types
- Workaround: Provide explicit `return_type` in type hints; avoid forward references

**Potential race condition in global registry access:**
- Symptoms: `ValueError: Asset X is already registered` when registering same asset from multiple threads
- Files: `src/lattice/registry.py:43-45`
- Trigger: Concurrent `@asset` decorator execution in multi-threaded context (pytest-asyncio, ASGI servers)
- Workaround: Use isolated registries per test/request; avoid module-level asset definitions in concurrent code

## Security Considerations

**SQLite default timeout with concurrent web access:**
- Risk: SQLite database locked errors under high concurrent write load (multiple async tasks writing simultaneously)
- Files: `src/lattice/observability/history/sqlite.py:85`
- Current mitigation: Default 5-second timeout; per-connection creation (not pooled)
- Recommendations:
  - Add `timeout` parameter to `sqlite3.connect()` call; increase from default 5 to 30 seconds
  - Implement connection retry logic with exponential backoff
  - For production: consider PostgreSQL or SQLAlchemy with proper connection pooling

**Missing input validation in CLI:**
- Risk: Arbitrary database paths accepted without validation; no sanitization of file paths
- Files: `src/lattice/cli.py:28-29`
- Current mitigation: None
- Recommendations:
  - Validate `db_path` is within expected directory
  - Use `pathlib.Path.resolve()` to prevent directory traversal

**No rate limiting on web API:**
- Risk: Execution endpoints accept unlimited concurrent requests; no throttling on execution start
- Files: `src/lattice/web/routes.py`, `src/lattice/web/execution.py`
- Current mitigation: `max_concurrency` limits asset-level parallelism, not request rate
- Recommendations:
  - Add FastAPI `SlowAPILimiter` or custom middleware
  - Implement per-IP request rate limiting (max 10 executions/minute)
  - Add execution queue with max size to prevent memory exhaustion

**JSON deserialization without schema validation:**
- Risk: Arbitrary JSON in logs, lineage, and check results fields; no type validation on storage
- Files: `src/lattice/cli.py:79,91,101`; `src/lattice/observability/history/sqlite.py`
- Current mitigation: None
- Recommendations:
  - Define Pydantic schemas for JSON fields (LogEntry, LineageEvent, CheckResult)
  - Validate on deserialization in `RunRecord` model

## Performance Bottlenecks

**Inefficient graph reconstruction in execution loop:**
- Problem: New `DependencyGraph` created from temporary registry on every execution
- Files: `src/lattice/executor.py:482-490`
- Cause: Graph not cached in plan; executor rebuilds from asset definitions
- Improvement path:
  - Store `DependencyGraph` in `ExecutionPlan` at creation time
  - Pass to executor constructor to avoid reconstruction
  - Expected improvement: ~50-100ms saved on large graphs (100+ assets)

**No connection pooling for SQLite operations:**
- Problem: New database connection created per `save()`, `get()`, `list_runs()` call
- Files: `src/lattice/observability/history/sqlite.py:85, 144, 176`
- Cause: File-based database uses context manager that opens/closes on each operation
- Improvement path:
  - Implement simple connection pool with 1-3 persistent connections
  - Reuse connections within thread (SQLite connection not thread-safe)
  - Expected improvement: ~5-10ms per database operation

**Memory inefficiency in large execution state:**
- Problem: Full asset results dictionary stored in `ExecutionState`; timeline stores all snapshots
- Files: `src/lattice/executor.py:466-470`; `src/lattice/web/execution.py:85, 128`
- Cause: No size limits on history; all asset results kept in memory
- Improvement path:
  - Limit memory timeline to last N snapshots (currently 100 on retrieve, not on storage)
  - Archive old asset results to history store instead of keeping in memory
  - Expected improvement: Linear memory usage instead of unbounded

**String concatenation in logging inside loops:**
- Problem: List comprehensions creating strings for debug logs on every asset
- Files: `src/lattice/executor.py:316-321`
- Cause: `[str(d) for d in asset_def.dependencies]` executed even if log level is WARNING
- Improvement path:
  - Wrap with `if logger.isEnabledFor(logging.DEBUG):` guard
  - Use lazy formatting with `%s` and arguments instead of f-strings
  - Expected improvement: Minimal, but scales with asset count

## Fragile Areas

**Executor state management across multiple execution runs:**
- Files: `src/lattice/executor.py:235-240, 295-296`
- Why fragile: `_current_state` modified during execution and cleared in finally block; multiple concurrent executions on same executor instance would corrupt state
- Safe modification: Create new executor per execution (web layer does this correctly); mark Executor as single-use
- Test coverage: Gap in concurrent execution tests; `test_executor.py` has no test for calling execute() twice on same instance

**DependencyGraph cycle detection with incomplete graph:**
- Files: `src/lattice/graph.py:99-146`
- Why fragile: Cycle detection attempts to process external dependencies (not in registry) - reconstruction path vulnerable
- Safe modification: Always build complete subgraph before cycle detection; add assertion that all dependencies are in registry
- Test coverage: `test_graph.py` has no test for external dependencies or partial graphs

**WebSocket broadcast failure handling:**
- Files: `src/lattice/web/execution.py:139-157`
- Why fragile: Broadcast continues even if some sends fail; no guarantee of message delivery order
- Safe modification: Document that broadcast is best-effort; add exception handler for individual send failures
- Test coverage: `test_web.py` has WebSocket tests but no connection drop/error scenarios

## Scaling Limits

**Single-server ExecutionManager not suitable for horizontal scaling:**
- Current capacity: ~4-10 concurrent executions (max_concurrency); in-memory WebSocket registry
- Limit: Server restart loses all WebSocket connections and in-flight metadata
- Scaling path:
  1. Move WebSocket registry to Redis (pub/sub for broadcasts)
  2. Store execution state in PostgreSQL instead of memory
  3. Use distributed locks for asset registration
  4. Currently blocks deployment to multi-server setups

**SQLite not suitable for production concurrent writes:**
- Current capacity: Single writer at a time; blocking under contention
- Limit: >5 concurrent history writes cause "database is locked" errors
- Scaling path: Migrate to PostgreSQL with connection pooling; add async SQLAlchemy

**Memory-based IO Manager accumulates all asset values:**
- Current capacity: Depends on total data size of all assets in memory
- Limit: Graph with 100+ large (100MB+) dataframe assets exceeds typical memory
- Scaling path: Add configurable IO manager backends (Parquet, S3, Redis); implement eviction policy

## Dependencies at Risk

**Pydantic version constraint too loose:**
- Risk: `pydantic>=2.12.5` allows breaking changes in 2.x; v3 may introduce incompatibilities
- Impact: Future pydantic release could break validation in models
- Migration plan:
  - Pin to `pydantic>=2.12.5,<3.0`
  - Add integration tests against latest pydantic 2.x monthly
  - Plan v3 migration when released

**FastAPI optional dependency management:**
- Risk: Web features silently fail if optional dependencies missing; no clear error messages
- Impact: `import psutil` error caught and returns zero metrics; web import errors not caught
- Migration plan:
  - Add explicit check in web module: `if fastapi is None: raise ImportError("..."`
  - Document `pip install lattice[web]` requirement in README
  - Add CI test for web dependencies

**Polars as core dependency without platform testing:**
- Risk: Polars has complex C dependencies; may fail on some Linux distributions
- Impact: Installation failures on stripped-down environments (Alpine Linux, AWS Lambda)
- Migration plan:
  - Make polars optional (move to extras)
  - Support pure-Python fallback or pandas
  - Add CI test for Alpine Linux

## Missing Critical Features

**No graceful shutdown mechanism for long-running executions:**
- Problem: No way to cancel execution from API; only stop flag set
- Blocks: Cannot interrupt stuck asset functions; cannot recover from deadlocks
- Recommendation: Implement execution cancellation with timeout per asset; cleanup handlers

**No audit logging for asset modifications:**
- Problem: No record of when assets were registered or modified
- Blocks: Cannot debug registry state changes or track configuration history
- Recommendation: Add audit log to AssetRegistry.register() with timestamp and caller

**No validation of asset dependency contracts:**
- Problem: No check that dependency asset output type matches consumer input type
- Blocks: Runtime errors from type mismatches only detected during execution
- Recommendation: Add type checking in ExecutionPlan.resolve(); validate producer output type vs consumer input

## Test Coverage Gaps

**Concurrent registry access not tested:**
- What's not tested: Multi-threaded `@asset` decorator registration; concurrent checks registration
- Files: `src/lattice/registry.py`, `src/lattice/observability/checks.py`
- Risk: Race conditions go undetected; data corruption in global state
- Priority: High

**Web WebSocket error scenarios:**
- What's not tested: Client disconnect during execution; connection drops; send failures
- Files: `src/lattice/web/execution.py`
- Risk: Resource leaks and zombie connections in production
- Priority: High

**Async execution with many dependencies:**
- What's not tested: Deeply nested dependency chains (10+ levels); wide dependency trees (100+ assets at same level)
- Files: `src/lattice/executor.py`
- Risk: Stack overflow or deadlocks in real-world graphs
- Priority: Medium

**SQLite concurrency under load:**
- What's not tested: Multiple simultaneous writes to history store; connection timeout behavior
- Files: `src/lattice/observability/history/sqlite.py`
- Risk: Intermittent "database locked" failures in production
- Priority: High

**Error handling in asset functions:**
- What's not tested: Assets that raise exceptions during execution; exception propagation through dependencies
- Files: `src/lattice/executor.py`
- Risk: Unclear error messages; incomplete failure context
- Priority: Medium

**Partition key injection:**
- What's not tested: Assets with partition_key parameter; multiple dates in batch execution
- Files: `src/lattice/executor.py:339-342`, `src/lattice/web/execution.py:209-220`
- Risk: Silent failures if partition_key not injected correctly
- Priority: Medium

---

*Concerns audit: 2026-02-06*

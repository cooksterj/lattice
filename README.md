# Lattice

An asset-centric orchestration framework inspired by Dagster's design philosophy.

## Why Lattice?

If you've chained shell scripts together for data pipelines, you've likely hit these limitations:

| Concern | Shell Scripts | Lattice |
|---------|---------------|---------|
| **Dependencies** | Linear chains only | Complex DAGs (diamonds, fan-out/fan-in) |
| **Parallelism** | Manual with `&` and `wait` | Automatic based on DAG structure |
| **Partial runs** | All or nothing | Run single asset + its dependencies |
| **Failure handling** | `set -e` stops everything | Skip downstream, continue independent branches |
| **Observability** | Custom logging | Built-in status, timing, run history |
| **Caching** | DIY file checks | IO managers handle storage/retrieval |
| **Testing** | Difficult to unit test | Standard Python functions |

The key insight is the **DAG model**: you declare what depends on what, and the framework handles execution order, parallelism, and failure propagation.

```python
from lattice import asset, materialize

@asset
def raw_data() -> list:
    return fetch_from_api()

@asset
def cleaned_data(raw_data: list) -> list:
    return [clean(r) for r in raw_data]

@asset
def report(cleaned_data: list) -> dict:
    return generate_report(cleaned_data)

# Run everything, or just what's needed for a specific target
materialize()                    # all assets
materialize(target="report")     # report + dependencies only
```

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check src tests

# Run type checker
uv run mypy src
```

## Web Visualization

Lattice includes a web-based visualization for exploring asset dependency graphs.

```bash
# Install with web dependencies
uv sync --all-extras

# Run the demo
uv run python examples/web_demo.py
```

Then open http://localhost:8000 in your browser.

The visualization features:
- Left-to-right hierarchical layout showing dependency flow
- Interactive nodes (click for details, drag to reposition)
- Dependency highlighting on hover
- Dark/light theme toggle

## Contributing

This project uses [Conventional Commits](https://www.conventionalcommits.org/) for automated releases.

| Prefix | Purpose | Version Bump |
|--------|---------|--------------|
| `feat:` | New feature | Minor (0.1.0 → 0.2.0) |
| `fix:` | Bug fix | Patch (0.1.0 → 0.1.1) |
| `chore:` | Maintenance | None |
| `docs:` | Documentation | None |
| `feat!:` | Breaking change | Major (0.1.0 → 1.0.0) |

Examples:
```
feat: add dependency graph resolution
fix: handle empty registry in asset decorator
docs: update README with development instructions
chore: update dev dependencies
```

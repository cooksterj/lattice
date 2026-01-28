# Lattice

An asset-centric orchestration framework inspired by Dagster's design philosophy.

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
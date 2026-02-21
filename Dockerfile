# syntax=docker/dockerfile:1
# ── Lattice container image ──────────────────────────────────────────
# Build:  docker build -t lattice .
# Run:    docker run -p 8000:8000 lattice
# ─────────────────────────────────────────────────────────────────────

# ── Stage 1: build ───────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build-only dependencies (uv for fast installs)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy only dependency metadata first for layer caching
COPY pyproject.toml uv.lock ./

# Install runtime dependencies (core + web extras) into a virtual env
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python --requirement pyproject.toml --extra web

# Copy source code and install the package itself
COPY src/ src/
RUN uv pip install --python /opt/venv/bin/python --no-deps .

# ── Stage 2: runtime ────────────────────────────────────────────────
FROM python:3.11-slim

# Install curl for the HEALTHCHECK probe
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd --gid 1000 lattice && \
    useradd --uid 1000 --gid lattice --create-home lattice

WORKDIR /app

# Copy the virtual env from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy example asset definitions so the demo works out of the box
COPY examples/ examples/

# Create data directory for SQLite persistence (volume mount target)
RUN mkdir -p /app/data && chown lattice:lattice /app/data

# Switch to non-root user
USER lattice

# ── Configuration ────────────────────────────────────────────────────
ENV LATTICE_HOST=0.0.0.0 \
    LATTICE_PORT=8000 \
    LATTICE_DB_PATH=/app/data/lattice_runs.db \
    LATTICE_MAX_CONCURRENCY=4

EXPOSE 8000

# ── Health check ─────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Default command ──────────────────────────────────────────────────
CMD ["python", "examples/web_demo.py"]

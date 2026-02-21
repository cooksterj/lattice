# Deployment Guide

This document covers deploying Lattice as a Docker container in three scenarios: local development, AWS ECS Fargate, and EC2.

---

## Table of Contents

1. [Architecture Decision](#architecture-decision)
2. [Environment Variables](#environment-variables)
3. [Local Docker](#local-docker)
4. [AWS ECS Fargate](#aws-ecs-fargate)
5. [AWS EC2](#aws-ec2)

---

## Architecture Decision

Lattice runs as a **single container**. The `ExecutionManager`, WebSocket connections, replay buffers, and `AssetRegistry` are all in-process state that cannot be cleanly separated without introducing a message queue or shared state layer. The codebase is designed for single-process operation where:

- The asset registry is populated at import time via `@asset` decorators
- The `ExecutionManager` holds active run state and broadcasts to WebSocket clients
- The `AsyncExecutor` runs asset functions concurrently within the same event loop
- SQLite is used for run history persistence (single-writer)

Splitting into separate web/executor containers would require a message broker (Redis, RabbitMQ) and a shared database (PostgreSQL), adding operational complexity without meaningful benefit at the current scale.

---

## Environment Variables

All configuration is done through `LATTICE_*` environment variables. Explicit arguments passed to `serve()` or `SQLiteRunHistoryStore()` always override environment variables.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LATTICE_HOST` | `str` | `127.0.0.1` | Bind address for the web server. Use `0.0.0.0` in containers. |
| `LATTICE_PORT` | `int` | `8000` | Web server port. |
| `LATTICE_DB_PATH` | `str` | `lattice_runs.db` | Path to the SQLite run-history database. |
| `LATTICE_MAX_CONCURRENCY` | `int` | `4` | Maximum concurrent asset executions in `AsyncExecutor`. |
| `LATTICE_LOGGING_CONFIG` | `str` | *(built-in)* | Path to a custom logging configuration file (INI format). |

---

## Local Docker

### Building the Image

```bash
docker build -t lattice .
```

### Running with `docker run`

```bash
# Create a data directory for persistence
mkdir -p data

# Run the container
docker run -p 8000:8000 \
  -v ./data:/app/data \
  -e LATTICE_DB_PATH=/app/data/lattice_runs.db \
  lattice
```

Open `http://localhost:8000` in your browser.

### Running with Docker Compose

```bash
# Start (builds if needed)
docker compose up

# Start in the background
docker compose up -d

# Rebuild after code changes
docker compose up --build

# Stop
docker compose down
```

Run history persists in `./data/` across container restarts.

### Verifying the Health Check

```bash
curl http://localhost:8000/health
# {"status":"healthy","version":"0.9.1","asset_count":17}
```

---

## AWS ECS Fargate

### Prerequisites

- An ECR repository for the Lattice image
- An EFS file system for SQLite persistence
- An ALB (Application Load Balancer) for ingress

### Push Image to ECR

```bash
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

docker tag lattice:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/lattice:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/lattice:latest
```

### Task Definition

```json
{
  "family": "lattice",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "lattice",
      "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/lattice:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        { "name": "LATTICE_HOST", "value": "0.0.0.0" },
        { "name": "LATTICE_PORT", "value": "8000" },
        { "name": "LATTICE_DB_PATH", "value": "/app/data/lattice_runs.db" },
        { "name": "LATTICE_MAX_CONCURRENCY", "value": "4" }
      ],
      "mountPoints": [
        {
          "sourceVolume": "lattice-data",
          "containerPath": "/app/data"
        }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 10
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/lattice",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "lattice"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "lattice-data",
      "efsVolumeConfiguration": {
        "fileSystemId": "<efs-file-system-id>",
        "rootDirectory": "/lattice"
      }
    }
  ]
}
```

### ALB Target Group

Configure the ALB target group with:

- **Protocol:** HTTP
- **Port:** 8000
- **Health check path:** `/health`
- **Health check interval:** 30 seconds
- **Healthy threshold:** 2
- **Unhealthy threshold:** 3

WebSocket connections (`/ws/execution`, `/ws/asset/{key}`) require the ALB to have **stickiness enabled** so that WebSocket upgrade requests reach the same task.

### Recommended Resources

- **CPU:** 512 (0.5 vCPU) — sufficient for moderate DAG execution
- **Memory:** 1024 MB — allows headroom for concurrent asset execution
- Scale up to 1024/2048 for pipelines with many parallel assets or large data payloads

---

## AWS EC2

### Direct Docker Run

```bash
# Pull the image (or build locally)
docker pull <account-id>.dkr.ecr.us-east-1.amazonaws.com/lattice:latest

# Run with EBS volume mount
docker run -d \
  --name lattice \
  -p 8000:8000 \
  -v /mnt/lattice-data:/app/data \
  --restart unless-stopped \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/lattice:latest
```

### Systemd Service (Alternative)

Create `/etc/systemd/system/lattice.service`:

```ini
[Unit]
Description=Lattice Orchestration Framework
After=docker.service
Requires=docker.service

[Service]
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/docker stop lattice
ExecStartPre=-/usr/bin/docker rm lattice
ExecStart=/usr/bin/docker run \
  --name lattice \
  -p 8000:8000 \
  -v /mnt/lattice-data:/app/data \
  lattice:latest
ExecStop=/usr/bin/docker stop lattice

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable lattice
sudo systemctl start lattice
```

### Security Group

| Type | Protocol | Port | Source | Purpose |
|------|----------|------|--------|---------|
| Inbound | TCP | 8000 | Your IP / VPC CIDR | Web UI + API |
| Inbound | TCP | 22 | Your IP | SSH access |
| Outbound | All | All | 0.0.0.0/0 | Default |

Restrict port 8000 to your VPC or specific IPs. For public access, place an ALB in front with HTTPS termination.

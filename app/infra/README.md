# OrderFlow Infra

## Responsibilities
- Runtime deployment templates.
- Logging and observability.
- Secure access and audit controls.

## Implemented in T11-A-004
- Docker Compose stack for local foundation services.
- PostgreSQL with pgvector extension bootstrap.
- Redis cache service.
- MinIO object storage with bucket bootstrap job.
- OpenTelemetry Collector and local Jaeger UI.

## Local Boot Sequence

```powershell
cd app/infra
docker compose up -d
```

Check service status:

```powershell
docker compose ps
```

Stop stack:

```powershell
docker compose down
```

## Service Endpoints
- PostgreSQL: localhost:${ORDERFLOW_INFRA_POSTGRES_PORT:-5432}
- Redis: localhost:6379
- MinIO API: http://localhost:${ORDERFLOW_INFRA_MINIO_API_PORT:-9000}
- MinIO Console: http://localhost:${ORDERFLOW_INFRA_MINIO_CONSOLE_PORT:-9001}
- OTel gRPC: localhost:4317
- OTel HTTP: localhost:4318
- Jaeger UI: http://localhost:16686

If your machine already uses port 5432, set `ORDERFLOW_INFRA_POSTGRES_PORT` in `app/infra/.env`
before running `docker compose up -d`.
If your machine already uses ports 9000 or 9001, set `ORDERFLOW_INFRA_MINIO_API_PORT` and
`ORDERFLOW_INFRA_MINIO_CONSOLE_PORT` in `app/infra/.env`.

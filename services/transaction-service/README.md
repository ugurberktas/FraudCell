# transaction-service

Manages financial transactions and fraud evaluation requests for FraudCell.

## Endpoints

| Method | Path | Description | Expected Status |
|---|---|---|---|
| `GET` | `/health` | Liveness check (Independent of Database) | `200 OK` |
| `GET` | `/ready` | Readiness check (Executes `SELECT 1` on `transaction-db`) | `200 OK` (connected) / `503 Service Unavailable` |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SERVICE_NAME` | `transaction-service` | Service identifier |
| `VERSION` | `0.1.0` | Service semantic version |
| `DATABASE_URL` | `postgresql+psycopg://...` | PostgreSQL connection URL |
| `RABBITMQ_URL` | `amqp://...` | RabbitMQ connection URL |
| `REDIS_URL` | `redis://...` | Redis connection URL |

## Running Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

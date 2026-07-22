# identity-service

Handles user identity, authentication, and user metadata for FraudCell.

## Endpoints

| Method | Path | Description | Expected Status |
|---|---|---|---|
| `GET` | `/health` | Liveness check (Independent of Database) | `200 OK` |
| `GET` | `/ready` | Readiness check (Executes `SELECT 1` on `identity-db`) | `200 OK` (connected) / `503 Service Unavailable` |
| `POST` | `/customers/otp/request` | Create a five-minute customer OTP challenge | `200 OK` |
| `POST` | `/customers/register` | Register a customer using GSM and OTP | `201 Created` |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SERVICE_NAME` | `identity-service` | Service identifier |
| `VERSION` | `0.1.0` | Service semantic version |
| `DATABASE_URL` | `postgresql+psycopg://...` | PostgreSQL connection URL |
| `RABBITMQ_URL` | `amqp://...` | RabbitMQ connection URL |
| `REDIS_URL` | `redis://...` | Redis connection URL |
| `DEMO_OTP_CODE` | `1234` | Demo-only OTP code (never stored or returned) |

## Staff password security

Staff passwords are hashed with Argon2id and plaintext passwords are never stored or
returned. Passwords must contain at least eight characters, one uppercase letter,
one digit, and one non-whitespace special character.

There is intentionally no public staff-creation endpoint yet. An Admin-only HTTP
endpoint will be added after JWT authentication and RBAC are available.

## Bootstrap the first Admin

Set all four variables to deployment-specific values (do not commit real secrets):

- `BOOTSTRAP_ADMIN_FIRST_NAME`
- `BOOTSTRAP_ADMIN_LAST_NAME`
- `BOOTSTRAP_ADMIN_EMAIL`
- `BOOTSTRAP_ADMIN_PASSWORD`

Run the explicit, idempotent CLI command inside the Identity Service container:

```bash
docker compose run --rm \
  -e BOOTSTRAP_ADMIN_FIRST_NAME='Initial' \
  -e BOOTSTRAP_ADMIN_LAST_NAME='Admin' \
  -e BOOTSTRAP_ADMIN_EMAIL='admin@example.com' \
  -e BOOTSTRAP_ADMIN_PASSWORD='<replace-with-a-strong-password>' \
  identity-service python -m app.cli.bootstrap_admin
```

## Running Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

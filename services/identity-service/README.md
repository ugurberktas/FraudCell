# identity-service

Handles user identity, authentication, and user metadata for FraudCell.

## Endpoints

| Method | Path | Description | Expected Status |
|---|---|---|---|
| `GET` | `/health` | Liveness check (Independent of Database) | `200 OK` |
| `GET` | `/ready` | Readiness check (Executes `SELECT 1` on `identity-db`) | `200 OK` (connected) / `503 Service Unavailable` |
| `POST` | `/customers/otp/request` | Create a five-minute customer OTP challenge | `200 OK` |
| `POST` | `/customers/register` | Register a customer using GSM and OTP | `201 Created` |
| `POST` | `/customers/login/otp/request` | Request a generic customer login OTP response | `200 OK` |
| `POST` | `/customers/login` | Customer GSM and OTP login | `200 OK` |
| `POST` | `/staff/login` | Staff email and password login | `200 OK` |
| `POST` | `/tokens/refresh` | Rotate a refresh token | `200 OK` |
| `POST` | `/tokens/logout` | Revoke one refresh session | `200 OK` |
| `GET` | `/me` | Return the access-token user | `200 OK` |
| `POST` | `/staff/accounts` | Create staff (ADMIN access token required) | `201 Created` |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SERVICE_NAME` | `identity-service` | Service identifier |
| `VERSION` | `0.1.0` | Service semantic version |
| `DATABASE_URL` | `postgresql+psycopg://...` | PostgreSQL connection URL |
| `RABBITMQ_URL` | `amqp://...` | RabbitMQ connection URL |
| `REDIS_URL` | `redis://...` | Redis connection URL |
| `DEMO_OTP_CODE` | `1234` | Demo-only OTP code (never stored or returned) |
| `ENVIRONMENT` | `development` | Set to `production` to enforce startup secret checks |
| `JWT_SECRET` | none | At least 32 random characters; required for token operations |
| `JWT_ALGORITHM` | `HS256` | Fixed JWT signing algorithm |
| `JWT_ISSUER` | `fraudcell-identity` | Required access-token issuer |
| `JWT_AUDIENCE` | `fraudcell-platform` | Required access-token audience |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access-token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Opaque refresh-token lifetime |

## Authentication tokens

Access tokens are HS256 JWTs containing `sub`, `user_id`, `role`,
`specializations`, `regions`, `type`, `jti`, `iat`, `exp`, `iss`, and `aud`.
They expire after 15 minutes. Refresh tokens are opaque 256-bit values that expire
after seven days; only their SHA-256 hashes are stored.

Every refresh rotates to a new token in one transaction. Reusing a token that was
already rotated returns `TOKEN_REUSE_DETECTED` and revokes every active refresh
session belonging to that user. Logout is idempotent and revokes only the supplied
session.

## Staff account lockout

Staff login counters are updated under a database row lock. The first four invalid
password attempts return `401 AUTHENTICATION_FAILED`. The fifth returns
`429 ACCOUNT_LOCKED`, sets a 15-minute UTC lock, and includes both
`details.remaining_seconds` and `Retry-After`. A successful login after expiry
clears `failed_login_count` and `locked_until`.

## RBAC and immutable audit logs

`/me` accepts every authenticated active role. `POST /staff/accounts` and
`GET /audit-logs` require the user's current database role to be `ADMIN`; stale JWT
role claims cannot grant access. Inactive users and insufficient roles return
`403 FORBIDDEN`, and each denial appends an `ACCESS_DENIED` audit record.

`GET /audit-logs` supports pagination plus action, actor, result, and UTC date
filters. There are deliberately no audit update or delete endpoints. Supported
actions are:

- `AUTH_LOGIN_SUCCESS`
- `AUTH_LOGIN_FAILED`
- `AUTH_ACCOUNT_LOCKED`
- `AUTH_TOKEN_REFRESHED`
- `AUTH_TOKEN_REUSE_DETECTED`
- `AUTH_LOGOUT`
- `STAFF_ACCOUNT_CREATED`
- `ACCESS_DENIED`
- `ROLE_CHANGED`

Audit details are recursively stripped of password, OTP, authorization, token, and
secret fields before persistence and again before API serialization.

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

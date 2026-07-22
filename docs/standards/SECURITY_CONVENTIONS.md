# FraudCell Security Conventions & Guidelines

## 1. Security Headers & Authentication

### 1.1 `Authorization` Header
- Authentication token must be passed via HTTP header using the Bearer scheme:
  `Authorization: Bearer <jwt_token>`
- Token validation is performed at the API Gateway level (Kong) before routing to internal microservices.

### 1.2 `Idempotency-Key` Header
- State-changing requests (`POST`, `PUT`, `PATCH`) that require deduplication must accept an `Idempotency-Key` header (UUID v4).
- Request payloads with the same key must return cached results without executing redundant processing.

### 1.3 `X-Request-ID` Header
- Required for end-to-end request tracing and audit logging.

---

## 2. Sensitive Data & Privacy (PII Protection)

- **No Logging of Sensitive Data:** Raw passwords, credit card PAN numbers, CVVs, or full identity numbers must NEVER be written to application log files or traces.
- Masking rules apply to log outputs (e.g. `4111****1111`).

---

## 3. Internal Error Masking & Information Leakage Prevention

- Stack traces, internal SQL queries, database error messages, or internal IP addresses must NEVER be returned to the client in production responses.
- Unhandled exceptions must return a generic 500 error code with a safe message (`"An internal error occurred. Please contact system administrator."`).

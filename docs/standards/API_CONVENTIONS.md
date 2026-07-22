# FraudCell API Conventions Standard

## 1. Response Structure

All FraudCell REST API endpoints return a uniform JSON envelope structure.

### 1.1 Successful Response (`2xx`)

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

- `success` (boolean): Always `true` for successful operations.
- `data` (object/array/null): Payload containing the requested data or operation result.
- `error` (null): Always `null` on success.

### 1.2 Error Response (`4xx` / `5xx`)

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource could not be found.",
    "details": {
      "resource_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    }
  }
}
```

- `success` (boolean): Always `false` for error responses.
- `data` (null): Always `null` on error.
- `error` (object): Error details object containing:
  - `code` (string): UPPER_SNAKE_CASE machine-readable error code.
  - `message` (string): Human-readable error description.
  - `details` (object): Additional context or field-level validation errors.

---

## 2. Request Tracing (`X-Request-ID`)

- Every HTTP request should include the `X-Request-ID` header containing a UUID v4 string.
- If the header is missing, the API Gateway (Kong) or receiving service must auto-generate a new UUID v4.
- The `X-Request-ID` must be propagated across all internal microservice calls and included in log messages.

---

## 3. Standard HTTP Status Codes

| Code | Status | Usage |
|---|---|---|
| `200` | OK | Successful retrieval or update operation |
| `201` | Created | Successful resource creation |
| `204` | No Content | Successful deletion or operation with empty body |
| `400` | Bad Request | Invalid request parameters or payload syntax |
| `401` | Unauthorized | Missing or invalid authentication token |
| `403` | Forbidden | Authenticated user lacks required permissions |
| `404` | Not Found | Target resource does not exist |
| `409` | Conflict | State conflict (e.g. duplicate key or concurrent update) |
| `422` | Unprocessable Entity | Domain validation rule failure |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unhandled internal server exception |
| `503` | Service Unavailable | Downstream database or service unreachable |

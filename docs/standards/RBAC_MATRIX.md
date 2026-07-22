# FraudCell RBAC Matrix

This document records the platform authorization target matrix. Identity rules in
the **Enforcement** column are implemented now. Transaction and Dashboard rules are
the target for their next implementation steps; Identity Service does not expose
placeholder endpoints for them.

| Capability | Public | CUSTOMER | ANALYST | SUPERVISOR | ADMIN | Enforcement |
|---|---:|---:|---:|---:|---:|---|
| Customer registration and registration OTP | ✓ | ✓ | ✓ | ✓ | ✓ | Identity: public |
| Customer login OTP and login | ✓ | ✓ | ✓ | ✓ | ✓ | Identity: public |
| Staff login | ✓ | ✓ | ✓ | ✓ | ✓ | Identity: public authentication entry |
| Refresh and logout own session | — | ✓ | ✓ | ✓ | ✓ | Identity: refresh-token ownership |
| View own identity (`GET /me`) | — | ✓ | ✓ | ✓ | ✓ | Identity: authenticated, active user |
| Create staff accounts | — | — | — | — | ✓ | Identity: ADMIN |
| View immutable audit logs | — | — | — | — | ✓ | Identity: ADMIN |
| Change a user's role | — | — | — | — | ✓ | Identity: planned; audit helper ready |
| Submit/view own transactions | — | ✓ | — | — | ✓ | Transaction step: planned |
| View fraud investigation queue | — | — | ✓ | ✓ | ✓ | Transaction step: planned |
| Review assigned cases | — | — | ✓ | ✓ | ✓ | Transaction step: planned |
| Decide/block a transaction | — | — | ✓ | ✓ | ✓ | Transaction step: planned |
| Assign/reassign cases | — | — | — | ✓ | ✓ | Transaction step: planned |
| Override analyst decisions | — | — | — | ✓ | ✓ | Transaction step: planned |
| Configure platform/reference data | — | — | — | — | ✓ | Platform step: planned |
| Customer dashboard | — | ✓ | — | — | ✓ | Dashboard step: planned |
| Analyst operations dashboard | — | — | ✓ | ✓ | ✓ | Dashboard step: planned |
| Supervisor performance/dashboard views | — | — | — | ✓ | ✓ | Dashboard step: planned |
| Administration dashboard | — | — | — | — | ✓ | Dashboard step: planned |

Authorization always uses the active user's current database role. JWT role claims
are descriptive and must not override the current database state. Missing or invalid
authentication returns `401`; authenticated but unauthorized or inactive users
return `403`, with Identity denials appended as `ACCESS_DENIED` audit records.

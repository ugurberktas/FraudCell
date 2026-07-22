# FraudCell Event Catalog & Specifications

This document serves as the authoritative domain event catalog and schema specification for the FraudCell event-driven architecture.

---

## 🏛️ Producer Responsibility Matrix

| Microservice | Authoritative Produced Events |
|---|---|
| **Identity Service** | *None (Consumption only)* |
| **Transaction Service** | `transaction.created`, `case.assigned`, `case.decision_made`, `transaction.blocked`, `fraud_type.changed`, `customer.verified`, `sla.exceeded`, `feedback.submitted` |
| **AI Service** | `transaction.scored`, `case.assigned` |
| **Gamification Service** | `badge.earned` |

---

## ⚡ Standard Event Envelope Format

All events emitted across the message broker must strictly adhere to the `EventEnvelope` model schema:

```json
{
  "event_id": "c1510888-5812-45b4-83fa-9d1d83e36c0a",
  "event_type": "transaction.created",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:50:00Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {}
}
```

- **`event_id`** (UUID v4): Unique event instance identifier.
- **`event_type`** (string): Standardized event type string from canonical catalog.
- **`event_version`** (integer > 0): Event schema version. Defaults to `1`.
- **`occurred_at`** (UTC ISO-8601 string): Timezone-aware UTC timestamp when event occurred.
- **`producer`** (string): Microservice component name emitting the event.
- **`correlation_id`** (UUID v4): Trace correlation identifier matching `X-Request-ID`.
- **`payload`** (object): Domain event data payload.

---

## 📋 Catalog of Domain Events

### 1. `transaction.created`
- **Amaç:** Yeni bir finansal işlem sisteme kaydedildiğinde tetiklenir.
- **Producer:** `transaction-service`
- **Consumer:** `ai-service`
- **Version:** `1`
- **Idempotency Key:** `payload.transaction_number`
- **Payload Fields:** `transaction_number`, `account_id`, `amount`, `currency`, `transaction_type`
- **Example JSON:**
```json
{
  "event_id": "c1510888-5812-45b4-83fa-9d1d83e36c0a",
  "event_type": "transaction.created",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:50:00Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "transaction_number": "TRX-2026-000123",
    "account_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "amount": 1250.50,
    "currency": "TRY",
    "transaction_type": "TRANSFER"
  }
}
```

---

### 2. `transaction.scored`
- **Amaç:** Yapay zeka modeli finansal işlemin risk skorlamasını tamamladığında tetiklenir.
- **Producer:** `ai-service`
- **Consumer:** `transaction-service`, `gamification-service`
- **Version:** `1`
- **Idempotency Key:** `event_id`
- **Payload Fields:** `transaction_number`, `risk_score`, `risk_level`, `ai_decision`
- **Example JSON:**
```json
{
  "event_id": "b26829aa-1234-4ef8-9999-123456789abc",
  "event_type": "transaction.scored",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:51:00Z",
  "producer": "ai-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "transaction_number": "TRX-2026-000123",
    "risk_score": 0.94,
    "risk_level": "KRITIK",
    "ai_decision": "BLOK"
  }
}
```

---

### 3. `case.assigned`
- **Amaç:** Şüpheli bir işlem incelenmek üzere bir dolandırıcılık analistine atandığında tetiklenir.
- **Producer:** `ai-service`, `transaction-service`
- **Consumer:** `gamification-service`
- **Version:** `1`
- **Idempotency Key:** `payload.case_id + ":" + payload.analyst_id`
- **Payload Fields:** `case_id`, `transaction_number`, `analyst_id`, `status`
- **Example JSON:**
```json
{
  "event_id": "d37730bb-5678-4ef8-8888-987654321def",
  "event_type": "case.assigned",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:52:00Z",
  "producer": "ai-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "case_id": "e48841cc-9012-4ef8-7777-111122223333",
    "transaction_number": "TRX-2026-000123",
    "analyst_id": "f59952dd-3456-4ef8-6666-444455556666",
    "status": "ATANDI"
  }
}
```

---

### 4. `case.decision_made`
- **Amaç:** Analist vaka incelemesini tamamlayıp karar (onay/blok) verdiğinde tetiklenir.
- **Producer:** `transaction-service`
- **Consumer:** `gamification-service`, `identity-service`
- **Version:** `1`
- **Idempotency Key:** `payload.case_id`
- **Payload Fields:** `case_id`, `analyst_id`, `decision`, `fraud_type`
- **Example JSON:**
```json
{
  "event_id": "e48841cc-9012-4ef8-7777-111122223333",
  "event_type": "case.decision_made",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:55:00Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "case_id": "e48841cc-9012-4ef8-7777-111122223333",
    "analyst_id": "f59952dd-3456-4ef8-6666-444455556666",
    "decision": "BLOKLANDI",
    "fraud_type": "CALINTI_KART"
  }
}
```

---

### 5. `transaction.blocked`
- **Amaç:** Yüksek riskli bir işlem durdurulup bloke edildiğinde tetiklenir.
- **Producer:** `transaction-service`
- **Consumer:** `identity-service`, `gamification-service`
- **Version:** `1`
- **Idempotency Key:** `payload.case_id`
- **Payload Fields:** `case_id`, `analyst_id`, `fraud_type`, `risk_level`, `amount`, `created_at`, `decided_at`
- **Example JSON:**
```json
{
  "event_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "event_type": "transaction.blocked",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:55:30Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "case_id": "e48841cc-9012-4ef8-7777-111122223333",
    "analyst_id": "f59952dd-3456-4ef8-6666-444455556666",
    "fraud_type": "CALINTI_KART",
    "risk_level": "KRITIK",
    "amount": 4500.0,
    "created_at": "2026-07-22T23:50:00Z",
    "decided_at": "2026-07-22T23:55:00Z"
  }
}
```

---

### 6. `fraud_type.changed`
- **Amaç:** İncelenen bir vakanın dolandırıcılık türü güncellendiğinde tetiklenir.
- **Producer:** `transaction-service`
- **Consumer:** `ai-service`
- **Version:** `1`
- **Idempotency Key:** `event_id`
- **Payload Fields:** `case_id`, `old_fraud_type`, `new_fraud_type`, `updated_by`
- **Example JSON:**
```json
{
  "event_id": "f59952dd-3456-4ef8-6666-444455556666",
  "event_type": "fraud_type.changed",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:56:00Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "case_id": "e48841cc-9012-4ef8-7777-111122223333",
    "old_fraud_type": "SUPHELI_DAVRANIS",
    "new_fraud_type": "CALINTI_KART",
    "updated_by": "f59952dd-3456-4ef8-6666-444455556666"
  }
}
```

---

### 7. `customer.verified`
- **Amaç:** Müşteri doğrulama adımı (SMS/Push vb.) başarıyla tamamlandığında tetiklenir.
- **Producer:** `transaction-service`
- **Consumer:** `identity-service`
- **Version:** `1`
- **Idempotency Key:** `payload.customer_id + ":" + occurred_at`
- **Payload Fields:** `customer_id`, `verification_channel`, `response`
- **Example JSON:**
```json
{
  "event_id": "11112222-3333-4444-5555-666677778888",
  "event_type": "customer.verified",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:56:30Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "customer_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "verification_channel": "SMS_OTP",
    "response": "BEN_YAPTIM"
  }
}
```

---

### 8. `sla.exceeded`
- **Amaç:** Bir vaka incelemesi tanımlanan SLA süresini aştığında tetiklenir.
- **Producer:** `transaction-service`
- **Consumer:** `gamification-service`
- **Version:** `1`
- **Idempotency Key:** `payload.case_id + ":sla_exceeded"`
- **Payload Fields:** `case_id`, `sla_threshold_minutes`, `elapsed_minutes`
- **Example JSON:**
```json
{
  "event_id": "22223333-4444-5555-6666-777788889999",
  "event_type": "sla.exceeded",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:57:00Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "case_id": "e48841cc-9012-4ef8-7777-111122223333",
    "sla_threshold_minutes": 15,
    "elapsed_minutes": 22
  }
}
```

---

### 9. `feedback.submitted`
- **Amaç:** Müşteri güvenlik geri bildirimi sunduğunda tetiklenir.
- **Producer:** `transaction-service`
- **Consumer:** `identity-service`, `ai-service`
- **Version:** `1`
- **Idempotency Key:** `payload.feedback_id`
- **Payload Fields:** `feedback_id`, `customer_id`, `score`, `comments`
- **Example JSON:**
```json
{
  "event_id": "33334444-5555-6666-7777-888899990000",
  "event_type": "feedback.submitted",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:57:30Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "feedback_id": "44445555-6666-7777-8888-999900001111",
    "customer_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "score": 5,
    "comments": "Hızlı doğrulama için teşekkürler."
  }
}
```

---

### 10. `badge.earned`
- **Amaç:** Bir analist başarım/rozet kazandığında tetiklenir.
- **Producer:** `gamification-service`
- **Consumer:** `identity-service`
- **Version:** `1`
- **Idempotency Key:** `payload.analyst_id + ":" + payload.badge_code`
- **Payload Fields:** `analyst_id`, `badge_code`, `badge_name`, `earned_at`
- **Example JSON:**
```json
{
  "event_id": "55556666-7777-8888-9999-000011112222",
  "event_type": "badge.earned",
  "event_version": 1,
  "occurred_at": "2026-07-22T23:58:00Z",
  "producer": "gamification-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "analyst_id": "f59952dd-3456-4ef8-6666-444455556666",
    "badge_code": "FAST_RESOLVER_100",
    "badge_name": "Hızlı Müdahale Uzmanı",
    "earned_at": "2026-07-22T23:58:00Z"
  }
}
```

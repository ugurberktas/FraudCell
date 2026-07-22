# FraudCell Event Contracts & Message Schema Specification

> **Note:** This document serves as the architectural blueprint for asynchronous event contracts in the FraudCell platform. Current implementation represents the infrastructure skeleton (RabbitMQ broker provisioning); event producers and consumers will be implemented in upcoming features.

## 📡 Message Broker Infrastructure

- **Broker:** RabbitMQ (Management Plugin enabled)
- **Container Name:** `fraudcell-rabbitmq-1`
- **Internal Port:** `5672` (isolated to `platform-network`)
- **Management UI:** `http://localhost:15672`

---

## 🔀 Event Exchanges & Queues (Planned Specification)

### 1. `identity.events` (Topic Exchange)

| Routing Key | Source Service | Consumer Service(s) | Description |
|---|---|---|---|
| `user.created` | `identity-service` | `gamification-service` | Triggered when a new user registers |
| `user.blocked` | `identity-service` | `transaction-service`, `ai-service` | Triggered when a user is flagged or blocked |

### 2. `transaction.events` (Topic Exchange)

| Routing Key | Source Service | Consumer Service(s) | Description |
|---|---|---|---|
| `transaction.initiated` | `transaction-service` | `ai-service` | Triggered when a new transaction requires fraud scoring |
| `transaction.flagged` | `transaction-service` | `gamification-service`, `identity-service` | Triggered when fraud is detected |

### 3. `ai.events` (Topic Exchange)

| Routing Key | Source Service | Consumer Service(s) | Description |
|---|---|---|---|
| `score.completed` | `ai-service` | `transaction-service` | Returns real-time AI risk score for a transaction |

---

## 📄 Standard Event Payload Envelope

All asynchronous messages will conform to the CloudEvents specification format:

```json
{
  "specversion": "1.0",
  "type": "com.fraudcell.transaction.initiated",
  "source": "/services/transaction-service",
  "id": "evt_9f8e7d6c-5b4a-3f2e-1d0c-9b8a7f6e5d4c",
  "time": "2026-07-22T23:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "transaction_id": "tx_12345",
    "user_id": "usr_67890",
    "amount": 1250.00,
    "currency": "TRY"
  }
}
```

# FraudCell Domain Conventions & Data Types

## 1. Identifiers & Formats

### 1.1 Internal Primary Keys
- All entity identifiers across microservices must use **UUID v4** strings.
- Example: `"a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"`

### 1.2 Transaction Numbers
- Business transaction numbers follow the formatted pattern: `TRX-YYYY-NNNNNN`
- `YYYY`: 4-digit UTC year (e.g. `2026`)
- `NNNNNN`: 6-digit zero-padded sequence number (e.g. `000123`)
- Example: `"TRX-2026-000123"`

### 1.3 Timestamps
- All date-time values across APIs, databases, and events must be in **UTC** formatted according to **ISO-8601** with the `Z` suffix.
- Format: `YYYY-MM-DDTHH:mm:ss.sssZ`
- Example: `"2026-07-22T23:50:00.000Z"`

### 1.4 Currency & Monetary Amounts
- Amounts in JSON payloads must be formatted as Decimal-compatible numeric values (or string formatted numbers when precision requires it) with up to 2 decimal places.
- Example: `1250.50`

---

## 2. Canonical Domain Enums

Canonical enumeration values are centralized in `contracts/domain-enums.json`.

1. **User Roles (`roles`):**
   `CUSTOMER`, `ANALYST`, `SUPERVISOR`, `ADMIN`

2. **Transaction Types (`transaction_types`):**
   `ODEME`, `TRANSFER`, `FATURA`, `CEKIM`

3. **Fraud Classifications (`fraud_types`):**
   `CALINTI_KART`, `HESAP_ELE_GECIRME`, `PARA_AKLAMA`, `SUPHELI_DAVRANIS`, `TEMIZ`

4. **AI Decision Outcomes (`ai_decisions`):**
   `ONAY`, `INCELEME`, `BLOK`

5. **Risk Assessment Levels (`risk_levels`):**
   `DUSUK`, `ORTA`, `YUKSEK`, `KRITIK`, `BELIRSIZ`

6. **Analyst Case Statuses (`case_statuses`):**
   `YENI`, `ATANDI`, `INCELENIYOR`, `MUSTERI_DOGRULAMA`, `ONAYLANDI`, `BLOKLANDI`, `KAPANDI`

7. **Customer Verification Responses (`customer_responses`):**
   `BEN_YAPTIM`, `BEN_YAPMADIM`, `YANIT_YOK`

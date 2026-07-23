# FraudCell Event Sözleşmeleri

Bu doküman çalışan broker akışını, shared event envelope'ını ve henüz yalnızca
şema kataloğunda bulunan event adlarını birbirinden ayırır.

## Çalışan event akışı

Runtime'da RabbitMQ'ya yayınlanan yalnızca iki event vardır:

| Event | Producer | Consumer | Etki |
|---|---|---|---|
| `case.decision_made` | Transaction Service | Gamification worker | Ledger, profil, seviye ve gerekirse `ILK_YAKALAMA` |
| `feedback.submitted` | Transaction Service | Gamification worker | Idempotent `ProcessedEvent`; puan/rozet üretmez |

Her iki event de Transaction DB'deki `outbox_events` tablosu üzerinden yayınlanır.
AI skorlaması ve Analyst ataması şu an Transaction Service ile AI Service arasındaki
senkron HTTP çağrısıdır; `transaction.scored` veya `case.assigned` broker event'i
üretilmez. Rozet DB'ye yazılır; `badge.earned` yayınlanmaz.

## Broker topolojisi

| Bileşen | Değer |
|---|---|
| Exchange | `fraudcell.events` |
| Exchange türü | durable topic |
| Queue | `gamification.case-decisions.v1` |
| Binding keys | `case.decision_made`, `feedback.submitted` |
| Producer worker | `transaction-outbox-worker` |
| Consumer worker | `gamification-worker` |
| Mesaj | JSON, persistent (`delivery_mode=2`) |
| Teslim modeli | at-least-once |
| Idempotency | `processed_events.event_id` unique |

## Event envelope v1

```json
{
  "event_id": "e48841cc-9012-4ef8-8777-111122223333",
  "event_type": "case.decision_made",
  "event_version": 1,
  "occurred_at": "2026-07-23T01:35:00Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {}
}
```

- `event_id`: event instance UUID'si ve consumer idempotency anahtarıdır.
- `event_type`: shared `EventType` kataloğundaki değerdir.
- `event_version`: çalışan consumer için `1` olmalıdır.
- `occurred_at`: timezone-aware ISO-8601 zamandır.
- `producer`: event'i oluşturan servis adıdır.
- `correlation_id`: Request ID geçerli UUID ise taşınır; değilse yeni UUID üretilir.
- `payload`: event'e özgü, consumer tarafından `extra=forbid` ile doğrulanan objedir.

## `case.decision_made` v1

Analyst `ONAYLANDI` veya `BLOKLANDI` kararı verdiğinde `RiskCase`, `CaseHistory`,
Transaction kararı ve outbox satırı aynı PostgreSQL transactionında commit edilir.

| Alan | Tür | Açıklama |
|---|---|---|
| `case_id` | UUID | RiskCase kimliği |
| `transaction_id` | UUID | İşlem kimliği |
| `analyst_id` | UUID | Kararı veren atanmış Analyst |
| `decision` | enum | `ONAYLANDI` veya `BLOKLANDI` |
| `fraud_type` | string | İşlemde kayıtlı fraud sınıfı |
| `risk_level` | enum | `DUSUK`, `ORTA`, `YUKSEK`, `KRITIK`, `BELIRSIZ` |
| `customer_response` | enum | `BEN_YAPTIM`, `BEN_YAPMADIM`, `YANIT_YOK` |
| `case_created_at` | datetime | Timezone-aware vaka zamanı |
| `decided_at` | datetime | Timezone-aware karar zamanı |
| `resolution_seconds` | integer | Negatif olmayan çözüm süresi |
| `sla_exceeded` | boolean | Karar anı SLA sonrasındaysa `true` |
| `is_false_positive` | boolean | Mevcut akışta producer `false` gönderir |

Golden Demo'ya uygun örnek:

```json
{
  "event_id": "e48841cc-9012-4ef8-8777-111122223333",
  "event_type": "case.decision_made",
  "event_version": 1,
  "occurred_at": "2026-07-23T01:35:00Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "case_id": "548841cc-9012-4ef8-8777-111122223333",
    "transaction_id": "a0eebc99-1c0b-4ef8-bb6d-6bb9bd380a11",
    "analyst_id": "f59952dd-3456-4ef8-8666-444455556666",
    "decision": "BLOKLANDI",
    "fraud_type": "HESAP_ELE_GECIRME",
    "risk_level": "YUKSEK",
    "customer_response": "BEN_YAPMADIM",
    "case_created_at": "2026-07-23T01:30:00Z",
    "decided_at": "2026-07-23T01:35:00Z",
    "resolution_seconds": 300,
    "sla_exceeded": false,
    "is_false_positive": false
  }
}
```

Bu örnek `+30` üretir: `CASE_RESOLVED +10`, `FAST_DECISION +5` ve
`CONFIRMED_FRAUD +15`. `risk_level=KRITIK` ve `sla_exceeded=false` olsaydı ayrıca
`CRITICAL_WITHIN_SLA +15` oluşurdu.

## `feedback.submitted` v1

Supervisor vakayı `KAPANDI` durumuna getirdikten sonra işlem sahibi Customer bir
kez 1–5 rating gönderebilir. Feedback ile outbox satırı aynı DB transactionında
oluşur.

| Alan | Tür | Açıklama |
|---|---|---|
| `feedback_id` | UUID | Feedback kimliği |
| `case_id` | UUID | Kapatılmış vaka |
| `customer_id` | UUID | İşlemin sahibi |
| `rating` | integer | `1..5` |
| `created_at` | datetime | Timezone-aware kayıt zamanı |

```json
{
  "event_id": "33334444-5555-4666-8777-888899990000",
  "event_type": "feedback.submitted",
  "event_version": 1,
  "occurred_at": "2026-07-23T01:40:00Z",
  "producer": "transaction-service",
  "correlation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "feedback_id": "44445555-6666-4777-8888-999900001111",
    "case_id": "548841cc-9012-4ef8-8777-111122223333",
    "customer_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "rating": 5,
    "created_at": "2026-07-23T01:40:00Z"
  }
}
```

Gamification worker şemayı doğrular ve `ProcessedEvent` yazar; mevcut MVP'de
feedback puanı veya rozeti yoktur.

## Teslim ve recovery davranışı

1. API, domain değişikliği ile outbox satırını tek DB transactionında commit eder.
2. HTTP response RabbitMQ'yu beklemez ve `event_delivery=PENDING` döner.
3. Outbox worker pending satırı persistent mesaj olarak yayınlar ve publisher confirm
   aldıktan sonra `published_at` alanını doldurur.
4. RabbitMQ kapalıysa karar/feedback DB'de kalır; outbox denemeleri backoff ile sürer.
5. Gamification worker DB commitinden sonra ACK verir. Geçici hatada NACK/requeue,
   geçersiz payload'da reject/no-requeue kullanır.
6. Aynı `event_id` tekrar gelirse `ProcessedEvent` unique kontrolü ikinci ledger,
   profil artışı veya rozet üretmez.

Transaction Service, Gamification Service'e doğrudan HTTP çağrısı yapmaz.

## Şema kataloğunda rezerv, runtime'da yayınlanmayan adlar

Shared `EventType`, contract örnekleri ve `scripts/validate_contracts.py` aşağıdaki
gelecek sözleşme adlarını da tanır. Bunların bu MVP'de producer/consumer akışı yoktur:

- `transaction.created`
- `transaction.scored`
- `case.assigned`
- `transaction.blocked`
- `fraud_type.changed`
- `customer.verified`
- `sla.exceeded`
- `badge.earned`

Contract validator bu dosyaların envelope biçimini kontrol eder; runtime entegrasyonu
olduğunu kanıtlamaz.

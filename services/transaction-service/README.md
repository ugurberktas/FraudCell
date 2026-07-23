# transaction-service

FraudCell Golden Demo işlemlerini, AI skorlamasını ve minimal risk vaka akışını yönetir.

## Endpointler

| Method | Path | Rol | Açıklama |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness |
| `GET` | `/ready` | Public | PostgreSQL readiness |
| `POST` | `/transactions` | CUSTOMER | İşlem oluşturur ve AI skorlaması ister |
| `GET` | `/transactions/me` | CUSTOMER | Kendi işlemlerini en yeni önce listeler |
| `GET` | `/transactions/{id}` | Sahip CUSTOMER, atanmış ANALYST, SUPERVISOR, ADMIN | IDOR korumalı işlem detayı |
| `GET` | `/cases/assigned-to-me` | ANALYST | Atanmış vakaları risk ve SLA önceliğiyle listeler |
| `GET` | `/cases` | SUPERVISOR, ADMIN | Tüm vakalar; opsiyonel `status` filtresi |
| `POST` | `/cases/{id}/assign` | SUPERVISOR | Fallback vakayı analiste atar |
| `POST` | `/cases/{id}/start` | Atanmış ANALYST | Vakayı incelemeye alır |
| `POST` | `/cases/{id}/request-verification` | Atanmış ANALYST | Müşteri doğrulaması ister |
| `POST` | `/cases/{id}/customer-response` | İşlem sahibi CUSTOMER | Doğrulama cevabı verir |
| `POST` | `/cases/{id}/decision` | Atanmış ANALYST | Onay/blok kararı verir |
| `POST` | `/cases/{id}/close` | SUPERVISOR | Karar verilmiş vakayı kapatır |
| `POST` | `/cases/{id}/feedback` | İşlem sahibi CUSTOMER | Kapalı vakaya tek seferlik 1–5 puan verir |

Kong dış adresleri `/api/v1/transactions` önekiyle erişilir. Tüm başarılı ve hatalı cevaplar standart `success/data/error` envelope kullanır ve `X-Request-ID` korunur.

## State machine

```text
YENI -> ATANDI -> INCELENIYOR -> MUSTERI_DOGRULAMA
                         ^                 |
                         +-----------------+

INCELENIYOR -> ONAYLANDI -> KAPANDI
INCELENIYOR -> BLOKLANDI -> KAPANDI
```

Her geçiş `case_history` tablosuna append edilir. Kural dışı geçişler `422 INVALID_CASE_TRANSITION` döner. `BLOKLANDI` kararında açıklama zorunludur.

## AI çağrısı ve fallback

İşlem oluşturulurken `POST {AI_SERVICE_URL}/api/v1/ai/score-and-assign` senkron çağrılır. `X-Request-ID` ve `X-Internal-Service-Key` iletilir; timeout 3 saniyedir.

AI timeout, bağlantı hatası, HTTP hatası veya geçersiz payload üretirse işlem yine `201` ile kaydedilir:

- `ai_status=UNAVAILABLE`
- `risk_score=null`
- `risk_level=BELIRSIZ`
- `decision=INCELEME`
- atanmamış `YENI` manuel vaka
- response içinde `ai_fallback=true`

AI üretim kodunda mock skor bulunmaz; testler dependency override/fake client kullanır.

## SLA

| Risk | Süre |
|---|---:|
| `KRITIK` | 15 dakika |
| `YUKSEK` | 1 saat |
| `ORTA` | 4 saat |
| `DUSUK` | 24 saat |
| `BELIRSIZ` | 1 saat manuel inceleme |

`sla_due_at` DB’de tutulur. `sla_remaining_seconds` ve `sla_exceeded` response sırasında hesaplanır; background scheduler yoktur.

## JWT ve roller

Identity tarafından imzalanan yalnızca `type=access` JWT kabul edilir. HS256 algoritması sabittir; issuer ve audience doğrulanır. CUSTOMER kimliği body’den alınmaz, doğrulanmış JWT `user_id` claiminden türetilir.

ADMIN bu aşamada yalnızca işlem/vaka görüntüler; atama veya karar veremez.

## Environment variables

| Variable | Açıklama |
|---|---|
| `DATABASE_URL` | Transaction PostgreSQL URL |
| `JWT_SECRET` | Identity ile ortak, en az 32 karakter secret |
| `JWT_ALGORITHM` | `HS256` |
| `JWT_ISSUER` | `fraudcell-identity` |
| `JWT_AUDIENCE` | `fraudcell-platform` |
| `AI_SERVICE_URL` | `/api/v1/ai` yolunu sunan Kong iç URL’si |
| `INTERNAL_SERVICE_KEY` | Servisler arası kimlik doğrulama anahtarı |
| `AI_TIMEOUT_SECONDS` | Varsayılan `3` |
| `RABBITMQ_URL` | RabbitMQ bağlantısı; secret repository dışında tutulur |
| `EVENT_EXCHANGE` | Durable topic exchange, varsayılan `fraudcell.events` |
| `OUTBOX_POLL_INTERVAL_SECONDS` | Pending outbox tarama aralığı, varsayılan `1` |

Gerçek secret değerleri repository’ye yazılmamalıdır.

## Migration ve test

```bash
alembic upgrade head
alembic downgrade base
pytest tests/ -q
```

Compose, `transaction-migrate` tamamlanmadan `transaction-service` başlatmaz. Uygulama `create_all` çağırmaz.

## Transactional outbox

`ONAYLANDI` veya `BLOKLANDI` kararı, `CaseHistory` ve `case.decision_made` outbox kaydı tek PostgreSQL transactionında commit edilir. HTTP response brokerı beklemeden `event_delivery=PENDING` ve benzersiz `event_id` döner. RabbitMQ erişilemezse karar kaybolmaz; outbox kaydı pending kalır.

`python -m app.workers.outbox_publisher` workerı pending kayıtları `fraudcell.events` durable topic exchange'ine persistent mesaj ve publisher confirm ile yollar. Başarıdan sonra `published_at` set edilir; hatada yalnızca güvenli hata türü ve deneme sayısı saklanır, exponential backoff ile yeniden bağlanır. Compose servis adı `transaction-outbox-worker`dır.

Customer feedback yalnızca `KAPANDI` vakada, işlem sahibi tarafından ve vaka başına
bir kez gönderilebilir. Feedback kaydı ile `feedback.submitted` outbox olayı aynı DB
transactionında oluşur; Gamification'a doğrudan HTTP çağrısı yapılmaz. Olay bu MVP'de
puan üretmez.

`python -m app.cli.reset_demo_data` yalnızca `DEMO_CUSTOMER_ID` sahibinin
transaction, case, history, feedback ve ilgili outbox kayıtlarını siler. Alembic veya
demo dışı verilere dokunmaz ve tekrar çalıştırılması güvenlidir.

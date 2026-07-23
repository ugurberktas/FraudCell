# Transaction Service

Transaction Service Customer işlemlerini, AI skor çağrısını, fraud vaka state
machine'ini ve RabbitMQ transactional outbox'ını yönetir. Kong dış öneki
`/api/v1/transactions` şeklindedir.

## Endpointler

| Method | İç path | Erişim | Açıklama |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness |
| `GET` | `/ready` | Public | Transaction PostgreSQL readiness |
| `POST` | `/transactions` | CUSTOMER | İşlem oluşturur ve AI skor/atama ister |
| `GET` | `/transactions/me` | CUSTOMER | Kendi işlemlerini en yeni önce listeler |
| `GET` | `/transactions/{id}` | Sahip Customer, atanmış Analyst, Supervisor, Admin | IDOR korumalı detay |
| `GET` | `/cases/assigned-to-me` | ANALYST | Kendi atanmış vakaları |
| `GET` | `/cases` | SUPERVISOR, ADMIN | Tüm vakalar; opsiyonel `status` filtresi |
| `POST` | `/cases/{id}/assign` | SUPERVISOR | `YENI` vakayı Analyst UUID'sine atar |
| `POST` | `/cases/{id}/start` | Atanmış ANALYST | İncelemeyi başlatır |
| `POST` | `/cases/{id}/request-verification` | Atanmış ANALYST | Customer doğrulaması ister |
| `POST` | `/cases/{id}/customer-response` | İşlem sahibi CUSTOMER | `BEN_YAPTIM` / `BEN_YAPMADIM` |
| `POST` | `/cases/{id}/decision` | Atanmış ANALYST | `ONAYLANDI` / `BLOKLANDI` |
| `POST` | `/cases/{id}/close` | SUPERVISOR | Karar verilmiş vakayı kapatır |
| `POST` | `/cases/{id}/feedback` | İşlem sahibi CUSTOMER | Kapalı vakaya bir kez 1–5 rating |

Örneğin create endpointinin dış adresi
`POST /api/v1/transactions/transactions` olur. Başarı ve hata cevapları
`success/data/error` envelope kullanır; `X-Request-ID` korunur.

## İşlem bütünlüğü ve yetkilendirme

`TransactionCreate` extra alanları reddeder. `customer_id` body'de kabul edilmez;
doğrulanmış access JWT'deki `user_id` kullanılır. `amount`, Pydantic `Decimal` olarak
doğrulanır ve PostgreSQL `NUMERIC(18,2)` alanında tutulur. `risk_score` da
`NUMERIC(6,5)` olarak saklanır.

Okunabilir ve unique işlem numarası yıllık atomik sayaçla üretilir:
`TRX-YYYY-000001`. Customer yalnızca kendi işlemini/vakasını, Analyst yalnızca
kendisine atanmış vakayı yönetebilir. Supervisor manuel atama ve kapanış yapabilir;
Admin yalnızca vaka/işlem görüntüleyebilir.

## AI çağrısı ve case oluşturma

Create sırasında servis aşağıdaki çağrıyı üç saniye timeout ile yapar:

```text
POST {AI_SERVICE_URL}/api/v1/ai/score-and-assign
X-Request-ID: <request id>
X-Internal-Service-Key: <internal key>
```

Frontend risk skoru, fraud türü, karar veya Analyst kimliği gönderemez. AI sonucu
doğrulanmış response şemasından gelir. Skor, fraud türü, karar, risk, model sürümü ve
`risk_reasons` Transaction kaydında saklanır; vaka listeleri de bunları taşır.
`decision != ONAY` veya risk `DUSUK` değilse RiskCase oluşur. AI Analyst döndürmüşse
vaka aynı DB commitinde `YENI -> ATANDI` geçişini ve iki history satırını alır.

Golden quick-fill (`48500`, `TRANSFER`, `Demo Alıcı`, `Yeni iPhone`, Berlin,
01:30Z, yeni cihaz, frekans 20) checked-in artifact ile `0.840797 / YUKSEK /
HESAP_ELE_GECIRME / INCELEME` üretir ve temiz seed sonrasında Hesap Analisti'ne
atanır.

## AI fallback

AI timeout, bağlantı/HTTP hatası veya geçersiz response üretirse create yine HTTP
`201` ile commit edilir:

- `ai_status=UNAVAILABLE`
- `risk_score=null`
- `fraud_type=TEMIZ`
- `risk_level=BELIRSIZ`
- `decision=INCELEME`
- `model_version=null`
- atanmamış `YENI` manuel RiskCase
- response içinde `ai_fallback=true`

Transaction ve diğer servisler AI kesintisinde çalışmaya devam eder. AI yeniden
healthy olduğunda sonraki işlemler tekrar gerçek artifact ile skorlanır.

## Vaka state machine

```text
YENI -> ATANDI -> INCELENIYOR -> MUSTERI_DOGRULAMA
                         ^                 |
                         +-----------------+

INCELENIYOR -> ONAYLANDI -> KAPANDI
INCELENIYOR -> BLOKLANDI -> KAPANDI
```

Her geçiş append-only `case_history` satırı üretir. Kural dışı geçiş
`422 INVALID_CASE_TRANSITION` döner. `BLOKLANDI` için boş olmayan, en fazla 4.000
karakterlik karar notu zorunludur. Customer response yalnızca
`MUSTERI_DOGRULAMA -> INCELENIYOR` geçişinde kabul edilir.

## SLA

| Risk | Süre |
|---|---:|
| `KRITIK` | 15 dakika |
| `YUKSEK` | 1 saat |
| `ORTA` | 4 saat |
| `DUSUK` | 24 saat |
| `BELIRSIZ` | 1 saat |

`sla_due_at` DB'de tutulur. `sla_remaining_seconds` ve `sla_exceeded` response
üretilirken hesaplanır; ayrıca çalışan bir SLA scheduler/event publisher yoktur.

## Transactional outbox

Analyst kararı, Transaction güncellemesi, `CaseHistory` ve `case.decision_made`
outbox satırı tek PostgreSQL transactionında commit edilir. Feedback kaydı ve
`feedback.submitted` outbox satırı da aynı ilkeyi kullanır. API RabbitMQ sonucunu
beklemeden `event_delivery=PENDING` ve unique `event_id` döner.

`transaction-outbox-worker`, pending satırları `fraudcell.events` durable topic
exchange'ine persistent mesaj ve publisher confirm ile yollar. Confirm sonrasında
`published_at` set edilir. RabbitMQ kapalıysa karar kaybolmaz; outbox pending kalır ve
worker exponential backoff ile yeniden bağlanır. Transaction Service Gamification'a
doğrudan HTTP çağrısı yapmaz.

Uygulanan event ayrıntıları için root [EVENTS.md](../../EVENTS.md) dosyasına bakın.

## Ayarlar

| Değişken | Açıklama |
|---|---|
| `DATABASE_URL` | Transaction PostgreSQL URL |
| `JWT_SECRET` | Identity ile ortak access-token secret'ı |
| `JWT_ALGORITHM` | `HS256` |
| `JWT_ISSUER` / `JWT_AUDIENCE` | Identity claim doğrulaması |
| `AI_SERVICE_URL` | Kong iç adresi |
| `INTERNAL_SERVICE_KEY` | Transaction/AI kimlik doğrulama anahtarı |
| `AI_TIMEOUT_SECONDS` | Varsayılan `3` |
| `RABBITMQ_URL` | Broker bağlantısı |
| `EVENT_EXCHANGE` | Varsayılan `fraudcell.events` |
| `OUTBOX_POLL_INTERVAL_SECONDS` | Varsayılan `1` saniye |

## Demo reset, migration ve test

```bash
python -m app.cli.reset_demo_data
alembic upgrade head
alembic downgrade base
pytest tests -q
```

Reset komutu `DEMO_CUSTOMER_ID` sahibinin transaction, case, history, feedback ve
ilgili outbox satırlarını siler; demo dışı verilere veya migrationlara dokunmaz.
Compose, `transaction-migrate` bitmeden API/workerı başlatmaz.

## Mevcut teknik borç

SLA aşımları ayrıca event olarak yayınlanmaz ve AI Analyst kapasitesi vaka kapanınca
otomatik azaltılmaz. Manuel Supervisor ataması da AI kapasite profiliyle çift yönlü
senkronize edilmez.

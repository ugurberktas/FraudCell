# Gamification Service

Gamification Service gerçek `case.decision_made` eventlerinden Analyst ledger,
profil, seviye, `ILK_YAKALAMA` rozeti ve leaderboard üretir. Sahte puan veya
leaderboard verisi kullanmaz. Kong dış öneki `/api/v1/game` şeklindedir.

## RabbitMQ consumer

| Ayar | Değer |
|---|---|
| Exchange | `fraudcell.events` durable topic |
| Queue | `gamification.case-decisions.v1` durable |
| Binding | `case.decision_made`, `feedback.submitted` |
| Worker | `python -m app.workers.event_consumer` |
| Prefetch | varsayılan `10` |

Consumer event envelope ve payloadını strict şemayla doğrular. DB commitinden sonra
ACK verir; geçici hatada NACK/requeue, geçersiz eventte reject/no-requeue uygular.
RabbitMQ bağlantısını exponential backoff ile yeniden kurar.

`processed_events.event_id` unique idempotency anahtarıdır. Duplicate teslim ikinci
ledger satırı, profil artışı, resolved case veya rozet üretmeden ACK edilir.
`score_ledger` ayrıca `(event_id, reason)` unique constraint taşır.

`feedback.submitted` doğrulanıp `ProcessedEvent` olarak kaydedilir; mevcut MVP'de
puan veya rozet üretmez. Çalışan event sözleşmeleri için root
[EVENTS.md](../../EVENTS.md) dosyasına bakın.

## Puan kuralları

| Koşul | Puan | Ledger reason |
|---|---:|---|
| `ONAYLANDI` veya `BLOKLANDI` | `+10` | `CASE_RESOLVED` |
| `resolution_seconds < 900` | `+5` | `FAST_DECISION` |
| `BLOKLANDI + BEN_YAPMADIM` | `+15` | `CONFIRMED_FRAUD` |
| `KRITIK` ve SLA içinde | `+15` | `CRITICAL_WITHIN_SLA` |
| SLA aşımı | `-5` | `SLA_EXCEEDED` |
| `is_false_positive=true` | `-8` | `FALSE_POSITIVE` |

Kurallar bağımsız toplanır. Golden quick-fill mevcut artifactte `YUKSEK` olduğu için
hızlı ve Customer tarafından reddedilmiş blok kararı `+30` üretir. `+45` ancak aynı
koşullara ek olarak risk `KRITIK` ve karar SLA içindeyse oluşur.

Seviyeler:

| Toplam puan | Seviye |
|---:|---|
| `< 500` | `BRONZ` |
| `500–1499` | `GUMUS` |
| `1500–2999` | `ALTIN` |
| `>= 3000` | `PLATIN` |

Aktif tek rozet `ILK_YAKALAMA`dır. Analyst'in ilk
`BLOKLANDI + BEN_YAPMADIM` vakasında unique `(analyst_id, badge_code)` kontrolüyle
bir kez yazılır. Badge şu an RabbitMQ event'i olarak yayınlanmaz.

## API

Identity access JWT'si HS256 imzası, issuer, audience ve `type=access` ile doğrulanır.

| Method | Path | Erişim |
|---|---|---|
| `GET` | `/health` | Public |
| `GET` | `/ready` | Public |
| `GET` | `/leaderboard?period=daily|weekly&limit=10` | ANALYST, SUPERVISOR, ADMIN |
| `GET` | `/profiles/me` | ANALYST |
| `GET` | `/profiles/{analyst_id}` | Kendi profili Analyst; tüm profiller Supervisor/Admin |

Leaderboard günlük periyot için UTC gün başlangıcını, haftalık periyot için UTC
pazartesi başlangıcını kullanır. Sıralama `period_points`, sonra `total_points`, sonra
`analyst_id` ile deterministiktir. Profile response toplam puan, seviye, rozetler,
resolved case, günlük/haftalık sıra ve son ledger hareketlerini döner.

## Worker/RabbitMQ recovery

Gamification worker kapalıyken Transaction kararı ve RabbitMQ mesajı kaybolmaz;
durable queue mesajı saklar. Worker tekrar başladığında işler. RabbitMQ kapalıyken
Transaction outbox satırı `PENDING` kalır; broker ve outbox worker bağlantısı geri
geldiğinde event yayınlanır. At-least-once tekrarları idempotency kontrolü nedeniyle
puanı yalnızca bir kez etkiler.

## Demo seed/reset

```bash
python -m app.cli.seed_demo_profiles
python -m app.cli.seed_demo_profiles --check
python -m app.cli.reset_demo_profiles
```

Seed, gerçek Identity Analyst UUID'leriyle sıfır puanlı `BRONZ` profiller oluşturur.
Reset yalnızca üç demo Analyst'in ledger/rozetlerini ve verilen demo eventlerin
`ProcessedEvent` kayıtlarını temizleyip profilleri sıfırlar.

## Ayarlar, migration ve test

Gerekli ayarlar `DATABASE_URL`, `RABBITMQ_URL`, `EVENT_EXCHANGE`,
`CASE_DECISION_QUEUE`, `CONSUMER_PREFETCH`, `JWT_SECRET`, `JWT_ALGORITHM`,
`JWT_ISSUER` ve `JWT_AUDIENCE` değerleridir.

```bash
alembic upgrade head
alembic downgrade base
python -m app.workers.event_consumer
pytest tests -q
```

Compose, `gamification-migrate` tamamlanmadan API ve workerı başlatmaz.

## Sınırlar

Yalnızca `ILK_YAKALAMA` rozeti uygulanmıştır. Yanlış pozitif bilgisi mevcut
Transaction producer tarafından her zaman `false` gönderildiği için ceza kuralı
şemada/consumerda vardır fakat Golden akışta tetiklenmez. Badge notification frontend
polling ile profil farkından üretilir; WebSocket yoktur.

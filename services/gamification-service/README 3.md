# gamification-service

FraudCell analist puanlarını gerçek `case.decision_made` olaylarından üreten minimal Gamification servisidir. Sahte leaderboard verisi üretmez.

## Event akışı

- Exchange: `fraudcell.events` (durable topic)
- Queue: `gamification.case-decisions.v1` (durable)
- Binding/routing key: `case.decision_made`, `feedback.submitted`
- Worker: `python -m app.workers.event_consumer`
- Prefetch: varsayılan `10`

Consumer DB commit tamamlanmadan ACK vermez. Geçici DB hatasında NACK/requeue, geçersiz payload'da reject/no-requeue uygular ve RabbitMQ bağlantısını backoff ile yeniden kurar. `processed_events.event_id` unique idempotency anahtarıdır; duplicate delivery yeni ledger, puan veya rozet üretmeden ACK edilir.

`feedback.submitted` aynı consumer tarafından şema doğrulaması ve `ProcessedEvent`
idempotency kaydıyla kabul edilir; Golden Demo MVP'sinde puan veya rozet üretmez.

## Puanlar ve seviye

| Kural | Puan | Ledger reason |
|---|---:|---|
| ONAYLANDI/BLOKLANDI vaka | +10 | `CASE_RESOLVED` |
| 900 saniyeden hızlı karar | +5 | `FAST_DECISION` |
| BLOKLANDI + BEN_YAPMADIM | +15 | `CONFIRMED_FRAUD` |
| KRITIK ve SLA içinde | +15 | `CRITICAL_WITHIN_SLA` |
| SLA aşımı | -5 | `SLA_EXCEEDED` |
| Yanlış blok | -8 | `FALSE_POSITIVE` |

Kurallar bağımsızdır. Örnek hızlı, kritik ve doğrulanmış blok vakası `+45` üretir. Seviyeler: `BRONZ` 0–499 (negatifler dahil), `GUMUS` 500–1499, `ALTIN` 1500–2999, `PLATIN` 3000+.

Aktif tek MVP rozeti `ILK_YAKALAMA`dır: analistin ilk `BLOKLANDI + BEN_YAPMADIM` vakasında bir kez verilir. Diğer rozetler henüz uygulanmamıştır.

## API

Kong dış öneki `/api/v1/game`dir. Identity access JWT'si HS256, issuer ve audience ile doğrulanır.

| Method | Path | Roller |
|---|---|---|
| `GET` | `/health`, `/ready` | Public |
| `GET` | `/leaderboard?period=daily|weekly&limit=10` | ANALYST, SUPERVISOR, ADMIN |
| `GET` | `/profiles/me` | ANALYST |
| `GET` | `/profiles/{analyst_id}` | Kendi profili ANALYST; tümü SUPERVISOR, ADMIN |

Leaderboard UTC gün başlangıcı veya pazartesi hafta başlangıcından itibaren ledger toplamını kullanır; `period_points`, sonra `total_points`, sonra `analyst_id` ile deterministik sıralanır.

## Environment ve çalıştırma

Gerekli ayarlar: `DATABASE_URL`, `RABBITMQ_URL`, `EVENT_EXCHANGE`, `CASE_DECISION_QUEUE`, `CONSUMER_PREFETCH`, `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_ISSUER`, `JWT_AUDIENCE`. Gerçek secret commit edilmez.

```bash
alembic upgrade head
python -m app.workers.event_consumer
pytest tests/ -q
```

Compose'ta `gamification-migrate` başarıyla bitmeden API ve worker başlamaz. Recovery sırasında durable queue bekleyen mesajları worker yeniden başlayınca işler; duplicate delivery idempotenttir.

Demo profilleri gerçek Identity analyst UUID'leriyle
`python -m app.cli.seed_demo_profiles` komutundan oluşturulur; başlangıç puanı 0,
seviye BRONZ ve rozet listesi boştur. `--check` doğrulama yapar.
`python -m app.cli.reset_demo_profiles` yalnızca verilen demo analyst ledger/rozet ve
ilgili processed event kayıtlarını temizleyip profilleri sıfırlar.

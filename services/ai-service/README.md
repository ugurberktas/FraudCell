# ai-service

FraudCell Golden Demo için deterministik sentetik veriyle eğitilmiş küçük risk modeli ve kapasite kontrollü analist atama servisidir. Model sabit skor üretmez; scikit-learn olasılıkları farklı girdilerde değişir.

## Endpointler

| Method | Path | Güvenlik | Açıklama |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness |
| `GET` | `/ready` | Public | PostgreSQL readiness |
| `POST` | `/score-and-assign` | `X-Internal-Service-Key` | Risk skoru ve analist ataması |
| `POST` | `/internal/analysts/sync` | `X-Internal-Service-Key` | AnalystProfile idempotent upsert |

Kong dış yolu `POST /api/v1/ai/score-and-assign` biçimindedir. Internal key yoksa `401`, yanlışsa `403` döner.

## Model ve veri

- Model: `DictVectorizer + RandomForestClassifier`
- Model version: `fraudcell-demo-v1`
- Random seed: `20260723`
- Dataset: 2.400 sentetik, gürültülü ve örtüşen örnek
- Split: 1.800 train / 600 test
- Hedefler: `TEMIZ`, `CALINTI_KART`, `HESAP_ELE_GECIRME`, `PARA_AKLAMA`, `SUPHELI_DAVRANIS`

Özellikler tutar, işlem tipi, saat/gece sinyali, 24 saatlik frekans, yeni cihaz, ev şehri uyuşmazlığı, şehir, cihaz ailesi ve recipient uzunluğudur. Tek bir özellik etiketi tamamen belirlemez; veri üretimi label flip ve sınıf gürültüsü içerir.

Artifactler:

- `artifacts/fraud_model.joblib`
- `artifacts/model_metadata.json`
- `artifacts/training_metrics.json`
- `artifacts/feature_schema.json`
- `data/synthetic_fraud_transactions.csv`

Artifact bulunamaz veya yüklenemezse uygulama güvenli biçimde başlamaz; mock skora düşmez.

## Risk ve karar eşikleri

| Risk skoru | Karar | Risk seviyesi |
|---:|---|---|
| `< 0.40` | `ONAY` | `DUSUK` |
| `0.40–<0.70` | `INCELEME` | `ORTA` |
| `0.70–0.90` | `INCELEME` | `YUKSEK` |
| `> 0.90` | `BLOK` | `KRITIK` |

Risk skoru `1 - P(TEMIZ)` olarak model olasılığından hesaplanır. `risk_reasons`, model açıklaması değildir; yüksek tutar, gece, alışılmadık şehir, yeni cihaz ve yüksek frekans gibi gözlenen giriş sinyallerini listeler.

## Analist atama

```text
assignment_score = specialization_match * 0.50
                 + availability_ratio * 0.30
                 + accuracy_rate * 0.20

availability_ratio = 1 - active_cases / max_active_cases
```

Pasif veya kapasitesi dolu analistler elenir. Eşit skorda önce düşük `active_cases`, sonra UUID sırası kazanır. Atama kapasitesi koşullu atomik update ile artırılır ve aday satırları PostgreSQL `FOR UPDATE` ile kilitlenir. Kapasite yoksa `QUEUED` döner. `ONAY` işlemleri analist kapasitesi tüketmez.

## Eğitim

Eğitim Docker build sırasında çalışmaz. Artifactleri deterministik olarak yeniden üretmek için:

```bash
python -m app.ml.train
```

Komut dataset ve dört artifacti yeniden yazar, accuracy, macro F1, fraud recall, confusion matrix ve satır sayılarını ekrana basar.

## Demo analyst seed

Gerçek Identity ANALYST UUID’lerini environment ile verin:

```bash
DEMO_CARD_ANALYST_ID=<uuid> \
DEMO_ACCOUNT_ANALYST_ID=<uuid> \
DEMO_LAUNDERING_ANALYST_ID=<uuid> \
python scripts/seed_demo_analysts.py
```

Aynı değerlerle tekrar çalıştırmak duplicate üretmez. Eşdeğer CLI seçenekleri `--card-analyst-id`, `--account-analyst-id` ve `--laundering-analyst-id` şeklindedir.

## Environment

| Variable | Açıklama |
|---|---|
| `DATABASE_URL` | AI PostgreSQL bağlantısı |
| `INTERNAL_SERVICE_KEY` | Transaction/AI ortak internal key |
| `MODEL_ARTIFACT_PATH` | Joblib model yolu |
| `MODEL_METADATA_PATH` | Model metadata yolu |

## Migration ve test

```bash
alembic upgrade head
alembic downgrade base
pytest tests/ -q
```

Compose `ai-migrate` başarıyla tamamlanmadan AI Service’i başlatmaz. Production kodu `create_all` kullanmaz.

## Sınırlamalar

Bu model yalnızca Golden Demo için sentetik veriye dayanır; gerçek finansal karar sistemi değildir. Drift izleme, calibration, fairness analizi, gerçek zamanlı feature store ve karar sonrası analist kapasitesi azaltımı bu kapsamda yoktur.

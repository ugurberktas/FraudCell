# AI Service

AI Service, checked-in scikit-learn artifactiyle deterministik risk inference ve
kapasite kontrollü Analyst ataması yapar. Sabit veya random mock skor üretmez. Kong
dış öneki `/api/v1/ai` şeklindedir.

## Endpointler

| Method | İç path | Güvenlik | Açıklama |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness |
| `GET` | `/ready` | Public | AI PostgreSQL readiness |
| `POST` | `/score-and-assign` | `X-Internal-Service-Key` | Model skoru ve kapasite rezervasyonu |
| `POST` | `/internal/analysts/sync` | `X-Internal-Service-Key` | AnalystProfile idempotent upsert |

Kong dış score adresi `POST /api/v1/ai/score-and-assign` olur. Internal key yoksa
`401`, yanlışsa `403` döner. Başarılı/hatalı response'lar `success/data/error`
envelope kullanır ve `X-Request-ID` korunur.

## Model ve veri

| Özellik | Değer |
|---|---|
| Pipeline | `DictVectorizer + RandomForestClassifier` |
| Model version | `fraudcell-demo-v1` |
| Random seed | `20260723` |
| Veri | 2.400 deterministik sentetik satır |
| Split | 1.800 train / 600 test |
| Accuracy | `0.66` |
| Macro F1 | `0.331712` |
| Fraud recall | `0.483871` |

Hedefler `TEMIZ`, `CALINTI_KART`, `HESAP_ELE_GECIRME`, `PARA_AKLAMA` ve
`SUPHELI_DAVRANIS` sınıflarıdır. Özellikler tutar, işlem türü, saat/gece,
24 saatlik frekans, yeni cihaz, şehir uyuşmazlığı, şehir, cihaz ailesi ve alıcı
uzunluğudur. Dataset sentetiktir; gerçek banka verisi içermez.

Artifactler:

- `artifacts/fraud_model.joblib`
- `artifacts/model_metadata.json`
- `artifacts/training_metrics.json`
- `artifacts/feature_schema.json`
- `data/synthetic_fraud_transactions.csv`

Model modülü import edilirken artifact yüklenir. Dosya eksik/bozuksa servis başlamaz;
mock skora düşmez.

## Skor, karar ve açıklama

```text
risk_score = 1 - P(TEMIZ)
```

| Skor | Karar | Risk |
|---:|---|---|
| `< 0.40` | `ONAY` | `DUSUK` |
| `0.40–<0.70` | `INCELEME` | `ORTA` |
| `0.70–0.90` | `INCELEME` | `YUKSEK` |
| `> 0.90` | `BLOK` | `KRITIK` |

Response `risk_score`, `risk_level`, `fraud_type`, `decision`, `risk_reasons`,
`model_version`, `assigned_analyst_id`, `assignment_status` ve `assignment_score`
alanlarını döner. `risk_reasons` SHAP açıklaması değildir; girdide gözlenen yüksek
tutar, gece, alışılmadık şehir, yeni cihaz ve yüksek frekans kurallarının listesidir.

Checked-in artifact için üç örnek:

| Senaryo | Skor | Fraud türü | Karar / risk |
|---|---:|---|---|
| Normal `250` TL fatura | `0.396577` | `TEMIZ` | `ONAY / DUSUK` |
| `15000` TL, yeni cihaz, Berlin | `0.691419` | `HESAP_ELE_GECIRME` | `INCELEME / ORTA` |
| Golden `48500` TL gece transferi | `0.840797` | `HESAP_ELE_GECIRME` | `INCELEME / YUKSEK` |

Tam girdiler ve veri sınırlamaları için [AI yaklaşımı](../../docs/AI_APPROACH.md)
dokümanına bakın.

## Analyst atama

```text
assignment_score = specialization_match * 0.50
                 + availability_ratio * 0.30
                 + accuracy_rate * 0.20

availability_ratio = 1 - active_cases / max_active_cases
```

Pasif veya kapasitesi dolu Analyst elenir. Sıralama eşitliğinde önce düşük
`active_cases`, sonra UUID kullanılır. PostgreSQL `FOR UPDATE` ve koşullu atomik
update kapasiteyi rezerve eder. Uygun profil yoksa `QUEUED` döner. `ONAY` işlemi
Analyst kapasitesi tüketmez.

Golden fraud türü `HESAP_ELE_GECIRME` olduğu için temiz seed'de Hesap Analisti
atanır. `regions` profil alanında bulunur ancak mevcut ranking formülüne katılmaz.

## Demo seed/reset

Gerçek Identity ANALYST UUID'leriyle:

```bash
python -m app.cli.seed_demo_analysts
python -m app.cli.seed_demo_analysts --check
python -m app.cli.reset_demo_analysts
```

Gerekli ID değişkenleri `DEMO_CARD_ANALYST_ID`, `DEMO_ACCOUNT_ANALYST_ID` ve
`DEMO_AML_ANALYST_ID` şeklindedir. Root `scripts/demo_prepare.py` bunları Identity
seed sonucundan aktarır. Reset profilleri silmez; yalnızca üç demo profilinin
`active_cases` değerini sıfırlar.

## Ayarlar, eğitim ve test

| Değişken | Açıklama |
|---|---|
| `DATABASE_URL` | AI PostgreSQL URL |
| `INTERNAL_SERVICE_KEY` | Transaction ile ortak internal key |
| `MODEL_ARTIFACT_PATH` | Joblib artifact yolu |
| `MODEL_METADATA_PATH` | Metadata yolu |

```bash
python -m app.ml.train
alembic upgrade head
alembic downgrade base
pytest tests -q
```

Docker build modeli eğitmez; doğrulanmış artifacti image içine alır. Compose,
`ai-migrate` tamamlanmadan API'yi başlatmaz.

## Sınırlar

Model demo amaçlı sentetik veriye dayanır; calibration, gerçek fraud maliyet
optimizasyonu, drift/fairness takibi, registry ve online retraining yoktur. Identity
profil sync'i otomatik event değildir. Karar/kapanış sonrası `active_cases` otomatik
azaltılmaz.

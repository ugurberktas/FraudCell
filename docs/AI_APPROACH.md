# FraudCell AI Yaklaşımı

## Kapsam ve dürüst sınır

AI Service sabit/random mock cevap vermez. Repository'deki doğrulanmış
`fraud_model.joblib` artifactini yükler ve gelen işlem özelliklerinde gerçek
`predict_proba` inference çalıştırır. Aynı artifact ve aynı girdi aynı sonucu üretir.

Model gerçek banka müşterilerinden öğrenmemiştir. Golden Demo için sentetik veriyle
eğitilmiş açıklanabilir bir prototiptir; finansal karar veya production fraud modeli
olarak kullanılmamalıdır.

## Veri kaynağı

Repository'de uygun gerçek fraud datası olmadığı için `random_seed=20260723` ile
2.400 satır deterministik sentetik veri üretilmiştir:

`services/ai-service/data/synthetic_fraud_transactions.csv`

Veri üretiminde kullanılan sinyaller:

- tutar ve işlem türü;
- UTC saat ve gece göstergesi;
- son 24 saat işlem sıklığı;
- yeni cihaz;
- işlem şehri ile ev şehri uyuşmazlığı;
- şehir, cihaz ailesi ve alıcı metni uzunluğu.

Hedef kataloğu `TEMIZ`, `CALINTI_KART`, `HESAP_ELE_GECIRME`, `PARA_AKLAMA` ve
`SUPHELI_DAVRANIS` sınıflarıdır. Etiket üretimine gürültü ve label flip eklenmiştir;
tek bir özellik sonucu kesin olarak belirlemez.

## Model ve artifactler

Pipeline:

```text
DictVectorizer -> RandomForestClassifier
```

Random Forest 80 ağaçlı, derinliği sınırlı ve sabit seed'lidir. Stratified ayrım
1.800 train / 600 test satırıdır. Checked-in `fraudcell-demo-v1` metrikleri:

| Metrik | Değer |
|---|---:|
| Accuracy | `0.660000` |
| Macro F1 | `0.331712` |
| Fraud recall | `0.483871` |

Bu metrikler modelin demo ölçeğinde olduğunu, production doğruluğu iddiası
taşımadığını açıkça gösterir.

Artifact dosyaları:

- `artifacts/fraud_model.joblib`
- `artifacts/model_metadata.json`
- `artifacts/training_metrics.json`
- `artifacts/feature_schema.json`

Metadata dataset ve model SHA-256 değerlerini, model sürümünü, sınıf kataloğunu ve
seed'i içerir. Artifact yoksa veya güvenli biçimde yüklenemezse AI Service başlamayı
reddeder; mock skora düşmez.

## Risk skoru ve karar politikası

```text
risk_score = 1 - P(TEMIZ)
```

Skor `0..1` aralığına sınırlandırılır. İnceleme gereken işlemde `fraud_type`, temiz
olmayan sınıflar arasındaki en yüksek model olasılığıdır. Düşük risk onayında
`fraud_type=TEMIZ` döner.

| Risk skoru | `decision` | `risk_level` |
|---:|---|---|
| `< 0.40` | `ONAY` | `DUSUK` |
| `0.40–<0.70` | `INCELEME` | `ORTA` |
| `0.70–0.90` | `INCELEME` | `YUKSEK` |
| `> 0.90` | `BLOK` | `KRITIK` |

`risk_reasons` SHAP, feature importance veya nedensel açıklama değildir. Yalnızca
input üzerinde doğrudan gözlenen yüksek tutar, gece, şehir uyuşmazlığı, yeni cihaz
ve yüksek frekans koşullarını deterministik metinlerle listeler.

## Üç demo girdisinin artifact çıktısı

Aşağıdaki sonuçlar checked-in artifact üzerinde doğrudan inference ile alınmıştır:

| Senaryo | Özet girdi | Skor | Tür | Karar | Risk |
|---|---|---:|---|---|---|
| Normal fatura | `250`, FATURA, bilinen iPhone, Istanbul, 12:00Z, frekans 1 | `0.396577` | `TEMIZ` | `ONAY` | `DUSUK` |
| Yeni cihaz | `15000`, TRANSFER, yeni Android, Berlin, 16:00Z, frekans 4 | `0.691419` | `HESAP_ELE_GECIRME` | `INCELEME` | `ORTA` |
| Golden yüksek risk | `48500`, TRANSFER, Yeni iPhone, Berlin, 01:30Z, frekans 20 | `0.840797` | `HESAP_ELE_GECIRME` | `INCELEME` | `YUKSEK` |

Golden girdinin nedenleri: `Yüksek işlem tutarı`, `Gece saatinde işlem`,
`Alışılmadık şehir`, `Yeni cihaz`, `Yüksek işlem sıklığı`.

## Analyst atama

AI DB, gerçek Identity ANALYST UUID'leriyle hazırlanmış `AnalystProfile` satırlarını
kullanır. Atama formülü:

```text
specialization_match * 0.50
+ availability_ratio * 0.30
+ accuracy_rate * 0.20

availability_ratio = 1 - active_cases / max_active_cases
```

Pasif veya kapasitesi dolu profiller elenir. Tie-break önce daha düşük
`active_cases`, sonra Analyst UUID'sidir. PostgreSQL satır kilidi ve koşullu kapasite
artışı eşzamanlı rezervasyonda kapasite aşımını önler. Uygun kapasite yoksa
`assignment_status=QUEUED` ve `assigned_analyst_id=null` döner. `ONAY` işlemleri
kapasite tüketmez.

Golden girdi `HESAP_ELE_GECIRME` ürettiği için temiz reset sonrasında
`demo.analyst.account@fraudcell.com` uzmanlık eşleşmesiyle seçilir. Profilde region
verisi saklanır ancak mevcut atama formülü region kullanmaz.

## Eğitimi yeniden üretme

```bash
cd services/ai-service
python -m app.ml.train
```

Docker build modeli yeniden eğitmez; image içine checked-in artifactleri alır.

## Mevcut teknik borçlar

- Gerçek finansal veri, calibration ve maliyet-duyarlı threshold doğrulaması yoktur.
- Drift/fairness izleme, feature store, model registry ve online retraining yoktur.
- Identity Analyst profilleri event ile senkronize edilmez; demo seed/internal sync
  kullanılır.
- Karar/kapanış sonrası AI `active_cases` otomatik azaltılmaz; uzun çalışmada yeniden
  atama kapasitesi yanlış görünebilir.
- Region bilgisi atama skoruna dahil değildir.
- Model metrikleri production kabul seviyesi için yeterli değildir.

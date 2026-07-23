# FraudCell Golden Demo AI Yaklaşımı

## Amaç

Bu bileşen production fraud platformu iddiası taşımaz. Amacı, FraudCell demo akışında sabit cevap vermeyen, tekrar üretilebilir, hızlı ve açıklanabilir giriş sinyallerine sahip gerçek bir scikit-learn modeli sunmaktır.

## Sentetik veri

Repository’de uygun hazır fraud datası bulunmadığı için `random_seed=20260723` ile 2.400 örnek üretilir. Dataset repository içinde `services/ai-service/data/synthetic_fraud_transactions.csv` olarak paylaşılır.

Veri üretimi şu sinyalleri birlikte kullanır:

- işlem tutarı ve işlem tipi;
- günün saati/gece işlemi;
- 24 saatlik işlem sıklığı;
- yeni cihaz;
- işlem şehri ile ev şehrinin uyuşmaması;
- cihaz ailesi ve recipient özellikleri.

Etiketler olasılıksal latent risk üzerinden üretilir. Bağımsız label flip ve fraud sınıf gürültüsü eklenir. Böylece yüksek tutar veya yeni cihaz gibi tek bir alan etiketi tamamen belirlemez; `TEMIZ` ile dört fraud sınıfı örtüşür.

## Model

`DictVectorizer`, kategorik özellikleri one-hot forma dönüştürür. Ardından 80 ağaçlı, derinliği sınırlandırılmış deterministik `RandomForestClassifier` çalışır. Eğitim/test ayrımı stratified ve sabit seed’lidir.

Risk skoru modelin temiz sınıf olasılığından türetilir:

```text
risk_score = 1 - P(TEMIZ)
```

İnceleme gereken bir işlemde fraud türü, temiz olmayan sınıfların en yüksek olasılıklısıdır. Düşük risk onaylarında fraud türü `TEMIZ` kalır.

Artifact metadata SHA-256 dataset ve model hashlerini, model sürümünü ve sınıf kataloğunu taşır. Eğitim metrikleri accuracy, macro F1, fraud recall, confusion matrix, train/test boyutları ve random seed içerir.

## Karar politikası

| Skor | Karar | Risk |
|---:|---|---|
| `<0.40` | ONAY | DUSUK |
| `0.40–<0.70` | INCELEME | ORTA |
| `0.70–0.90` | INCELEME | YUKSEK |
| `>0.90` | BLOK | KRITIK |

`risk_reasons` bir SHAP/feature-importance açıklaması değildir. Yalnızca input üzerinde doğrudan gözlenen yüksek tutar, gece, şehir uyuşmazlığı, yeni cihaz ve frekans sinyallerini güvenli ve deterministik metinlerle gösterir.

## Akıllı atama

Atama skoru:

```text
specialization_match * 0.50
+ availability_ratio * 0.30
+ accuracy_rate * 0.20
```

`availability_ratio = 1 - active_cases / max_active_cases` olarak hesaplanır. Pasif ve dolu profiller elenir. Tie-break sırası düşük aktif vaka, ardından analyst UUID’dir. PostgreSQL satır kilidi ve koşullu atomik kapasite artışı eşzamanlı atamalarda kapasite aşımını önler.

## Eğitim komutu

```bash
cd services/ai-service
python -m app.ml.train
```

Docker image build’i model eğitmez; doğrulanmış artifactleri image context içine alır. Artifact eksikse servis sabit/mock cevapla devam etmez ve güvenli biçimde başlamayı reddeder.

## Sınırlamalar

- Veri tamamen sentetiktir ve demo amaçlıdır.
- Olasılık calibration ve fraud maliyet optimizasyonu yapılmamıştır.
- Identity profilleri internal sync/seed ile kopyalanır; otomatik event sync yoktur.
- Karar/kapanış sonrası AI `active_cases` azaltımı henüz yoktur.
- Drift, fairness, feature store, model registry ve online retraining production aşamasına bırakılmıştır.

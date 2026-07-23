# FraudCell Jüri Soru-Cevap Notları

Yanıtları kısa tutun; ekranda veya testte kanıtlanmayan bir iddia eklemeyin.

## AI gerçekten model mi?

Evet. `DictVectorizer + RandomForestClassifier` pipeline'ı checked-in
`fraud_model.joblib` artifactinden yükleniyor ve `predict_proba` çalıştırıyor.
`risk_score = 1 - P(TEMIZ)`. Sabit veya random mock skor yok; artifact yüklenemezse
AI Service başlamıyor.

## Veri nereden geldi?

Gerçek müşteri verisi değil. `random_seed=20260723` ile üretilmiş 2.400 satırlık
sentetik demo datası. Etiket gürültüsü var; checked-in test metrikleri accuracy `0.66`,
macro F1 `0.331712`, fraud recall `0.483871`. Bunlar production model iddiası için
yeterli değil.

## Model neden bu işlemi riskli buldu?

Golden işlemde yüksek tutar, gece saati, ev şehrinden farklı şehir, yeni cihaz ve
yüksek 24 saatlik frekans sinyalleri var. Ekrandaki `risk_reasons` bu gözlenen
koşullardır; SHAP veya nedensel açıklama değildir.

## Neden mikroservis?

Demo, Identity, Transaction, AI ve Gamification sahipliğini/verisini ayırmak ve AI ya
da worker kesintisinin kalan platformdan izole edilebildiğini göstermek için bu yapıyı
kullanıyor. Küçük ekip/ürün için operasyon maliyeti yüksektir; daha erken aşamada
modüler monolith de makul olabilirdi.

## RabbitMQ neden kullanıldı?

Analyst kararının puanlama servisini senkron beklememesi ve Gamification worker
kesintisinde mesajın durable queue'da kalması için. AI skor çağrısı RabbitMQ değil,
senkron HTTP'dir. Runtime broker eventleri yalnızca `case.decision_made` ve
`feedback.submitted`dır.

## Transactional outbox neden var?

“Case DB'ye yazıldı ama event yayınlanamadı” ikili yazım boşluğunu kapatmak için.
Karar, history ve outbox satırı tek Transaction PostgreSQL transactionında commit
edilir. Ayrı worker daha sonra RabbitMQ'ya yayınlar.

## Duplicate event nasıl engellendi?

Teslim at-least-once'dır; duplicate'in gelmesi normal kabul edilir. Gamification DB'de
`processed_events.event_id` unique, ledgerda `(event_id, reason)` unique ve badge'de
`(analyst_id, badge_code)` unique constraint vardır. Duplicate delivery ikinci puan,
resolved case veya rozet üretmez.

## AI kapanırsa ne oluyor?

Transaction create yine HTTP 201 döner. `ai_status=UNAVAILABLE`, `risk_score=null`,
`risk_level=BELIRSIZ`, `decision=INCELEME` ve atanmamış `YENI` manuel RiskCase
oluşur. Identity ve Gamification çalışmaya devam eder. AI geri gelince yeni işlemler
artifact ile yeniden skorlanır.

## JWT rotation nasıl çalışıyor?

Access token 15 dakikalık HS256 JWT'dir. Refresh token opaque 256-bit değerdir ve
DB'de yalnızca SHA-256 hash'i tutulur. Her refresh eski tokenı rotated yapıp yeni
çift üretir. Rotated token tekrar kullanılırsa reuse tespit edilir ve kullanıcının
aktif refresh sessionları revoke edilir.

## Database-per-service nasıl korunuyor?

Her servisin ayrı PostgreSQL containerı, volume'u, credential seti ve private Compose
ağı var. DB portları hosta ve ortak platform ağına açılmıyor. Servisler başka servisin
DB'sine query atmıyor; senkron iletişim HTTP/Kong, asenkron karar akışı RabbitMQ ile.

## Analyst nasıl seçiliyor?

AI DB'deki gerçek Identity Analyst UUID'li profiller kullanılıyor. Uzmanlık eşleşmesi
%50, boş kapasite %30, accuracy rate %20. Pasif/dolu profil eleniyor; kapasite
PostgreSQL kilidi ve koşullu update ile rezerve ediliyor. Uygun profil yoksa
`QUEUED`. Region profil alanında var ama mevcut skora dahil değil.

## Neler gerçek?

Dört FastAPI servisi, dört PostgreSQL DB, Kong route'ları, JWT/RBAC/audit, model
artifact inference, Analyst atama, vaka state machine/history, transactional outbox,
RabbitMQ publish/consume, idempotent ScoreLedger, `ILK_YAKALAMA`, leaderboard ve
frontend API/polling akışları gerçek çalışan bileşenlerdir.

## Neler simülasyon?

OTP sabit demo kodudur; gerçek SMS yok. Eğitim datası sentetiktir. Quick-fill yalnızca
sabit demo girdisi hazırlar. Demo hesapları seed edilir. `BLOKLANDI` Transaction
DB'de karar/temporary flag yazar; gerçek bankacılık core'una para transferi bloklama
çağrısı yapmaz. Cloud/Kubernetes/WebSocket yoktur.

## Sistem production-ready mi?

Hayır. Bu, failure davranışı ve güvenlik kuralları test edilmiş bir Golden Demo
MVP'sidir. Production etiketi için gerçek veri/model validasyonu, SMS/MFA, TLS ve
secret manager, gözlemlenebilirlik, rate limiting, HA/backup/DR, yük/kaos testleri ve
operasyon süreçleri gerekir.

## Kalan teknik borçlar neler?

- AI `active_cases`, vaka kapanınca otomatik azaltılmıyor.
- Identity Analyst profil değişiklikleri AI'ya event ile otomatik sync edilmiyor.
- Region, Analyst ranking formülüne dahil değil.
- Model calibration, drift/fairness izleme ve gerçek fraud veri doğrulaması yok.
- SLA için background scheduler ve `sla.exceeded` runtime event'i yok.
- Shared event kataloğundaki sekiz isim şema rezervidir; runtime'da yalnızca iki event
  yayınlanır.
- Gerçek banka core'u, SMS, distributed tracing/metrics/alerting ve HA/DR yok.

## Golden vaka neden +30; dokümanda +45 örneği de var mı?

Golden artifact sonucu `YUKSEK`. Bu yüzden `+10` vaka, `+5` hızlı karar ve `+15`
doğrulanmış fraud, toplam `+30`. `+45` ancak risk gerçekten `KRITIK` ve SLA içindeyse
ek `+15` ile oluşur.

## `BLOKLANDI` kararını AI mı veriyor?

Golden model `INCELEME` öneriyor. Customer `BEN_YAPMADIM` dedikten sonra atanmış
Analyst zorunlu notla `BLOKLANDI` kararı veriyor. AI skoru ve insan vaka kararı ayrı
alanlar ve ayrı sorumluluklardır.

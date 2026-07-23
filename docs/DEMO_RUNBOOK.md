# FraudCell Golden Demo Runbook

Bu runbook temiz demo hazırlığını, canlı UI akışını ve kontrollü fault/recovery
adımlarını tarif eder. Komutlar repository kökünden çalıştırılır.

## 1. Ön koşullar ve secret güvenliği

```bash
cp .env.example .env
```

Root `.env` içinde gerçek yerel değerleri tanımlayın:

- `DEMO_ADMIN_PASSWORD`
- `DEMO_SUPERVISOR_PASSWORD`
- `DEMO_ANALYST_PASSWORD`
- `DEMO_CUSTOMER_GSM`
- `DEMO_OTP_CODE=1234`
- `INTERNAL_SERVICE_KEY`
- `JWT_SECRET`
- PostgreSQL ve RabbitMQ credential değerleri

`.env` Git'e eklenmemelidir. Parolaları, OTP'yi, JWT'leri veya internal key'i ekran
paylaşımında göstermeyin. `demo_prepare.py`, `demo_status.py` ve
`final_acceptance.py` eksik shell değişkenlerini root `.env` dosyasından okur; secret
değerlerini kendi başarı çıktılarında yazmaz.

## 2. Platformu başlat

```bash
docker compose config --quiet
docker compose up -d --build --wait
docker compose ps -a
```

Beklenen:

- dört API, dört PostgreSQL, Kong, RabbitMQ, Redis, frontend ve iki worker running/
  healthy;
- `identity-migrate`, `transaction-migrate`, `ai-migrate` ve
  `gamification-migrate` `Exited (0)`;
- hostta yalnızca frontend `3000`, Kong `8000` ve RabbitMQ management `15672`
  portları açık.

## 3. Temiz demo hazırla

Reset bilinçli confirmation olmadan çalışmaz:

```bash
python3 scripts/demo_reset.py --confirm RESET_DEMO
python3 scripts/demo_prepare.py
python3 scripts/demo_prepare.py
python3 scripts/demo_status.py
```

Beklenen:

- reset sonunda `DEMO RESET COMPLETE`;
- iki prepare çağrısı aynı hesap/profilleri duplicate üretmeden doğrular;
- status sonunda `DEMO READY`;
- Admin, Supervisor, üç Analyst ve Customer gerçek UUID'lerle bulunur;
- AI Analyst profilleri ve Gamification profilleri mevcuttur;
- demo Analyst puanları `0`, resolved case `0`, rozetler boştur;
- eski demo Customer işlem/vaka/outbox/feedback verisi yoktur;
- `transaction-outbox-worker` ve `gamification-worker` çalışır.

## 4. Otomatik final acceptance

Temiz hazırlıktan sonra:

```bash
python3 scripts/final_acceptance.py
```

Yalnızca tüm `[PASS]` satırları gerçek kontrollerden geçer ve son satır
`FRAUDCELL FINAL ACCEPTANCE PASSED` olursa kanıt başarılıdır. Script API/OpenAPI
operasyonları, DB, RabbitMQ, outbox, ProcessedEvent, ScoreLedger, badge, leaderboard
ve AI fallback/recovery kontrollerini yapar.

Acceptance demo verisini değiştirir. Jüri öncesinde temiz sahne için 3. bölümdeki
reset/prepare/prepare/status sırasını bir kez daha çalıştırın.

## 5. Demo hesapları

| Rol | Hesap |
|---|---|
| Customer | `.env` içindeki `DEMO_CUSTOMER_GSM`, OTP `1234` |
| Hesap Analisti | `demo.analyst.account@fraudcell.com` |
| Kart Analisti | `demo.analyst.card@fraudcell.com` |
| AML Analisti | `demo.analyst.aml@fraudcell.com` |
| Supervisor | `demo.supervisor@fraudcell.com` |
| Admin | `demo.admin@fraudcell.com` |

Üç Analyst aynı `DEMO_ANALYST_PASSWORD` değerini, Supervisor
`DEMO_SUPERVISOR_PASSWORD` değerini kullanır. Parolaları bu dokümana yazmayın.

Customer, Analyst ve Supervisor oturumlarının birbirini ezmemesi için üç ayrı browser
profili/private context kullanın. Golden input temiz reset sonrasında
`HESAP_ELE_GECIRME` ürettiği için atanacak hesap `demo.analyst.account@fraudcell.com`
olur. Canlı sonuç farklıysa vaka response'undaki `assigned_analyst_id` ile
`demo_prepare.py` çıktısındaki gerçek UUID'yi eşleştirin; tahminle başka hesaba
geçmeyin.

## 6. Customer: login ve yüksek riskli işlem

1. `http://localhost:3000/login` açın.
2. **Musteri** sekmesinde demo GSM'i girin, **OTP iste**'ye basın.
3. `1234` girip **Giris yap**'a basın.
4. `/customer` ekranında **Yüksek risk hızlı doldur**'a basın.
5. Formu ekranda doğrulayın:

| Alan | Değer |
|---|---|
| Tutar | `48500` |
| Tür | `TRANSFER` |
| Alıcı | `Demo Alıcı` |
| Cihaz | `Yeni iPhone` |
| Şehir | `Berlin` |
| UTC zaman | `2026-07-23T01:30:00.000Z` |
| Frekans / yeni cihaz / ev şehri | `20` / `true` / `Istanbul` |

6. **İşlemi gönder**'e basın.
7. HTTP create sonucu UI'da işlem numarası, AI durumu, skor, risk, fraud türü,
   karar, model sürümü ve risk nedenleriyle görünmelidir.

Checked-in artifact için beklenen inference:

```text
risk_score=0.840797
risk_level=YUKSEK
fraud_type=HESAP_ELE_GECIRME
decision=INCELEME
model_version=fraudcell-demo-v1
```

Nedenler: yüksek tutar, gece, şehir uyuşmazlığı, yeni cihaz ve yüksek frekans.
Vaka `ATANDI`, Analyst Hesap Analisti olmalıdır.

## 7. Analyst vaka akışı

1. Analyst browser contextinde `/login` > **Personel** seçin.
2. `demo.analyst.account@fraudcell.com` ve `DEMO_ANALYST_PASSWORD` ile giriş yapın.
3. `/analyst` ekranında `ATANDI` ve yüksek öncelikli vakayı bulun.
4. **Başlat**: durum `INCELENIYOR` olur.
5. **Müşteri doğrula**: durum `MUSTERI_DOGRULAMA` olur.

SLA sayacı, model/risk alanları, beş `risk_reasons` maddesi ve vaka geçmişi kalıcı
Transaction/vaka API verisinden gelmelidir. Karar butonuna henüz basmayın.

## 8. Customer doğrulaması

Customer contextine dönün. En geç beş saniyelik polling sonrasında
**Şüpheli işlem doğrulaması gerekiyor.** bannerı görünür.

İşlem numarası/tutar/şehir/zamanı gösterip **Bu işlemi ben yapmadım**'a basın.
Case `MUSTERI_DOGRULAMA -> INCELENIYOR` olur ve `customer_response=BEN_YAPMADIM`
kaydedilir.

## 9. Analyst kararı, puan ve rozet

Analyst contextine dönün:

1. Karar notuna örneğin “Müşteri işlemi reddetti; güvenlik için bloklandı.” yazın.
2. **Blokla**'ya basın.
3. Case `BLOKLANDI` olur; response `event_delivery=PENDING` ve event UUID döner.
4. Profil polling'i sonrasında toplam puan `30`, resolved case `1`, seviye `BRONZ`
   ve rozet `ILK_YAKALAMA` olmalıdır.

Golden risk `YUKSEK` olduğu için beklenen ledger:

```text
CASE_RESOLVED       +10
FAST_DECISION        +5
CONFIRMED_FRAUD     +15
Toplam              +30
```

Bu vaka `KRITIK` değildir; `CRITICAL_WITHIN_SLA +15` beklemeyin.

## 10. Leaderboard ve Supervisor

Analyst contextinde `/leaderboard` açın, **Gunluk** ve **Yenile**'ye basın. Hesap
Analisti satırı `period_points=30`, `total_points=30`, `BRONZ`, bir resolved case ve
`ILK_YAKALAMA` göstermelidir.

Supervisor contextinde `demo.supervisor@fraudcell.com` ile giriş yapın:

- aktif/kritik/SLA/bekleyen metriklerinin gerçek vaka listesinden hesaplandığını;
- risk, fraud türü ve vaka durumu dağılımlarını;
- `BLOKLANDI` Golden vakayı ve atanmış Analyst UUID'sini gösterin.

İsterseniz **Vakayı kapat** ile `KAPANDI` yapın. Ardından Customer kapalı vaka için
1–5 yıldız **Geri bildirim gönder** kullanabilir. Feedback event'i idempotent işlenir
ancak puan üretmez.

## 11. Canlı AI fallback ve recovery

Terminalde:

```bash
docker compose stop ai-service
```

Customer ekranında **Normal işlem** ve ardından **İşlemi gönder**'e basın. Beklenen:

- işlem HTTP `201` ile kaydedilir;
- `ai_fallback=true`;
- `ai_status=UNAVAILABLE`;
- `risk_score=null`, `risk_level=BELIRSIZ`, `decision=INCELEME`;
- atanmamış `YENI` manuel inceleme vakası;
- frontend tamamen çökmez ve açık fallback mesajı gösterir.

Recovery:

```bash
docker compose start ai-service
docker compose ps ai-service
```

Servis healthy olduktan sonra tekrar **Normal işlem** > **İşlemi gönder** yapın.
`ai_fallback=false`, `ai_status=SCORED` ve `model_version=fraudcell-demo-v1`
görünmelidir.

## 12. Worker recovery kabulü

Bu adım 6–7 dakikalık sahne demosu dışında, final kanıt sırasında ayrı temiz vaka
ile yapılır:

1. Yeni Golden vakayı `INCELENIYOR` ve Customer cevabı `BEN_YAPMADIM` olacak şekilde
   hazırlayın.
2. `docker compose stop gamification-worker` çalıştırın.
3. Analyst `BLOKLANDI` kararı versin; karar başarılı olmalı, profil puanı henüz
   değişmemelidir.
4. `docker compose start gamification-worker` çalıştırın.
5. Profil/leaderboard `+30` olana kadar bekleyin.
6. Workerı bir kez daha restart edin; toplam puan değişmemelidir.

## 13. RabbitMQ recovery kabulü

Ayrı temiz vakada:

1. Vaka karar öncesine kadar hazırlanır.
2. `docker compose stop rabbitmq` çalıştırılır.
3. Analyst kararı başarılı olmalı; outbox `PENDING` kalmalı ve puan oluşmamalıdır.
4. `docker compose start rabbitmq` çalıştırılır.
5. Gerekirse iki workerın running olduğunu `docker compose ps` ile doğrulayın.
6. Outbox publish, tek `ProcessedEvent`, doğru ledger ve toplam `+30` beklenir.

## 14. Kapanış kontrolleri

Fault testten sonra sistemin tamamını tekrar doğrulayın:

```bash
python3 scripts/smoke_test.py
python3 scripts/demo_status.py
docker compose ps
```

Her fault adımında durdurulan servis mutlaka yeniden başlatılmalıdır. Son dakika
volume silme veya `docker compose down -v` kullanmayın.

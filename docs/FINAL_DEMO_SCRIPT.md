# FraudCell 6–7 Dakikalık Final Demo Metni

Hedef süre: **6 dakika 35 saniye**. Bu akış temiz reset ve `DEMO READY` sonrasında
uygulanır. Ekranda görünmeyen bir sonucu söylemeyin; beklenen değer farklıysa canlı
değeri okuyun ve sonrasında acceptance kaydını inceleyin.

## Sahne öncesi hazırlık

- `docker compose up -d --build --wait` tamamlanmış olmalı.
- `demo_reset`, iki kez `demo_prepare`, `demo_status` ve `final_acceptance` geçmiş
  olmalı; acceptance sonrası jüri için tekrar temiz reset/prepare/status yapılmalı.
- Terminalde secret içermeyen son `DEMO READY` çıktısı açık olmalı.
- Üç izole browser context hazırlayın:
  - Customer: `/login`, `.env` içindeki `DEMO_CUSTOMER_GSM`, OTP `1234`;
  - Analyst: `/login`, `demo.analyst.account@fraudcell.com`, parola
    `DEMO_ANALYST_PASSWORD`;
  - Supervisor: `/login`, `demo.supervisor@fraudcell.com`, parola
    `DEMO_SUPERVISOR_PASSWORD`.
- Personel parolalarını ekranda veya terminalde göstermeyin.
- Terminal repository kökünde olmalı; `docker compose stop/start ai-service`
  komutları history'de hazır olabilir.

## Dakika dakika akış

| Süre | Ekran ve yapılacak işlem | Söylenecek tek cümle | Beklenen canlı kanıt |
|---|---|---|---|
| **0:00–0:20** | Terminalde `DEMO READY` ve `docker compose ps` özetini gösterin. | “Platform dört bağımsız API, dört PostgreSQL, Kong, RabbitMQ ve iki event workerıyla temiz demo durumunda.” | Servisler healthy/running; migrationlar `Exited (0)` |
| **0:20–0:50** | Customer context: **Musteri** > GSM > **OTP iste** > `1234` > **Giris yap**. | “Demo OTP gerçek SMS değildir; Identity challenge'ı DB'de doğrulayıp gerçek access/refresh oturumu üretiyor.” | `/customer` açılır; sahte işlem görünmez |
| **0:50–1:25** | **Yüksek risk hızlı doldur**; `48500`, `TRANSFER`, `Demo Alıcı`, `Yeni iPhone`, `Berlin`, gece UTC zamanını işaret edin; **İşlemi gönder**. | “Quick-fill yalnızca girdiyi dolduruyor; risk, fraud türü ve karar frontend'de hardcode değil, AI Service'ten geliyor.” | HTTP 201, `TRX-...`, AI sonucu ve RiskCase |
| **1:25–1:55** | **Son AI değerlendirmesi** kartında skor, risk, tür, karar, model ve nedenleri gösterin. | “Checked-in Random Forest bu girdide yaklaşık `0.840797`, `YUKSEK`, `HESAP_ELE_GECIRME`, `INCELEME` üretiyor ve nedenleri doğrudan giriş sinyallerinden açıklıyor.” | `fraudcell-demo-v1`; beş neden; vaka `ATANDI` |
| **1:55–2:30** | Analyst context: **Personel** ile Hesap Analisti girişi; kalıcı risk nedenlerini gösterin; Golden vakada **Başlat**, sonra **Müşteri doğrula**. | “Uzmanlık, boş kapasite ve doğruluk profiliyle Hesap Analisti seçildi; model nedenleri vakayla saklanıyor ve state machine kural dışı geçişleri 422 ile reddediyor.” | Beş risk nedeni, `ATANDI -> INCELENIYOR -> MUSTERI_DOGRULAMA`, SLA sayacı |
| **2:30–2:55** | Customer context: doğrulama bannerında işlem detayını gösterip **Bu işlemi ben yapmadım**. | “Customer yalnızca kendi vakasına cevap verebiliyor ve yanıt vaka geçmişine gerçek bir geçiş olarak ekleniyor.” | `BEN_YAPMADIM`, vaka tekrar `INCELENIYOR` |
| **2:55–3:40** | Analyst context: karar notunu yazın, **Blokla**; profil yenilenmesini bekleyin. | “Karar ve outbox aynı DB transactionında; RabbitMQ üzerinden tüketilen event `+30` ve ilk yakalama rozetini yalnızca bir kez üretiyor.” | `BLOKLANDI`; `+30`, `BRONZ`, resolved `1`, `ILK_YAKALAMA` |
| **3:40–4:05** | `/leaderboard`; **Gunluk** > **Yenile**. | “Leaderboard frontend verisi değil, aynı eventten oluşan ScoreLedger toplamının UTC günlük sorgusudur.” | Hesap Analisti `30` dönem/toplam puan ve rozet |
| **4:05–4:35** | Supervisor context: login; `/supervisor` metrik, dağılım ve Golden vakayı gösterin. | “Supervisor paneli aynı gerçek vaka havuzundan aktif, risk, fraud türü, durum ve SLA özetlerini hesaplıyor; fallback vakaları buradan manuel atanabiliyor.” | Golden vaka `BLOKLANDI`, Analyst UUID; sahte chart yok |
| **4:35–5:20** | Terminal: `docker compose stop ai-service`; Customer context: **Normal işlem** > **İşlemi gönder**. | “AI tamamen kapalıyken transaction servisi fail-open değil, güvenli manuel inceleme fallback'iyle işlemi yine 201 kaydediyor.” | Warning; `UNAVAILABLE`, `BELIRSIZ`, `INCELEME`, atanmamış `YENI` vaka |
| **5:20–6:15** | Terminal: `docker compose start ai-service`; `docker compose ps ai-service`; healthy olunca Customer: tekrar **Normal işlem** > **İşlemi gönder**. | “Servis geri geldiğinde yeniden deploy veya veri düzeltmesi olmadan sonraki işlem gerçek modele dönüyor.” | `ai_fallback=false`, `SCORED`, model version görünür |
| **6:15–6:35** | Customer AI sonucu, leaderboard ve terminal health'i kısa yan yana gösterin. | “FraudCell'in gösterdiğimiz kısmı uçtan uca gerçek: model inference, güvenli vaka akışı, outbox/RabbitMQ idempotency, puan ve kontrollü AI fallback; gerçek SMS ve production model ise bilinçli olarak demo kapsamı dışında.” | Tüm servisler tekrar healthy |

## Golden değerin puan açıklaması

Golden artifact çıktısı `YUKSEK` olduğu için bu sahnede doğru toplam **+30**'dur:

```text
CASE_RESOLVED       +10
FAST_DECISION        +5
CONFIRMED_FRAUD     +15
```

`CRITICAL_WITHIN_SLA +15` yalnızca risk gerçekten `KRITIK` ise eklenir. Ekran
`YUKSEK` gösterirken `+45` demeyin.

## Süre taşarsa kesilecek parçalar

Önce dağılım kartlarının ayrıntılı anlatımını, sonra model feature listesini kısaltın.
AI stop/fallback/recovery, Customer doğrulaması, Analyst kararı ve leaderboard
sahnelerini kesmeyin.

## Canlı hata protokolü

- Beklenmeyen sonuçta aynı butona art arda basmayın; ekrandaki HTTP/error mesajını
  okuyun.
- AI stop sahnesinden sonra her koşulda `docker compose start ai-service` çalıştırın.
- Atanan Analyst beklenenden farklıysa response UUID'sini demo kullanıcı UUID'leriyle
  eşleştirip doğru contexti açın.
- Puan polling'i birkaç saniye sürerse **Yenile** kullanın; frontend'de geçici puan
  uydurmayın.
- Zorunlu kanıt kırılırsa PASS demeyin; terminalde `python3 scripts/final_acceptance.py`
  çıktısına dönüp başarısız adımı açıkça belirtin.

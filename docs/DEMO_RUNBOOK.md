# FraudCell Golden Demo Runbook

Bu akış gerçek servis, model, PostgreSQL ve RabbitMQ verisini kullanır. Parolaları,
JWT secret'ını ve internal service key'i yalnızca çalıştıran shell/container
environment'ında tutun; dokümana veya Git'e yazmayın.

## 1. Platformu başlat

`.env.example` dosyasındaki placeholder'ları yerel `.env` içinde güçlü değerlerle
değiştirin ve `docker compose up -d --build --wait` çalıştırın.

## 2. Migrationları kontrol et

`docker compose ps -a` çıktısında `identity-migrate`, `transaction-migrate`,
`ai-migrate` ve `gamification-migrate` servislerinin `Exited (0)` olduğunu doğrulayın.

## 3. Demo hesaplarını hazırla

Shell'de `DEMO_ADMIN_PASSWORD`, `DEMO_SUPERVISOR_PASSWORD`,
`DEMO_ANALYST_PASSWORD`, `DEMO_CUSTOMER_GSM`, `DEMO_OTP_CODE` ve
`INTERNAL_SERVICE_KEY` tanımlıyken `python3 scripts/demo_prepare.py` çalıştırın.
Komut idempotenttir ve başarıda `DEMO READY` yazar.

## 4. Demo durumunu doğrula

`python3 scripts/demo_status.py` çalıştırın. Dört API, RabbitMQ, iki worker, gerçek
demo kullanıcı/profilleri, loginler ve leaderboard kontrol edilir.

## 5. Giriş bilgileri

Sabit e-postalar: `demo.admin@fraudcell.com`, `demo.supervisor@fraudcell.com`,
`demo.analyst.card@fraudcell.com`, `demo.analyst.account@fraudcell.com` ve
`demo.analyst.aml@fraudcell.com`. Parolalar yukarıdaki environment değişkenlerinden,
Customer GSM/OTP ise `DEMO_CUSTOMER_GSM` ve `DEMO_OTP_CODE` değerlerinden gelir.

## 6. Customer login

Frontend'de demo GSM ile OTP isteyin ve mevcut demo OTP configuration değerini
girin. OTP response veya log içinde gösterilmez.

## 7. High-risk transaction

“Yüksek risk demo” ile formu doldurun ve işlemi gönderin. Buton risk sonucu
üretmez; skor, fraud türü ve karar gerçek AI Service'ten gelir.

## 8. Analyst vaka akışı

Atanan Analyst ile giriş yapın, `ATANDI` vakayı başlatın ve
`MUSTERI_DOGRULAMA` geçişini gerçek endpointten isteyin.

## 9. Customer doğrulaması

Customer workspace polling sonrası “Şüpheli işlem doğrulaması gerekiyor.” bannerını
gösterir. İşlem bilgilerini doğrulayıp “Bu işlemi ben yapmadım” seçin.

## 10. Analyst kararı

Analyst vakaya dönüp açıklamalı `BLOKLANDI` kararı verir. Response brokerı beklemez;
`event_delivery=PENDING` ve `event_id` döner.

## 11. Puan ve rozet

Outbox worker olayı RabbitMQ'ya, Gamification worker DB'ye taşır. Hızlı kritik ve
doğrulanmış blok senaryosu +45 puan ve ilk seferde `ILK_YAKALAMA` üretir.

## 12. Leaderboard

Analyst, Supervisor veya Admin ile daily leaderboard'u yenileyin; puan ve rozet
gerçek Gamification DB verisinden görünür.

## 13. Supervisor görünümü ve kapanış

Supervisor tüm vakaları görüntüler. Karar verilmiş vakayı `/cases/{id}/close` ile
`KAPANDI` durumuna geçirir; Admin karar/kapanış yapmaz.

## 14. Customer feedback

Customer kapalı vakada 1–5 yıldız seçer. Aynı vaka ikinci kez feedback kabul etmez.
`feedback.submitted` transactional outbox üzerinden yayınlanır ve Gamification'da
idempotent işlendi olarak kaydedilir; bu MVP'de puan üretmez.

## 15. AI fallback

`docker compose stop ai-service` sonrası yeni işlem gönderin. Transaction 201 dönmeli,
`ai_fallback=true`, `risk_level=BELIRSIZ` ve manuel `YENI` vaka oluşmalıdır.

## 16. AI recovery

`docker compose start ai-service` çalıştırın, healthy olmasını bekleyin ve yeni bir
işlemle gerçek skorlamanın geri geldiğini doğrulayın.

## 17. Demo reset

`python3 scripts/demo_reset.py --confirm RESET_DEMO` yalnızca sabit demo müşteri
işlem/vaka/feedback/outbox verisini ve demo analyst gamification ilerlemesini temizler;
AI kapasitesini ve Identity auth state'ini sıfırlar. Demo kullanıcılarını veya volume'ları
silmez. Ardından `demo_prepare.py` tekrar güvenle çalıştırılabilir.

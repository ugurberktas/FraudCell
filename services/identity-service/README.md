# Identity Service

Identity Service, FraudCell Customer ve staff hesaplarının kimlik doğrulamasını,
JWT/refresh oturumlarını, rol kontrolünü ve immutable audit kayıtlarını yönetir.
Kong dış öneki `/api/v1/auth` şeklindedir.

## Endpointler

| Method | Path | Erişim | Açıklama |
|---|---|---|---|
| `GET` | `/health` | Public | DB'den bağımsız liveness |
| `GET` | `/ready` | Public | Identity PostgreSQL readiness |
| `POST` | `/customers/otp/request` | Public | Customer registration için 5 dakikalık OTP challenge |
| `POST` | `/customers/register` | Public | GSM ve registration OTP ile Customer oluşturma |
| `POST` | `/customers/login/otp/request` | Public | Hesap varlığını açıklamayan login OTP isteği |
| `POST` | `/customers/login` | Public | GSM ve login OTP ile Customer oturumu |
| `POST` | `/staff/login` | Public | Analyst/Supervisor/Admin email-parola oturumu |
| `POST` | `/tokens/refresh` | Refresh token | Refresh rotation |
| `POST` | `/tokens/logout` | Refresh token | İlgili refresh oturumunu revoke etme |
| `GET` | `/me` | Access token | Güncel aktif kullanıcı |
| `POST` | `/staff/accounts` | ADMIN | Staff hesabı oluşturma |
| `GET` | `/audit-logs` | ADMIN | Filtreli, sayfalı audit listesi |

Başarılı ve hatalı HTTP cevapları `success/data/error` envelope kullanır.
`X-Request-ID` response headerında korunur.

## Demo OTP

Bu MVP gerçek SMS göndermez. OTP challenge DB'de tutulur, beş dakika geçerlidir ve
beş hatalı doğrulama denemesinden sonra tüketilir. Doğru kod
`DEMO_OTP_CODE` konfigürasyonundan gelir ve API response/log içinde döndürülmez.
Golden Demo'da bu değer `1234` olarak konfigüre edilir.

Customer login OTP request, GSM sistemde olmasa da aynı genel mesajı verir; hesap
enumeration'ını azaltır. Registration ve login challenge'ları ayrı purpose ile tutulur.

## Access ve refresh tokenları

Access tokenları HS256 JWT'dir; `sub`, `user_id`, `role`, `specializations`,
`regions`, `type`, `jti`, `iat`, `exp`, `iss` ve `aud` claimleri doğrulanır. Varsayılan
ömür 15 dakikadır.

Refresh tokenları opaque 256-bit değerdir; DB'de yalnızca SHA-256 hashleri tutulur ve
varsayılan ömür yedi gündür. Her refresh tek transaction içinde yeni access/refresh
çifti üretir ve eski tokenı rotated olarak işaretler. Rotated token tekrar kullanılırsa
`TOKEN_REUSE_DETECTED` döner ve kullanıcının aktif refresh sessionları revoke edilir.
Logout yalnızca verilen sessionı idempotent biçimde revoke eder.

## Staff parola, lockout ve RBAC

Staff parolaları Argon2id ile hashlenir. Parola politikası en az sekiz karakter,
bir büyük harf, bir rakam ve whitespace olmayan bir özel karakter ister.

İlk dört yanlış staff login `401 AUTHENTICATION_FAILED` döner. Beşinci deneme hesabı
15 dakika kilitler ve `429 ACCOUNT_LOCKED`, `Retry-After` ile
`details.remaining_seconds` döner. Süre sonrasındaki başarılı giriş sayaçları temizler.

`POST /staff/accounts` ve `GET /audit-logs` yalnızca DB'deki güncel rolü `ADMIN`
olan aktif kullanıcıya açıktır. Stale JWT rol claimi yetki kazandırmaz. Audit endpointi
read-only'dir; update/delete endpointi yoktur. Audit detail alanları password, OTP,
authorization, token ve secret benzeri anahtarlar için hem yazarken hem serialize
ederken temizlenir.

## Temel ayarlar

| Değişken | Açıklama |
|---|---|
| `DATABASE_URL` | Identity PostgreSQL bağlantısı |
| `DEMO_OTP_CODE` | Demo-only OTP; response/log içinde gösterilmez |
| `ENVIRONMENT` | `production` olduğunda zayıf JWT secret startup'ı engeller |
| `JWT_SECRET` | En az 32 karakterlik imzalama secret'ı |
| `JWT_ALGORITHM` | Sabit `HS256` |
| `JWT_ISSUER` | Varsayılan `fraudcell-identity` |
| `JWT_AUDIENCE` | Varsayılan `fraudcell-platform` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Varsayılan `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Varsayılan `7` |

Gerçek değerler root `.env` veya çalışma environment'ında tutulur; repository'ye
commit edilmez.

## İlk Admin ve Golden Demo seed

İlk Admin için açık ve idempotent CLI:

```bash
python -m app.cli.bootstrap_admin
```

Komut `BOOTSTRAP_ADMIN_FIRST_NAME`, `BOOTSTRAP_ADMIN_LAST_NAME`,
`BOOTSTRAP_ADMIN_EMAIL` ve `BOOTSTRAP_ADMIN_PASSWORD` değerlerini environment'tan
alır.

Golden Demo hesapları:

```bash
python -m app.cli.seed_demo_users
python -m app.cli.seed_demo_users --check
python -m app.cli.reset_demo_identity
```

Seed, Admin, Supervisor, üç Analyst ve Customer hesabını gerçek UUID'lerle oluşturur.
Mevcut hesapta rol/profil çakışması varsa sessizce üzerine yazmaz. Root
`scripts/demo_prepare.py` gerekli env değerlerini container'a güvenli biçimde aktarır.
Reset kullanıcıları silmez; demo refresh sessionlarını, OTP kayıtlarını ve staff lock
sayaçlarını temizler.

## Migration ve test

```bash
alembic upgrade head
alembic downgrade base
pytest tests -q
```

Compose, `identity-migrate` başarıyla tamamlanmadan API'yi başlatmaz. Uygulama
runtime'da `create_all` çağırmaz.

## Sınırlar

Gerçek SMS provider, MFA, harici KMS/secret manager, TLS termination ve dağıtık rate
limiting bu demo kapsamında yoktur. `DEMO_OTP_CODE` production kimlik doğrulaması
olarak kullanılamaz.

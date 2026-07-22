from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def jwt_secret_is_unsafe(secret: str) -> bool:
    normalized = secret.strip().lower()
    return (
        len(secret) < 32
        or normalized.startswith("change_me")
        or normalized.startswith("changeme")
        or normalized in {"secret", "jwt_secret", "your-secret-here"}
        or len(set(secret)) < 8
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    service_name: str = "identity-service"
    version: str = "0.1.0"
    debug: bool = False
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/identity_db"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    demo_otp_code: str = "1234"
    environment: str = "development"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "fraudcell-identity"
    jwt_audience: str = "fraudcell-platform"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    @model_validator(mode="after")
    def validate_production_jwt_secret(self) -> "Settings":
        if self.environment.lower() == "production":
            if jwt_secret_is_unsafe(self.jwt_secret):
                raise ValueError(
                    "JWT_SECRET must contain at least 32 characters in production"
                )
        return self


settings = Settings()

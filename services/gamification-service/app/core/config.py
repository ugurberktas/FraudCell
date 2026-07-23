from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    service_name: str = "gamification-service"
    version: str = "0.1.0"
    debug: bool = False
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/gamification_db"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "fraudcell-identity"
    jwt_audience: str = "fraudcell-platform"
    event_exchange: str = "fraudcell.events"
    case_decision_queue: str = "gamification.case-decisions.v1"
    consumer_prefetch: int = 10


settings = Settings()

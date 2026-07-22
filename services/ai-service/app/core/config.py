from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    service_name: str = "ai-service"
    version: str = "0.1.0"
    debug: bool = False
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/ai_db"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    redis_url: str = "redis://localhost:6379/0"
    internal_service_key: str = ""
    model_artifact_path: str = "artifacts/fraud_model.joblib"
    model_metadata_path: str = "artifacts/model_metadata.json"


settings = Settings()

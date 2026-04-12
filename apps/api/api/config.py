from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ekamcore:ekamcore_dev_password@localhost:5432/ekamcore"

    # Redis
    REDIS_URL: str = "redis://:ekamcore_redis_dev@localhost:6379/0"

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = "ekamcore_qdrant_dev"

    # Ollama
    OLLAMA_URL: str = "http://localhost:11434"

    # Paperless
    PAPERLESS_URL: str = "http://ekamcore-paperless:8000/api"
    PAPERLESS_API_TOKEN: str = ""

    # JWT
    JWT_SECRET_KEY: str = "ekamcore-dev-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8420
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Photo thumbnails
    THUMBNAIL_DIR: str = "./data/thumbnails"

    # Phase 3: face clustering encryption key (Fernet, base64-encoded 32 bytes)
    # Loaded from FACE_EMBED_KEY env var. Empty = face pipeline disabled.
    FACE_EMBED_KEY: str = ""

    # Phase 3 (S11-005): InsightFace buffalo_l model directory. Bind-mounted
    # into the workers container at /models/insightface. Download the pack
    # with `make download-face-models` before the first container start.
    INSIGHTFACE_MODEL_DIR: str = "/models/insightface"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

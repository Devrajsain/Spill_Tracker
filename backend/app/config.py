import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "SlickTrace - Marine Oil Spill Detection & Vessel Attribution System"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "national-maritime-defense-secret-key"
    
    # DB URL: Default SQLite for standalone execution
    DATABASE_URL: str = "sqlite:///./slicktrace.db"
    
    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Folders
    UPLOAD_DIR: str = "./uploads"
    OUTPUT_DIR: str = "./outputs"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

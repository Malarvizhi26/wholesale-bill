"""Core configuration settings for Hardware Billing OS."""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Hardware Billing OS"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment: 'development', 'testing', 'production'
    ENVIRONMENT: str = "development"
    
    # Default Database URL (Postgres or SQLite for offline/dev)
    DATABASE_URL: str = "sqlite+aiosqlite:///./hardware_billing.db"
    
    # Security
    SECRET_KEY: str = "dev-insecure-secret-key-change-in-production-12345678"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Default State for GST calculation (33 = Tamil Nadu)
    DEFAULT_STATE_CODE: str = "33"
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "tauri://localhost",
        "http://tauri.localhost",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )


settings = Settings()

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App & Server Settings
    APP_NAME: str = "QuickDrop Rider Dispute Desk"
    PORT: int = 8000
    DEBUG: bool = False

    # External Services
    PAYSWIFT_BASE_URL: str = "http://localhost:8081"
    DATABASE_URL: str = "sqlite+aiosqlite:///./quickdrop.db"

    # LLM Settings
    LLM_PROVIDER: Literal["gemini", "groq", "openai", "mock"] = "mock"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Business Rules (docs/policy.md)
    BASE_FARE: float = 25.0
    BASE_KM_THRESHOLD: float = 2.0
    RATE_PER_KM: float = 6.0
    DAILY_INCENTIVE_TRIPS: int = 12
    DAILY_INCENTIVE_AMOUNT: int = 150
    CANCELLATION_PENALTY: int = 10
    DISPUTE_LOOKBACK_DAYS: int = 7

    # Financial Guardrails
    AUTO_PAY_MAX_AMOUNT: int = 200
    MAX_AUTO_PAYS_PER_RIDER_PER_DAY: int = 1


settings = Settings()

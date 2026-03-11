from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    POWER_AUTOMATE_URL: str
    EOD_SCHEDULE_TIME: str = "17:00"
    MODEL_NAME: str = "gemini-2.5-flash"
    DATABASE_URL: str = "sqlite:///eod_reporter.db"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

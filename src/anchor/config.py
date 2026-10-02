from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Blank entries copied from .env.example fall back to the defaults below.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    database_url: str = "postgresql+psycopg://anchor:anchor@localhost:5432/anchor"
    redis_url: str = "redis://localhost:6379/0"
    # SEC rejects requests without a contact string: "Full Name email@example.com".
    edgar_user_agent: str = ""
    raw_storage_dir: Path = Path("data/raw")


@lru_cache
def get_settings() -> Settings:
    return Settings()

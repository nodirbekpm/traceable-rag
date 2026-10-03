from decimal import Decimal
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

    # Local CPU model, 384 dimensions. A model with another size needs a migration.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # HNSW search breadth: higher finds more true neighbours, slower. pgvector default: 40.
    hnsw_ef_search: int = 40

    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"
    gemini_api_key: str = ""
    # USD per million tokens at list price; used to report cost even on a free tier.
    llm_price_input_per_mtok: Decimal = Decimal("0.30")
    llm_price_output_per_mtok: Decimal = Decimal("2.50")


@lru_cache
def get_settings() -> Settings:
    return Settings()

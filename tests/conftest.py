from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from anchor.config import get_settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """A scratch database next to the configured one, so tests never touch dev data."""
    base = make_url(get_settings().database_url)
    name = f"{base.database}_test"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return base.set(database=name).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def alembic_config(test_database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_url"] = test_database_url
    return config


@pytest.fixture(scope="session")
def engine(test_database_url: str, alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Each test runs inside a transaction that is rolled back afterwards."""
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()

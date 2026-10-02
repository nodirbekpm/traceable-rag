from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from anchor.models import Base


def test_models_and_migrations_describe_the_same_schema(engine: Engine) -> None:
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == []


def test_current_facts_have_a_partial_index(engine: Engine) -> None:
    indexes = {index["name"]: index for index in inspect(engine).get_indexes("extracted_fact")}

    predicate = indexes["ix_extracted_fact_current"]["dialect_options"]["postgresql_where"]
    assert "is_current" in predicate


def test_migrations_downgrade_to_base_and_upgrade_again(
    engine: Engine, alembic_config: Config
) -> None:
    engine.dispose()

    command.downgrade(alembic_config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]

    command.upgrade(alembic_config, "head")
    assert "source_document" in inspect(engine).get_table_names()

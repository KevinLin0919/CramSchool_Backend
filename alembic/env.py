from logging.config import fileConfig

from sqlalchemy import DateTime, engine_from_config, pool

from alembic import context
from app.config import get_settings
from app.models import Base, UTCDateTime

config = context.config

# The database URL lives in one place (Settings), so alembic.ini does not carry
# a second copy that can drift from what the application actually connects to.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """Render UTCDateTime as the plain DDL type it actually is.

    A migration is a historical record that must keep running years later, so
    it should not import application code — renaming or deleting the model
    class would otherwise break every past revision. At the database level the
    decorator is just a timestamp column, so emit that.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("import sqlalchemy as sa")
        return "sa.DateTime(timezone=True)"
    return False


def compare_type(_ctx, _inspected_col, _metadata_col, inspected_type, metadata_type):
    """Treat a reflected TIMESTAMP as equal to the UTCDateTime decorator.

    Autogenerate otherwise sees `TIMESTAMP(timezone=True)` in the database and
    `UTCDateTime()` in the metadata, cannot prove they are the same, and emits
    a modify_type for every timestamp column on every run. `alembic check`
    would never go green, and genuine drift would be buried in that noise.
    SQLite's looser reflection hides this; Postgres does not.
    """
    if isinstance(metadata_type, UTCDateTime) and isinstance(inspected_type, DateTime):
        return False
    return None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        render_item=render_item,
        compare_type=compare_type,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER most things; batch mode rewrites the table
            # instead, so the same migration runs on both backends.
            render_as_batch=True,
            render_item=render_item,
            compare_type=compare_type,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_db = current_app.extensions["migrate"].db


def get_engine():
    try:
        return target_db.get_engine()
    except (TypeError, AttributeError):
        return target_db.engine


def get_engine_url():
    return get_engine().url.render_as_string(hide_password=False).replace("%", "%%")


def get_metadata():
    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


config.set_main_option("sqlalchemy.url", get_engine_url())


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=get_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **current_app.extensions["migrate"].configure_args,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **current_app.extensions["migrate"].configure_args,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

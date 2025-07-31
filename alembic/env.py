import sys
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

# Подключаем app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import engine, Base
from app import models  # Важно для обнаружения всех моделей при autogenerate

# Alembic Config
config = context.config

# Логирование из .ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные моделей
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Миграции в офлайн-режиме (без подключения к БД)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Миграции в онлайн-режиме (с реальным подключением к БД)."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

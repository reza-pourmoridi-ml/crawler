from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from app.infra.db import Base
from app.infra.config import settings


from app.control.airlines.models import (
    Airline,
    AirlineAlias,
)
from app.control.websites.models import Website
from app.control.flight_paths.models import (
    FlightPath,
)
from app.control.airports.models import Airport
from app.control.search_box.models import (
    SearchRequest,
)
from app.orchestration.models import Job

config = context.config

config.set_main_option(
    "sqlalchemy.url",
    settings.database_url,
)

fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
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

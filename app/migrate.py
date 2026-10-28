"""Apply Alembic migrations under a Postgres advisory lock.

Both the API and the consumer run this on startup. The lock makes the race safe.
"""

import asyncio
import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

LOCK_ID = 824_651_093


def _upgrade() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


async def apply_migrations() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        await _wait_for_database(engine)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": LOCK_ID})
            await connection.commit()
            try:
                logger.info("applying database migrations")
                await asyncio.to_thread(_upgrade)
                logger.info("database migrations are up to date")
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": LOCK_ID},
                )
                await connection.commit()
    finally:
        await engine.dispose()


async def _wait_for_database(engine) -> None:
    delay = 1.0
    last_error: Exception | None = None
    for _ in range(30):
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return
        except Exception as exc:
            last_error = exc
            logger.warning("database is not ready: %s", exc)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 5.0)
    raise RuntimeError("database is not ready") from last_error


def main() -> None:
    configure_logging()
    asyncio.run(apply_migrations())


if __name__ == "__main__":
    main()

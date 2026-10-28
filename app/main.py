from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.deps import APIKeyMiddleware
from app.api.health import router as health_router
from app.api.payments import router as payments_router
from app.db import engine
from app.logging_config import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Payment Processing Service",
        version=__version__,
        summary="Асинхронный сервис процессинга платежей",
        description=(
            "Принимает платёж, сохраняет его вместе с outbox-событием и отвечает 202. "
            "Дальше событие публикуется в RabbitMQ, consumer проводит платёж через "
            "эмуляцию шлюза и уведомляет webhook."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(APIKeyMiddleware)
    application.include_router(health_router)
    application.include_router(payments_router, prefix="/api/v1")
    return application


app = create_app()

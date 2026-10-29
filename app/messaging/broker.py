from faststream.rabbit import Channel, RabbitBroker

from app.config import settings

broker = RabbitBroker(
    settings.rabbitmq_url,
    app_id="payment-service",
    graceful_timeout=30.0,
    default_channel=Channel(
        prefetch_count=settings.prefetch_count,
        publisher_confirms=True,
        on_return_raises=True,
    ),
)

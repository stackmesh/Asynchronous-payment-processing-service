import asyncio

from app.logging_config import configure_logging
from app.messaging.consumer_app import app


def main() -> None:
    configure_logging()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()

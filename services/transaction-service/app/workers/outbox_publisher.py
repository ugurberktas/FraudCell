"""Reliable RabbitMQ publisher for pending transactional outbox rows."""
from __future__ import annotations

import json
import logging
import time

import pika
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import _get_engine
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)


class RabbitPublisher:
    def __init__(self) -> None:
        self.connection = None
        self.channel = None

    def connect(self) -> None:
        parameters = pika.URLParameters(settings.rabbitmq_url)
        parameters.heartbeat = 30
        parameters.blocked_connection_timeout = 10
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(
            exchange=settings.event_exchange, exchange_type="topic", durable=True
        )
        self.channel.confirm_delivery()

    def publish(self, routing_key: str, payload: dict) -> None:
        if self.channel is None or self.channel.is_closed:
            self.connect()
        confirmed = self.channel.basic_publish(
            exchange=settings.event_exchange,
            routing_key=routing_key,
            body=json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(),
            properties=pika.BasicProperties(
                content_type="application/json", delivery_mode=2
            ),
            mandatory=True,
        )
        if confirmed is False:
            raise RuntimeError("publisher confirm was negative")

    def close(self) -> None:
        if self.connection is not None and self.connection.is_open:
            self.connection.close()


def publish_one(publisher: RabbitPublisher) -> bool:
    with Session(_get_engine()) as session:
        repository = OutboxRepository(session)
        row = repository.next_pending()
        if row is None:
            session.rollback()
            return False
        try:
            publisher.publish(row.routing_key, row.payload)
            repository.mark_published(row)
            session.commit()
        except Exception as exc:
            repository.mark_failed(row, type(exc).__name__)
            session.commit()
            raise
        return True


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    publisher = RabbitPublisher()
    failures = 0
    while True:
        try:
            published = publish_one(publisher)
            failures = 0
            if not published:
                time.sleep(settings.outbox_poll_interval_seconds)
        except KeyboardInterrupt:
            publisher.close()
            return
        except Exception as exc:
            failures += 1
            publisher.close()
            publisher = RabbitPublisher()
            delay = min(30.0, max(1.0, 2 ** min(failures - 1, 5)))
            logger.warning("Outbox publish failed (%s); retrying in %.1fs", type(exc).__name__, delay)
            time.sleep(delay)


if __name__ == "__main__":
    run()

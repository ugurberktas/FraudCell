"""RabbitMQ consumer for idempotent case decision scoring."""
import json
import logging
import time

import pika
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import _get_engine
from app.services.event_service import EventService, InvalidEvent

logger = logging.getLogger(__name__)


def handle_delivery(channel, method, properties, body: bytes) -> None:
    try:
        raw = json.loads(body)
        with Session(_get_engine()) as session:
            EventService(session).process(raw)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except (json.JSONDecodeError, UnicodeDecodeError, InvalidEvent, ValidationError) as exc:
        logger.warning("Rejected invalid case decision event (%s)", type(exc).__name__)
        channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as exc:
        logger.warning("Event processing failed (%s); message requeued", type(exc).__name__)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def consume_once() -> None:
    parameters = pika.URLParameters(settings.rabbitmq_url)
    parameters.heartbeat = 30
    parameters.blocked_connection_timeout = 10
    connection = pika.BlockingConnection(parameters)
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange=settings.event_exchange, exchange_type="topic", durable=True)
        channel.queue_declare(queue=settings.case_decision_queue, durable=True)
        channel.queue_bind(
            queue=settings.case_decision_queue,
            exchange=settings.event_exchange,
            routing_key="case.decision_made",
        )
        channel.queue_bind(
            queue=settings.case_decision_queue,
            exchange=settings.event_exchange,
            routing_key="feedback.submitted",
        )
        channel.basic_qos(prefetch_count=settings.consumer_prefetch)
        channel.basic_consume(
            queue=settings.case_decision_queue,
            on_message_callback=handle_delivery,
            auto_ack=False,
        )
        channel.start_consuming()
    finally:
        if connection.is_open:
            connection.close()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    failures = 0
    while True:
        try:
            consume_once()
            failures = 0
        except KeyboardInterrupt:
            return
        except Exception as exc:
            failures += 1
            delay = min(30.0, 2 ** min(failures - 1, 5))
            logger.warning("RabbitMQ consumer disconnected (%s); retrying in %.1fs", type(exc).__name__, delay)
            time.sleep(delay)


if __name__ == "__main__":
    run()

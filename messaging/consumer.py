import json
import logging
import os
import signal
from typing import Any

import pika

from messaging.publisher import RabbitMQPublisher
from messaging.topology import RabbitMQTopology, connection_parameters
from parser.amazon_scraper import AmazonScraper

logger = logging.getLogger(__name__)


class InvalidScrapeRequest(ValueError):
    pass


class RabbitMQConsumer:
    """Worker que consome comandos, raspa uma URL e publica o resultado."""

    def __init__(self) -> None:
        self.topology = RabbitMQTopology()
        self.max_retries = int(os.getenv("RABBITMQ_MAX_RETRIES", "3"))
        self.prefetch = int(os.getenv("RABBITMQ_PREFETCH", "1"))
        self.connection: pika.BlockingConnection | None = None
        self.channel = None
        self.scraper = AmazonScraper()
        self.publisher = RabbitMQPublisher(required=True)

    @staticmethod
    def _decode(body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidScrapeRequest("invalid_json") from exc

        if not isinstance(payload, dict):
            raise InvalidScrapeRequest("payload_must_be_an_object")
        if not payload.get("request_id"):
            raise InvalidScrapeRequest("request_id_is_required")
        if not payload.get("url"):
            raise InvalidScrapeRequest("url_is_required")
        return payload

    @staticmethod
    def _retry_count(properties: pika.BasicProperties) -> int:
        headers = properties.headers or {}
        try:
            return int(headers.get("x-retry-count", 0))
        except (TypeError, ValueError):
            return 0

    def _publish_retry(
        self, body: bytes, properties: pika.BasicProperties, retry_count: int
    ) -> None:
        headers = dict(properties.headers or {})
        headers["x-retry-count"] = retry_count
        self.channel.basic_publish(
            exchange=self.topology.retry_exchange,
            routing_key=self.topology.request_routing_key,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=pika.DeliveryMode.Persistent,
                message_id=properties.message_id,
                correlation_id=properties.correlation_id,
                headers=headers,
            ),
            mandatory=True,
        )

    def _on_message(self, channel, method, properties, body: bytes) -> None:
        try:
            payload = self._decode(body)
        except InvalidScrapeRequest as exc:
            logger.error("Comando inválido enviado para a DLQ: %s", exc)
            channel.basic_nack(method.delivery_tag, requeue=False)
            return

        request_id = str(payload["request_id"])
        retry_count = self._retry_count(properties)
        logger.info(
            "Processando request_id=%s tentativa=%s url=%s",
            request_id,
            retry_count + 1,
            payload["url"],
        )

        try:
            result = self.scraper.scrape(payload["url"])
            self.publisher.publish_scraped_event(
                request_id=request_id,
                product_id=payload.get("product_id"),
                listing_id=payload.get("listing_id"),
                store=payload.get("store", "amazon"),
                url=result["url"],
                title=result["title"],
                price=result["price"],
                currency=result["currency"],
                image_url=result["image_url"],
            )
            channel.basic_ack(method.delivery_tag)
            logger.info("Raspagem concluída request_id=%s", request_id)
        except Exception as exc:
            reason = str(exc)
            retryable = reason in {"blocked", "timeout"}
            if retryable and retry_count < self.max_retries:
                next_retry = retry_count + 1
                logger.warning(
                    "Falha temporária request_id=%s; enviando para retry %s/%s",
                    request_id,
                    next_retry,
                    self.max_retries,
                )
                self._publish_retry(body, properties, next_retry)
                channel.basic_ack(method.delivery_tag)
                return

            normalized_reason = (
                reason
                if reason in {"blocked", "timeout", "not_found", "parse_error"}
                else "parse_error"
            )
            try:
                self.publisher.publish_failed_event(
                    request_id=request_id,
                    product_id=payload.get("product_id"),
                    listing_id=payload.get("listing_id"),
                    store=payload.get("store", "amazon"),
                    url=payload["url"],
                    reason=normalized_reason,
                )
                channel.basic_ack(method.delivery_tag)
            except Exception:
                logger.exception(
                    "Não foi possível publicar a falha request_id=%s; mensagem será reprocessada",
                    request_id,
                )
                channel.basic_nack(method.delivery_tag, requeue=True)

    def run(self) -> None:
        self.connection = pika.BlockingConnection(connection_parameters())
        self.channel = self.connection.channel()
        self.topology.declare(self.channel)
        self.channel.confirm_delivery()
        self.channel.basic_qos(prefetch_count=self.prefetch)
        self.channel.basic_consume(
            queue=self.topology.requests_queue,
            on_message_callback=self._on_message,
            auto_ack=False,
        )

        def stop(*_args) -> None:
            if self.connection and self.connection.is_open:
                self.connection.add_callback_threadsafe(self.channel.stop_consuming)

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        logger.info(
            "Worker aguardando mensagens queue=%s prefetch=%s",
            self.topology.requests_queue,
            self.prefetch,
        )
        try:
            self.channel.start_consuming()
        finally:
            self.publisher.close()
            if self.connection and self.connection.is_open:
                self.connection.close()
            logger.info("Worker encerrado")

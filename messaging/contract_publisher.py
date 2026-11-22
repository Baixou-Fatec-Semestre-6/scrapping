import json
import logging
from datetime import datetime, timezone

import pika
from pika.exceptions import AMQPChannelError, AMQPConnectionError

from messaging.publisher import RabbitMQPublisher

logger = logging.getLogger(__name__)


class ContractPublisher(RabbitMQPublisher):
    """Publicador compatível com o contrato Laravel de 31/10/2026."""

    def _reset_connection(self) -> None:
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
        except Exception:
            pass
        self.connection = None
        self.channel = None

    def _publish_contract(self, routing_key: str, payload: dict) -> bool:
        self.published_events.append(payload)
        if not self.enabled:
            return True
        # A BlockingConnection de publicacao fica ociosa entre pedidos e nao
        # responde heartbeats; o broker a encerra e o cliente so descobre ao
        # publicar. Por isso: processa eventos pendentes antes de publicar e,
        # se a conexao estiver morta, reconecta e reenvia uma unica vez.
        for attempt in (1, 2):
            self.ensure_connection()
            if not self.channel:
                raise RuntimeError("rabbitmq_unavailable")
            try:
                if self.connection is not None:
                    self.connection.process_data_events(time_limit=0)
                # Com publisher confirms, o Pika sinaliza nack/unroutable por exceção;
                # uma publicação confirmada pode retornar None dependendo da versão.
                self.channel.basic_publish(
                    exchange=self.exchange,
                    routing_key=routing_key,
                    body=json.dumps(payload),
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=pika.DeliveryMode.Persistent,
                    ),
                    mandatory=True,
                )
                return True
            except (AMQPConnectionError, AMQPChannelError, ConnectionError) as exc:
                if attempt == 2:
                    raise
                logger.warning(
                    "Conexão de publicação perdida (%s); reconectando e reenviando %s",
                    exc.__class__.__name__,
                    routing_key,
                )
                self._reset_connection()
        return False

    def publish_scraped_event(
        self,
        listing_id,
        title,
        price,
        currency,
        image_url,
        event_id=None,
        scraped_at=None,
        **_legacy,
    ):
        return self._publish_contract(
            "scrape.completed",
            {
                "event_id": event_id,
                "listing_id": listing_id,
                "title": title,
                "image_url": image_url,
                "price": float(price),
                "currency": currency or "BRL",
                "scraped_at": scraped_at or datetime.now(timezone.utc).isoformat(),
            },
        )

    def publish_failed_event(
        self,
        listing_id,
        reason,
        event_id=None,
        scraped_at=None,
        **_legacy,
    ):
        return self._publish_contract(
            "scrape.failed",
            {
                "event_id": event_id,
                "listing_id": listing_id,
                "reason": reason,
                "scraped_at": scraped_at or datetime.now(timezone.utc).isoformat(),
            },
        )

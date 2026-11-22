import json
from datetime import datetime, timezone

import pika

from messaging.publisher import RabbitMQPublisher


class ContractPublisher(RabbitMQPublisher):
    """Publicador compatível com o contrato Laravel de 31/10/2026."""

    def _publish_contract(self, routing_key: str, payload: dict) -> bool:
        self.published_events.append(payload)
        if not self.enabled:
            return True
        self.ensure_connection()
        if not self.channel:
            raise RuntimeError("rabbitmq_unavailable")
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

import argparse
import json
import uuid
from datetime import datetime, timezone

import pika
from dotenv import load_dotenv

from messaging.topology import RabbitMQTopology, connection_parameters


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Publica um comando de teste para o scraper")
    parser.add_argument("url", help="URL Amazon a raspar")
    parser.add_argument("--listing-id", type=int, default=1)
    args = parser.parse_args()

    topology = RabbitMQTopology()
    connection = pika.BlockingConnection(connection_parameters())
    channel = connection.channel()
    topology.declare(channel)
    channel.confirm_delivery()

    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "listing_id": args.listing_id,
        "store": "Amazon",
        "url": args.url,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    # confirm_delivery faz o Pika lançar uma exceção em nack/unroutable.
    # O retorno pode ser None mesmo quando a publicação foi confirmada.
    channel.basic_publish(
        exchange=topology.commands_exchange,
        routing_key=topology.request_routing_key,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=event_id,
            correlation_id=event_id,
        ),
        mandatory=True,
    )
    connection.close()
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

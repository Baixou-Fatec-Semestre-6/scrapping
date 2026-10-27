import argparse
import json
import uuid

import pika
from dotenv import load_dotenv

from messaging.topology import RabbitMQTopology, connection_parameters


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Publica um comando de teste para o scraper")
    parser.add_argument("url", help="URL Amazon a raspar")
    parser.add_argument("--product-id", type=int, default=1)
    parser.add_argument("--listing-id", type=int, default=1)
    args = parser.parse_args()

    topology = RabbitMQTopology()
    connection = pika.BlockingConnection(connection_parameters())
    channel = connection.channel()
    topology.declare(channel)
    channel.confirm_delivery()

    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "product_id": args.product_id,
        "listing_id": args.listing_id,
        "store": "amazon",
        "url": args.url,
    }
    confirmed = channel.basic_publish(
        exchange=topology.commands_exchange,
        routing_key=topology.request_routing_key,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=request_id,
            correlation_id=request_id,
        ),
        mandatory=True,
    )
    connection.close()
    if not confirmed:
        raise RuntimeError("Comando não confirmado pelo RabbitMQ")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

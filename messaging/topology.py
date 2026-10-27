import os

import pika


class RabbitMQTopology:
    """Nomes e declaração idempotente da topologia usada pelo scraper."""

    def __init__(self) -> None:
        self.commands_exchange = os.getenv("RABBITMQ_EXCHANGE_COMMANDS", "scrape_commands")
        self.events_exchange = os.getenv("RABBITMQ_EXCHANGE_EVENTS", "price_events")
        self.retry_exchange = os.getenv("RABBITMQ_EXCHANGE_RETRY", "scrape_commands.retry")
        self.dead_letter_exchange = os.getenv("RABBITMQ_EXCHANGE_DLX", "scrape_commands.dlx")
        self.requests_queue = os.getenv("RABBITMQ_QUEUE_REQUESTS", "scrape_requests")
        self.retry_queue = os.getenv("RABBITMQ_QUEUE_RETRY", "scrape_requests.retry")
        self.dead_letter_queue = os.getenv("RABBITMQ_QUEUE_DLQ", "scrape_requests.dlq")
        self.request_routing_key = os.getenv("RABBITMQ_ROUTING_KEY_REQUEST", "scrape.requested")
        self.dead_letter_routing_key = os.getenv("RABBITMQ_ROUTING_KEY_DLQ", "scrape.dead")
        self.retry_delay_ms = int(os.getenv("RABBITMQ_RETRY_DELAY_MS", "30000"))

    def declare(self, channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
        channel.exchange_declare(self.commands_exchange, "topic", durable=True)
        channel.exchange_declare(self.events_exchange, "topic", durable=True)
        channel.exchange_declare(self.retry_exchange, "topic", durable=True)
        channel.exchange_declare(self.dead_letter_exchange, "topic", durable=True)

        channel.queue_declare(
            queue=self.requests_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": self.dead_letter_exchange,
                "x-dead-letter-routing-key": self.dead_letter_routing_key,
            },
        )
        channel.queue_bind(
            queue=self.requests_queue,
            exchange=self.commands_exchange,
            routing_key=self.request_routing_key,
        )

        channel.queue_declare(
            queue=self.retry_queue,
            durable=True,
            arguments={
                "x-message-ttl": self.retry_delay_ms,
                "x-dead-letter-exchange": self.commands_exchange,
                "x-dead-letter-routing-key": self.request_routing_key,
            },
        )
        channel.queue_bind(
            queue=self.retry_queue,
            exchange=self.retry_exchange,
            routing_key=self.request_routing_key,
        )

        channel.queue_declare(queue=self.dead_letter_queue, durable=True)
        channel.queue_bind(
            queue=self.dead_letter_queue,
            exchange=self.dead_letter_exchange,
            routing_key=self.dead_letter_routing_key,
        )


def connection_parameters() -> pika.ConnectionParameters:
    rabbitmq_url = os.getenv("RABBITMQ_URL", "").strip()
    if rabbitmq_url:
        parameters = pika.URLParameters(rabbitmq_url)
        parameters.heartbeat = int(os.getenv("RABBITMQ_HEARTBEAT", "60"))
        parameters.blocked_connection_timeout = int(
            os.getenv("RABBITMQ_BLOCKED_CONNECTION_TIMEOUT", "30")
        )
        return parameters

    credentials = pika.PlainCredentials(
        os.getenv("RABBITMQ_USER", "guest"),
        os.getenv("RABBITMQ_PASS", "guest"),
    )
    return pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        credentials=credentials,
        heartbeat=int(os.getenv("RABBITMQ_HEARTBEAT", "60")),
        blocked_connection_timeout=int(
            os.getenv("RABBITMQ_BLOCKED_CONNECTION_TIMEOUT", "30")
        ),
        connection_attempts=int(os.getenv("RABBITMQ_CONNECTION_ATTEMPTS", "5")),
        retry_delay=int(os.getenv("RABBITMQ_CONNECTION_RETRY_DELAY", "5")),
    )

import os
import unittest
from unittest.mock import patch

from messaging.consumer import InvalidScrapeRequest, RabbitMQConsumer
from messaging.contract_publisher import ContractPublisher


class ConsumerContractTest(unittest.TestCase):
    def test_decodes_valid_command(self):
        payload = RabbitMQConsumer._decode(
            b'{"event_id":"event-1","listing_id":20,"url":"https://www.amazon.com.br/dp/B09TWDYSVP"}'
        )
        self.assertEqual(payload["event_id"], "event-1")
        self.assertEqual(payload["listing_id"], 20)

    def test_rejects_invalid_json(self):
        with self.assertRaises(InvalidScrapeRequest):
            RabbitMQConsumer._decode(b"not-json")

    def test_requires_event_listing_and_url(self):
        for body in (
            b"{}",
            b'{"event_id":"event-1","listing_id":20}',
            b'{"event_id":"event-1","url":"https://x"}',
            b'{"listing_id":20,"url":"https://x"}',
        ):
            with self.subTest(body=body), self.assertRaises(InvalidScrapeRequest):
                RabbitMQConsumer._decode(body)


class PublisherPayloadTest(unittest.TestCase):
    @patch.dict(os.environ, {"RABBITMQ_ENABLED": "False"})
    def test_success_payload_contains_correlation_fields(self):
        publisher = ContractPublisher()
        publisher.publish_scraped_event(
            event_id="event-1",
            listing_id=20,
            title="Produto",
            price=99.9,
            currency="BRL",
            image_url="https://example.com/image.jpg",
        )
        event = publisher.published_events[0]
        self.assertEqual(event["event_id"], "event-1")
        self.assertEqual(event["listing_id"], 20)
        self.assertNotIn("product_id", event)
        self.assertNotIn("url", event)


if __name__ == "__main__":
    unittest.main()

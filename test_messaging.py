import os
import unittest
from unittest.mock import patch

from messaging.consumer import InvalidScrapeRequest, RabbitMQConsumer
from messaging.publisher import RabbitMQPublisher


class ConsumerContractTest(unittest.TestCase):
    def test_decodes_valid_command(self):
        payload = RabbitMQConsumer._decode(
            b'{"request_id":"request-1","url":"https://www.amazon.com.br/dp/B09TWDYSVP"}'
        )
        self.assertEqual(payload["request_id"], "request-1")

    def test_rejects_invalid_json(self):
        with self.assertRaises(InvalidScrapeRequest):
            RabbitMQConsumer._decode(b"not-json")

    def test_requires_request_id_and_url(self):
        for body in (b"{}", b'{"request_id":"request-1"}', b'{"url":"https://x"}'):
            with self.subTest(body=body), self.assertRaises(InvalidScrapeRequest):
                RabbitMQConsumer._decode(body)


class PublisherPayloadTest(unittest.TestCase):
    @patch.dict(os.environ, {"RABBITMQ_ENABLED": "False"})
    def test_success_payload_contains_correlation_fields(self):
        publisher = RabbitMQPublisher()
        publisher.publish_scraped_event(
            request_id="request-1",
            product_id=10,
            listing_id=20,
            store="amazon",
            url="https://www.amazon.com.br/dp/B09TWDYSVP",
            title="Produto",
            price=99.9,
            currency="BRL",
            image_url="https://example.com/image.jpg",
        )
        event = publisher.published_events[0]
        self.assertEqual(event["event"], "price.scraped")
        self.assertEqual(event["request_id"], "request-1")
        self.assertEqual(event["listing_id"], 20)


if __name__ == "__main__":
    unittest.main()

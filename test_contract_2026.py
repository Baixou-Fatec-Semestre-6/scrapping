import os
import unittest
from unittest.mock import Mock, patch

from messaging.consumer import InvalidScrapeRequest, RabbitMQConsumer
from messaging.contract_publisher import ContractPublisher


class ScrapeContract2026Test(unittest.TestCase):
    def test_request_requires_event_and_listing(self):
        payload = RabbitMQConsumer._decode(
            b'{"event_id":"event-1","listing_id":20,"url":"https://example.com/product"}'
        )
        self.assertEqual(payload["event_id"], "event-1")
        self.assertEqual(payload["listing_id"], 20)
        with self.assertRaises(InvalidScrapeRequest):
            RabbitMQConsumer._decode(b'{"event_id":"event-1","url":"https://x"}')

    @patch.dict(os.environ, {"RABBITMQ_ENABLED": "False"})
    def test_completed_payload_matches_contract(self):
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

    @patch.dict(os.environ, {"RABBITMQ_ENABLED": "False"})
    def test_none_publish_return_is_a_confirmed_delivery(self):
        publisher = ContractPublisher()
        publisher.enabled = True
        publisher.ensure_connection = Mock()
        publisher.channel = Mock()
        publisher.channel.basic_publish.return_value = None

        published = publisher.publish_failed_event(
            event_id="event-1",
            listing_id=20,
            reason="Página não encontrada.",
        )

        self.assertTrue(published)
        publisher.channel.basic_publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()

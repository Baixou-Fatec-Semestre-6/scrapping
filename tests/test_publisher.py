import os
import unittest
from unittest.mock import patch

from messaging.contract_publisher import ContractPublisher


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

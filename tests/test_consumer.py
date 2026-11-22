import unittest

from messaging.consumer import InvalidScrapeRequest, RabbitMQConsumer


class ConsumerContractTest(unittest.TestCase):
    def test_decodes_valid_command(self):
        payload = RabbitMQConsumer._decode(
            b'{"event_id":"event-1","listing_id":20,"url":"https://example.com/product"}'
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
            with self.subTest(body=body):
                with self.assertRaises(InvalidScrapeRequest):
                    RabbitMQConsumer._decode(body)


if __name__ == "__main__":
    unittest.main()

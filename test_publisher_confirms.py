import unittest
from unittest.mock import Mock, patch

import pika

from messaging.publisher import RabbitMQPublisher


class PublisherConfirmationTest(unittest.TestCase):
    def publish_calls(self, publisher):
        return (
            lambda: publisher.publish_scraped_event(
                product_id=1, url="https://www.amazon.com.br/dp/B09TWDYSVP",
                title="Produto", price=99.9, currency="BRL", image_url=None,
            ),
            lambda: publisher.publish_failed_event(
                product_id=1, url="https://www.amazon.com.br/dp/B09TWDYSVP",
                reason="timeout",
            ),
        )

    @patch.object(RabbitMQPublisher, "connect")
    def test_confirmed_publish_accepts_none_return(self, _connect):
        publisher = RabbitMQPublisher(required=True)
        publisher.connection = Mock(is_closed=False)
        publisher.channel = Mock(is_closed=False)
        publisher.channel.basic_publish.return_value = None
        for publish, routing_key in zip(
            self.publish_calls(publisher), ("price.scraped", "price.failed")
        ):
            with self.subTest(routing_key=routing_key):
                self.assertTrue(publish())
                self.assertEqual(
                    publisher.channel.basic_publish.call_args.kwargs["routing_key"],
                    routing_key,
                )

    @patch.object(RabbitMQPublisher, "connect")
    def test_publish_failure_still_propagates(self, _connect):
        publisher = RabbitMQPublisher(required=True)
        publisher.connection = Mock(is_closed=False)
        publisher.channel = Mock(is_closed=False)
        for error_type in (pika.exceptions.NackError, pika.exceptions.UnroutableError):
            for publish in self.publish_calls(publisher):
                error = error_type([])
                publisher.channel.basic_publish.side_effect = error
                with self.subTest(error=error_type.__name__), self.assertRaises(error_type) as caught:
                    publish()
                self.assertIs(caught.exception, error)


if __name__ == "__main__":
    unittest.main()

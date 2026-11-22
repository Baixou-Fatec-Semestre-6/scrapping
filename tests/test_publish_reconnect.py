import unittest
from unittest import mock

from pika.exceptions import StreamLostError

from messaging.consumer import RabbitMQConsumer
from messaging.contract_publisher import ContractPublisher


def _publisher_with(connections):
    """ContractPublisher ativo cujo connect() entrega as conexões falsas em ordem."""
    publisher = ContractPublisher.__new__(ContractPublisher)
    publisher.enabled = True
    publisher.required = True
    publisher.exchange = "baixou"
    publisher.published_events = []
    publisher.connection = None
    publisher.channel = None
    pending = list(connections)

    def connect():
        conn = pending.pop(0)
        publisher.connection = conn
        publisher.channel = conn.channel()

    publisher.connect = connect
    return publisher


def _fake_connection(dead=False):
    conn = mock.MagicMock()
    conn.is_closed = False
    conn.channel.return_value.is_closed = False
    if dead:
        conn.process_data_events.side_effect = StreamLostError("Connection reset by peer")
    return conn


class PublishReconnectTest(unittest.TestCase):
    def test_reconnects_and_republishes_when_idle_connection_was_dropped(self):
        dead, fresh = _fake_connection(dead=True), _fake_connection()
        publisher = _publisher_with([dead, fresh])

        self.assertTrue(publisher._publish_contract("scrape.completed", {"event_id": "e1"}))

        dead.channel.return_value.basic_publish.assert_not_called()
        fresh.channel.return_value.basic_publish.assert_called_once()
        self.assertEqual(
            fresh.channel.return_value.basic_publish.call_args.kwargs["routing_key"],
            "scrape.completed",
        )

    def test_raises_when_broker_stays_unreachable(self):
        publisher = _publisher_with([_fake_connection(dead=True), _fake_connection(dead=True)])
        with self.assertRaises(StreamLostError):
            publisher._publish_contract("scrape.completed", {"event_id": "e1"})


class PublishFailureIsNotScrapeFailureTest(unittest.TestCase):
    def test_publish_error_requeues_instead_of_reporting_failed(self):
        consumer = RabbitMQConsumer.__new__(RabbitMQConsumer)
        consumer.max_retries = 3
        consumer.scraper = mock.Mock()
        consumer.scraper.scrape.return_value = {
            "title": "Produto", "price": 10.0, "currency": "BRL", "image_url": "https://x/img.jpg",
        }
        consumer.publisher = mock.Mock()
        consumer.publisher.publish_scraped_event.side_effect = StreamLostError("reset")
        channel, method, properties = mock.Mock(), mock.Mock(delivery_tag=7), mock.Mock(headers={})

        consumer._on_message(
            channel, method, properties,
            b'{"event_id":"e1","listing_id":1,"url":"https://www.amazon.com.br/dp/X"}',
        )

        consumer.publisher.publish_failed_event.assert_not_called()
        channel.basic_nack.assert_called_once_with(7, requeue=True)
        channel.basic_ack.assert_not_called()


if __name__ == "__main__":
    unittest.main()

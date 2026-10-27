import json
import logging
import os
from datetime import datetime, timezone
import pika
from dotenv import load_dotenv
from messaging.topology import RabbitMQTopology, connection_parameters

# Configura o logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Carrega as variáveis de ambiente
load_dotenv()

class RabbitMQPublisher:
    def __init__(self, required=False):
        self.host = os.getenv("RABBITMQ_HOST", "localhost")
        self.port = int(os.getenv("RABBITMQ_PORT", 5672))
        self.username = os.getenv("RABBITMQ_USER", "guest")
        self.password = os.getenv("RABBITMQ_PASS", "guest")
        self.topology = RabbitMQTopology()
        self.exchange = self.topology.events_exchange
        
        self.enabled = required or os.getenv("RABBITMQ_ENABLED", "True").lower() in ("true", "1", "yes")
        self.required = required
        self.published_events = []
        
        self.connection = None
        self.channel = None
        if self.enabled:
            self.connect()
        else:
            logger.info("Publicador do RabbitMQ está DESATIVADO localmente (RABBITMQ_ENABLED=False).")

    def connect(self):
        """Estabelece a conexão e declara as exchanges necessárias."""
        if not self.enabled:
            return
        try:
            self.connection = pika.BlockingConnection(connection_parameters())
            self.channel = self.connection.channel()
            self.topology.declare(self.channel)
            self.channel.confirm_delivery()
            logger.info(f"Conectado ao RabbitMQ e exchange '{self.exchange}' declarada.")
        except Exception as e:
            logger.error(f"Erro ao conectar ao RabbitMQ: {e}")
            self.connection = None
            self.channel = None
            if self.required:
                raise

    def ensure_connection(self):
        """Garante que a conexão e o canal estejam ativos."""
        if not self.enabled:
            return
        if not self.connection or self.connection.is_closed or not self.channel or self.channel.is_closed:
            logger.info("Reconectando ao RabbitMQ...")
            self.connect()

    def publish_scraped_event(self, product_id, url, title, price, currency, image_url, scraped_at=None, request_id=None, listing_id=None, store="amazon"):
        """Publica um evento de sucesso 'price.scraped'."""
        if scraped_at is None:
            scraped_at = datetime.now(timezone.utc).isoformat()

        payload = {
            "event": "price.scraped",
            "request_id": request_id,
            "product_id": product_id,
            "listing_id": listing_id,
            "store": store,
            "url": url,
            "title": title,
            "price": float(price) if price is not None else None,
            "currency": currency or "BRL",
            "image_url": image_url,
            "scraped_at": scraped_at
        }
        
        self.published_events.append(payload)
        
        if not self.enabled:
            logger.info(f"[SIMULAÇÃO] Sucesso coletado localmente para URL: {url}")
            return True

        self.ensure_connection()
        if not self.channel:
            raise RuntimeError("rabbitmq_unavailable")
        
        routing_key = "price.scraped"
        try:
            confirmed = self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(payload),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent
                )
            )
            if not confirmed:
                raise RuntimeError("rabbitmq_publish_not_confirmed")
            logger.info(f"Evento '{routing_key}' publicado com sucesso para URL: {url}")
            return True
        except Exception as e:
            logger.error(f"Erro ao publicar evento '{routing_key}': {e}")
            raise

    def publish_failed_event(self, product_id, url, reason, scraped_at=None, request_id=None, listing_id=None, store="amazon"):
        """Publica um evento de falha 'price.failed'."""
        if scraped_at is None:
            scraped_at = datetime.now(timezone.utc).isoformat()

        payload = {
            "event": "price.failed",
            "request_id": request_id,
            "product_id": product_id,
            "listing_id": listing_id,
            "store": store,
            "url": url,
            "reason": reason, # "blocked", "timeout", "not_found", "parse_error"
            "scraped_at": scraped_at
        }
        
        self.published_events.append(payload)
        
        if not self.enabled:
            logger.info(f"[SIMULAÇÃO] Falha coletada localmente para URL: {url} (razão: {reason})")
            return True

        self.ensure_connection()
        if not self.channel:
            raise RuntimeError("rabbitmq_unavailable")
        
        routing_key = "price.failed"
        try:
            confirmed = self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(payload),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent
                )
            )
            if not confirmed:
                raise RuntimeError("rabbitmq_publish_not_confirmed")
            logger.info(f"Evento '{routing_key}' publicado com sucesso para URL: {url} (razão: {reason})")
            return True
        except Exception as e:
            logger.error(f"Erro ao publicar evento '{routing_key}': {e}")
            raise

    def close(self):
        """Fecha a conexão com o RabbitMQ."""
        if not self.enabled:
            return
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                logger.info("Conexão com o RabbitMQ fechada de forma limpa.")
        except Exception as e:
            logger.error(f"Erro ao fechar conexão com o RabbitMQ: {e}")

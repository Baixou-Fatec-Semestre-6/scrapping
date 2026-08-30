import json
import logging
import os
from datetime import datetime, timezone
import pika
from dotenv import load_dotenv

# Configura o logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Carrega as variáveis de ambiente
load_dotenv()

class RabbitMQPublisher:
    def __init__(self):
        self.host = os.getenv("RABBITMQ_HOST", "localhost")
        self.port = int(os.getenv("RABBITMQ_PORT", 5672))
        self.username = os.getenv("RABBITMQ_USER", "guest")
        self.password = os.getenv("RABBITMQ_PASS", "guest")
        self.exchange = os.getenv("RABBITMQ_EXCHANGE_EVENTS", "price_events")
        
        self.enabled = os.getenv("RABBITMQ_ENABLED", "True").lower() in ("true", "1", "yes")
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
            rabbitmq_url = os.getenv("RABBITMQ_URL")
            if rabbitmq_url:
                parameters = pika.URLParameters(rabbitmq_url)
                logger.info("Usando URL de conexão do RabbitMQ (RABBITMQ_URL).")
            else:
                credentials = pika.PlainCredentials(self.username, self.password)
                parameters = pika.ConnectionParameters(
                    host=self.host,
                    port=self.port,
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declara a exchange do tipo topic como especificado
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type="topic",
                durable=True
            )
            logger.info(f"Conectado ao RabbitMQ e exchange '{self.exchange}' declarada.")
        except Exception as e:
            logger.error(f"Erro ao conectar ao RabbitMQ: {e}")
            self.connection = None
            self.channel = None

    def ensure_connection(self):
        """Garante que a conexão e o canal estejam ativos."""
        if not self.enabled:
            return
        if not self.connection or self.connection.is_closed or not self.channel or self.channel.is_closed:
            logger.info("Reconectando ao RabbitMQ...")
            self.connect()

    def publish_scraped_event(self, product_id, url, title, price, currency, image_url, scraped_at=None):
        """Publica um evento de sucesso 'price.scraped'."""
        if scraped_at is None:
            scraped_at = datetime.now(timezone.utc).isoformat()

        payload = {
            "event": "price.scraped",
            "product_id": product_id,
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
            logger.error("Não foi possível publicar o evento: sem conexão ativa com o RabbitMQ.")
            return False
        
        routing_key = "price.scraped"
        try:
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(payload),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent
                )
            )
            logger.info(f"Evento '{routing_key}' publicado com sucesso para URL: {url}")
            return True
        except Exception as e:
            logger.error(f"Erro ao publicar evento '{routing_key}': {e}")
            return False

    def publish_failed_event(self, product_id, url, reason, scraped_at=None):
        """Publica um evento de falha 'price.failed'."""
        if scraped_at is None:
            scraped_at = datetime.now(timezone.utc).isoformat()

        payload = {
            "event": "price.failed",
            "product_id": product_id,
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
            logger.error("Não foi possível publicar o evento: sem conexão ativa com o RabbitMQ.")
            return False
        
        routing_key = "price.failed"
        try:
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(payload),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent
                )
            )
            logger.info(f"Evento '{routing_key}' publicado com sucesso para URL: {url} (razão: {reason})")
            return True
        except Exception as e:
            logger.error(f"Erro ao publicar evento '{routing_key}': {e}")
            return False

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

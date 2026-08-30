import json
import logging
import os
import time
import pika
from dotenv import load_dotenv

# Configura o logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] consumer: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("test_consumer")

# Carrega configurações
load_dotenv()

def run_consumer():
    rabbitmq_url = os.getenv("RABBITMQ_URL")
    exchange = os.getenv("RABBITMQ_EXCHANGE_EVENTS", "price_events")
    
    logger.info("Iniciando Consumidor de Teste para o RabbitMQ...")

    while True:
        try:
            if rabbitmq_url:
                parameters = pika.URLParameters(rabbitmq_url)
                logger.info("Conectando usando a URL de conexão do RabbitMQ (RABBITMQ_URL)...")
            else:
                host = os.getenv("RABBITMQ_HOST", "localhost")
                port = int(os.getenv("RABBITMQ_PORT", 5672))
                username = os.getenv("RABBITMQ_USER", "guest")
                password = os.getenv("RABBITMQ_PASS", "guest")
                logger.info(f"Conectando ao host local {host}:{port}...")
                credentials = pika.PlainCredentials(username, password)
                parameters = pika.ConnectionParameters(
                    host=host,
                    port=port,
                    credentials=credentials,
                    heartbeat=600
                )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            # 1. Garante que a exchange de tópicos 'price_events' existe
            channel.exchange_declare(
                exchange=exchange,
                exchange_type="topic",
                durable=True
            )
            
            # 2. Cria uma fila temporária exclusiva para este console de teste
            # (Ela será excluída automaticamente quando o script fechar)
            result = channel.queue_declare(queue="test_backoffice_events_queue", durable=True)
            queue_name = result.method.queue
            
            # 3. Faz o binding da fila com a exchange para receber ambos os eventos:
            # - price.scraped (sucesso)
            # - price.failed (falha)
            # O padrão "price.*" escuta qualquer chave que comece com "price."
            routing_key_pattern = "price.*"
            channel.queue_bind(
                exchange=exchange,
                queue=queue_name,
                routing_key=routing_key_pattern
            )
            
            logger.info(f"Fila '{queue_name}' vinculada com a exchange '{exchange}' com a chave '{routing_key_pattern}'.")
            
            def callback(ch, method, properties, body):
                try:
                    payload = json.loads(body.decode())
                    event_type = payload.get("event", "desconhecido")
                    url = payload.get("url", "N/A")
                    
                    print("\n" + "📥 [NOVA MENSAGEM RECEBIDA DO RABBITMQ] " + "="*40)
                    print(f"Chave de Roteamento: {method.routing_key}")
                    print(f"Tipo de Evento:      {event_type}")
                    
                    if event_type == "price.scraped":
                        print(f"Título do Produto:   {payload.get('title')}")
                        print(f"Preço Extraído:      {payload.get('price')} {payload.get('currency')}")
                        print(f"URL da Imagem:       {payload.get('image_url')}")
                    elif event_type == "price.failed":
                        print(f"URL com erro:        {url}")
                        print(f"Razão do Erro:       {payload.get('reason')}")
                        
                    print(f"Timestamp do Evento: {payload.get('scraped_at')}")
                    print("="*80 + "\n")
                    
                except Exception as e:
                    logger.error(f"Erro ao processar mensagem recebida: {e}")
                
                # Confirma recebimento da mensagem
                ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=queue_name, on_message_callback=callback)
            logger.info("Consumidor ativo e aguardando eventos. Pressione Ctrl+C para sair.\n")
            channel.start_consuming()
            
        except pika.exceptions.AMQPConnectionError:
            logger.warning("Não foi possível conectar ao RabbitMQ. Tentando novamente em 5 segundos...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Consumidor encerrado pelo usuário.")
            break
        except Exception as e:
            logger.error(f"Erro inesperado: {e}. Reiniciando em 5 segundos...")
            time.sleep(5)

if __name__ == "__main__":
    run_consumer()

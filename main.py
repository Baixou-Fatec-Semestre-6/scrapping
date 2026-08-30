import argparse
import json
import logging
import os
import random
import time
from dotenv import load_dotenv

from messaging.publisher import RabbitMQPublisher
from parser.amazon_scraper import AmazonScraper
from parser.amazon_crawler import AmazonCrawler

# Configura o logger padrão para exibir no console de forma bonita e limpa
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("main")

# Carrega as configurações do arquivo .env
load_dotenv()

def run_batch():
    """Vareja a categoria de tecnologia de forma paginada e raspa os produtos até atingir a meta de 100 sucessos."""
    target_success = int(os.getenv("MAX_CRAWL_PRODUCTS", 100))
    logger.info(f"Iniciando modo BATCH... Meta de Sucessos: {target_success} produtos de tecnologia.")
    
    crawler = AmazonCrawler()
    scraper = AmazonScraper()
    publisher = RabbitMQPublisher()
    
    # Coleta mais links do que o alvo de sucesso para tolerar possíveis falhas e atingir exatamente o alvo
    candidate_urls = crawler.discover_urls(max_urls=int(target_success * 1.5))
    
    if not candidate_urls:
        logger.error("Nenhuma URL de tecnologia foi descoberta pelo crawler. Abortando execução.")
        return

    logger.info(f"Total de {len(candidate_urls)} URLs candidatas coletadas. Iniciando raspagem individual...")
    
    success_count = 0
    fail_count = 0
    
    for idx, url in enumerate(candidate_urls, 1):
        if success_count >= target_success:
            logger.info(f"Meta de {target_success} produtos raspados com sucesso foi atingida!")
            break
            
        logger.info(f"[{idx}/{len(candidate_urls)}] Processando URL: {url} | Progresso: {success_count}/{target_success}")
        
        try:
            # Executa a raspagem
            result = scraper.scrape(url)
            # Envia evento de sucesso (ou acumula simulado)
            publisher.publish_scraped_event(
                product_id=None, # Busca dinâmica não tem ID de banco de dados pré-definido
                url=result["url"],
                title=result["title"],
                price=result["price"],
                currency=result["currency"],
                image_url=result["image_url"]
            )
            success_count += 1
        except Exception as scrape_err:
            reason = str(scrape_err)
            if reason not in ["blocked", "timeout", "not_found", "parse_error"]:
                reason = "parse_error"
            
            logger.error(f"Falha ao processar URL {url}: {reason}")
            # Envia evento de falha (ou acumula simulado)
            publisher.publish_failed_event(
                product_id=None,
                url=url,
                reason=reason
            )
            fail_count += 1
            
        # Atraso dinâmico de segurança entre requisições
        if idx < len(candidate_urls) and success_count < target_success:
            delay = random.uniform(
                float(os.getenv("SCRAPE_DELAY_MIN", 2)),
                float(os.getenv("SCRAPE_DELAY_MAX", 5))
            )
            logger.info(f"Aguardando {delay:.2f} segundos...")
            time.sleep(delay)
            
    # Fecha conexões
    publisher.close()
    logger.info(f"Processamento em lote concluído. Sucessos obtidos: {success_count}/{target_success} | Falhas: {fail_count}")

    # Salva todos os eventos estruturados em um arquivo JSON local e imprime
    output_path = os.getenv("OUTPUT_JSON_PATH", "scraped_results.json")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(publisher.published_events, f, indent=2, ensure_ascii=False)
        logger.info(f"Lista final de mensagens geradas salva com sucesso em '{output_path}'.")
        
        logger.info(
            f"JSON DE PRODUTOS PARA ENVIAR ({len(publisher.published_events)} itens):\n"
            f"{json.dumps(publisher.published_events, indent=2, ensure_ascii=False)}"
        )
    except Exception as e:
        logger.error(f"Erro ao salvar arquivo de saída de mensagens '{output_path}': {e}")

def run_test(url: str):
    """Executa o scrape de uma única URL e exibe os resultados na tela para debug rápido."""
    logger.info(f"Iniciando raspagem de teste para: {url}")
    scraper = AmazonScraper()
    try:
        result = scraper.scrape(url)
        logger.info(
            f"RESULTADO DA RASPAGEM DE TESTE:\n"
            f"URL Limpa:  {result['url']}\n"
            f"Título:     {result['title']}\n"
            f"Preço:      {result['price']} {result['currency']}\n"
            f"Imagem URL: {result['image_url']}"
        )
    except Exception as e:
        logger.error(
            f"FALHA DE RASPAGEM NO TESTE:\n"
            f"URL:        {url}\n"
            f"Erro:       {e}"
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serviço de Scrape de Preços da Amazon em Python (Modo Lote)")
    parser.add_argument(
        "--mode", 
        choices=["batch", "test"], 
        default="batch",
        help="Modo de execução: 'batch' (lote dinâmico) ou 'test' (teste local)"
    )
    parser.add_argument(
        "--url",
        help="URL do produto Amazon para usar com o modo 'test'"
    )
    
    args = parser.parse_args()
    
    if args.mode == "batch":
        run_batch()
    elif args.mode == "test":
        if not args.url:
            parser.error("O modo 'test' requer a especificação de uma URL com '--url <link>'.")
        run_test(args.url)

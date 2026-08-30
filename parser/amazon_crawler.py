import logging
import random
import time
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

from .amazon_scraper import clean_amazon_url, HEADERS, is_blocked_or_captcha

logger = logging.getLogger(__name__)
load_dotenv()

# Fontes redundantes de tecnologia: nós de categoria e buscas por termos gerais
SOURCES = [
    {"type": "category", "value": "16209062011"}, # Eletrônicos e Tecnologia
    {"type": "category", "value": "16339926011"}, # Computadores e Informática
    {"type": "search", "value": "tecnologia"},
    {"type": "search", "value": "eletronicos"}
]

class AmazonCrawler:
    def __init__(self):
        self.playwright_headless = os.getenv("PLAYWRIGHT_HEADLESS", "True").lower() in ("true", "1", "yes")

    def discover_urls(self, max_urls: int = 150) -> list:
        """Busca URLs de produtos de tecnologia paginando pelas categorias/buscas da Amazon."""
        discovered_urls = set()
        
        logger.info(f"Iniciando descoberta de URLs. Meta: Coletar pelo menos {max_urls} links candidatos.")
        
        for source in SOURCES:
            if len(discovered_urls) >= max_urls:
                break
                
            page = 1
            max_pages = 5 # Limita a navegação de páginas para evitar detecção
            
            # Reconstrói a URL dependendo se é categoria (nó) ou busca textual
            if source["type"] == "category":
                logger.info(f"Vasculhando nó de categoria Amazon: {source['value']}...")
            else:
                logger.info(f"Vasculhando resultados de busca por palavra-chave: '{source['value']}'...")
                
            while page <= max_pages and len(discovered_urls) < max_urls:
                if source["type"] == "category":
                    search_url = f"https://www.amazon.com.br/s?rh=n%3A{source['value']}&page={page}"
                else:
                    query = urllib.parse.quote_plus(source["value"])
                    search_url = f"https://www.amazon.com.br/s?k={query}&page={page}"
                    
                logger.info(f"Lendo Página {page} (Acumulado: {len(discovered_urls)} URLs)...")
                
                html_content = None
                
                # 1. Tenta baixar a página com HTTPX
                try:
                    with httpx.Client(http2=True, headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
                        response = client.get(search_url)
                        if response.status_code == 200 and not is_blocked_or_captcha(response.text, response.status_code):
                            # Valida se realmente extraímos links com HTTPX
                            temp_urls = self._parse_search_results(response.text)
                            if len(temp_urls) > 0:
                                html_content = response.text
                                logger.info("Links encontrados no HTML via HTTPX.")
                            else:
                                logger.warning("Nenhum link de produto encontrado no HTML do HTTPX. Ativando Playwright...")
                        else:
                            logger.warning(f"HTTPX retornou status {response.status_code} ou captcha. Ativando Playwright...")
                except Exception as e:
                    logger.error(f"Erro na busca com HTTPX para pág {page}: {e}. Ativando Playwright...")
                
                # 2. Se falhar ou não encontrar links, tenta com Playwright
                if not html_content:
                    try:
                        html_content = self._fetch_search_with_playwright(search_url)
                    except Exception as e:
                        logger.error(f"Erro no Playwright ao carregar pág {page}: {e}")
                        
                # 3. Faz o parse da página de listagem
                if html_content:
                    urls_on_page = self._parse_search_results(html_content)
                    if not urls_on_page:
                        logger.warning(f"Nenhum produto extraído na página {page} do recurso. Pulando página.")
                        page += 1
                        continue
                        
                    initial_count = len(discovered_urls)
                    for url in urls_on_page:
                        cleaned = clean_amazon_url(url)
                        if cleaned and ("dp/" in cleaned or "product/" in cleaned):
                            discovered_urls.add(cleaned)
                            if len(discovered_urls) >= max_urls:
                                break
                                
                    new_links_count = len(discovered_urls) - initial_count
                    logger.info(f"Página {page} processada. {new_links_count} novos links únicos adicionados.")
                else:
                    logger.error(f"Não foi possível obter o HTML da página {page} por nenhum método.")
                
                page += 1
                
                # Delay de evasão dinâmico
                delay = random.uniform(2.5, 5.0)
                logger.info(f"Aguardando {delay:.2f} segundos...")
                time.sleep(delay)

        result_list = list(discovered_urls)
        logger.info(f"Descoberta finalizada. Total de links coletados: {len(result_list)}")
        return result_list

    def _fetch_search_with_playwright(self, url: str) -> str:
        """Abre a página de listagem no Playwright em modo headless para burlar captcha."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright não instalado.")
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.playwright_headless)
                context = browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()
                page.goto(url, wait_until="load", timeout=30000)
                
                # Rola suavemente para baixo para carregar todas as imagens e links
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(random.uniform(2.0, 3.5))
                
                html_content = page.content()
                browser.close()
                
                if is_blocked_or_captcha(html_content):
                    logger.error("Playwright foi bloqueado pela Amazon na listagem de categoria.")
                    return None
                    
                return html_content
        except Exception as e:
            logger.error(f"Erro no Playwright ao buscar URL {url}: {e}")
            return None

    def _parse_search_results(self, html_content: str) -> list:
        """Extrai todos os links de produtos da listagem da categoria."""
        soup = BeautifulSoup(html_content, "html.parser")
        product_links = []
        
        # Encontra todos os links 'a' contendo dp ou product
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            
            # Filtra por links de produtos da Amazon
            if "/dp/" in href or "/gp/product/" in href:
                if href.startswith("/"):
                    href = "https://www.amazon.com.br" + href
                product_links.append(href)
                
        return product_links

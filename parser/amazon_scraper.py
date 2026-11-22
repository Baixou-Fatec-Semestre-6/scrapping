import re
import json
import logging
import random
import time
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

# Configura o logger
logger = logging.getLogger(__name__)
load_dotenv()

# Headers realistas para simular um navegador Chrome no Windows
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0"
}

SUPPORTED_AMAZON_HOSTS = {
    "amazon.com",
    "amazon.com.br",
    "amazon.es",
    "amazon.co.uk",
}


def clean_amazon_url(url: str) -> str:
    """Extrai o ASIN e o domínio da URL da Amazon para gerar uma URL limpa."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("invalid_url")

        domain = (parsed.hostname or "").lower()
        normalized_domain = domain.removeprefix("www.")
        if normalized_domain not in SUPPORTED_AMAZON_HOSTS:
            raise ValueError("unsupported_store")

        domain = f"www.{normalized_domain}"
        
        # Procura por /dp/ASIN ou /gp/product/ASIN
        match = re.search(r'/(dp|gp/product)/([A-Za-z0-9]{10})', url)
        if match:
            asin = match.group(2).upper()
            return f"https://{domain}/dp/{asin}"
        raise ValueError("invalid_amazon_product_url")
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Erro ao limpar URL {url}: {e}")
        raise ValueError("invalid_url") from e

def is_blocked_or_captcha(html_content: str, status_code: int = 200) -> bool:
    """Verifica se fomos bloqueados ou recebemos CAPTCHA."""
    if status_code in [503, 403, 429]:
        return True
    
    lowercase_html = html_content.lower()
    blocked_patterns = [
        "robot check",
        "captcha",
        "digite os caracteres",
        "api-services-support@amazon.com",
        "sorry, we just need to make sure you're not a robot",
        "g-recaptcha"
    ]
    return any(pattern in lowercase_html for pattern in blocked_patterns)

class AmazonScraper:
    def __init__(self):
        self.playwright_headless = os.getenv("PLAYWRIGHT_HEADLESS", "True").lower() in ("true", "1", "yes")

    def scrape(self, url: str) -> dict:
        """Tenta raspar a URL usando HTTPX. Caso seja bloqueado, faz o fallback para o Playwright."""
        try:
            cleaned_url = clean_amazon_url(url)
        except ValueError as exc:
            raise Exception("not_found") from exc
        logger.info(f"Iniciando raspagem de: {cleaned_url}")
        
        # Determina a moeda com base no domínio
        currency = "USD"
        if "amazon.com.br" in cleaned_url:
            currency = "BRL"
        elif "amazon.es" in cleaned_url:
            currency = "EUR"
        elif "amazon.co.uk" in cleaned_url:
            currency = "GBP"

        # Tenta com HTTPX primeiro (HTTP/2 ativado para evitar detecções)
        try:
            with httpx.Client(http2=True, headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
                response = client.get(cleaned_url)
                
                if response.status_code == 404:
                    logger.warning(f"Produto não encontrado (404) na URL: {cleaned_url}")
                    raise Exception("not_found")
                
                if not is_blocked_or_captcha(response.text, response.status_code):
                    logger.info("Raspagem com HTTPX foi bem-sucedida.")
                    return self._parse_html(response.text, cleaned_url, currency)
                else:
                    logger.warning("HTTPX detectou bloqueio ou CAPTCHA. Ativando fallback para Playwright...")
        except Exception as e:
            if str(e) == "not_found":
                raise e
            logger.error(f"Falha na requisição HTTPX para {cleaned_url}: {e}. Ativando fallback para Playwright...")

        # Fallback: Playwright
        return self._scrape_with_playwright(cleaned_url, currency)

    def _scrape_with_playwright(self, url: str, currency: str) -> dict:
        """Abre a página em um navegador real headless para evitar detecção de robôs."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Biblioteca 'playwright' não está instalada ou configurada.")
            raise Exception("blocked")

        try:
            with sync_playwright() as p:
                logger.info("Iniciando navegador Playwright Chromium...")
                browser = p.chromium.launch(headless=self.playwright_headless)
                context = browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()
                
                # Vai para a URL
                page.goto(url, wait_until="load", timeout=30000)
                
                # Aguarda um pequeno delay para renderização de scripts dinâmicos (caso existam)
                time.sleep(random.uniform(1.0, 2.5))
                
                html_content = page.content()
                
                # Verifica se mesmo com Playwright fomos bloqueados
                # (ex: ip banido ou captcha obrigatório)
                if is_blocked_or_captcha(html_content):
                    logger.error("Playwright também foi detectado/bloqueado pela Amazon.")
                    browser.close()
                    raise Exception("blocked")
                
                # Se não contiver o título do produto, pode ser 404
                if "page not found" in page.title().lower() or "página não encontrada" in page.title().lower():
                    logger.warning(f"Playwright detectou página não encontrada (404) para URL: {url}")
                    browser.close()
                    raise Exception("not_found")

                result = self._parse_html(html_content, url, currency)
                browser.close()
                return result
        except Exception as e:
            if str(e) in ["not_found", "blocked"]:
                raise e
            logger.error(f"Erro na execução do Playwright: {e}")
            raise Exception("timeout")

    def _parse_html(self, html_content: str, url: str, currency: str) -> dict:
        """Realiza o parsing do HTML usando BeautifulSoup para extrair informações."""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Extração do Título
        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else None
        
        if not title:
            # Fallback de título
            title_el = soup.select_one("h1.a-size-large")
            if title_el:
                title = title_el.get_text(strip=True)
            else:
                meta_title = soup.find("meta", name="title")
                if meta_title and meta_title.get("content"):
                    title = meta_title["content"].strip()

        if not title:
            logger.error("Não foi possível extrair o título do produto.")
            raise Exception("parse_error")

        # 2. Extração do Preço
        price = None
        price_selectors = [
            "span.a-price span.a-offscreen",
            "span#price_inside_buybox",
            "span#priceblock_ourprice",
            "span#priceblock_dealprice",
            "span.a-size-base.a-color-price",
            "#corePrice_feature_div span.a-price span.a-offscreen",
            "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen"
        ]
        
        for selector in price_selectors:
            price_el = soup.select_one(selector)
            if price_el:
                price_text = price_el.get_text(strip=True)
                price = self._clean_and_parse_price(price_text)
                if price is not None:
                    break

        # Fallback de preço: tenta juntar a parte inteira e decimal
        if price is None:
            whole_el = soup.select_one("span.a-price-whole")
            fraction_el = soup.select_one("span.a-price-fraction")
            if whole_el:
                whole_text = whole_el.get_text(strip=True)
                fraction_text = fraction_el.get_text(strip=True) if fraction_el else "00"
                # Remove pontos de milhares
                whole_text = whole_text.replace(".", "").replace(",", "")
                try:
                    price = float(f"{whole_text}.{fraction_text}")
                except ValueError:
                    pass

        # 3. Extração da URL da Imagem
        if price is None or price <= 0:
            logger.error("Não foi possível extrair um preço válido do produto.")
            raise Exception("parse_error")

        image_url = self._extract_image_url(soup)

        return {
            "title": title,
            "price": price,
            "currency": currency,
            "image_url": image_url,
            "url": url
        }

    def _clean_and_parse_price(self, price_str: str) -> float:
        """Limpa caracteres de moeda e formatação para converter o preço em float."""
        if not price_str:
            return None
        
        # Remove caracteres indesejados mantendo números, vírgulas e pontos
        cleaned = "".join(c for c in price_str if c.isdigit() or c in [',', '.'])
        if not cleaned:
            return None
        
        # Determina formatação decimal
        if ',' in cleaned and '.' in cleaned:
            # Caso tenha os dois, ex: 1.234,56 ou 1,234.56
            if cleaned.rfind(',') > cleaned.rfind('.'):
                # Padrão Brasileiro (1.234,56)
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                # Padrão Americano (1,234.56)
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            # Padrão Brasileiro simplificado (1234,56)
            integer, decimal = cleaned.rsplit(',', 1)
            cleaned = (
                integer + decimal
                if len(decimal) == 3
                else integer + '.' + decimal
            )
        elif '.' in cleaned:
            integer, decimal = cleaned.rsplit('.', 1)
            if len(decimal) == 3:
                cleaned = integer + decimal
            
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _extract_image_url(self, soup: BeautifulSoup) -> str:
        """Busca imagens de alta resolução a partir do atributo data-a-dynamic-image ou fallbacks."""
        # 1. Busca por landingImage
        img_el = soup.select_one("#landingImage")
        if img_el:
            dyn_img = img_el.get("data-a-dynamic-image")
            if dyn_img:
                try:
                    urls = json.loads(dyn_img)
                    if urls:
                        # Retorna a imagem com maior resolução (multiplicando largura x altura)
                        return max(urls.keys(), key=lambda k: urls[k][0] * urls[k][1])
                except Exception:
                    pass
            
            old_hires = img_el.get("data-old-hires")
            if old_hires:
                return old_hires.strip()
            
            src = img_el.get("src")
            if src:
                return src.strip()
        
        # 2. Busca em outros elementos comuns de imagem da Amazon
        for selector in ["#imgBlkFront", "#ebooksImgBlkFront", "img#main-image"]:
            el = soup.select_one(selector)
            if el:
                dyn_img = el.get("data-a-dynamic-image")
                if dyn_img:
                    try:
                        urls = json.loads(dyn_img)
                        if urls:
                            return max(urls.keys(), key=lambda k: urls[k][0] * urls[k][1])
                    except Exception:
                        pass
                src = el.get("src")
                if src:
                    return src.strip()

        # 3. Fallback final para OpenGraph image
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            return og_img["content"].strip()
            
        return None

# Amazon Price Scraper Service

Este é o serviço de **Scraping de Preços da Amazon**, desenvolvido em Python. Ele opera de forma assíncrona, consumindo uma lista local de produtos, raspando suas informações (Título, Preço atual, Moeda, e Imagem) e publicando os eventos de sucesso ou falha em um Broker de Mensageria **RabbitMQ**.

---

## 🛠️ Tecnologias Utilizadas

- **Python 3.14.7** (Retrocompatível com 3.10+)
- **HTTPX (com HTTP/2)**: Para requisições leves de baixa latência e evasão inteligente de bloqueios de rede.
- **BeautifulSoup 4**: Para parsing e extração de dados do HTML estruturado.
- **Playwright (Chromium Headless)**: Fallback automático utilizando um navegador real para carregar a página e contornar captchas se as requisições HTTP normais forem bloqueadas.
- **Pika**: Cliente oficial do RabbitMQ para publicação de eventos.
- **Python-dotenv**: Gerenciamento de segredos e variáveis de ambiente.

---

## 📋 Pré-requisitos

1. **Python 3.10+** (Testado e homologado no Python 3.14.7).
2. **RabbitMQ** em execução (para envio dos eventos de mensageria).

---

## 🚀 Instalação e Configuração

### 1. Criar e Ativar Ambiente Virtual
Crie um ambiente virtual `.venv` para isolar as dependências do projeto:

```powershell
# No PowerShell (Windows):
python -m venv .venv
.venv\Scripts\Activate.ps1

# No Prompt de Comando (Windows CMD):
python -m venv .venv
.venv\Scripts\activate.bat

# No Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar as Dependências
Com o ambiente virtual ativo, instale os pacotes listados no `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 3. Instalar o Navegador do Playwright
Instale o binário do Chromium utilizado pelo Playwright como fallback de segurança contra captchas:

```bash
playwright install chromium
```

### 4. Configurar as Variáveis de Ambiente (`.env`)
Certifique-se de configurar o arquivo `.env` localizado na raiz do projeto com as credenciais do seu RabbitMQ local ou de produção:

```ini
# Configurações do RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_EXCHANGE_EVENTS=price_events

# Configurações do Scraper
SCRAPE_DELAY_MIN=2
SCRAPE_DELAY_MAX=5
PLAYWRIGHT_HEADLESS=True
MAX_CRAWL_PRODUCTS=100
PRODUCTS_JSON_PATH=products.json
```

---

## 📂 Arquivo de Entrada (`products.json`)

No modo de execução padrão em lote (Batch), o scraper consome o arquivo local configurado em `PRODUCTS_JSON_PATH` (padrão: `products.json`). Crie o arquivo na raiz da pasta com o seguinte formato:

```json
[
  {
    "product_id": 1,
    "url": "https://www.amazon.com.br/dp/B09B8VGCR8"
  },
  {
    "product_id": 2,
    "url": "https://www.amazon.com.br/dp/B082XYKBLT"
  }
]
```

---

## 🏃 Como Executar os Modos do Scraper

O script principal `main.py` aceita argumentos de linha de comando para definir a execução:

### A. Executar em Lote (Modo Batch - Padrão)
Lê o arquivo `products.json`, processa sequencialmente os produtos aplicando delays aleatórios, publica os eventos no RabbitMQ e finaliza a execução de forma limpa. Ideal para agendamentos (ex: Cron jobs rodando 2 vezes ao dia):

```bash
python main.py --mode batch
# ou simplesmente:
python main.py
```

### B. Executar um Teste Rápido de Raspagem
Testa a raspagem de uma única URL diretamente no console para validação visual e de seletores HTML, **sem depender de conexão com o RabbitMQ**:

```bash
python main.py --mode test --url "https://www.amazon.com.br/dp/B09B8VGCR8"
```

### C. Executar a Varredura Autônoma (Modo Crawler)
Executa a busca autônoma de até 100 produtos de tecnologia na Amazon, extrai seus dados e publica os resultados no RabbitMQ com `product_id: null` para indexação inicial no banco de dados centralizado:

```bash
python main.py --mode crawler
```

---

## 📥 Estrutura de Mensagens Publicadas (RabbitMQ Exchange `price_events`)

### 1. Sucesso (`price.scraped`)
Publicado quando a página foi acessada e os dados do produto foram extraídos com sucesso.

```json
{
  "event": "price.scraped",
  "product_id": 1,
  "url": "https://www.amazon.com.br/dp/B09B8VGCR8",
  "title": "Echo Dot (Geração mais recente) | Smart speaker com Alexa",
  "price": 329.00,
  "currency": "BRL",
  "image_url": "https://m.media-amazon.com/images/I/61evEYmxBZL._AC_SX679_.jpg",
  "scraped_at": "2026-08-29T23:05:00Z"
}
```

### 2. Falha (`price.failed`)
Publicado em caso de falha de carregamento ou extração do produto.

```json
{
  "event": "price.failed",
  "product_id": 2,
  "url": "https://www.amazon.com.br/dp/B082XYKBLT",
  "reason": "not_found",
  "scraped_at": "2026-08-29T23:05:00Z"
}
```
*Razões de erro comuns no campo `reason`: `"not_found"` (404), `"blocked"` (IP bloqueado ou captcha persistente), `"timeout"` (tempo de carregamento estourado) ou `"parse_error"` (página mudou de layout).*

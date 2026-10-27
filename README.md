# Amazon Price Scraper Service

O serviço possui um worker RabbitMQ contínuo, com ACK manual, publisher confirms, retry com TTL e dead-letter queue. O modo em lote permanece disponível para descoberta inicial de catálogo.

Este é o serviço de **Scraping de Preços da Amazon**, desenvolvido em Python. Ele opera de forma assíncrona para varrer páginas de categorias de tecnologia da Amazon, paginar seus resultados, raspar os dados dos produtos individuais (Título, Preço atual, Moeda e Imagem) de forma resiliente contra bloqueios e publicar os eventos de sucesso ou falha em um Broker de Mensageria **RabbitMQ** ou gerar um relatório JSON consolidado localmente.

---

## 🛠️ Tecnologias Utilizadas

- **Python 3.14.7** (Retrocompatível com 3.10+)
- **HTTPX (com HTTP/2)**: Para requisições leves de baixa latência e evasão de bloqueios.
- **BeautifulSoup 4**: Para parsing de dados do HTML estruturado.
- **Playwright (Chromium Headless)**: Fallback automático utilizando um navegador real simulado para carregar a listagem de páginas e páginas de produtos caso as requisições normais caiam em CAPTCHA ou bloqueios.
- **Pika**: Cliente oficial do RabbitMQ para comunicação via protocolo AMQP/AMQPS.
- **Python-dotenv**: Gerenciamento de segredos e variáveis de ambiente.

---

## 📋 Pré-requisitos

1. **Python 3.10+**.
2. **RabbitMQ** (Instalado localmente via Docker ou uma instância de nuvem gratuita no **CloudAMQP**).

---

## 🚀 Instalação e Configuração

### 1. Criar e Ativar Ambiente Virtual
Crie um ambiente virtual `.venv` para isolar as dependências:

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
Instale os binários do Chromium necessários para o fallback do Playwright:

```bash
playwright install chromium
```

### 4. Configurar as Variáveis de Ambiente (`.env`)
Configure o arquivo `.env` na raiz da pasta `scrapping` para escolher entre o modo simulação (apenas salvar JSON local) ou modo publicação real no RabbitMQ (local ou na nuvem):

```ini
# --- Configurações do RabbitMQ ---
# Defina como True para enviar as mensagens para o RabbitMQ, ou False para apenas gerar o JSON local
RABBITMQ_ENABLED=False

# URL de conexão AMQPS completa (Ideal para serviços em nuvem como o CloudAMQP)
# OBS: Se definida, esta URL tem prioridade sobre as credenciais de host/port abaixo!
RABBITMQ_URL=amqps://usuario:senha@jackal.rmq.cloudamqp.com/usuario

# Credenciais individuais (Caso vá usar o RabbitMQ rodando no Docker local)
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASS=guest
RABBITMQ_EXCHANGE_EVENTS=price_events

# --- Configurações do Scraper ---
SCRAPE_DELAY_MIN=2
SCRAPE_DELAY_MAX=5
PLAYWRIGHT_HEADLESS=True
MAX_CRAWL_PRODUCTS=100
OUTPUT_JSON_PATH=scraped_results.json
```

---

## 🏃 Como Executar e Testar

### Worker RabbitMQ (modo padrão)

```bash
python main.py --mode worker
```

O worker consome `scrape_requests`. O comando esperado é:

```json
{
  "request_id": "01J...",
  "product_id": 123,
  "listing_id": 456,
  "store": "amazon",
  "url": "https://www.amazon.com.br/dp/B09B8VGCR8"
}
```

Falhas temporárias (`blocked` e `timeout`) passam por `scrape_requests.retry`. Comandos inválidos vão para `scrape_requests.dlq`. Depois do limite de tentativas, o worker publica `price.failed`.

### Ambiente completo via Docker

Copie `.env.example` para `.env` e execute:

```bash
docker-compose up --build -d
docker-compose logs -f scraper-worker
```

RabbitMQ Management: `http://localhost:15672`.

### Validação local

Antes de subir o worker, execute a compilação e a suíte automatizada:

```powershell
.\scripts\check.ps1
```

Os testes cobrem o contrato das mensagens, normalização de URL, formatos de
preço, parsing de título/imagem e rejeição de páginas sem preço.

### Contrato operacional

- O worker aceita atualmente apenas `store=amazon`.
- URLs devem ser páginas de produto Amazon contendo `/dp/ASIN` ou
  `/gp/product/ASIN`.
- Uma coleta sem preço válido é tratada como `parse_error`; nunca como sucesso
  com preço nulo.
- `blocked` e `timeout` são retentados. `not_found` e `parse_error` geram falha
  definitiva.
- O Core deve deduplicar eventos por `request_id`, pois a entrega é
  *at-least-once*.

Para enviar um comando sem depender do backoffice:

```bash
python publish_test_request.py "https://www.amazon.com.br/dp/B09B8VGCR8"
```

O script principal `main.py` possui dois modos de execução:

### A. Executar em Lote
O Scraper inicia navegando de forma paginada pelas categorias de Tecnologia da Amazon Brasil, descobrindo as URLs dos produtos em tempo real. Ele raspará os detalhes de cada produto até atingir a meta de sucessos definida em `MAX_CRAWL_PRODUCTS` (ex: **100 produtos**).

Para rodar (ideal para rodar 2 vezes ao dia por exemplo):
```bash
python main.py --mode batch
# ou simplesmente:
python main.py
```
*Se `RABBITMQ_ENABLED=False`, as mensagens simuladas que seriam postadas na fila serão salvas compiladas em `scraped_results.json` e impressas de forma formatada no terminal.*

### B. Executar um Teste de Raspagem Rápida
Testa a raspagem de uma única URL diretamente no console para validar os seletores HTML, **sem depender de conexões com o RabbitMQ**:
```bash
python main.py --mode test --url "https://www.amazon.com.br/dp/B09B8VGCR8"
```

---

## 🐇 Simulando e Visualizando Mensagens com o RabbitMQ (Nuvem ou Docker)

Criamos uma simulação completa onde você pode visualizar as mensagens trafegando em tempo real através de um consumidor fictício de backend.

1. **Suba ou configure o RabbitMQ**:
   - **Nuvem**: Crie uma conta grátis no [CloudAMQP](https://www.cloudamqp.com/), pegue o campo **AMQP URL** e cole no seu `.env` na variável `RABBITMQ_URL`.
   - **Local**: Suba via Docker `docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management`.
2. **Ative a Publicação no Scraper**:
   Mude a linha do seu `.env` para `RABBITMQ_ENABLED=True`.
3. **Inicie o Consumidor de Teste**:
   Abra um terminal, ative o ambiente virtual e rode o ouvinte para receber mensagens:
   ```bash
   python test_consumer.py
   ```
4. **Execute o Scraper**:
   Abra **outro terminal**, ative o ambiente virtual e rode o scraper:
   ```bash
   python main.py
   ```
5. **Acompanhe**:
   - No terminal do `test_consumer.py`, você verá os dados das mensagens JSON caindo na tela instantaneamente à medida que o scraper as publica!
   - No site do CloudAMQP (clicando no botão **RabbitMQ Manager**) ou em `http://localhost:15672` localmente, você pode visualizar no dashboard os fluxos, as exchanges (`price_events`) e as filas ativas (`test_backoffice_events_queue`).

---

## 📥 Estrutura de Mensagens de Eventos

O formato das mensagens JSON publicadas e processadas é:

### 1. Sucesso (`price.scraped`)
Disparado para produtos raspados com sucesso.
```json
{
  "event": "price.scraped",
  "product_id": null,
  "url": "https://www.amazon.com.br/dp/B09B8VGCR8",
  "title": "Echo Dot (Geração mais recente) | Smart speaker com Alexa",
  "price": 329.00,
  "currency": "BRL",
  "image_url": "https://m.media-amazon.com/images/I/61evEYmxBZL._AC_SX679_.jpg",
  "scraped_at": "2026-08-29T23:05:00Z"
}
```

### 2. Falha (`price.failed`)
Disparado quando a raspagem de um link falha ou retorna página não encontrada.
```json
{
  "event": "price.failed",
  "product_id": null,
  "url": "https://www.amazon.com.br/dp/B082XYKBLT",
  "reason": "not_found",
  "scraped_at": "2026-08-29T23:05:00Z"
}
```
*Razões de falha comuns no campo `reason`: `"not_found"` (404), `"blocked"` (IP bloqueado ou captcha persistente), `"timeout"` (tempo excedido de carregamento) ou `"parse_error"` (página mudou de layout).*

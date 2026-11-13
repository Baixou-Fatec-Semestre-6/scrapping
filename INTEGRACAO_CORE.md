# Integração com o Core

O worker usa a mesma topologia declarada por `core/docker/rabbitmq/definitions.json`:

- exchange topic: `baixou`
- fila de entrada: `scraper.requests`
- routing key de entrada: `scrape.requested`
- routing keys de saída: `scrape.completed` e `scrape.failed`
- fila de resultados consumida pelo core: `core.scrape.results`

## Execução integrada com Docker

1. Suba o core primeiro, a partir da pasta `core`:

   ```bash
   docker compose -f docker/docker-compose.yml up -d
   ```

2. Copie `.env.example` para `.env` nesta pasta.
3. Suba o scraper:

   ```bash
   docker compose up --build -d
   ```

O compose do scraper conecta o worker à rede externa `docker_core` e usa o
container `core_rabbitmq`. Se o projeto Docker do core tiver outro nome, defina
`CORE_DOCKER_NETWORK` com o nome real da rede antes de subir o scraper.

## Contrato

O comando exige `event_id`, `listing_id` e `url`. O worker só confirma a
mensagem depois de publicar o resultado. Falhas temporárias são reenfileiradas
com atraso; ao esgotar as tentativas, o worker publica `scrape.failed` com uma
mensagem curta para apresentação no aplicativo.

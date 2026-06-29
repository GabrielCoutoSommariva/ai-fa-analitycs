# Farmacias Associadas BI

Aplicacao BI para dashboards de vendas de farmacias, com frontend Next.js, backend FastAPI, PostgreSQL BI local e integracao com IA.

## Stack

- Frontend: Next.js, React, TypeScript, Recharts, TanStack Table.
- Backend: FastAPI, Python, psycopg 3.
- Banco: PostgreSQL 17, `postgres_fdw`, views e materialized views.
- IA: OpenAI SDK, compativel com OpenAI e Gemini via endpoint OpenAI-compatible.
- Deploy: Docker Compose, Nginx, cron.

## Estrutura Principal

```text
app/
  backend/      API FastAPI
  frontend/     Dashboard Next.js
  nginx/        Reverse proxy
  scripts/      Rotinas operacionais, incluindo refresh BI
  docker-compose.prod.yml
  .env.prod.example

bi/sql/
  01_analytics_schema.sql
  02_kpi_views.sql
  03_semantic_catalog.sql
  05_materialized_kpis.sql
```

## Banco

A aplicacao nao precisa de dump no repositorio. Em producao, ela usa um banco BI local:

```text
db_farmacias_bi
```

Esse banco usa `postgres_fdw` para ler o banco original do cliente em modo read-only e materializa KPIs no schema `analytics`.

## Variaveis De Ambiente

Copie o exemplo:

```bash
cp app/.env.prod.example app/.env
```

Preencha os valores reais somente no ambiente de deploy. Nao versionar `.env`.

## Documentacao

- `DEPLOY_AZURE.md`: passo a passo para subir no Azure.
- `OPERACAO.md`: comandos de operacao, logs, refresh e validacoes.

## Itens Que Nao Devem Ser Versionados

- Dumps SQL ou ZIPs.
- `.env` real.
- Senhas, chaves OpenAI/Gemini, credenciais SSH.
- `node_modules`, `.next`, `__pycache__`.

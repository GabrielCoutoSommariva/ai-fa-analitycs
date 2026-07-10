# Deploy Azure

Este documento descreve como subir a aplicacao no Azure usando apenas arquivos do repositorio e conexao read-only no banco original do cliente. Nao use dump.

## Arquitetura

```text
Banco original do cliente
schemas vendas/cargas
somente SELECT
        |
        | postgres_fdw
        v
Banco BI local no Azure
db_farmacias_bi
analytics.mv_*
        |
        v
Aplicacao BI
Next.js + FastAPI + Nginx
```

## Recursos Azure Recomendados

- VM Ubuntu 24.04 LTS.
- Disco de dados: minimo 100 GB.
- IP publico estatico ou dominio.
- NSG:
  - `22` restrito aos IPs da equipe.
  - `80/443` conforme politica do cliente.
- Acesso do IP da VM liberado no PostgreSQL original do cliente.

## Preparar VM

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg unzip ufw
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Entre novamente na sessao SSH para aplicar o grupo `docker`.

```bash
sudo mkdir -p /opt/farmacia-bi
sudo chown -R $USER:$USER /opt/farmacia-bi
```

## Subir Arquivos

Copie para a VM:

```text
app/
bi/sql/
```

Estrutura esperada:

```text
/opt/farmacia-bi/app
/opt/farmacia-bi/bi/sql
```

## Configurar Ambiente

```bash
cd /opt/farmacia-bi/app
cp .env.prod.example .env
nano .env
```

Exemplo:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=trocar-em-producao
POSTGRES_DB=db_farmacias_bi
DATABASE_URL=postgresql://postgres:trocar-em-producao@db:5432/db_farmacias_bi
APP_HTTP_PORT=80
CORS_ORIGINS=https://bi.cliente.com.br
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
```

Para Gemini:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gemini-2.0-flash
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

Preencha `OPENAI_API_KEY` somente no `.env` real do servidor.

## Subir PostgreSQL Local

```bash
cd /opt/farmacia-bi/app
docker compose -f docker-compose.prod.yml up -d db
```

Criar banco BI:

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d postgres -c "create database db_farmacias_bi;"
```

Se o banco ja existir, ignore o erro ou use checagem idempotente no processo de automacao.

## Configurar FDW

Entre no banco BI:

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi
```

Execute, trocando placeholders:

```sql
create extension if not exists postgres_fdw;
create schema if not exists vendas;
create schema if not exists cargas;
create schema if not exists analytics;
create schema if not exists etl_control;

create table if not exists etl_control.sync_runs (
  id bigserial primary key,
  job_name text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',
  details jsonb not null default '{}'::jsonb,
  error_message text
);

create server cliente_farmacias
foreign data wrapper postgres_fdw
options (
  host 'HOST_BANCO_ORIGINAL',
  port '5432',
  dbname 'NOME_BANCO_ORIGINAL',
  sslmode 'disable',
  fetch_size '50000'
);

create user mapping for postgres
server cliente_farmacias
options (
  user 'USUARIO_READONLY',
  password 'SENHA_READONLY'
);

import foreign schema vendas from server cliente_farmacias into vendas;
import foreign schema cargas from server cliente_farmacias into cargas;
```

Validar:

```sql
select foreign_table_schema, count(*)
from information_schema.foreign_tables
group by foreign_table_schema;

select count(*) from (select 1 from vendas.vendas_cab limit 1) s;
```

## Aplicar Analytics

```bash
cd /opt/farmacia-bi/app

docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -v ON_ERROR_STOP=1 < /opt/farmacia-bi/bi/sql/01_analytics_schema.sql
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -v ON_ERROR_STOP=1 < /opt/farmacia-bi/bi/sql/01_local_dimensions.sql
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -v ON_ERROR_STOP=1 < /opt/farmacia-bi/bi/sql/02_kpi_views.sql
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -v ON_ERROR_STOP=1 < /opt/farmacia-bi/bi/sql/03_semantic_catalog.sql
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -v ON_ERROR_STOP=1 < /opt/farmacia-bi/bi/sql/05_materialized_kpis.sql
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -v ON_ERROR_STOP=1 < /opt/farmacia-bi/bi/sql/06_ai_kpis.sql
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -v ON_ERROR_STOP=1 < /opt/farmacia-bi/bi/sql/08_bronze_sales.sql
```

## Subir Aplicacao

```bash
cd /opt/farmacia-bi/app
docker compose -f docker-compose.prod.yml up -d --build backend frontend nginx
```

Validar:

```bash
curl http://IP_OU_DOMINIO/api/health
curl http://IP_OU_DOMINIO/api/metrics/periodo-vendas
```

## Agendar Refresh

```bash
mkdir -p /opt/farmacia-bi/logs
chmod +x /opt/farmacia-bi/app/scripts/refresh-bi-kpis.sh
crontab -e
```

Agenda recomendada para evitar bloqueio durante horario comercial:

```cron
12 3 * * * flock -n /tmp/farmacia-bi-refresh.lock /opt/farmacia-bi/app/scripts/refresh-bi-kpis.sh >> /opt/farmacia-bi/logs/refresh-bi-kpis.log 2>&1
```

## Validacoes Finais

```bash
curl http://IP_OU_DOMINIO/api/health
curl "http://IP_OU_DOMINIO/api/metrics/summary?data_inicio=2026-06-01&data_fim=2026-06-25"
curl -X POST http://IP_OU_DOMINIO/api/ai/question \
  -H "Content-Type: application/json" \
  -d '{"question":"Quanto vendi no periodo?","data_inicio":"2026-06-01","data_fim":"2026-06-25"}'
```

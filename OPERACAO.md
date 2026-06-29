# Operacao

Comandos operacionais para ambiente Docker Compose.

## Containers

```bash
cd /opt/farmacia-bi/app
docker compose -f docker-compose.prod.yml ps
```

Reiniciar backend/nginx:

```bash
docker compose -f docker-compose.prod.yml up -d backend nginx
```

Rebuild completo da aplicacao:

```bash
docker compose -f docker-compose.prod.yml up -d --build backend frontend nginx
```

## Logs

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend
docker compose -f docker-compose.prod.yml logs -f nginx
docker compose -f docker-compose.prod.yml logs -f db
```

Log do refresh:

```bash
tail -f /opt/farmacia-bi/logs/refresh-bi-kpis.log
```

## Validar API

```bash
curl http://IP_OU_DOMINIO/api/health
curl http://IP_OU_DOMINIO/api/docs
curl http://IP_OU_DOMINIO/api/metrics/periodo-vendas
```

Resumo KPI:

```bash
curl "http://IP_OU_DOMINIO/api/metrics/summary?data_inicio=2026-06-01&data_fim=2026-06-25"
```

Chat:

```bash
curl -X POST http://IP_OU_DOMINIO/api/ai/question \
  -H "Content-Type: application/json" \
  -d '{"question":"Quanto vendi no periodo?","data_inicio":"2026-06-01","data_fim":"2026-06-25"}'
```

## Validar Banco BI

```bash
cd /opt/farmacia-bi/app
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -c "select current_database();"
```

Periodo materializado:

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -c "select min(data), max(data) from analytics.mv_kpi_faturamento_diario;"
```

Ultimos refreshes:

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -c "select id, started_at, finished_at, status, error_message from etl_control.sync_runs order by id desc limit 10;"
```

## Refresh Manual

```bash
flock -n /tmp/farmacia-bi-refresh.lock /opt/farmacia-bi/app/scripts/refresh-bi-kpis.sh
```

Evite rodar refresh em horario comercial, porque `refresh materialized view` pode bloquear leituras temporariamente.

## Cron

Ver agenda:

```bash
crontab -l
```

Agenda recomendada:

```cron
12 3 * * * flock -n /tmp/farmacia-bi-refresh.lock /opt/farmacia-bi/app/scripts/refresh-bi-kpis.sh >> /opt/farmacia-bi/logs/refresh-bi-kpis.log 2>&1
```

## OpenAI Ou Gemini

OpenAI:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
```

Gemini via API compativel com OpenAI:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gemini-2.0-flash
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

Preencha `OPENAI_API_KEY` somente no `.env` real do servidor.

Depois de alterar `.env`:

```bash
docker compose -f docker-compose.prod.yml up -d backend nginx
```

## Espaco Em Disco

```bash
df -h /
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d postgres -c "select datname, pg_size_pretty(pg_database_size(datname)) from pg_database where datistemplate = false;"
```

## Troubleshooting

API retorna `504`:

- Verifique se refresh esta rodando.
- Evite refresh em horario comercial.

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -c "select pid, state, now() - query_start as duration, left(query, 160) from pg_stat_activity where datname='db_farmacias_bi' and pid <> pg_backend_pid();"
```

Interromper refresh em emergencia:

```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d db_farmacias_bi -c "select pg_terminate_backend(pid) from pg_stat_activity where datname='db_farmacias_bi' and query ilike 'refresh materialized view analytics.%';"
```

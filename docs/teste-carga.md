# Teste de Carga

Este projeto usa um smoke de carga com k6 para validar disponibilidade e latência dos endpoints principais sem versionar tokens ou credenciais.

## Arquivo

- `load-tests/k6-dashboard-smoke.js`

## Execução Pública

Instale o k6 antes de rodar. No Windows, use uma das opções oficiais:

```powershell
winget install k6.k6
```

ou:

```powershell
choco install k6
```

Confirme a instalação:

```bash
k6 version
```

Valida somente `/api/health`, sem autenticação:

```bash
k6 run load-tests/k6-dashboard-smoke.js
```

## Execução Autenticada

Use um token JWT válido em variável de ambiente. Não salve o token no repositório.

```bash
k6 run \
  -e BASE_URL=https://dash.farmaciasassociadas.com.br \
  -e AUTH_TOKEN='<token_jwt>' \
  -e START_DATE=2026-06-01 \
  -e END_DATE=2026-07-01 \
  -e VUS=10 \
  -e DURATION=2m \
  load-tests/k6-dashboard-smoke.js
```

Para filtrar um CNPJ autorizado pelo token:

```bash
k6 run \
  -e AUTH_TOKEN='<token_jwt>' \
  -e CNPJ=00000000000000 \
  load-tests/k6-dashboard-smoke.js
```

## Escopo Do Smoke

Com autenticação, o teste chama:

- `/api/metrics/summary`
- `/api/metrics/summary-matriz`
- `/api/metrics/operacional-summary`
- `/api/metrics/operacional-summary-matriz`
- `/api/metrics/faturamento-tendencia?granularidade=auto`

## Critérios Atuais

- `http_req_failed < 5%`
- `p95 http_req_duration < 2000ms`
- `api_errors < 5%`
- `p95 api_latency < 2000ms`

## Observações

- Rode primeiro com `VUS=10` e aumente gradualmente.
- Para validar 200 simultâneos, usar janela controlada e monitorar Postgres, Nginx e containers.
- Se houver erro 401/403, validar o token e os CNPJs autorizados antes de interpretar como falha de performance.
- Segredos usados em testes manuais devem ser rotacionados se forem compartilhados em canais inseguros.

## Resultado Registrado Na Azure

Execução em `2026-07-10` contra `https://dash.farmaciasassociadas.com.br`:

| Cenário | Carga | Duração | Requisições | Falhas | p95 |
|---|---:|---:|---:|---:|---:|
| Health público | 10 VUs | 1m | 600 | 0 | 6.5ms |
| Dashboard autenticado | 5 VUs | 1m | 1.723 | 0 | 16.94ms |
| Dashboard autenticado | 20 VUs | 2m | 13.717 | 0 | 14.8ms |

Após o teste de 20 VUs: health `200`, containers ativos, `running=0` em `etl_control.sync_runs` e `active_non_autovacuum=0` no PostgreSQL.

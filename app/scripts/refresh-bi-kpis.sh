#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/farmacia-bi/app}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BI_DATABASE="${BI_DATABASE:-db_farmacias_bi}"

cd "$APP_DIR"

run_psql() {
  docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -d "$BI_DATABASE" -v ON_ERROR_STOP=1 "$@"
}

RUN_ID="$(
  run_psql -At -c "insert into etl_control.sync_runs (job_name, status, details) values ('refresh_materialized_kpis', 'running', jsonb_build_object('mode', 'scheduled_refresh')) returning id;" \
    | head -n 1 \
    | tr -d '\r'
)"

finish_success() {
  run_psql -c "update etl_control.sync_runs set status = 'success', finished_at = now() where id = $RUN_ID;"
}

finish_failure() {
  run_psql -c "update etl_control.sync_runs set status = 'failed', finished_at = now(), error_message = 'refresh failed; check cron/container logs' where id = $RUN_ID;" || true
}

trap finish_failure ERR

run_psql <<'SQL'
refresh materialized view analytics.mv_kpi_faturamento_diario;
refresh materialized view analytics.mv_kpi_faturamento_mensal;
refresh materialized view analytics.mv_kpi_cupons;
refresh materialized view analytics.mv_kpi_itens_vendidos;
refresh materialized view analytics.mv_kpi_faturamento_loja;
refresh materialized view analytics.mv_kpi_lucro_produto;
refresh materialized view analytics.mv_kpi_lucro_produto_total_loja;
refresh materialized view analytics.mv_kpi_lucro_total_diario;
refresh materialized view analytics.mv_ai_resumo_executivo_diario;
refresh materialized view analytics.mv_ai_vendedor_diario;
refresh materialized view analytics.mv_ai_vendas_horario;
refresh materialized view analytics.mv_ai_alertas_operacionais;
refresh materialized view analytics.mv_ai_cliente_diario;
refresh materialized view analytics.mv_ai_produto_mensal;

analyze analytics.mv_kpi_faturamento_diario;
analyze analytics.mv_kpi_faturamento_mensal;
analyze analytics.mv_kpi_cupons;
analyze analytics.mv_kpi_itens_vendidos;
analyze analytics.mv_kpi_faturamento_loja;
analyze analytics.mv_kpi_lucro_produto;
analyze analytics.mv_kpi_lucro_produto_total_loja;
analyze analytics.mv_kpi_lucro_total_diario;
analyze analytics.mv_ai_resumo_executivo_diario;
analyze analytics.mv_ai_vendedor_diario;
analyze analytics.mv_ai_vendas_horario;
analyze analytics.mv_ai_alertas_operacionais;
analyze analytics.mv_ai_cliente_diario;
analyze analytics.mv_ai_produto_mensal;
SQL

trap - ERR
finish_success

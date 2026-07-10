#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/farmacia-bi/app}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BI_DATABASE="${BI_DATABASE:-db_farmacias_bi}"
BRONZE_SALES_DAYS="${BRONZE_SALES_DAYS:-45}"
FULL_REFRESH_TIMEOUT_SECONDS="${FULL_REFRESH_TIMEOUT_SECONDS:-3600}"
BRONZE_SYNC_TIMEOUT_SECONDS="${BRONZE_SYNC_TIMEOUT_SECONDS:-1800}"
BI_LOCK_TIMEOUT_SECONDS="${BI_LOCK_TIMEOUT_SECONDS:-10}"
BI_JOB_LOCK_FILE="${BI_JOB_LOCK_FILE:-/tmp/farmacia-bi-etl.lock}"

for numeric_value in BRONZE_SALES_DAYS FULL_REFRESH_TIMEOUT_SECONDS BRONZE_SYNC_TIMEOUT_SECONDS BI_LOCK_TIMEOUT_SECONDS; do
  case "${!numeric_value}" in
  ''|*[!0-9]*)
    echo "$numeric_value must be a non-negative integer" >&2
    exit 1
    ;;
  esac
done

if ! command -v flock >/dev/null 2>&1; then
  echo "flock is required to prevent overlapping BI jobs" >&2
  exit 1
fi

exec 9>"$BI_JOB_LOCK_FILE"
if ! flock -n 9; then
  echo "Another BI job is already running; skipping full refresh" >&2
  exit 0
fi

cd "$APP_DIR"

run_psql() {
  docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -d "$BI_DATABASE" -v ON_ERROR_STOP=1 "$@"
}

RUN_ID="$(
  run_psql -At -c "insert into etl_control.sync_runs (job_name, status, details) values ('refresh_materialized_kpis', 'running', jsonb_build_object('mode', 'scheduled_refresh', 'bronze_days', $BRONZE_SALES_DAYS, 'full_timeout_seconds', $FULL_REFRESH_TIMEOUT_SECONDS, 'bronze_timeout_seconds', $BRONZE_SYNC_TIMEOUT_SECONDS)) returning id;" \
    | head -n 1 \
    | tr -d '\r'
)"

finish_success() {
  run_psql -c "update etl_control.sync_runs set status = 'success', finished_at = now() where id = $RUN_ID;"
}

finish_failure() {
  run_psql -c "update etl_control.sync_runs set status = 'failed', finished_at = now(), error_message = 'refresh failed; check cron/container logs' where id = $RUN_ID;" || true
}

finish_interrupted() {
  finish_failure
  exit 130
}

trap 'finish_failure; exit 1' ERR
trap finish_interrupted INT TERM

if ! run_psql -v statement_timeout="${FULL_REFRESH_TIMEOUT_SECONDS}s" -v lock_timeout="${BI_LOCK_TIMEOUT_SECONDS}s" <<'SQL'
set statement_timeout = :'statement_timeout';
set lock_timeout = :'lock_timeout';

select analytics.refresh_local_dimensions();
SQL
then
  finish_failure
  exit 1
fi

if ! run_psql -v statement_timeout="${BRONZE_SYNC_TIMEOUT_SECONDS}s" -v lock_timeout="${BI_LOCK_TIMEOUT_SECONDS}s" <<SQL
set statement_timeout = :'statement_timeout';
set lock_timeout = :'lock_timeout';

select * from analytics.refresh_bronze_sales($BRONZE_SALES_DAYS);
SQL
then
  finish_failure
  exit 1
fi

if ! run_psql -v statement_timeout="${FULL_REFRESH_TIMEOUT_SECONDS}s" -v lock_timeout="${BI_LOCK_TIMEOUT_SECONDS}s" <<'SQL'
set statement_timeout = :'statement_timeout';
set lock_timeout = :'lock_timeout';

refresh materialized view analytics.mv_kpi_faturamento_diario;
refresh materialized view analytics.mv_kpi_faturamento_mensal;
refresh materialized view analytics.mv_kpi_cupons;
refresh materialized view analytics.mv_kpi_itens_vendidos;
refresh materialized view analytics.mv_kpi_faturamento_loja;
refresh materialized view analytics.mv_kpi_lucro_produto;
refresh materialized view analytics.mv_kpi_lucro_produto_total_loja;
refresh materialized view analytics.mv_kpi_lucro_total_diario;
refresh materialized view analytics.mv_kpi_operacional_diario;
refresh materialized view analytics.mv_ai_resumo_executivo_diario;
refresh materialized view analytics.mv_ai_vendedor_diario;
refresh materialized view analytics.mv_ai_vendas_horario;
refresh materialized view analytics.mv_ai_alertas_operacionais;
refresh materialized view analytics.mv_ai_cliente_diario;
refresh materialized view analytics.mv_ai_produto_mensal;
refresh materialized view analytics.mv_ai_sazonalidade_dia_semana;
refresh materialized view analytics.mv_ai_desconto_devolucao_diario;
refresh materialized view analytics.mv_ai_desconto_devolucao_produto_mensal;

analyze analytics.mv_kpi_faturamento_diario;
analyze analytics.mv_kpi_faturamento_mensal;
analyze analytics.mv_kpi_cupons;
analyze analytics.mv_kpi_itens_vendidos;
analyze analytics.mv_kpi_faturamento_loja;
analyze analytics.mv_kpi_lucro_produto;
analyze analytics.mv_kpi_lucro_produto_total_loja;
analyze analytics.mv_kpi_lucro_total_diario;
analyze analytics.mv_kpi_operacional_diario;
analyze analytics.mv_ai_resumo_executivo_diario;
analyze analytics.mv_ai_vendedor_diario;
analyze analytics.mv_ai_vendas_horario;
analyze analytics.mv_ai_alertas_operacionais;
analyze analytics.mv_ai_cliente_diario;
analyze analytics.mv_ai_produto_mensal;
analyze analytics.mv_ai_sazonalidade_dia_semana;
analyze analytics.mv_ai_desconto_devolucao_diario;
analyze analytics.mv_ai_desconto_devolucao_produto_mensal;
SQL
then
  finish_failure
  exit 1
fi

trap - ERR INT TERM
finish_success

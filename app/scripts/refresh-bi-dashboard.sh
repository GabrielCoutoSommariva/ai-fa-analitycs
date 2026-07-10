#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/farmacia-bi/app}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BI_DATABASE="${BI_DATABASE:-db_farmacias_bi}"
DASHBOARD_REFRESH_HEAVY="${DASHBOARD_REFRESH_HEAVY:-false}"
BI_JOB_LOCK_FILE="${BI_JOB_LOCK_FILE:-/tmp/farmacia-bi-etl.lock}"

case "$DASHBOARD_REFRESH_HEAVY" in
  true|false) ;;
  *)
    echo "DASHBOARD_REFRESH_HEAVY must be true or false" >&2
    exit 1
    ;;
esac

if ! command -v flock >/dev/null 2>&1; then
  echo "flock is required to prevent overlapping BI jobs" >&2
  exit 1
fi

exec 9>"$BI_JOB_LOCK_FILE"
if ! flock -n 9; then
  echo "Another BI job is already running; skipping dashboard refresh" >&2
  exit 0
fi

cd "$APP_DIR"

run_psql() {
  docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -d "$BI_DATABASE" -v ON_ERROR_STOP=1 "$@"
}

RUN_ID="$(
  run_psql -At -c "insert into etl_control.sync_runs (job_name, status, details) values ('refresh_dashboard_kpis', 'running', jsonb_build_object('mode', 'scheduled_dashboard_refresh', 'heavy', '$DASHBOARD_REFRESH_HEAVY'::boolean)) returning id;" \
    | head -n 1 \
    | tr -d '\r'
)"

finish_success() {
  run_psql -c "update etl_control.sync_runs set status = 'success', finished_at = now() where id = $RUN_ID;"
}

finish_failure() {
  run_psql -c "update etl_control.sync_runs set status = 'failed', finished_at = now(), error_message = 'dashboard refresh failed; check cron/container logs' where id = $RUN_ID;" || true
}

finish_interrupted() {
  finish_failure
  exit 130
}

trap 'finish_failure; exit 1' ERR
trap finish_interrupted INT TERM

if ! run_psql <<'SQL'
set statement_timeout = '120s';
set lock_timeout = '5s';

select analytics.refresh_local_dimensions(false);

refresh materialized view analytics.mv_kpi_faturamento_diario;
refresh materialized view analytics.mv_kpi_faturamento_mensal;
refresh materialized view analytics.mv_kpi_cupons;
refresh materialized view analytics.mv_kpi_faturamento_loja;

analyze analytics.mv_kpi_faturamento_diario;
analyze analytics.mv_kpi_faturamento_mensal;
analyze analytics.mv_kpi_cupons;
analyze analytics.mv_kpi_faturamento_loja;
SQL
then
  finish_failure
  exit 1
fi

if [ "$DASHBOARD_REFRESH_HEAVY" = "true" ]; then
  if ! run_psql <<'SQL'
set statement_timeout = '120s';
set lock_timeout = '5s';

refresh materialized view analytics.mv_kpi_itens_vendidos;
analyze analytics.mv_kpi_itens_vendidos;
SQL
  then
    finish_failure
    exit 1
  fi
fi

trap - ERR INT TERM
finish_success

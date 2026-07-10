#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/farmacia-bi/app}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BI_DATABASE="${BI_DATABASE:-db_farmacias_bi}"
BRONZE_SALES_DAYS="${BRONZE_SALES_DAYS:-45}"
BRONZE_SYNC_TIMEOUT_SECONDS="${BRONZE_SYNC_TIMEOUT_SECONDS:-1800}"
BI_LOCK_TIMEOUT_SECONDS="${BI_LOCK_TIMEOUT_SECONDS:-10}"
BI_JOB_LOCK_FILE="${BI_JOB_LOCK_FILE:-/tmp/farmacia-bi-etl.lock}"

for numeric_value in BRONZE_SALES_DAYS BRONZE_SYNC_TIMEOUT_SECONDS BI_LOCK_TIMEOUT_SECONDS; do
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
  echo "Another BI job is already running; skipping bronze sync" >&2
  exit 0
fi

cd "$APP_DIR"

run_psql() {
  docker compose -f "$COMPOSE_FILE" exec -T db psql -U postgres -d "$BI_DATABASE" -v ON_ERROR_STOP=1 "$@"
}

RUN_ID="$(
  run_psql -At -c "insert into etl_control.sync_runs (job_name, status, details) values ('sync_bronze_sales', 'running', jsonb_build_object('days_back', $BRONZE_SALES_DAYS, 'timeout_seconds', $BRONZE_SYNC_TIMEOUT_SECONDS)) returning id;" \
    | head -n 1 \
    | tr -d '\r'
)"

finish_success() {
  run_psql -c "update etl_control.sync_runs set status = 'success', finished_at = now() where id = $RUN_ID;"
}

finish_failure() {
  run_psql -c "update etl_control.sync_runs set status = 'failed', finished_at = now(), error_message = 'bronze sales sync failed; check cron/container logs' where id = $RUN_ID;" || true
}

finish_interrupted() {
  finish_failure
  exit 130
}

trap 'finish_failure; exit 1' ERR
trap finish_interrupted INT TERM

if ! run_psql -v statement_timeout="${BRONZE_SYNC_TIMEOUT_SECONDS}s" -v lock_timeout="${BI_LOCK_TIMEOUT_SECONDS}s" <<SQL
set statement_timeout = :'statement_timeout';
set lock_timeout = :'lock_timeout';

select * from analytics.refresh_bronze_sales($BRONZE_SALES_DAYS);
SQL
then
  finish_failure
  exit 1
fi

trap - ERR INT TERM
finish_success

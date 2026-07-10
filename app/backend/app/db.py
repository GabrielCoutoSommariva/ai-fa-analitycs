from collections.abc import Iterable
from contextlib import contextmanager
import atexit
import re
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings


_pool: ConnectionPool | None = None
_pool_config: tuple[str, int, int] | None = None


def close_pool() -> None:
    global _pool, _pool_config
    if _pool is not None:
        _pool.close()
        _pool = None
        _pool_config = None


atexit.register(close_pool)


def get_pool() -> ConnectionPool:
    global _pool, _pool_config
    settings = get_settings()
    config = (settings.database_url, settings.database_pool_min_size, settings.database_pool_max_size)
    if _pool is None or _pool_config != config:
        if _pool is not None:
            _pool.close()
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.database_pool_min_size,
            max_size=settings.database_pool_max_size,
            kwargs={"row_factory": dict_row},
        )
        _pool_config = config
    return _pool


@contextmanager
def get_connection():
    with get_pool().connection() as conn:
        yield conn


def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            return list(cur.fetchall())


def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            return cur.fetchone()


def execute_select(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return fetch_all(sql, params)


def build_where(filters: dict[str, Any], allowed: Iterable[str]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    allowed_set = set(allowed)

    for key, value in filters.items():
        if value is None or key not in allowed_set:
            continue
        if key == "data_inicio":
            clauses.append("data >= %(data_inicio)s")
        elif key == "data_fim":
            clauses.append("data <= %(data_fim)s")
        elif key == "mes_inicio":
            clauses.append("mes >= %(mes_inicio)s")
        elif key == "mes_fim":
            clauses.append("mes <= %(mes_fim)s")
        elif key == "cnpj":
            value = re.sub(r"\D", "", str(value))
            if not value:
                continue
            clauses.append(
                "loja_id in ("
                "select filtro_loja.loja_id from analytics.dim_loja filtro_loja "
                "where "
                "regexp_replace(coalesce(filtro_loja.cnpj, ''), '\\D', '', 'g') = %(cnpj)s"
                ")"
            )
        elif key == "cnpjs":
            value = [re.sub(r"\D", "", str(item)) for item in value]
            value = [item for item in value if item]
            if not value:
                clauses.append("false")
                continue
            clauses.append(
                "loja_id in ("
                "select filtro_loja.loja_id from analytics.dim_loja filtro_loja "
                "where "
                "regexp_replace(coalesce(filtro_loja.cnpj, ''), '\\D', '', 'g') = any(%(cnpjs)s)"
                ")"
            )
        else:
            clauses.append(f"{key} = %({key})s")
        params[key] = value

    if not clauses:
        return "", params
    return "where " + " and ".join(clauses), params

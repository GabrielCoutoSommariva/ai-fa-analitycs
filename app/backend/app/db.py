from collections.abc import Iterable
from contextlib import contextmanager
import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


@contextmanager
def get_connection():
    settings = get_settings()
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
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

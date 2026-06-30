from datetime import date
from functools import lru_cache
import re
from typing import Literal

from app.db import build_where, fetch_all, fetch_one


DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def normalize_cnpj(cnpj: str | None) -> str | None:
    if not cnpj:
        return None
    digits = re.sub(r"\D", "", cnpj)
    return digits or None


def cnpj_scope(cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, str | list[str]]:
    normalized = normalize_cnpj(cnpj)
    if normalized:
        return {"cnpj": normalized}
    if authorized_cnpjs is not None:
        return {"cnpjs": [item for item in (normalize_cnpj(value) for value in authorized_cnpjs) if item]}
    return {}


@lru_cache(maxsize=1)
def complete_sales_period() -> dict:
    return fetch_one(
        """
        select min(data) as data_inicio, max(data) as data_fim
        from analytics.fact_venda
        """
    ) or {"data_inicio": None, "data_fim": None}


def is_complete_period(data_inicio: date | None, data_fim: date | None) -> bool:
    period = complete_sales_period()
    start = period.get("data_inicio")
    end = period.get("data_fim")
    if not start or not end:
        return False
    return (data_inicio is None or data_inicio <= start) and (data_fim is None or data_fim >= end)


def get_catalog() -> list[dict]:
    return fetch_all(
        """
        select metric_key, metric_name, business_question, source_view, date_field, value_field, caveats
        from analytics.ai_metric_catalog
        order by metric_key
        """
    )


def periodo_vendas(authorized_cnpjs: list[str] | None = None) -> dict:
    scope = cnpj_scope(None, authorized_cnpjs)
    if not scope:
        return complete_sales_period()
    where, params = build_where(scope, ["cnpjs"])
    return fetch_one(
        f"""
        select min(data) as data_inicio, max(data) as data_fim
        from analytics.fact_venda
        {where}
        """,
        params,
    ) or {"data_inicio": None, "data_fim": None}


def lojas_cnpj(authorized_cnpjs: list[str] | None = None) -> list[dict]:
    scope = cnpj_scope(None, authorized_cnpjs)
    params: dict[str, list[str]] = {}
    auth_filter = ""
    if "cnpjs" in scope:
        params["cnpjs"] = scope["cnpjs"]
        auth_filter = "and regexp_replace(coalesce(cnpj, ''), '\\D', '', 'g') = any(%(cnpjs)s)" if scope["cnpjs"] else "and false"
    return fetch_all(
        f"""
        select
          cnpj,
          regexp_replace(coalesce(cnpj, ''), '\\D', '', 'g') as cnpj_digits,
          count(*) as lojas,
          array_agg(json_build_object('loja_id', loja_id, 'loja', nome) order by nome) as lojas_vinculadas
        from analytics.dim_loja
        where cnpj is not null and btrim(cnpj) <> ''
        {auth_filter}
        group by cnpj
        order by cnpj
        """,
        params,
    )


def get_summary(data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict:
    where, params = build_where(
        {"data_inicio": data_inicio, "data_fim": data_fim, **cnpj_scope(cnpj, authorized_cnpjs)},
        ["data_inicio", "data_fim", "cnpj", "cnpjs"],
    )
    return fetch_one(
        f"""
        with fat as (
          select
            coalesce(sum(faturamento_liquido), 0) as faturamento,
            coalesce(sum(qtd_cupons), 0) as cupons
          from analytics.mv_kpi_faturamento_diario
          {where}
        ), itens as (
          select coalesce(sum(qtd_itens_vendidos), 0) as itens
          from analytics.mv_kpi_itens_vendidos
          {where}
        ), lucro as (
          select
            coalesce(sum(receita_liquida_item), 0) as receita,
            coalesce(sum(custo_total_estimado), 0) as custo,
            coalesce(sum(lucro_bruto_total), 0) as lucro,
            case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_total) / sum(receita_liquida_item) end as margem
          from analytics.mv_kpi_lucro_total_diario
          {where}
        )
      select
        fat.faturamento,
        fat.cupons,
        case when fat.cupons = 0 then 0 else fat.faturamento / fat.cupons end as ticket_medio,
        itens.itens,
        lucro.receita,
        lucro.custo,
        lucro.lucro,
        lucro.margem
        from fat cross join itens cross join lucro
        """,
        params,
    ) or {}


def faturamento_diario(data_inicio: date | None, data_fim: date | None, cnpj: str | None, limit: int | None, authorized_cnpjs: list[str] | None = None) -> list[dict]:
    where, params = build_where(
        {"data_inicio": data_inicio, "data_fim": data_fim, **cnpj_scope(cnpj, authorized_cnpjs)},
        ["data_inicio", "data_fim", "cnpj", "cnpjs"],
    )
    params["limit"] = clamp_limit(limit)
    return fetch_all(
        f"""
        select data, associado_id, loja_id, qtd_cupons, faturamento_liquido, faturamento_produto, faturamento_servico, valor_devolucao
        from analytics.mv_kpi_faturamento_diario
        {where}
        order by data desc, faturamento_liquido desc
        limit %(limit)s
        """,
        params,
    )


def faturamento_mensal(mes_inicio: date | None, mes_fim: date | None, cnpj: str | None, limit: int | None, authorized_cnpjs: list[str] | None = None) -> list[dict]:
    where, params = build_where(
        {"mes_inicio": mes_inicio, "mes_fim": mes_fim, **cnpj_scope(cnpj, authorized_cnpjs)},
        ["mes_inicio", "mes_fim", "cnpj", "cnpjs"],
    )
    params["limit"] = clamp_limit(limit)
    return fetch_all(
        f"""
        select mes, associado_id, loja_id, qtd_cupons, faturamento_liquido, faturamento_produto, faturamento_servico, valor_devolucao
        from analytics.mv_kpi_faturamento_mensal
        {where}
        order by mes desc, faturamento_liquido desc
        limit %(limit)s
        """,
        params,
    )


def faturamento_loja(data_inicio: date | None, data_fim: date | None, cnpj: str | None, limit: int | None, authorized_cnpjs: list[str] | None = None) -> list[dict]:
    params = {"limit": clamp_limit(limit)}
    vendas_clauses: list[str] = []
    lojas_clauses: list[str] = []

    if data_inicio is not None:
        vendas_clauses.append("data >= %(data_inicio)s")
        params["data_inicio"] = data_inicio
    if data_fim is not None:
        vendas_clauses.append("data <= %(data_fim)s")
        params["data_fim"] = data_fim

    scope = cnpj_scope(cnpj, authorized_cnpjs)
    if scope.get("cnpj"):
        lojas_clauses.append("regexp_replace(coalesce(l.cnpj, ''), '\\D', '', 'g') = %(cnpj)s")
        params["cnpj"] = scope["cnpj"]
    elif "cnpjs" in scope:
        lojas_clauses.append("regexp_replace(coalesce(l.cnpj, ''), '\\D', '', 'g') = any(%(cnpjs)s)" if scope["cnpjs"] else "false")
        params["cnpjs"] = scope["cnpjs"]
    else:
        lojas_clauses.append("l.loja_id in (select distinct loja_id from analytics.mv_kpi_faturamento_loja)")

    vendas_where = "where " + " and ".join(vendas_clauses) if vendas_clauses else ""
    lojas_where = "where " + " and ".join(lojas_clauses)

    return fetch_all(
        f"""
        with vendas as (
          select
            loja_id,
            max(loja) as loja,
            sum(qtd_cupons) as qtd_cupons,
            sum(faturamento_liquido) as faturamento_liquido
          from analytics.mv_kpi_faturamento_loja
          {vendas_where}
          group by loja_id
        )
        select
          l.loja_id,
          coalesce(v.loja, l.nome) as loja,
          l.cnpj,
          coalesce(v.qtd_cupons, 0) as qtd_cupons,
          coalesce(v.faturamento_liquido, 0) as faturamento_liquido
        from analytics.dim_loja l
        left join vendas v on v.loja_id = l.loja_id
        {lojas_where}
        order by faturamento_liquido desc
        limit %(limit)s
        """,
        params,
    )


def cupons(data_inicio: date | None, data_fim: date | None, cnpj: str | None, limit: int | None, authorized_cnpjs: list[str] | None = None) -> list[dict]:
    where, params = build_where(
        {"data_inicio": data_inicio, "data_fim": data_fim, **cnpj_scope(cnpj, authorized_cnpjs)},
        ["data_inicio", "data_fim", "cnpj", "cnpjs"],
    )
    params["limit"] = clamp_limit(limit)
    return fetch_all(
        f"""
        select data, associado_id, loja_id, qtd_cupons, nro_venda_distintos, tickets_distintos
        from analytics.mv_kpi_cupons
        {where}
        order by data desc, qtd_cupons desc
        limit %(limit)s
        """,
        params,
    )


def itens_vendidos(data_inicio: date | None, data_fim: date | None, cnpj: str | None, limit: int | None, authorized_cnpjs: list[str] | None = None) -> list[dict]:
    where, params = build_where(
        {"data_inicio": data_inicio, "data_fim": data_fim, **cnpj_scope(cnpj, authorized_cnpjs)},
        ["data_inicio", "data_fim", "cnpj", "cnpjs"],
    )
    params["limit"] = clamp_limit(limit)
    return fetch_all(
        f"""
        select data, associado_id, loja_id, linhas_item, cupons_com_item, qtd_itens_vendidos, itens_por_cupom
        from analytics.mv_kpi_itens_vendidos
        {where}
        order by data desc, qtd_itens_vendidos desc
        limit %(limit)s
        """,
        params,
    )


def lucro_produto(
    data_inicio: date | None,
    data_fim: date | None,
    cnpj: str | None,
    order: Literal["asc", "desc"],
    limit: int | None,
    authorized_cnpjs: list[str] | None = None,
) -> list[dict]:
    full_period = is_complete_period(data_inicio, data_fim)
    scope = cnpj_scope(cnpj, authorized_cnpjs)
    filters = scope if full_period else {"data_inicio": data_inicio, "data_fim": data_fim, **scope}
    allowed = ["cnpj", "cnpjs"] if full_period else ["data_inicio", "data_fim", "cnpj", "cnpjs"]
    source = "analytics.mv_kpi_lucro_produto_total_loja" if full_period else "analytics.mv_kpi_lucro_produto"
    where, params = build_where(filters, allowed)
    direction = "asc" if order == "asc" else "desc"
    params["limit"] = clamp_limit(limit)
    return fetch_all(
        f"""
        select
          produto_id,
          max(produto) as produto,
          sum(qtd_vendida) as qtd_vendida,
          sum(receita_liquida_item) as receita_liquida_item,
          sum(custo_total_estimado) as custo_total_estimado,
          sum(lucro_bruto_estimado) as lucro_bruto_estimado,
          case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_estimado) / sum(receita_liquida_item) end as margem_bruta_percentual
        from {source}
        {where}
        group by produto_id
        order by lucro_bruto_estimado {direction}
        limit %(limit)s
        """,
        params,
    )


def produtos_prejuizo(data_inicio: date | None, data_fim: date | None, cnpj: str | None, limit: int | None, authorized_cnpjs: list[str] | None = None) -> list[dict]:
    full_period = is_complete_period(data_inicio, data_fim)
    scope = cnpj_scope(cnpj, authorized_cnpjs)
    filters = scope if full_period else {"data_inicio": data_inicio, "data_fim": data_fim, **scope}
    allowed = ["cnpj", "cnpjs"] if full_period else ["data_inicio", "data_fim", "cnpj", "cnpjs"]
    source = "analytics.mv_kpi_lucro_produto_total_loja" if full_period else "analytics.mv_kpi_lucro_produto"
    where, params = build_where(filters, allowed)
    params["limit"] = clamp_limit(limit)
    return fetch_all(
        f"""
        select
          produto_id,
          max(produto) as produto,
          sum(qtd_vendida) as qtd_vendida,
          sum(receita_liquida_item) as receita_liquida_item,
          sum(custo_total_estimado) as custo_total_estimado,
          sum(lucro_bruto_estimado) as lucro_bruto_estimado
        from {source}
        {where}
        group by produto_id
        having sum(lucro_bruto_estimado) < 0
        order by lucro_bruto_estimado asc
        limit %(limit)s
        """,
        params,
    )

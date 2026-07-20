from datetime import date
from decimal import Decimal
import re
from time import monotonic
from typing import Any, Literal
import unicodedata

from app.db import execute_select
from app.services.openai_service import answer_with_kpis, has_openai_key, summarize_with_openai
from app.services.periods import parse_period
from app.services.semantic import find_question_route
from app.sql_guard import is_safe_select, template_to_psycopg


KPI_CONTEXT_CACHE_SECONDS = 300
_kpi_context_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
PRODUCT_ANSWER_CACHE_SECONDS = 120
_product_answer_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
LIST_TEXT_LIMIT = 50


KPI_DEFINITIONS: dict[str, dict[str, str]] = {
    "faturamento": {
        "label": "Faturamento liquido",
        "formula": "sum(faturamento_liquido), onde faturamento_liquido = vlr_liquido - vlr_devolucao.",
        "source": "analytics.mv_kpi_faturamento_diario",
    },
    "faturamento_por_loja": {
        "label": "Faturamento por loja",
        "formula": "sum(faturamento_liquido) agrupado por loja_id.",
        "source": "analytics.mv_kpi_faturamento_loja",
    },
    "ticket_medio": {
        "label": "Ticket medio",
        "formula": "sum(faturamento_liquido) / sum(qtd_cupons).",
        "source": "analytics.mv_kpi_faturamento_diario",
    },
    "margem": {
        "label": "Margem bruta estimada",
        "formula": "sum(lucro_bruto_total) / sum(receita_liquida_item), com lucro_bruto_total = receita_liquida_item - CMV estimado.",
        "source": "analytics.mv_kpi_lucro_total_diario",
    },
    "cmv": {
        "label": "CMV estimado",
        "formula": "sum(custo_total_estimado) / sum(receita_liquida_item) para percentual; valor absoluto = sum(custo_total_estimado).",
        "source": "analytics.mv_kpi_lucro_total_diario",
    },
    "desconto_usuario": {
        "label": "Desconto usuario",
        "formula": "sum(desconto_manual) / sum(receita_liquida_item).",
        "source": "analytics.mv_kpi_operacional_diario",
    },
    "desconto_automatico": {
        "label": "Desconto automatico",
        "formula": "sum(desconto_automatico) / sum(receita_liquida_item).",
        "source": "analytics.mv_kpi_operacional_diario",
    },
    "desconto_cmv": {
        "label": "Desconto / CMV",
        "formula": "sum(desconto_total) / sum(custo_total_estimado).",
        "source": "analytics.mv_kpi_operacional_diario",
    },
    "cupons_um_item": {
        "label": "Cupons com 1 item",
        "formula": "sum(cupons_um_item) / sum(total_cupons).",
        "source": "analytics.mv_kpi_operacional_diario",
    },
    "descontos_devolucoes": {
        "label": "Descontos e devolucoes",
        "formula": "descontos e devolucoes sao somados no periodo e comparados contra a base de faturamento/venda bruta aproximada indicada na resposta.",
        "source": "analytics.mv_ai_desconto_devolucao_diario e analytics.mv_ai_desconto_devolucao_produto_mensal",
    },
    "dre": {
        "label": "DRE parcial/gerencial",
        "formula": "receita liquida analisada - CMV estimado = lucro bruto estimado. Nao inclui DRE contabil completa.",
        "source": "analytics.mv_kpi_lucro_total_diario",
    },
    "produto_especifico": {
        "label": "Produto especifico",
        "formula": "valor do item = sum(vlr_venda - vlr_devol); margem do item = sum(lucro_bruto_estimado) / sum(venda_liquida_item). O total dos cupons soma os cupons validos que contem o item.",
        "source": "bronze.vendas_item, bronze.vendas_cab e analytics.dim_produto",
    },
}


PHARMACY_BUSINESS_SCOPE_KEYWORDS = [
    "farmacia",
    "farmacias",
    "drogaria",
    "medicamento",
    "medicamentos",
    "pdv",
    "balcao",
    "balconista",
    "atendimento",
    "loja",
    "lojas",
    "venda",
    "vendas",
    "faturamento",
    "receita",
    "cupom",
    "ticket",
    "cliente",
    "clientes",
    "produto",
    "produtos",
    "estoque",
    "ruptura",
    "giro",
    "margem",
    "cmv",
    "lucro",
    "dre",
    "desconto",
    "devolucao",
    "vendedor",
    "vendedores",
    "equipe",
    "compra",
    "compras",
    "fornecedor",
    "fornecedores",
    "preco",
    "precificacao",
    "promocao",
    "campanha",
    "campanhas",
    "marketing",
    "crescimento",
    "crescer",
    "negocio",
    "business",
    "gestao",
    "estrategia",
    "estrategico",
    "desenvolvimento",
    "performance",
    "meta",
    "indicador",
    "kpi",
    "concorrente",
    "bairro",
    "sazonalidade",
]


CLEAR_OUT_OF_SCOPE_PATTERNS = [
    "origem da vida",
    "sentido da vida",
    "vida apos a morte",
    "deus existe",
    "religiao",
    "horoscopo",
    "signo",
    "previsao do tempo",
    "clima hoje",
    "futebol",
    "placar do jogo",
    "filme",
    "serie de tv",
    "musica",
    "celebridade",
    "fofoca",
    "receita de bolo",
    "segunda guerra",
    "guerra mundial",
    "historia do brasil",
    "politica partidaria",
    "eleicao presidencial",
    "presidente do brasil",
    "hackear",
    "bomba",
    "arma de fogo",
    "drogas ilicitas",
]


def serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value


def normalize_cnpj(cnpj: str | None) -> str | None:
    if not cnpj:
        return None
    digits = re.sub(r"\D", "", cnpj)
    return digits or None


def scoped_cnpjs(authorized_cnpjs: list[str] | None = None) -> list[str]:
    return [item for item in (normalize_cnpj(cnpj) for cnpj in authorized_cnpjs or []) if item]


def add_cnpj_params(params: dict[str, Any], cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> None:
    normalized_cnpj = normalize_cnpj(cnpj)
    if normalized_cnpj:
        params["cnpj"] = normalized_cnpj
    elif authorized_cnpjs is not None:
        params["cnpjs"] = scoped_cnpjs(authorized_cnpjs)


def cnpj_filter(cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> str:
    if normalize_cnpj(cnpj):
        return "and loja_id in (select filtro_loja.loja_id from analytics.dim_loja filtro_loja where regexp_replace(coalesce(filtro_loja.cnpj, ''), '\\D', '', 'g') = %(cnpj)s)"
    if authorized_cnpjs is not None:
        return "and loja_id in (select filtro_loja.loja_id from analytics.dim_loja filtro_loja where regexp_replace(coalesce(filtro_loja.cnpj, ''), '\\D', '', 'g') = any(%(cnpjs)s))"
    return ""


def cnpj_filter_for_column(alias: str, column: str, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> str:
    if normalize_cnpj(cnpj):
        return f"and {alias}.{column} in (select filtro_loja.loja_id from analytics.dim_loja filtro_loja where regexp_replace(coalesce(filtro_loja.cnpj, ''), '\\D', '', 'g') = %(cnpj)s)"
    if authorized_cnpjs is not None:
        return f"and {alias}.{column} in (select filtro_loja.loja_id from analytics.dim_loja filtro_loja where regexp_replace(coalesce(filtro_loja.cnpj, ''), '\\D', '', 'g') = any(%(cnpjs)s))"
    return ""


def apply_cnpj_scope_to_sql(sql: str, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> str:
    filter_sql = cnpj_filter(cnpj, authorized_cnpjs).removeprefix("and ")
    if not filter_sql:
        return sql

    scoped_sql = sql.strip().rstrip(";")
    lower_sql = scoped_sql.lower()
    insert_at = len(scoped_sql)
    for keyword in [" group by", " having", " order by", " limit"]:
        index = lower_sql.find(keyword)
        if index >= 0:
            insert_at = min(insert_at, index)

    if " where " in lower_sql:
        return f"{scoped_sql[:insert_at]} and {filter_sql}{scoped_sql[insert_at:]}"
    return f"{scoped_sql[:insert_at]} where {filter_sql}{scoped_sql[insert_at:]}"


def execute_optional_select(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        return execute_select(sql, params)
    except Exception:
        return []


def kpi_context_cache_key(data_inicio: date, data_fim: date, cnpj: str | None, authorized_cnpjs: list[str] | None) -> tuple[Any, ...]:
    return (
        data_inicio.isoformat(),
        data_fim.isoformat(),
        normalize_cnpj(cnpj),
        tuple(sorted(scoped_cnpjs(authorized_cnpjs))) if authorized_cnpjs is not None else None,
    )


def scoped_cache_part(cnpj: str | None, authorized_cnpjs: list[str] | None) -> tuple[Any, ...]:
    return (normalize_cnpj(cnpj), tuple(sorted(scoped_cnpjs(authorized_cnpjs))) if authorized_cnpjs is not None else None)


def build_kpi_context(data_inicio: date | None, data_fim: date | None, cnpj: str | None = None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    if not data_inicio or not data_fim:
        return {"periodo": {"data_inicio": serialize(data_inicio), "data_fim": serialize(data_fim)}, "erro": "periodo ausente"}

    cache_key = kpi_context_cache_key(data_inicio, data_fim, cnpj, authorized_cnpjs)
    cached = _kpi_context_cache.get(cache_key)
    now = monotonic()
    if cached and now - cached[0] <= KPI_CONTEXT_CACHE_SECONDS:
        return cached[1]

    params: dict[str, Any] = {"data_inicio": data_inicio, "data_fim": data_fim}
    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    summary_sql = f"""
    with fat as (
      select coalesce(sum(faturamento_liquido), 0) as faturamento, coalesce(sum(qtd_cupons), 0) as cupons
      from analytics.mv_kpi_faturamento_diario
      where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    ), itens as (
      select coalesce(sum(qtd_itens_vendidos), 0) as itens
      from analytics.mv_kpi_itens_vendidos
      where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    ), lucro as (
      select
        coalesce(sum(lucro_bruto_total), 0) as lucro,
        coalesce(sum(receita_liquida_item), 0) as receita,
        coalesce(sum(custo_total_estimado), 0) as custo,
        case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_total) / sum(receita_liquida_item) end as margem
      from analytics.mv_kpi_lucro_total_diario
      where data between %(data_inicio)s and %(data_fim)s {loja_filter}
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
    """
    stores_sql = f"""
    select loja_id, max(loja) as loja, sum(qtd_cupons) as cupons, sum(faturamento_liquido) as faturamento
    from analytics.mv_kpi_faturamento_loja
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by loja_id
    order by faturamento desc
    """
    profit_sql = f"""
    select produto_id, max(produto) as produto, sum(qtd_vendida) as qtd, sum(receita_liquida_item) as receita, sum(custo_total_estimado) as custo, sum(lucro_bruto_estimado) as lucro
    from analytics.mv_kpi_lucro_produto
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by produto_id
    order by lucro desc
    limit 50
    """
    loss_sql = f"""
    select produto_id, max(produto) as produto, sum(qtd_vendida) as qtd, sum(receita_liquida_item) as receita, sum(custo_total_estimado) as custo, sum(lucro_bruto_estimado) as lucro
    from analytics.mv_kpi_lucro_produto
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by produto_id
    having sum(lucro_bruto_estimado) < 0
    order by lucro asc
    limit 10
    """
    trend_sql = f"""
    select data, sum(faturamento_liquido) as faturamento, sum(qtd_cupons) as cupons
    from analytics.mv_kpi_faturamento_diario
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by data
    order by data desc
    limit 14
    """
    monthly_sql = f"""
    select *
    from (
      select
        mes,
        sum(faturamento_liquido) as faturamento,
        sum(qtd_cupons) as cupons,
        case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
      from analytics.mv_kpi_faturamento_mensal
      where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date {loja_filter}
      group by mes
      order by mes desc
      limit 36
    ) mensal
    order by mes
    """
    executive_sql = f"""
    with atual as (
      select
        coalesce(sum(faturamento_liquido), 0) as faturamento,
        coalesce(sum(qtd_cupons), 0) as cupons,
        case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio,
        coalesce(sum(qtd_itens_vendidos), 0) as itens,
        coalesce(sum(lucro_bruto_total), 0) as lucro,
        case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_total) / sum(receita_liquida_item) end as margem
      from analytics.mv_ai_resumo_executivo_diario
      where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    ), anterior as (
      select
        coalesce(sum(faturamento_liquido), 0) as faturamento,
        coalesce(sum(qtd_cupons), 0) as cupons,
        coalesce(sum(lucro_bruto_total), 0) as lucro
      from analytics.mv_ai_resumo_executivo_diario
      where data between (%(data_inicio)s::date - ((%(data_fim)s::date - %(data_inicio)s::date) + 1)) and (%(data_inicio)s::date - 1) {loja_filter}
    )
    select
      atual.*,
      anterior.faturamento as faturamento_periodo_anterior,
      anterior.cupons as cupons_periodo_anterior,
      anterior.lucro as lucro_periodo_anterior,
      case when anterior.faturamento = 0 then null else (atual.faturamento - anterior.faturamento) / anterior.faturamento end as variacao_faturamento,
      case when anterior.cupons = 0 then null else (atual.cupons - anterior.cupons) / anterior.cupons end as variacao_cupons,
      case when anterior.lucro = 0 then null else (atual.lucro - anterior.lucro) / anterior.lucro end as variacao_lucro
    from atual cross join anterior
    """
    sellers_sql = f"""
    select
      vendedor_id,
      vendedor,
      sum(valor_vendido) as valor_vendido,
      sum(qtd_vendas) as qtd_vendas,
      case when sum(qtd_vendas) = 0 then 0 else sum(valor_vendido) / sum(qtd_vendas) end as ticket_medio,
      case when sum(qtd_vendas) = 0 then 0 else sum(qtd_itens_vendidos) / sum(qtd_vendas) end as itens_por_venda,
      sum(qtd_skus) as qtd_skus,
      sum(lucro_bruto_estimado) as lucro,
      case when sum(valor_vendido) = 0 then null else sum(lucro_bruto_estimado) / sum(valor_vendido) end as margem,
      sum(desconto_manual) as desconto_manual,
      sum(desconto_automatico) as desconto_automatico,
      sum(valor_devolucao) as valor_devolucao
    from analytics.mv_ai_vendedor_diario
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by vendedor_id, vendedor
    order by valor_vendido desc
    limit 10
    """
    hourly_sql = f"""
    select
      hora,
      max(faixa_horaria) as faixa_horaria,
      sum(faturamento_liquido) as faturamento,
      sum(qtd_cupons) as cupons,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
    from analytics.mv_ai_vendas_horario
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by hora
    order by faturamento desc
    """
    seasonality_sql = f"""
    select
      dia_semana,
      max(nome_dia_semana) as nome_dia_semana,
      count(distinct data) as dias_analisados,
      sum(faturamento_liquido) as faturamento,
      sum(qtd_cupons) as cupons,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
    from analytics.mv_ai_sazonalidade_dia_semana
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by dia_semana
    order by faturamento desc
    """
    alerts_sql = f"""
    select
      tipo_alerta,
      severidade,
      max(titulo) as titulo,
      max(descricao) as descricao,
      count(*) as ocorrencias,
      sum(valor_atual) as valor_total,
      max(data_ref) as ultima_data
    from analytics.mv_ai_alertas_operacionais
    where data_ref between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by tipo_alerta, severidade
    order by case severidade when 'alta' then 1 when 'media' then 2 else 3 end, ocorrencias desc
    limit 10
    """
    customers_sql = f"""
    with periodo_cliente as (
      select
        cliente_id,
        max(cliente) as cliente,
        sum(qtd_cupons) as cupons,
        sum(faturamento_liquido) as faturamento,
        case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio,
        min(primeira_compra_loja) as primeira_compra,
        max(data) as ultima_compra
      from analytics.mv_ai_cliente_diario
      where data between %(data_inicio)s and %(data_fim)s {loja_filter}
      group by cliente_id
    ), inativos as (
      select count(distinct h.cliente_id) as clientes_inativos
      from analytics.mv_ai_cliente_diario h
      where h.data < %(data_inicio)s {loja_filter}
        and not exists (
          select 1
          from analytics.mv_ai_cliente_diario p
          where p.cliente_id = h.cliente_id
            and p.loja_id = h.loja_id
            and p.data between %(data_inicio)s and %(data_fim)s
        )
    )
    select
      count(*) as clientes_ativos,
      count(*) filter (where primeira_compra between %(data_inicio)s and %(data_fim)s) as clientes_novos,
      count(*) filter (where cupons > 1) as clientes_recorrentes,
      coalesce(max(inativos.clientes_inativos), 0) as clientes_inativos,
      coalesce(sum(faturamento), 0) as faturamento_clientes,
      case when sum(cupons) = 0 then 0 else sum(faturamento) / sum(cupons) end as ticket_medio_clientes
    from periodo_cliente cross join inativos
    """
    vip_customers_sql = f"""
    select
      cliente_id,
      max(cliente) as cliente,
      sum(qtd_cupons) as cupons,
      sum(faturamento_liquido) as faturamento,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio,
      max(data) as ultima_compra
    from analytics.mv_ai_cliente_diario
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by cliente_id
    order by faturamento desc
    limit 10
    """
    strategic_products_sql = f"""
    with produto as (
      select
        produto_id,
        max(produto) as produto,
        sum(qtd_vendida) as qtd_vendida,
        sum(receita_liquida_item) as receita,
        sum(lucro_bruto_estimado) as lucro,
        case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_estimado) / sum(receita_liquida_item) end as margem
      from analytics.mv_ai_produto_mensal
      where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date {loja_filter}
      group by produto_id
    ), abc as (
      select
        *,
        sum(receita) over () as receita_total,
        sum(receita) over (order by receita desc rows unbounded preceding) as receita_acumulada
      from produto
    )
    select
      produto_id,
      produto,
      qtd_vendida,
      receita,
      lucro,
      margem,
      case
        when receita_total = 0 then 'C'
        when receita_acumulada / receita_total <= 0.80 then 'A'
        when receita_acumulada / receita_total <= 0.95 then 'B'
        else 'C'
      end as curva_abc_faturamento
    from abc
    order by receita desc
    limit 15
    """
    product_trends_sql = f"""
    with mensal as (
      select
        mes,
        produto_id,
        max(produto) as produto,
        sum(receita_liquida_item) as receita,
        sum(qtd_vendida) as qtd_vendida,
        sum(lucro_bruto_estimado) as lucro
      from analytics.mv_ai_produto_mensal
      where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date {loja_filter}
      group by mes, produto_id
    ), bordas as (
      select distinct on (produto_id)
        produto_id,
        first_value(produto) over w as produto,
        first_value(receita) over w as receita_inicio,
        last_value(receita) over w as receita_fim,
        first_value(qtd_vendida) over w as qtd_inicio,
        last_value(qtd_vendida) over w as qtd_fim
      from mensal
      window w as (partition by produto_id order by mes rows between unbounded preceding and unbounded following)
    )
    select
      produto_id,
      produto,
      receita_inicio,
      receita_fim,
      receita_fim - receita_inicio as variacao_receita,
      qtd_inicio,
      qtd_fim,
      qtd_fim - qtd_inicio as variacao_qtd
    from bordas
    where receita_inicio is not null and receita_fim is not null
    order by abs(receita_fim - receita_inicio) desc
    limit 10
    """
    discounts_sql = f"""
    select
      coalesce(sum(faturamento_liquido), 0) as faturamento,
      coalesce(sum(desconto_manual), 0) as desconto_manual,
      coalesce(sum(desconto_automatico), 0) as desconto_automatico,
      coalesce(sum(desconto_total), 0) as desconto_total,
      case when sum(faturamento_liquido) = 0 then null else sum(desconto_total) / sum(faturamento_liquido) end as percentual_desconto,
      coalesce(sum(valor_devolucao), 0) as valor_devolucao,
      case when sum(faturamento_liquido + valor_devolucao) = 0 then null else sum(valor_devolucao) / sum(faturamento_liquido + valor_devolucao) end as percentual_devolucao
    from analytics.mv_ai_desconto_devolucao_diario
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    """
    discount_return_products_sql = f"""
    select
      produto_id,
      max(produto) as produto,
      sum(desconto_total) as desconto_total,
      sum(valor_devolucao) as valor_devolucao,
      sum(qtd_devolvida) as qtd_devolvida,
      sum(receita_liquida_item) as receita
    from analytics.mv_ai_desconto_devolucao_produto_mensal
    where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date {loja_filter}
    group by produto_id
    order by valor_devolucao desc, desconto_total desc
    limit 10
    """

    context = serialize({
        "periodo": {"data_inicio": data_inicio, "data_fim": data_fim, "cnpj": cnpj, "cnpjs_autorizados": authorized_cnpjs},
        "resumo": execute_select(summary_sql, params)[0],
        "faturamento_mensal": execute_select(monthly_sql, params),
        "lojas": execute_select(stores_sql, params),
        "tendencia_diaria": execute_select(trend_sql, params),
        "observacoes": [
            "faturamento = vlr_liquido - vlr_devolucao",
            "faturamento_mensal contem ate os ultimos 36 meses do periodo filtrado, em ordem cronologica",
            "lucro e margem sao estimados a partir dos custos disponiveis",
            "lojas lista todas as lojas autorizadas do usuario que tiveram consolidacao no periodo",
            "perguntas detalhadas de produtos, vendedores, horarios, sazonalidade, clientes, descontos e alertas usam rotas especializadas para nao pesar o contexto generico",
            "KPIs executivos AI-only ignoram vendas com data futura",
            "use o periodo selecionado como referencia quando a pergunta for vaga",
        ],
    })
    _kpi_context_cache[cache_key] = (now, context)
    if len(_kpi_context_cache) > 256:
        oldest_key = min(_kpi_context_cache, key=lambda key: _kpi_context_cache[key][0])
        _kpi_context_cache.pop(oldest_key, None)
    return context


def local_answer(route: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    template = route.get("template") or {}
    metric = template.get("metric_key", "metrica")

    if not rows:
        return f"Nao encontrei dados para a metrica {metric} no filtro informado."

    first = rows[0]
    if metric in {"faturamento_diario", "faturamento_mensal", "faturamento_loja"}:
        value = first.get("faturamento") or first.get("faturamento_liquido")
        return f"Faturamento encontrado: {format_brl(value)}."
    if metric == "ticket_medio":
        return f"Ticket medio: {format_brl(first.get('ticket_medio'))}."
    if metric == "quantidade_cupons":
        return f"Quantidade de cupons: {format_int(first.get('qtd_cupons'))}."
    if metric == "itens_vendidos":
        return f"Itens vendidos: {format_int(first.get('itens_vendidos'))}."
    if metric == "margem_bruta":
        margem = float(first.get("margem_bruta_percentual") or 0) * 100
        return f"Margem bruta estimada: {margem:,.2f}%. Receita analisada: {format_brl(first.get('receita'))}. Lucro bruto estimado: {format_brl(first.get('lucro_bruto_total'))}."
    if metric == "produtos_prejuizo":
        products = []
        for index, row in enumerate(rows[:5]):
            loss = row.get("prejuizo") or row.get("lucro_bruto_estimado") or row.get("lucro") or 0
            products.append(f"{index + 1}. {row.get('produto', 'produto')}: prejuizo estimado de {format_brl(abs(float(loss or 0)))}")
        return f"Encontrei {len(rows)} produto(s) com prejuizo no periodo. Maiores pontos de atencao: " + " ".join(products)
    if metric == "lucro_produto":
        product = first.get("produto", "produto")
        profit = first.get("lucro") or first.get("lucro_bruto_estimado") or 0
        return f"Produto com maior lucro estimado: {product}, com {format_brl(profit)}. Lucro e margem sao estimados ate homologacao de custo."
    return f"Encontrei {len(rows)} linha(s) para {metric}."


def format_brl(value: Any) -> str:
    formatted = f"{float(value or 0):,.2f}"
    return "R$ " + formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def format_int(value: Any) -> str:
    formatted = f"{int(float(value or 0)):,}"
    return formatted.replace(",", ".")


def format_percent(value: Any) -> str:
    formatted = f"{float(value or 0):,.2f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".") + "%"


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def is_pharmacy_business_scope(question: str) -> bool:
    normalized = normalize_text(question)
    return any(keyword in normalized for keyword in PHARMACY_BUSINESS_SCOPE_KEYWORDS)


def is_clear_out_of_scope_question(question: str) -> bool:
    normalized = normalize_text(question)
    if not normalized:
        return False
    if is_pharmacy_business_scope(normalized):
        return False
    return any(pattern in normalized for pattern in CLEAR_OUT_OF_SCOPE_PATTERNS)


def answer_out_of_scope(question: str, data_inicio: date | None, data_fim: date | None) -> dict[str, Any]:
    return {
        "status": "answered",
        "question": question,
        "answer": (
            "Nao vou responder esse tema porque ele foge do escopo do assistente BI para farmacias. "
            "Posso ajudar com vendas, faturamento, margem, produtos, lojas, atendimento, campanhas, crescimento "
            "e estrategias de negocio para farmacias."
        ),
        "openai_enabled": has_openai_key(),
        "rows": [],
        "route": {"status": "scope_blocked", "intent": "fora_escopo"},
        "params": serialize({"data_inicio": data_inicio, "data_fim": data_fim}),
    }


def is_formula_question(question: str) -> bool:
    normalized = normalize_text(question)
    return any(term in normalized for term in ["como calcul", "qual formula", "formula", "criterio", "regra", "de onde vem"])


def is_network_question(question: str) -> bool:
    normalized = normalize_text(question)
    return any(term in normalized for term in ["rede", "media geral", "geral do banco"])


def resolve_operational_metric(question: str) -> str | None:
    normalized = normalize_text(question)
    if "cupom" in normalized and any(term in normalized for term in ["1 item", "um item", "item unico"]):
        return "cupons_um_item"
    if "desconto" not in normalized:
        return None
    if "cmv" in normalized:
        return "desconto_cmv"
    if any(term in normalized for term in ["automatico", "auto"]):
        return "desconto_automatico"
    if any(term in normalized for term in ["usuario", "manual", "balcao"]):
        return "desconto_usuario"
    return None


def classify_topic(text: str | None) -> str | None:
    if not text:
        return None
    normalized = normalize_text(text)
    if extract_product_code(normalized):
        return "produto_especifico"
    operational_metric = resolve_operational_metric(normalized)
    if operational_metric:
        return operational_metric
    if "ticket" in normalized or "cupom medio" in normalized:
        return "ticket_medio"
    if "desconto" in normalized or "devolucao" in normalized:
        return "descontos_devolucoes"
    if "dre" in normalized or "demonstrativo" in normalized:
        return "dre"
    if "margem" in normalized or "lucro bruto" in normalized:
        return "margem"
    if "cmv" in normalized or "custo da mercadoria" in normalized or "custo mercadoria" in normalized:
        return "cmv"
    if "loja" in normalized or "filial" in normalized:
        if any(term in normalized for term in ["faturamento", "faturou", "vendi", "vendeu", "vendas", "receita", "loja que mais", "loja com menor"]):
            return "faturamento_por_loja"
    if any(term in normalized for term in ["faturamento", "faturou", "vendi", "vendeu", "vendas", "receita"]):
        return "faturamento"
    return None


def last_history_topic(question: str, history: list[dict[str, str]] | None) -> str | None:
    current_topic = classify_topic(question)
    if current_topic:
        return current_topic
    for message in reversed(history or []):
        topic = classify_topic(message.get("content"))
        if topic:
            return topic
    return None


def answer_formula(question: str, topic: str | None, data_inicio: date | None, data_fim: date | None) -> dict[str, Any]:
    definition = KPI_DEFINITIONS.get(topic or "")
    if not definition:
        answer = "Ainda nao identifiquei qual KPI voce quer detalhar. Pergunte, por exemplo: 'como calculou o faturamento?' ou 'como calculou a margem?'."
    else:
        answer = f"{definition['label']}: {definition['formula']} Fonte: {definition['source']}."
    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": [],
        "route": {"status": "local_followup", "intent": "formula", "topic": topic},
        "params": serialize({"data_inicio": data_inicio, "data_fim": data_fim}),
    }


def limited_list_note(total: int, shown: int) -> str:
    if total <= shown:
        return ""
    return f" Encontrei {total} itens; listei os {shown} principais para evitar uma resposta pesada. Refine por loja ou periodo para detalhar mais."


def has_revenue_word(question: str) -> bool:
    normalized = question.lower()
    return any(word in normalized for word in ["faturamento", "faturou", "vendi", "vendeu", "vendas", "receita"])


def has_list_word(question: str) -> bool:
    normalized = question.lower()
    return any(word in normalized for word in ["liste", "listar", "lista", "todos", "todas", "relacao", "relação", "ranking"])


def is_monthly_revenue_series(question: str) -> bool:
    normalized = question.lower()
    monthly_words = ["cada mes", "cada mês", "por mes", "por mês", "mes a mes", "mês a mês", "mensal", "mensais"]
    return has_revenue_word(normalized) and any(word in normalized for word in monthly_words)


def is_daily_revenue_series(question: str) -> bool:
    normalized = question.lower()
    daily_words = ["cada dia", "por dia", "dia a dia", "diario", "diário", "diaria", "diária"]
    return has_revenue_word(normalized) and any(word in normalized for word in daily_words)


def is_store_revenue_question(question: str) -> bool:
    normalized = question.lower()
    store_words = ["loja", "lojas", "jola", "jolas", "filial", "filiais"]
    ranking_words = ["mais", "maior", "melhor", "top", "ranking", "por", "pior", "menor", "menos", "fraca", "fraco", "baixo", "baixa"]
    return any(word in normalized for word in store_words) and (has_revenue_word(normalized) or has_list_word(normalized) or any(word in normalized for word in ranking_words))


def is_worst_store_question(question: str) -> bool:
    normalized = question.lower()
    return any(word in normalized for word in ["pior", "menor", "menos", "fraca", "fraco", "baixo", "baixa"])


def is_total_revenue_question(question: str) -> bool:
    normalized = question.lower()
    total_words = ["quanto", "total", "periodo", "período", "geral", "resumo"]
    return has_revenue_word(normalized) and any(word in normalized for word in total_words)


def is_ticket_question(question: str) -> bool:
    normalized = question.lower()
    return "ticket" in normalized or "cupom medio" in normalized or "cupom médio" in normalized


def is_goal_question(question: str) -> bool:
    normalized = question.lower()
    return any(word in normalized for word in ["meta", "metas", "orcado", "orçado", "objetivo"])


def answer_goal_unavailable(question: str, data_inicio: date | None, data_fim: date | None) -> dict[str, Any]:
    return {
        "status": "answered",
        "question": question,
        "answer": "Nao ha meta cadastrada na base analitica atual. Posso comparar o periodo selecionado com o periodo anterior ou com a media historica, mas nao devo tratar isso como meta oficial.",
        "openai_enabled": has_openai_key(),
        "rows": [],
        "route": {"status": "guardrail_matched", "intent": "meta_indisponivel"},
        "params": serialize({"data_inicio": data_inicio, "data_fim": data_fim}),
    }


def is_dre_question(question: str) -> bool:
    normalized = question.lower()
    return "dre" in normalized or "demonstrativo" in normalized or "resultado gerencial" in normalized


def is_cmv_question(question: str) -> bool:
    normalized = question.lower()
    return "cmv" in normalized or "custo da mercadoria" in normalized or "custo mercadoria" in normalized


def answer_margin_summary(
    question: str,
    data_inicio: date | None,
    data_fim: date | None,
    cnpj: str | None,
    authorized_cnpjs: list[str] | None = None,
    mode: Literal["cmv", "dre"] = "cmv",
) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para calcular CMV ou DRE gerencial, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "guardrail_matched", "intent": mode},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      coalesce(sum(receita_liquida_item), 0) as receita_liquida,
      coalesce(sum(custo_total_estimado), 0) as cmv_estimado,
      coalesce(sum(lucro_bruto_total), 0) as lucro_bruto_estimado,
      case when sum(receita_liquida_item) = 0 then null else sum(custo_total_estimado) / sum(receita_liquida_item) end as cmv_percentual,
      case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_total) / sum(receita_liquida_item) end as margem_bruta
    from analytics.mv_kpi_lucro_total_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    """
    rows = [serialize(row) for row in execute_select(sql, params)]
    first = rows[0] if rows else {}
    cmv_pct = float(first.get("cmv_percentual") or 0) * 100
    margin_pct = float(first.get("margem_bruta") or 0) * 100
    if mode == "dre":
        answer = (
            "DRE contabil completa nao esta disponivel na base atual porque faltam contas como despesas operacionais, impostos detalhados e resultado financeiro. "
            f"DRE parcial/gerencial do periodo {params['data_inicio']} a {params['data_fim']}: "
            f"receita liquida analisada {format_brl(first.get('receita_liquida'))}, "
            f"CMV estimado {format_brl(first.get('cmv_estimado'))} ({format_percent(cmv_pct)}), "
            f"lucro bruto estimado {format_brl(first.get('lucro_bruto_estimado'))} e margem bruta estimada {format_percent(margin_pct)}."
        )
    else:
        answer = (
            f"CMV percentual estimado: {format_percent(cmv_pct)} no periodo de {params['data_inicio']} a {params['data_fim']}. "
            f"Calculo padronizado: custo_total_estimado / receita_liquida_item. Base: CMV {format_brl(first.get('cmv_estimado'))} "
            f"sobre receita liquida analisada de {format_brl(first.get('receita_liquida'))}."
        )

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "guardrail_matched", "intent": mode},
        "params": serialize(params),
        "sql": sql,
    }


def is_seller_question(question: str) -> bool:
    normalized = question.lower()
    seller_words = ["vendedor", "vendedores", "colaborador", "colaboradores", "equipe", "operador", "operadores"]
    performance_words = ["vendeu", "venderam", "vende", "vendas", "mais", "maior", "melhor", "top", "ranking", "ticket", "margem", "lucro", "desconto", "devolucao", "devolução", "performance", "desempenho", "sku"]
    return any(word in normalized for word in seller_words) and (has_list_word(normalized) or any(word in normalized for word in performance_words))


def is_seller_margin_question(question: str) -> bool:
    normalized = question.lower()
    return any(word in normalized for word in ["margem", "lucro", "prejuizo", "prejuízo", "sem margem"])


def is_low_margin_question(question: str) -> bool:
    normalized = question.lower()
    return any(word in normalized for word in ["sem margem", "prejuizo", "prejuízo", "negativo", "negativa", "pior", "menor", "baixo", "baixa"])


def is_high_margin_question(question: str) -> bool:
    normalized = question.lower()
    return any(word in normalized for word in ["maior", "melhor", "mais", "alto", "alta"])


def is_hour_question(question: str) -> bool:
    normalized = question.lower()
    hour_words = ["horario", "horário", "hora", "horas", "faixa", "manha", "manhã", "tarde", "noite", "madrugada"]
    movement_words = ["vende", "vendo", "vendeu", "vendas", "mais", "maior", "melhor", "top", "faturamento", "movimento", "cupons", "ticket", "reforcar", "reforçar"]
    return any(word in normalized for word in hour_words) and (has_list_word(normalized) or any(word in normalized for word in movement_words))


def is_seasonality_question(question: str) -> bool:
    normalized = question.lower()
    day_words = [
        "dia da semana",
        "dias da semana",
        "semana",
        "segunda",
        "terca",
        "terça",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "sábado",
        "domingo",
        "sazonalidade",
    ]
    metric_words = ["vende", "vendeu", "vendas", "faturamento", "cupons", "ticket", "melhor", "pior", "movimento"]
    product_words = ["produto", "produtos", "sku", "item", "itens"]
    return any(word in normalized for word in day_words) and (has_list_word(normalized) or any(word in normalized for word in metric_words)) and not any(word in normalized for word in product_words)


def is_alert_question(question: str) -> bool:
    normalized = question.lower()
    alert_words = ["alerta", "alertas", "problema", "problemas", "risco", "riscos", "atenção", "atencao", "queda", "priorizar", "prioridade", "anomalia"]
    return any(word in normalized for word in alert_words)


def is_discount_return_question(question: str) -> bool:
    normalized = question.lower()
    words = [
        "desconto",
        "descontos",
        "devolucao",
        "devolução",
        "devolucoes",
        "devoluções",
        "produto devolvido",
        "produtos devolvidos",
        "estorno",
        "estornos",
    ]
    return any(word in normalized for word in words)


def answer_seasonality(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para analisar sazonalidade por dia da semana, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "sazonalidade_dia_semana"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      dia_semana,
      max(nome_dia_semana) as nome_dia_semana,
      count(distinct data) as dias_analisados,
      sum(qtd_cupons) as cupons,
      sum(faturamento_liquido) as faturamento,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
    from analytics.mv_ai_sazonalidade_dia_semana
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    group by dia_semana
    order by faturamento desc
    """
    rows = [serialize(row) for row in execute_optional_select(sql, params)]
    if not rows:
        answer = "Nao encontrei sazonalidade por dia da semana para o periodo selecionado."
    else:
        best = rows[0]
        worst = rows[-1]
        parts = [f"{row.get('nome_dia_semana')}: {format_brl(row.get('faturamento'))}" for row in rows]
        answer = (
            f"O melhor dia da semana foi {best.get('nome_dia_semana')}, com {format_brl(best.get('faturamento'))} "
            f"e ticket medio de {format_brl(best.get('ticket_medio'))}. "
            f"O dia mais fraco foi {worst.get('nome_dia_semana')}, com {format_brl(worst.get('faturamento'))}. "
            "Dias retornados: " + "; ".join(parts) + "."
        )

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": "sazonalidade_dia_semana"},
        "params": serialize(params),
        "sql": sql,
    }


def is_customer_question(question: str) -> bool:
    normalized = question.lower()
    customer_words = ["cliente", "clientes", "vip", "recorrente", "recorrentes", "inativo", "inativos", "abandono", "recompra", "ltv"]
    return any(word in normalized for word in customer_words)


def answer_discounts_returns(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para analisar descontos e devolucoes, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "descontos_devolucoes"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    summary_sql = f"""
    select
      coalesce(sum(faturamento_liquido), 0) as faturamento,
      coalesce(sum(qtd_cupons), 0) as cupons,
      coalesce(sum(desconto_manual), 0) as desconto_manual,
      coalesce(sum(desconto_automatico), 0) as desconto_automatico,
      coalesce(sum(desconto_total), 0) as desconto_total,
      case when sum(faturamento_liquido) = 0 then null else sum(desconto_total) / sum(faturamento_liquido) end as percentual_desconto,
      coalesce(sum(valor_devolucao), 0) as valor_devolucao,
      case when sum(faturamento_liquido + valor_devolucao) = 0 then null else sum(valor_devolucao) / sum(faturamento_liquido + valor_devolucao) end as percentual_devolucao
    from analytics.mv_ai_desconto_devolucao_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    """
    products_sql = f"""
    select
      produto_id,
      max(produto) as produto,
      sum(desconto_total) as desconto_total,
      sum(valor_devolucao) as valor_devolucao,
      sum(qtd_devolvida) as qtd_devolvida,
      sum(receita_liquida_item) as receita
    from analytics.mv_ai_desconto_devolucao_produto_mensal
    where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date
    {loja_filter}
    group by produto_id
    order by valor_devolucao desc, desconto_total desc
    limit 50
    """
    daily_sql = f"""
    select
      data,
      sum(faturamento_liquido) as faturamento,
      sum(desconto_total) as desconto_total,
      sum(valor_devolucao) as valor_devolucao
    from analytics.mv_ai_desconto_devolucao_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    group by data
    order by data desc
    limit 31
    """
    summary_rows = [serialize(row) for row in execute_optional_select(summary_sql, params)]
    product_rows = [serialize(row) for row in execute_optional_select(products_sql, params)]
    daily_rows = [serialize(row) for row in execute_optional_select(daily_sql, params)]
    summary = summary_rows[0] if summary_rows else {}
    discount_pct = float(summary.get("percentual_desconto") or 0) * 100
    return_pct = float(summary.get("percentual_devolucao") or 0) * 100
    answer = (
        f"No periodo de {params['data_inicio']} a {params['data_fim']}, "
        f"os descontos somaram {format_brl(summary.get('desconto_total'))} "
        f"({format_percent(discount_pct)} do faturamento) e as devolucoes somaram {format_brl(summary.get('valor_devolucao'))} "
        f"({format_percent(return_pct)} sobre venda bruta aproximada)."
    )
    if product_rows:
        top = product_rows[0]
        answer += f" Produto com maior devolucao: {top.get('produto')}, com {format_brl(top.get('valor_devolucao'))}."

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": [{"resumo": summary, "produtos": product_rows, "serie_diaria": daily_rows}],
        "route": {"status": "consultative_matched", "intent": "descontos_devolucoes"},
        "params": serialize(params),
        "sql": summary_sql,
    }


def operational_summary_row(data_inicio: date, data_fim: date, cnpj: str | None = None, authorized_cnpjs: list[str] | None = None) -> tuple[dict[str, Any], str, dict[str, Any]]:
    params: dict[str, Any] = {"data_inicio": data_inicio, "data_fim": data_fim}
    add_cnpj_params(params, cnpj, authorized_cnpjs)
    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      coalesce(sum(total_cupons), 0) as total_cupons,
      coalesce(sum(cupons_um_item), 0) as cupons_um_item,
      case when sum(total_cupons) = 0 then null else sum(cupons_um_item)::numeric / sum(total_cupons) end as percentual_cupons_um_item,
      coalesce(sum(desconto_manual), 0) as desconto_manual,
      coalesce(sum(desconto_automatico), 0) as desconto_automatico,
      coalesce(sum(desconto_total), 0) as desconto_total,
      coalesce(sum(receita_liquida_item), 0) as receita_liquida_item,
      coalesce(sum(custo_total_estimado), 0) as custo_total_estimado,
      case when sum(receita_liquida_item) = 0 then null else sum(desconto_manual) / sum(receita_liquida_item) end as percentual_desconto_manual,
      case when sum(receita_liquida_item) = 0 then null else sum(desconto_automatico) / sum(receita_liquida_item) end as percentual_desconto_automatico,
      case when sum(custo_total_estimado) = 0 then null else sum(desconto_total) / sum(custo_total_estimado) end as percentual_desconto_cmv
    from analytics.mv_kpi_operacional_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    """
    rows = [serialize(row) for row in execute_select(sql, params)]
    return (rows[0] if rows else {}, sql, params)


def answer_operational_kpi(
    question: str,
    data_inicio: date | None,
    data_fim: date | None,
    cnpj: str | None,
    authorized_cnpjs: list[str] | None = None,
    metric_key: str | None = None,
) -> dict[str, Any]:
    metric_key = metric_key or resolve_operational_metric(question)
    params = parse_period(question, data_inicio, data_fim)
    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para calcular o indicador operacional, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": metric_key or "operacional"},
            "params": serialize(params),
        }

    row, sql, query_params = operational_summary_row(params["data_inicio"], params["data_fim"], cnpj, authorized_cnpjs)
    if metric_key == "desconto_usuario":
        pct = float(row.get("percentual_desconto_manual") or 0) * 100
        answer = (
            f"Desconto usuario: {format_percent(pct)} no periodo de {params['data_inicio']} a {params['data_fim']}. "
            f"Base: {format_brl(row.get('desconto_manual'))} de desconto manual sobre {format_brl(row.get('receita_liquida_item'))} de receita liquida analisada."
        )
    elif metric_key == "desconto_automatico":
        pct = float(row.get("percentual_desconto_automatico") or 0) * 100
        answer = (
            f"Desconto automatico: {format_percent(pct)} no periodo de {params['data_inicio']} a {params['data_fim']}. "
            f"Base: {format_brl(row.get('desconto_automatico'))} de desconto automatico sobre {format_brl(row.get('receita_liquida_item'))} de receita liquida analisada."
        )
    elif metric_key == "desconto_cmv":
        pct = float(row.get("percentual_desconto_cmv") or 0) * 100
        answer = (
            f"Desconto / CMV: {format_percent(pct)} no periodo de {params['data_inicio']} a {params['data_fim']}. "
            f"Base: {format_brl(row.get('desconto_total'))} de desconto total sobre {format_brl(row.get('custo_total_estimado'))} de CMV estimado."
        )
    elif metric_key == "cupons_um_item":
        pct = float(row.get("percentual_cupons_um_item") or 0) * 100
        answer = (
            f"Cupons com 1 item: {format_percent(pct)} no periodo de {params['data_inicio']} a {params['data_fim']}. "
            f"Base: {format_int(row.get('cupons_um_item'))} cupons com 1 item sobre {format_int(row.get('total_cupons'))} cupons totais."
        )
    else:
        pct = float(row.get("percentual_desconto_manual") or 0) * 100
        answer = (
            f"Desconto usuario: {format_percent(pct)}. Para detalhar, pergunte por desconto usuario, automatico, desconto / CMV ou cupons com 1 item."
        )
        metric_key = "desconto_usuario"

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": [row],
        "route": {"status": "consultative_matched", "intent": metric_key},
        "params": serialize(query_params),
        "sql": sql,
    }


def revenue_summary_row(data_inicio: date, data_fim: date, cnpj: str | None = None, authorized_cnpjs: list[str] | None = None) -> tuple[dict[str, Any], str, dict[str, Any]]:
    params: dict[str, Any] = {"data_inicio": data_inicio, "data_fim": data_fim}
    add_cnpj_params(params, cnpj, authorized_cnpjs)
    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      coalesce(sum(faturamento_liquido), 0) as faturamento,
      coalesce(sum(qtd_cupons), 0) as cupons,
      count(distinct loja_id) filter (where faturamento_liquido <> 0) as lojas_com_faturamento,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio,
      case when count(distinct loja_id) filter (where faturamento_liquido <> 0) = 0 then 0 else sum(faturamento_liquido) / count(distinct loja_id) filter (where faturamento_liquido <> 0) end as faturamento_medio_loja
    from analytics.mv_kpi_faturamento_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    """
    rows = [serialize(row) for row in execute_select(sql, params)]
    return (rows[0] if rows else {}, sql, params)


def margin_summary_row(data_inicio: date, data_fim: date, cnpj: str | None = None, authorized_cnpjs: list[str] | None = None) -> tuple[dict[str, Any], str, dict[str, Any]]:
    params: dict[str, Any] = {"data_inicio": data_inicio, "data_fim": data_fim}
    add_cnpj_params(params, cnpj, authorized_cnpjs)
    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      coalesce(sum(receita_liquida_item), 0) as receita_liquida,
      coalesce(sum(custo_total_estimado), 0) as cmv_estimado,
      coalesce(sum(lucro_bruto_total), 0) as lucro_bruto_estimado,
      case when sum(receita_liquida_item) = 0 then null else sum(custo_total_estimado) / sum(receita_liquida_item) end as cmv_percentual,
      case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_total) / sum(receita_liquida_item) end as margem_bruta
    from analytics.mv_kpi_lucro_total_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    """
    rows = [serialize(row) for row in execute_select(sql, params)]
    return (rows[0] if rows else {}, sql, params)


def answer_network_comparison(
    question: str,
    data_inicio: date | None,
    data_fim: date | None,
    cnpj: str | None,
    authorized_cnpjs: list[str] | None,
    topic: str | None,
) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para comparar com a rede, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "local_followup", "intent": "rede", "topic": topic},
            "params": serialize(params),
        }

    start = params["data_inicio"]
    end = params["data_fim"]
    comparison_topic = "faturamento" if topic == "faturamento_por_loja" else topic
    if comparison_topic == "faturamento":
        user_row, sql, query_params = revenue_summary_row(start, end, cnpj, authorized_cnpjs)
        network_row, _, _ = revenue_summary_row(start, end)
        answer = (
            f"No seu filtro, o faturamento foi {format_brl(user_row.get('faturamento'))}. "
            f"Na rede geral do BI, o faturamento total foi {format_brl(network_row.get('faturamento'))}; "
            f"a media por loja com faturamento foi {format_brl(network_row.get('faturamento_medio_loja'))} "
            f"em {format_int(network_row.get('lojas_com_faturamento'))} lojas com faturamento."
        )
        rows = [{"usuario": user_row, "rede": network_row}]
    elif comparison_topic == "ticket_medio":
        user_row, sql, query_params = revenue_summary_row(start, end, cnpj, authorized_cnpjs)
        network_row, _, _ = revenue_summary_row(start, end)
        answer = (
            f"No seu filtro, o ticket medio foi {format_brl(user_row.get('ticket_medio'))}. "
            f"Na rede geral do BI, o ticket medio foi {format_brl(network_row.get('ticket_medio'))}. "
            f"Base rede: {format_int(network_row.get('cupons'))} cupons e {format_brl(network_row.get('faturamento'))} de faturamento."
        )
        rows = [{"usuario": user_row, "rede": network_row}]
    elif comparison_topic in {"margem", "cmv"}:
        user_row, sql, query_params = margin_summary_row(start, end, cnpj, authorized_cnpjs)
        network_row, _, _ = margin_summary_row(start, end)
        if comparison_topic == "cmv":
            answer = (
                f"No seu filtro, o CMV estimado foi {format_brl(user_row.get('cmv_estimado'))} "
                f"({format_percent(float(user_row.get('cmv_percentual') or 0) * 100)} da receita analisada). "
                f"Na rede geral do BI, o CMV estimado foi {format_brl(network_row.get('cmv_estimado'))} "
                f"({format_percent(float(network_row.get('cmv_percentual') or 0) * 100)})."
            )
        else:
            answer = (
                f"No seu filtro, a margem bruta estimada foi {format_percent(float(user_row.get('margem_bruta') or 0) * 100)}. "
                f"Na rede geral do BI, a margem bruta estimada foi {format_percent(float(network_row.get('margem_bruta') or 0) * 100)}. "
                f"A conta usa soma de lucro bruto sobre soma de receita, nao media simples de margens."
            )
        rows = [{"usuario": user_row, "rede": network_row}]
    elif comparison_topic in {"desconto_usuario", "desconto_automatico", "desconto_cmv", "cupons_um_item"}:
        user_row, sql, query_params = operational_summary_row(start, end, cnpj, authorized_cnpjs)
        network_row, _, _ = operational_summary_row(start, end)
        if comparison_topic == "desconto_usuario":
            answer = (
                f"No seu filtro, o desconto usuario foi {format_percent(float(user_row.get('percentual_desconto_manual') or 0) * 100)} "
                f"({format_brl(user_row.get('desconto_manual'))}). Na rede geral do BI, foi "
                f"{format_percent(float(network_row.get('percentual_desconto_manual') or 0) * 100)}."
            )
        elif comparison_topic == "desconto_automatico":
            answer = (
                f"No seu filtro, o desconto automatico foi {format_percent(float(user_row.get('percentual_desconto_automatico') or 0) * 100)} "
                f"({format_brl(user_row.get('desconto_automatico'))}). Na rede geral do BI, foi "
                f"{format_percent(float(network_row.get('percentual_desconto_automatico') or 0) * 100)}."
            )
        elif comparison_topic == "desconto_cmv":
            answer = (
                f"No seu filtro, desconto / CMV foi {format_percent(float(user_row.get('percentual_desconto_cmv') or 0) * 100)}. "
                f"Na rede geral do BI, foi {format_percent(float(network_row.get('percentual_desconto_cmv') or 0) * 100)}."
            )
        else:
            answer = (
                f"No seu filtro, cupons com 1 item foram {format_percent(float(user_row.get('percentual_cupons_um_item') or 0) * 100)} "
                f"({format_int(user_row.get('cupons_um_item'))} de {format_int(user_row.get('total_cupons'))}). "
                f"Na rede geral do BI, foram {format_percent(float(network_row.get('percentual_cupons_um_item') or 0) * 100)}."
            )
        rows = [{"usuario": user_row, "rede": network_row}]
    else:
        answer = "Consigo comparar com a rede para faturamento, ticket medio, margem, CMV, descontos operacionais e cupons com 1 item. Refaca indicando um desses KPIs."
        sql = ""
        query_params = {"data_inicio": start, "data_fim": end}
        rows = []

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "local_followup", "intent": "rede", "topic": comparison_topic},
        "params": serialize(query_params),
        "sql": sql,
    }


def extract_product_code(text: str | None) -> str | None:
    if not text:
        return None
    normalized = normalize_text(text)
    explicit_patterns = [
        r"\b(?:ean|gtin|codigo de barras|cod(?:igo)? de barras)\s*[:#-]?\s*(\d{6,14})\b",
        r"\b(?:item|produto|prod|sku|codigo|cod)\s*[:#-]?\s*(\d{2,14})\b",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, normalized)
        if match:
            return match.group(1)
    if any(term in normalized for term in ["item", "produto", "sku", "ean", "gtin"]):
        match = re.search(r"\b(\d{2,14})\b", normalized)
        if match:
            return match.group(1)
    return None


def product_code_from_history(history: list[dict[str, str]] | None) -> str | None:
    for message in reversed(history or []):
        if message.get("role") != "user":
            continue
        code = extract_product_code(message.get("content"))
        if code:
            return code
    return None


def is_product_specific_question(question: str, history: list[dict[str, str]] | None = None) -> bool:
    normalized = normalize_text(question)
    if extract_product_code(normalized):
        return any(term in normalized for term in ["item", "produto", "sku", "ean", "gtin", "venda", "vendas", "margem", "cupom", "cupons"])
    if not product_code_from_history(history):
        return False
    return any(
        term in normalized
        for term in ["esse item", "desse item", "este item", "produto", "margem", "cupom", "cupons", "dessas vendas", "destas vendas"]
    )


def resolve_product_specific_intent(question: str) -> str:
    normalized = normalize_text(question)
    if "margem" in normalized or "lucro" in normalized or "cmv" in normalized:
        return "margem_item"
    if "cupom" in normalized or "cupons" in normalized or "cesta" in normalized:
        return "cupons_com_item"
    return "venda_item"


def product_specific_answer(row: dict[str, Any], params: dict[str, Any], intent: str) -> str:
    product_label = str(row.get("produto") or "item informado")
    if int(float(row.get("produtos_encontrados") or 0)) > 1:
        product_label = f"codigo {params.get('produto_codigo')}"
    period = f"{params.get('data_inicio')} a {params.get('data_fim')}"
    margem = float(row.get("margem_item") or 0) * 100

    if intent == "cupons_com_item":
        return (
            f"No periodo de {period}, os cupons que continham o item {product_label} somaram "
            f"{format_brl(row.get('valor_total_cupons_com_item'))}. Foram {format_int(row.get('quantidade_cupons_com_item'))} "
            "cupons com esse item. Esse valor e o total dos cupons, nao apenas o valor do item."
        )
    if intent == "margem_item":
        return (
            f"No periodo de {period}, a margem estimada do item {product_label} foi {format_percent(margem)}. "
            f"Base: venda liquida do item {format_brl(row.get('valor_total_vendido_item'))}, "
            f"CMV estimado {format_brl(row.get('cmv_estimado_item'))} e lucro bruto estimado {format_brl(row.get('lucro_bruto_item'))}. "
            "A regra definida aqui e margem do item, nao margem total dos cupons que continham o item."
        )
    return (
        f"No periodo de {period}, o item {product_label} vendeu {format_brl(row.get('valor_total_vendido_item'))}. "
        f"Quantidade vendida liquida: {format_int(row.get('quantidade_vendida'))}. "
        f"Ele apareceu em {format_int(row.get('quantidade_cupons_com_item'))} cupons. "
        "Usei vendas validas PA/DP e valor liquido do item, ja abatendo devolucoes."
    )


def answer_product_specific_sales(
    question: str,
    data_inicio: date | None,
    data_fim: date | None,
    cnpj: str | None,
    history: list[dict[str, str]] | None = None,
    authorized_cnpjs: list[str] | None = None,
) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    code = extract_product_code(question) or product_code_from_history(history)
    if code:
        params["produto_codigo"] = code
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para analisar um item especifico, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "produto_especifico"},
            "params": serialize(params),
        }
    if not params.get("produto_codigo"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Informe o codigo do item, EAN/GTIN ou SKU para eu calcular as vendas do produto.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "produto_especifico"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter_for_column("vc", "id_loja", cnpj, authorized_cnpjs)
    sql = f"""
    with produto_match as (
      select
        vi.id as venda_item_id,
        vi.id_venda as venda_id,
        vi.id_produto as produto_id,
        p.id_produto_interno,
        coalesce(vi.ean_gtin, p.gtin) as ean_gtin,
        coalesce(p.nome, vi.nome_produto) as produto,
        vi.qtd_venda - vi.qtd_devol as qtd_liquida,
        vi.vlr_venda - vi.vlr_devol as venda_liquida_item,
        (vi.qtd_venda - vi.qtd_devol) * coalesce(nullif(vi.custo_real, 0), nullif(vi.custo_medio, 0), nullif(vi.custo_ult, 0), nullif(p.custo_ult_entrada, 0), 0) as custo_total_base,
        (vi.vlr_venda - vi.vlr_devol) - ((vi.qtd_venda - vi.qtd_devol) * coalesce(nullif(vi.custo_real, 0), nullif(vi.custo_medio, 0), nullif(vi.custo_ult, 0), nullif(p.custo_ult_entrada, 0), 0)) as lucro_bruto_estimado
      from bronze.vendas_item vi
      left join analytics.dim_produto p on p.produto_id = vi.id_produto
      where vi.id_produto::text = %(produto_codigo)s
         or p.id_produto_interno::text = %(produto_codigo)s
         or regexp_replace(coalesce(vi.ean_gtin, ''), '\\D', '', 'g') = regexp_replace(%(produto_codigo)s, '\\D', '', 'g')
         or regexp_replace(coalesce(p.gtin, ''), '\\D', '', 'g') = regexp_replace(%(produto_codigo)s, '\\D', '', 'g')
    ), vendas_validas_com_item as (
      select distinct
        vc.id as venda_id,
        vc.id_loja as loja_id,
        vc.data,
        vc.vlr_liquido - vc.vlr_devolucao as vlr_liquido_ajustado
      from bronze.vendas_cab vc
      join produto_match pm on pm.venda_id = vc.id
      where vc.data between %(data_inicio)s and %(data_fim)s
        and vc.st_caixa in ('PA', 'DP')
        {loja_filter}
    ), item_agregado as (
      select
        count(distinct pm.produto_id) as produtos_encontrados,
        max(pm.produto_id) as produto_id,
        max(pm.id_produto_interno) as id_produto_interno,
        max(pm.ean_gtin) as ean_gtin,
        max(pm.produto) as produto,
        coalesce(sum(pm.qtd_liquida), 0) as quantidade_vendida,
        coalesce(sum(pm.venda_liquida_item), 0) as valor_total_vendido_item,
        coalesce(sum(pm.custo_total_base), 0) as cmv_estimado_item,
        coalesce(sum(pm.lucro_bruto_estimado), 0) as lucro_bruto_item,
        case
          when sum(pm.venda_liquida_item) = 0 then null
          else sum(pm.lucro_bruto_estimado) / sum(pm.venda_liquida_item)
        end as margem_item
      from produto_match pm
      join vendas_validas_com_item vv on vv.venda_id = pm.venda_id
    ), cupons_agregado as (
      select
        count(*) as quantidade_cupons_com_item,
        coalesce(sum(vlr_liquido_ajustado), 0) as valor_total_cupons_com_item
      from vendas_validas_com_item
    )
    select *
    from item_agregado ia
    cross join cupons_agregado ca
    """
    rows = [serialize(row) for row in execute_select(sql, params)]
    row = rows[0] if rows else {}
    if not row or int(float(row.get("quantidade_cupons_com_item") or 0)) == 0:
        answer = f"Nao encontrei vendas validas PA/DP para o item {params['produto_codigo']} no periodo selecionado."
    else:
        answer = product_specific_answer(row, params, resolve_product_specific_intent(question))

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": "produto_especifico", "topic": resolve_product_specific_intent(question)},
        "params": serialize(params),
        "sql": sql,
    }


def is_product_strategy_question(question: str) -> bool:
    normalized = question.lower()
    product_words = ["produto", "produtos", "sku", "itens"]
    strategy_words = ["abc", "curva", "lider", "líder", "lideres", "líderes", "crescimento", "crescendo", "queda", "caindo", "sazonal", "sazonalidade", "estrategico", "estratégico"]
    return any(word in normalized for word in product_words) and any(word in normalized for word in strategy_words)


def is_product_loss_question(question: str) -> bool:
    normalized = question.lower()
    product_words = ["produto", "produtos", "sku", "item", "itens"]
    loss_words = ["prejuizo", "prejuízo", "perda", "perdas", "negativo", "negativos", "margem negativa", "sem margem"]
    return any(word in normalized for word in product_words) and any(word in normalized for word in loss_words)


def is_product_profit_question(question: str) -> bool:
    normalized = question.lower()
    product_words = ["produto", "produtos", "sku", "item", "itens"]
    profit_words = ["lucro", "lucrativo", "lucrativos", "margem", "rentavel", "rentável", "rentaveis", "rentáveis"]
    return any(word in normalized for word in product_words) and any(word in normalized for word in profit_words) and not is_product_loss_question(question)


def is_product_list_question(question: str) -> bool:
    normalized = question.lower()
    product_words = ["produto", "produtos", "sku", "item", "itens"]
    return any(word in normalized for word in product_words) and has_list_word(normalized)


def product_rows_answer(rows: list[dict[str, Any]], label: str, value_key: str) -> str:
    if not rows:
        return f"Nao encontrei {label} para o periodo selecionado."
    display_rows = rows[:LIST_TEXT_LIMIT]
    parts = [
        f"{index + 1}. {row.get('produto')}: {format_brl(row.get(value_key))}"
        for index, row in enumerate(display_rows)
    ]
    return f"Encontrei {len(rows)} {label} no periodo. Lista retornada para o usuario: " + " ".join(parts) + "." + limited_list_note(len(rows), len(display_rows))


def answer_product_profitability(
    question: str,
    data_inicio: date | None,
    data_fim: date | None,
    cnpj: str | None,
    authorized_cnpjs: list[str] | None = None,
    mode: Literal["loss", "profit"] = "profit",
) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para analisar produtos, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": f"produtos_{mode}"},
            "params": serialize(params),
        }

    cache_key = (
        mode,
        params["data_inicio"].isoformat(),
        params["data_fim"].isoformat(),
        *scoped_cache_part(cnpj, authorized_cnpjs),
    )
    cached = _product_answer_cache.get(cache_key)
    now = monotonic()
    if cached and now - cached[0] <= PRODUCT_ANSWER_CACHE_SECONDS:
        return cached[1]

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    params["limit"] = 300 if authorized_cnpjs is not None or cnpj else 100
    having = "having sum(lucro_bruto_estimado) < 0" if mode == "loss" else "having sum(lucro_bruto_estimado) > 0"
    direction = "asc" if mode == "loss" else "desc"
    sql = f"""
    select
      produto_id,
      max(produto) as produto,
      sum(qtd_vendida) as qtd_vendida,
      sum(receita_liquida_item) as receita,
      sum(custo_total_estimado) as custo,
      sum(lucro_bruto_estimado) as lucro,
      case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_estimado) / sum(receita_liquida_item) end as margem
    from analytics.mv_kpi_lucro_produto
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    group by produto_id
    {having}
    order by lucro {direction}
    limit %(limit)s
    """
    rows = [serialize(row) for row in execute_optional_select(sql, params)]
    label = "produto(s) com prejuizo estimado" if mode == "loss" else "produto(s) com lucro estimado"
    answer = product_rows_answer(rows, label, "lucro")
    if len(rows) == params["limit"]:
        answer += f" Retornei os {params['limit']} principais por seguranca operacional."
    answer += " Lucro e margem sao estimados ate homologacao final de custo."
    result = {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": f"produtos_{mode}"},
        "params": serialize(params),
        "sql": sql,
    }
    _product_answer_cache[cache_key] = (now, result)
    if len(_product_answer_cache) > 256:
        oldest_key = min(_product_answer_cache, key=lambda key: _product_answer_cache[key][0])
        _product_answer_cache.pop(oldest_key, None)
    return result


def answer_customers(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para analisar clientes, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "clientes"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    summary_sql = f"""
    with periodo_cliente as (
      select
        cliente_id,
        max(cliente) as cliente,
        sum(qtd_cupons) as cupons,
        sum(faturamento_liquido) as faturamento,
        min(primeira_compra_loja) as primeira_compra,
        max(data) as ultima_compra
      from analytics.mv_ai_cliente_diario
      where data between %(data_inicio)s and %(data_fim)s
      {loja_filter}
      group by cliente_id
    )
    select
      count(*) as clientes_ativos,
      count(*) filter (where primeira_compra between %(data_inicio)s and %(data_fim)s) as clientes_novos,
      count(*) filter (where cupons > 1) as clientes_recorrentes,
      null::numeric as clientes_inativos,
      coalesce(sum(faturamento), 0) as faturamento_clientes,
      case when sum(cupons) = 0 then 0 else sum(faturamento) / sum(cupons) end as ticket_medio_clientes
    from periodo_cliente
    """
    vip_sql = f"""
    select
      cliente_id,
      max(cliente) as cliente,
      sum(qtd_cupons) as cupons,
      sum(faturamento_liquido) as faturamento,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio,
      max(data) as ultima_compra
    from analytics.mv_ai_cliente_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    group by cliente_id
    order by faturamento desc
    limit 50
    """
    summary_rows = [serialize(row) for row in execute_optional_select(summary_sql, params)]
    vip_rows = [serialize(row) for row in execute_optional_select(vip_sql, params)]
    summary = summary_rows[0] if summary_rows else {}
    answer = (
        f"No periodo, encontrei {format_int(summary.get('clientes_ativos'))} cliente(s) ativo(s), "
        f"{format_int(summary.get('clientes_novos'))} novo(s), {format_int(summary.get('clientes_recorrentes'))} recorrente(s) "
        f"e ticket medio identificado de {format_brl(summary.get('ticket_medio_clientes'))}. "
        "Clientes inativos nao foram calculados nesta lista rapida para evitar consulta pesada."
    )
    if vip_rows:
        parts = [f"{index + 1}. {row.get('cliente')}: {format_brl(row.get('faturamento'))}" for index, row in enumerate(vip_rows)]
        answer += " Clientes com maior faturamento retornados: " + " ".join(parts) + "."

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": [{"resumo": summary, "clientes_vip": vip_rows}],
        "route": {"status": "consultative_matched", "intent": "clientes"},
        "params": serialize(params),
        "sql": summary_sql,
    }


def answer_product_strategy(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para analisar produtos estrategicos, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "produtos_estrategicos"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    abc_sql = f"""
    with produto as (
      select
        produto_id,
        max(produto) as produto,
        sum(qtd_vendida) as qtd_vendida,
        sum(receita_liquida_item) as receita,
        sum(lucro_bruto_estimado) as lucro,
        case when sum(receita_liquida_item) = 0 then null else sum(lucro_bruto_estimado) / sum(receita_liquida_item) end as margem
      from analytics.mv_ai_produto_mensal
      where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date
      {loja_filter}
      group by produto_id
    ), abc as (
      select
        *,
        sum(receita) over () as receita_total,
        sum(receita) over (order by receita desc rows unbounded preceding) as receita_acumulada
      from produto
    )
    select
      produto_id,
      produto,
      qtd_vendida,
      receita,
      lucro,
      margem,
      case
        when receita_total = 0 then 'C'
        when receita_acumulada / receita_total <= 0.80 then 'A'
        when receita_acumulada / receita_total <= 0.95 then 'B'
        else 'C'
      end as curva_abc_faturamento
    from abc
    order by receita desc
    limit 15
    """
    trends_sql = f"""
    with mensal as (
      select
        mes,
        produto_id,
        max(produto) as produto,
        sum(receita_liquida_item) as receita,
        sum(qtd_vendida) as qtd_vendida
      from analytics.mv_ai_produto_mensal
      where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date
      {loja_filter}
      group by mes, produto_id
    ), bordas as (
      select distinct on (produto_id)
        produto_id,
        first_value(produto) over w as produto,
        first_value(receita) over w as receita_inicio,
        last_value(receita) over w as receita_fim,
        first_value(qtd_vendida) over w as qtd_inicio,
        last_value(qtd_vendida) over w as qtd_fim
      from mensal
      window w as (partition by produto_id order by mes rows between unbounded preceding and unbounded following)
    )
    select
      produto_id,
      produto,
      receita_inicio,
      receita_fim,
      receita_fim - receita_inicio as variacao_receita,
      qtd_inicio,
      qtd_fim,
      qtd_fim - qtd_inicio as variacao_qtd
    from bordas
    where receita_inicio is not null and receita_fim is not null
    order by abs(receita_fim - receita_inicio) desc
    limit 50
    """
    abc_rows = [serialize(row) for row in execute_optional_select(abc_sql, params)]
    trend_rows = [serialize(row) for row in execute_optional_select(trends_sql, params)]
    if not abc_rows:
        answer = "Nao encontrei produtos estrategicos para o periodo selecionado."
    else:
        leader = abc_rows[0]
        products = [
            f"{index + 1}. {row.get('produto')}: {format_brl(row.get('receita'))}, curva {row.get('curva_abc_faturamento')}"
            for index, row in enumerate(abc_rows)
        ]
        answer = (
            f"Produto lider por faturamento: {leader.get('produto')}, com {format_brl(leader.get('receita'))} "
            f"e curva {leader.get('curva_abc_faturamento')}. Produtos retornados para o usuario: " + " ".join(products) + "."
        )
        if trend_rows:
            growth = max(trend_rows, key=lambda row: float(row.get("variacao_receita") or 0))
            fall = min(trend_rows, key=lambda row: float(row.get("variacao_receita") or 0))
            answer += f" Maior crescimento: {growth.get('produto')} ({format_brl(growth.get('variacao_receita'))}). Maior queda: {fall.get('produto')} ({format_brl(fall.get('variacao_receita'))})."

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": [{"curva_abc": abc_rows, "tendencias": trend_rows}],
        "route": {"status": "consultative_matched", "intent": "produtos_estrategicos"},
        "params": serialize(params),
        "sql": abc_sql,
    }


def answer_seller_performance(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para analisar vendedores, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "performance_vendedores"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    margin_mode = is_seller_margin_question(question)
    low_margin_mode = margin_mode and is_low_margin_question(question)
    high_margin_mode = margin_mode and is_high_margin_question(question) and not low_margin_mode
    if low_margin_mode:
        order_by = "margem asc nulls last, lucro asc"
    elif high_margin_mode:
        order_by = "margem desc nulls last, lucro desc"
    elif margin_mode:
        order_by = "lucro desc, margem desc nulls last"
    else:
        order_by = "valor_vendido desc"
    margin_filter = "where valor_vendido >= %(min_valor_vendido)s" if margin_mode else ""
    if margin_mode:
        params["min_valor_vendido"] = 100
    sql = f"""
    select * from (
    select
      vendedor_id,
      vendedor,
      sum(valor_vendido) as valor_vendido,
      sum(qtd_vendas) as qtd_vendas,
      case when sum(qtd_vendas) = 0 then 0 else sum(valor_vendido) / sum(qtd_vendas) end as ticket_medio,
      case when sum(qtd_vendas) = 0 then 0 else sum(qtd_itens_vendidos) / sum(qtd_vendas) end as itens_por_venda,
      sum(qtd_skus) as qtd_skus,
      sum(lucro_bruto_estimado) as lucro,
      case when sum(valor_vendido) = 0 then null else sum(lucro_bruto_estimado) / sum(valor_vendido) end as margem,
      sum(desconto_manual) as desconto_manual,
      sum(desconto_automatico) as desconto_automatico,
      sum(valor_devolucao) as valor_devolucao
    from analytics.mv_ai_vendedor_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    group by vendedor_id, vendedor
    ) vendedores
    {margin_filter}
    order by {order_by}
    limit 50
    """
    rows = [serialize(row) for row in execute_optional_select(sql, params)]
    if not rows:
        answer = "Nao encontrei vendas por vendedor para o periodo selecionado."
    elif margin_mode:
        leader = rows[0]
        parts = [
            f"{index + 1}. {row.get('vendedor')}: margem {format_percent(float(row.get('margem') or 0) * 100)}, lucro {format_brl(row.get('lucro'))}, venda {format_brl(row.get('valor_vendido'))}"
            for index, row in enumerate(rows)
        ]
        if low_margin_mode:
            answer = (
                f"O vendedor com menor margem estimada foi {leader.get('vendedor')}, com margem {format_percent(float(leader.get('margem') or 0) * 100)} "
                f"e lucro estimado de {format_brl(leader.get('lucro'))} entre {params['data_inicio']} e {params['data_fim']}. "
                "Considerei vendedores com pelo menos R$ 100,00 vendidos para evitar distorcoes de cupons residuais. Ranking por margem estimada: " + " ".join(parts)
            )
        elif high_margin_mode:
            answer = (
                f"O vendedor com maior margem estimada foi {leader.get('vendedor')}, com margem {format_percent(float(leader.get('margem') or 0) * 100)} "
                f"e lucro estimado de {format_brl(leader.get('lucro'))} entre {params['data_inicio']} e {params['data_fim']}. "
                "Considerei vendedores com pelo menos R$ 100,00 vendidos para evitar distorcoes de cupons residuais. Ranking por margem estimada: " + " ".join(parts)
            )
        else:
            answer = (
                f"O vendedor com maior lucro estimado foi {leader.get('vendedor')}, com {format_brl(leader.get('lucro'))} "
                f"e margem {format_percent(float(leader.get('margem') or 0) * 100)} entre {params['data_inicio']} e {params['data_fim']}. "
                "Considerei vendedores com pelo menos R$ 100,00 vendidos para evitar distorcoes de cupons residuais. Ranking por lucro/margem estimados: " + " ".join(parts)
            )
    else:
        leader = rows[0]
        parts = [f"{index + 1}. {row.get('vendedor')}: {format_brl(row.get('valor_vendido'))}" for index, row in enumerate(rows)]
        answer = (
            f"O vendedor com maior valor vendido foi {leader.get('vendedor')}, com {format_brl(leader.get('valor_vendido'))} "
            f"entre {params['data_inicio']} e {params['data_fim']}. Vendedores retornados: " + " ".join(parts)
        )

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": "performance_vendedores"},
        "params": serialize(params),
        "sql": sql,
    }


def answer_hour_performance(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para analisar vendas por horario, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "vendas_por_horario"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      hora,
      max(faixa_horaria) as faixa_horaria,
      sum(faturamento_liquido) as faturamento,
      sum(qtd_cupons) as cupons,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
    from analytics.mv_ai_vendas_horario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    group by hora
    order by faturamento desc
    limit 24
    """
    rows = [serialize(row) for row in execute_optional_select(sql, params)]
    if not rows:
        answer = "Nao encontrei vendas por horario para o periodo selecionado."
    else:
        leader = rows[0]
        parts = [f"{int(row.get('hora') or 0):02d}h ({row.get('faixa_horaria')}): {format_brl(row.get('faturamento'))}" for row in rows]
        answer = (
            f"O melhor horario foi {int(leader.get('hora') or 0):02d}h, com {format_brl(leader.get('faturamento'))}. "
            "Horarios retornados: " + "; ".join(parts) + "."
        )

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": "vendas_por_horario"},
        "params": serialize(params),
        "sql": sql,
    }


def answer_alerts(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para listar alertas, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "alertas_operacionais"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      tipo_alerta,
      severidade,
      max(titulo) as titulo,
      max(descricao) as descricao,
      count(*) as ocorrencias,
      sum(valor_atual) as valor_total,
      max(data_ref) as ultima_data
    from analytics.mv_ai_alertas_operacionais
    where data_ref between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    group by tipo_alerta, severidade
    order by case severidade when 'alta' then 1 when 'media' then 2 else 3 end, ocorrencias desc
    limit 10
    """
    rows = [serialize(row) for row in execute_optional_select(sql, params)]
    if not rows:
        answer = "Nao encontrei alertas operacionais no periodo selecionado."
    else:
        parts = [f"{row.get('severidade')}: {row.get('titulo')} ({format_int(row.get('ocorrencias'))} ocorrencias)" for row in rows]
        answer = "Alertas retornados no periodo: " + "; ".join(parts) + "."

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": "alertas_operacionais"},
        "params": serialize(params),
        "sql": sql,
    }


def answer_total_revenue(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para calcular quanto vendeu, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "faturamento_total_periodo"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      coalesce(sum(faturamento_liquido), 0) as faturamento,
      coalesce(sum(qtd_cupons), 0) as cupons,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
    from analytics.mv_kpi_faturamento_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    """
    rows = [serialize(row) for row in execute_select(sql, params)]
    first = rows[0] if rows else {}
    answer = (
        f"No periodo de {params['data_inicio']} a {params['data_fim']}, "
        f"o faturamento foi {format_brl(first.get('faturamento'))}. "
        f"Foram {format_int(first.get('cupons'))} cupons, com ticket medio de {format_brl(first.get('ticket_medio'))}."
    )

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": "faturamento_total_periodo"},
        "params": serialize(params),
        "sql": sql,
    }


def answer_ticket(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para calcular ticket medio, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "ticket_medio"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      coalesce(sum(faturamento_liquido), 0) as faturamento,
      coalesce(sum(qtd_cupons), 0) as cupons,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
    from analytics.mv_kpi_faturamento_diario
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    """
    rows = [serialize(row) for row in execute_select(sql, params)]
    first = rows[0] if rows else {}
    answer = (
        f"No periodo de {params['data_inicio']} a {params['data_fim']}, "
        f"o ticket medio foi {format_brl(first.get('ticket_medio'))}. "
        f"Base: {format_int(first.get('cupons'))} cupons e {format_brl(first.get('faturamento'))} de faturamento."
    )
    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": "ticket_medio"},
        "params": serialize(params),
        "sql": sql,
    }


def answer_store_revenue(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para comparar lojas, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "faturamento_por_loja"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      loja_id,
      max(loja) as loja,
      sum(faturamento_liquido) as faturamento,
      sum(qtd_cupons) as cupons,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
    from analytics.mv_kpi_faturamento_loja
    where data between %(data_inicio)s and %(data_fim)s
    {loja_filter}
    group by loja_id
    order by faturamento desc
    """
    rows = [serialize(row) for row in execute_select(sql, params)]

    if not rows:
        answer = "Nao encontrei faturamento por loja para o periodo selecionado."
    else:
        leader = rows[0]
        worst = rows[-1]
        parts = [f"{index + 1}. {row.get('loja')}: {format_brl(row.get('faturamento'))}" for index, row in enumerate(rows)]
        if is_worst_store_question(question):
            answer = (
                f"A loja com menor faturamento foi {worst.get('loja')}, com {format_brl(worst.get('faturamento'))} "
                f"entre {params['data_inicio']} e {params['data_fim']}. Todas as lojas do usuario no periodo: " + " ".join(parts)
            )
        else:
            answer = (
                f"A loja que mais vendeu foi {leader.get('loja')}, com {format_brl(leader.get('faturamento'))} "
                f"entre {params['data_inicio']} e {params['data_fim']}. Todas as lojas do usuario no periodo: " + " ".join(parts)
            )

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {"status": "consultative_matched", "intent": "faturamento_por_loja"},
        "params": serialize(params),
        "sql": sql,
    }


def answer_daily_revenue_series(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para mostrar o faturamento por dia, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "faturamento_diario_periodo"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select *
    from (
      select
        data,
        sum(faturamento_liquido) as faturamento,
        sum(qtd_cupons) as cupons,
        case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
      from analytics.mv_kpi_faturamento_diario
      where data between %(data_inicio)s and %(data_fim)s
      {loja_filter}
      group by data
      order by data desc
      limit 366
    ) diario
    order by data
    """
    rows = [serialize(row) for row in execute_select(sql, params)]

    if not rows:
        answer = "Nao encontrei faturamento diario para o periodo selecionado."
    else:
        display_rows = rows if len(rows) <= 31 else rows[-31:]
        parts = [f"{row['data']}: {format_brl(row['faturamento'])}" for row in display_rows]
        answer = "Faturamento diario no periodo: " + "; ".join(parts) + "."
        if len(rows) > len(display_rows):
            answer += f" O periodo tem {len(rows)} dias retornados; listei os 31 dias mais recentes."

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {
            "status": "consultative_matched",
            "intent": "faturamento_diario_periodo",
            "template": {
                "template_key": "consult_faturamento_diario_periodo",
                "metric_key": "faturamento_diario",
                "question_pattern": "faturamento por dia/cada dia/diario",
                "required_slots": ["data_inicio", "data_fim"],
                "sql_template": sql,
                "answer_guidance": "Listar faturamento diario no periodo filtrado.",
            },
        },
        "params": serialize(params),
        "sql": sql,
    }


def answer_monthly_revenue_series(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para mostrar o faturamento por mes, selecione um periodo.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "faturamento_mensal_periodo"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    select
      mes,
      sum(faturamento_liquido) as faturamento,
      sum(qtd_cupons) as cupons,
      case when sum(qtd_cupons) = 0 then 0 else sum(faturamento_liquido) / sum(qtd_cupons) end as ticket_medio
    from analytics.mv_kpi_faturamento_mensal
    where mes between date_trunc('month', %(data_inicio)s::date)::date and date_trunc('month', %(data_fim)s::date)::date
    {loja_filter}
    group by mes
    order by mes
    limit 240
    """
    rows = [serialize(row) for row in execute_select(sql, params)]

    if not rows:
        answer = "Nao encontrei faturamento mensal para o periodo selecionado."
    else:
        display_rows = rows if len(rows) <= 36 else rows[-12:]
        parts = [f"{row['mes']}: {format_brl(row['faturamento'])}" for row in display_rows]
        answer = "Faturamento mensal no periodo: " + "; ".join(parts) + "."
        if len(rows) > len(display_rows):
            answer += f" O periodo tem {len(rows)} meses; listei os 12 meses mais recentes."

    return {
        "status": "answered",
        "question": question,
        "answer": answer,
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": {
            "status": "consultative_matched",
            "intent": "faturamento_mensal_periodo",
            "template": {
                "template_key": "consult_faturamento_mensal_periodo",
                "metric_key": "faturamento_mensal",
                "question_pattern": "faturamento por mes/cada mes/mensal",
                "required_slots": ["data_inicio", "data_fim"],
                "sql_template": sql,
                "answer_guidance": "Listar faturamento mensal no periodo filtrado.",
            },
        },
        "params": serialize(params),
        "sql": sql,
    }


def is_product_recommendation(question: str) -> bool:
    normalized = question.lower()
    intent_words = [
        "focar",
        "priorizar",
        "recomenda",
        "recomendacao",
        "recomendação",
        "oportunidade",
        "proximo mes",
        "próximo mês",
        "investir",
        "melhor produto",
    ]
    product_words = ["produto", "produtos", "item", "itens", "sku"]
    return any(word in normalized for word in intent_words) and any(word in normalized for word in product_words)


def product_recommendation_answer(rows: list[dict[str, Any]]) -> str:
    focus = [row for row in rows if row.get("tipo") == "focar"]
    risks = [row for row in rows if row.get("tipo") == "corrigir"]

    if not focus and not risks:
        return "Nao encontrei produtos suficientes para recomendar no periodo selecionado."

    parts: list[str] = []
    if focus:
        names = ", ".join(str(row["produto"]) for row in focus)
        parts.append(f"Eu focaria em: {names}.")
        parts.append("Criterio: lucro estimado positivo, receita relevante e venda no periodo analisado.")
    if risks:
        names = ", ".join(str(row["produto"]) for row in risks)
        parts.append(f"Tambem monitoraria/corrigiria: {names}, pois aparecem com prejuizo estimado.")
    parts.append("Usei o periodo selecionado como referencia historica. Lucro e margem ainda sao estimados ate homologacao final de custo.")
    return " ".join(parts)


def answer_product_recommendation(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    if not params.get("data_inicio") or not params.get("data_fim"):
        return {
            "status": "missing_slots",
            "question": question,
            "answer": "Para recomendar produtos, selecione um periodo ou informe mes/ano na pergunta.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": {"status": "consultative_matched", "intent": "recomendacao_produto"},
            "params": serialize(params),
        }

    loja_filter = cnpj_filter(cnpj, authorized_cnpjs)
    sql = f"""
    with produto as (
      select
        produto_id,
        max(produto) as produto,
        sum(qtd_vendida) as qtd_vendida,
        sum(receita_liquida_item) as receita,
        sum(custo_total_estimado) as custo,
        sum(lucro_bruto_estimado) as lucro,
        case
          when sum(receita_liquida_item) = 0 then null
          else sum(lucro_bruto_estimado) / sum(receita_liquida_item)
        end as margem
      from analytics.mv_kpi_lucro_produto
      where data between %(data_inicio)s and %(data_fim)s
      {loja_filter}
      group by produto_id
    ), foco as (
      select
        'focar' as tipo,
        produto_id,
        produto,
        qtd_vendida,
        receita,
        custo,
        lucro,
        margem,
        (lucro * 0.60 + receita * 0.30 + qtd_vendida * 0.10) as score
      from produto
      where receita > 0 and lucro > 0 and qtd_vendida > 0
      order by lucro desc, receita desc
      limit 5
    ), corrigir as (
      select
        'corrigir' as tipo,
        produto_id,
        produto,
        qtd_vendida,
        receita,
        custo,
        lucro,
        margem,
        lucro as score
      from produto
      where lucro < 0 and receita > 0
      order by lucro asc
      limit 5
    )
    select * from foco
    union all
    select * from corrigir
    order by tipo desc, score desc
    """

    rows = [serialize(row) for row in execute_select(sql, params)]
    route = {
        "status": "consultative_matched",
        "intent": "recomendacao_produto",
        "template": {
            "template_key": "consult_recomendacao_produto",
            "metric_key": "recomendacao_produto",
            "question_pattern": "qual produto focar/priorizar?",
            "required_slots": ["data_inicio", "data_fim"],
            "sql_template": sql,
            "answer_guidance": "Recomendar produtos com bom lucro/receita e alertar itens com prejuizo.",
        },
    }
    ai_answer = summarize_with_openai(question, {**route, "params": serialize(params), "sql": sql}, rows)

    return {
        "status": "answered",
        "question": question,
        "answer": ai_answer or product_recommendation_answer(rows),
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": route,
        "params": serialize(params),
        "sql": sql,
    }


def answer_question(
    question: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    history: list[dict[str, str]] | None = None,
    authorized_cnpjs: list[str] | None = None,
) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    context_start = params.get("data_inicio") or data_inicio
    context_end = params.get("data_fim") or data_fim
    conversation_topic = last_history_topic(question, history)

    if is_formula_question(question):
        return answer_formula(question, conversation_topic, context_start, context_end)

    if is_network_question(question):
        return answer_network_comparison(question, data_inicio, data_fim, cnpj, authorized_cnpjs, conversation_topic)

    operational_metric = resolve_operational_metric(question)
    if operational_metric:
        return answer_operational_kpi(question, data_inicio, data_fim, cnpj, authorized_cnpjs, operational_metric)

    if is_product_specific_question(question, history):
        return answer_product_specific_sales(question, data_inicio, data_fim, cnpj, history, authorized_cnpjs)

    if is_daily_revenue_series(question):
        return answer_daily_revenue_series(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_monthly_revenue_series(question):
        return answer_monthly_revenue_series(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_store_revenue_question(question):
        return answer_store_revenue(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_total_revenue_question(question):
        return answer_total_revenue(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_ticket_question(question):
        return answer_ticket(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_goal_question(question):
        return answer_goal_unavailable(question, context_start, context_end)

    if is_dre_question(question):
        return answer_margin_summary(question, data_inicio, data_fim, cnpj, authorized_cnpjs, "dre")

    if is_cmv_question(question):
        return answer_margin_summary(question, data_inicio, data_fim, cnpj, authorized_cnpjs, "cmv")

    if is_discount_return_question(question):
        return answer_discounts_returns(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_seller_question(question):
        return answer_seller_performance(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_hour_question(question):
        return answer_hour_performance(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_seasonality_question(question):
        return answer_seasonality(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_alert_question(question):
        return answer_alerts(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_customer_question(question):
        return answer_customers(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_product_loss_question(question):
        return answer_product_profitability(question, data_inicio, data_fim, cnpj, authorized_cnpjs, "loss")

    if is_product_profit_question(question):
        return answer_product_profitability(question, data_inicio, data_fim, cnpj, authorized_cnpjs, "profit")

    if is_product_list_question(question):
        return answer_product_profitability(question, data_inicio, data_fim, cnpj, authorized_cnpjs, "profit")

    if is_product_strategy_question(question):
        return answer_product_strategy(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_product_recommendation(question):
        return answer_product_recommendation(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_clear_out_of_scope_question(question):
        return answer_out_of_scope(question, context_start, context_end)

    if has_openai_key():
        kpi_context = build_kpi_context(context_start, context_end, cnpj, authorized_cnpjs)
        ai_answer = answer_with_kpis(question, history or [], kpi_context)
        if ai_answer:
            return {
                "status": "answered",
                "question": question,
                "answer": ai_answer,
                "openai_enabled": True,
                "rows": [],
                "route": {"status": "openai_kpi_context", "mode": "conversation"},
                "params": serialize({"data_inicio": context_start, "data_fim": context_end, "cnpj": cnpj, "cnpjs_autorizados": authorized_cnpjs}),
                "kpi_context": kpi_context,
            }

    route = find_question_route(question)
    if route.get("status") != "template_matched" or not route.get("template"):
        return {
            "status": "needs_ai",
            "question": question,
            "answer": "Nao encontrei um template confiavel para essa pergunta ainda.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": route,
        }

    template = route["template"]
    params = parse_period(question, data_inicio, data_fim)
    add_cnpj_params(params, cnpj, authorized_cnpjs)

    missing = [slot for slot in template.get("required_slots", []) if not params.get(slot)]
    if missing:
        return {
            "status": "missing_slots",
            "question": question,
            "answer": f"Preciso dos filtros: {', '.join(missing)}.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": route,
            "params": serialize(params),
        }

    sql = apply_cnpj_scope_to_sql(template_to_psycopg(template["sql_template"]), cnpj, authorized_cnpjs)
    if not is_safe_select(sql):
        return {
            "status": "unsafe_sql",
            "question": question,
            "answer": "SQL bloqueado pela validacao de seguranca.",
            "openai_enabled": has_openai_key(),
            "rows": [],
            "route": route,
            "sql": sql,
        }

    rows = [serialize(row) for row in execute_select(sql, params)]
    ai_answer = summarize_with_openai(question, {**route, "params": serialize(params), "sql": sql}, rows)

    return {
        "status": "answered",
        "question": question,
        "answer": ai_answer or local_answer(route, rows),
        "openai_enabled": has_openai_key(),
        "rows": rows,
        "route": route,
        "params": serialize(params),
        "sql": sql,
    }

from datetime import date
from decimal import Decimal
import re
from typing import Any

from app.db import execute_select
from app.services.openai_service import answer_with_kpis, has_openai_key, summarize_with_openai
from app.services.periods import parse_period
from app.services.semantic import find_question_route
from app.sql_guard import is_safe_select, template_to_psycopg


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


def build_kpi_context(data_inicio: date | None, data_fim: date | None, cnpj: str | None = None, authorized_cnpjs: list[str] | None = None) -> dict[str, Any]:
    if not data_inicio or not data_fim:
        return {"periodo": {"data_inicio": serialize(data_inicio), "data_fim": serialize(data_fim)}, "erro": "periodo ausente"}

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
    limit 10
    """
    profit_sql = f"""
    select produto_id, max(produto) as produto, sum(qtd_vendida) as qtd, sum(receita_liquida_item) as receita, sum(custo_total_estimado) as custo, sum(lucro_bruto_estimado) as lucro
    from analytics.mv_kpi_lucro_produto
    where data between %(data_inicio)s and %(data_fim)s {loja_filter}
    group by produto_id
    order by lucro desc
    limit 10
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
    limit 10
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

    return serialize({
        "periodo": {"data_inicio": data_inicio, "data_fim": data_fim, "cnpj": cnpj, "cnpjs_autorizados": authorized_cnpjs},
        "resumo": execute_select(summary_sql, params)[0],
        "executivo": (execute_optional_select(executive_sql, params) or [{}])[0],
        "faturamento_mensal": execute_select(monthly_sql, params),
        "top_lojas": execute_select(stores_sql, params),
        "produtos_mais_lucrativos": execute_select(profit_sql, params),
        "produtos_com_prejuizo": execute_select(loss_sql, params),
        "tendencia_diaria": execute_select(trend_sql, params),
        "ranking_vendedores": execute_optional_select(sellers_sql, params),
        "vendas_por_horario": execute_optional_select(hourly_sql, params),
        "alertas_operacionais": execute_optional_select(alerts_sql, params),
        "clientes": (execute_optional_select(customers_sql, params) or [{}])[0],
        "clientes_vip": execute_optional_select(vip_customers_sql, params),
        "produtos_estrategicos": execute_optional_select(strategic_products_sql, params),
        "tendencias_produtos": execute_optional_select(product_trends_sql, params),
        "descontos_devolucoes": (execute_optional_select(discounts_sql, params) or [{}])[0],
        "produtos_com_desconto_devolucao": execute_optional_select(discount_return_products_sql, params),
        "observacoes": [
            "faturamento = vlr_liquido - vlr_devolucao",
            "faturamento_mensal contem ate os ultimos 36 meses do periodo filtrado, em ordem cronologica",
            "lucro e margem sao estimados a partir dos custos disponiveis",
            "KPIs executivos AI-only ignoram vendas com data futura",
            "vendedor usa itens da venda e pode diferir do atendente do cabecalho",
            "clientes dependem de cliente_id preenchido na venda",
            "curva ABC de produtos e tendencias usam meses dentro do periodo selecionado",
            "descontos e devolucoes usam campos do cabecalho e dos itens de venda disponiveis no banco",
            "use o periodo selecionado como referencia quando a pergunta for vaga",
        ],
    })


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


def has_revenue_word(question: str) -> bool:
    normalized = question.lower()
    return any(word in normalized for word in ["faturamento", "faturou", "vendi", "vendeu", "vendas", "receita"])


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
    ranking_words = ["mais", "maior", "melhor", "top", "ranking", "por"]
    return any(word in normalized for word in store_words) and (has_revenue_word(normalized) or any(word in normalized for word in ranking_words))


def is_total_revenue_question(question: str) -> bool:
    normalized = question.lower()
    total_words = ["quanto", "total", "periodo", "período", "geral", "resumo"]
    return has_revenue_word(normalized) and any(word in normalized for word in total_words)


def is_seller_question(question: str) -> bool:
    normalized = question.lower()
    seller_words = ["vendedor", "vendedores", "colaborador", "colaboradores", "equipe", "operador", "operadores"]
    performance_words = ["vendeu", "vendas", "ranking", "ticket", "margem", "lucro", "desconto", "devolucao", "devolução", "performance", "desempenho", "sku"]
    return any(word in normalized for word in seller_words) and any(word in normalized for word in performance_words)


def is_hour_question(question: str) -> bool:
    normalized = question.lower()
    hour_words = ["horario", "horário", "hora", "horas", "faixa", "manha", "manhã", "tarde", "noite", "madrugada"]
    movement_words = ["vende", "vendeu", "vendas", "faturamento", "movimento", "cupons", "ticket", "reforcar", "reforçar"]
    return any(word in normalized for word in hour_words) and any(word in normalized for word in movement_words)


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
    limit 10
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


def is_product_strategy_question(question: str) -> bool:
    normalized = question.lower()
    product_words = ["produto", "produtos", "sku", "itens"]
    strategy_words = ["abc", "curva", "lider", "líder", "lideres", "líderes", "crescimento", "crescendo", "queda", "caindo", "sazonal", "sazonalidade", "estrategico", "estratégico"]
    return any(word in normalized for word in product_words) and any(word in normalized for word in strategy_words)


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
    ), inativos as (
      select count(distinct h.cliente_id) as clientes_inativos
      from analytics.mv_ai_cliente_diario h
      where h.data < %(data_inicio)s
      {loja_filter}
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
    limit 10
    """
    summary_rows = [serialize(row) for row in execute_optional_select(summary_sql, params)]
    vip_rows = [serialize(row) for row in execute_optional_select(vip_sql, params)]
    summary = summary_rows[0] if summary_rows else {}
    answer = (
        f"No periodo, encontrei {format_int(summary.get('clientes_ativos'))} cliente(s) ativo(s), "
        f"{format_int(summary.get('clientes_novos'))} novo(s), {format_int(summary.get('clientes_recorrentes'))} recorrente(s) "
        f"e {format_int(summary.get('clientes_inativos'))} inativo(s). "
        f"Ticket medio identificado: {format_brl(summary.get('ticket_medio_clientes'))}."
    )
    if vip_rows:
        top = vip_rows[0]
        answer += f" Cliente VIP por faturamento: {top.get('cliente')}, com {format_brl(top.get('faturamento'))}."

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
    limit 10
    """
    abc_rows = [serialize(row) for row in execute_optional_select(abc_sql, params)]
    trend_rows = [serialize(row) for row in execute_optional_select(trends_sql, params)]
    if not abc_rows:
        answer = "Nao encontrei produtos estrategicos para o periodo selecionado."
    else:
        leader = abc_rows[0]
        answer = f"Produto lider por faturamento: {leader.get('produto')}, com {format_brl(leader.get('receita'))} e curva {leader.get('curva_abc_faturamento')}."
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
    sql = f"""
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
    order by valor_vendido desc
    limit 10
    """
    rows = [serialize(row) for row in execute_optional_select(sql, params)]
    if not rows:
        answer = "Nao encontrei vendas por vendedor para o periodo selecionado."
    else:
        leader = rows[0]
        parts = [f"{index + 1}. {row.get('vendedor')}: {format_brl(row.get('valor_vendido'))}" for index, row in enumerate(rows[:5])]
        answer = (
            f"O vendedor com maior valor vendido foi {leader.get('vendedor')}, com {format_brl(leader.get('valor_vendido'))} "
            f"entre {params['data_inicio']} e {params['data_fim']}. Top 5: " + " ".join(parts)
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
    limit 10
    """
    rows = [serialize(row) for row in execute_optional_select(sql, params)]
    if not rows:
        answer = "Nao encontrei vendas por horario para o periodo selecionado."
    else:
        leader = rows[0]
        parts = [f"{int(row.get('hora') or 0):02d}h ({row.get('faixa_horaria')}): {format_brl(row.get('faturamento'))}" for row in rows[:5]]
        answer = (
            f"O melhor horario foi {int(leader.get('hora') or 0):02d}h, com {format_brl(leader.get('faturamento'))}. "
            "Top horarios: " + "; ".join(parts) + "."
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
        parts = [f"{row.get('severidade')}: {row.get('titulo')} ({format_int(row.get('ocorrencias'))} ocorrencias)" for row in rows[:5]]
        answer = "Principais alertas do periodo: " + "; ".join(parts) + "."

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
    limit 10
    """
    rows = [serialize(row) for row in execute_select(sql, params)]

    if not rows:
        answer = "Nao encontrei faturamento por loja para o periodo selecionado."
    else:
        leader = rows[0]
        parts = [f"{index + 1}. {row.get('loja')}: {format_brl(row.get('faturamento'))}" for index, row in enumerate(rows[:5])]
        answer = (
            f"A loja que mais vendeu foi {leader.get('loja')}, com {format_brl(leader.get('faturamento'))} "
            f"entre {params['data_inicio']} e {params['data_fim']}. Top 5: " + " ".join(parts)
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
        names = ", ".join(str(row["produto"]) for row in focus[:3])
        parts.append(f"Eu focaria em: {names}.")
        parts.append("Criterio: lucro estimado positivo, receita relevante e venda no periodo analisado.")
    if risks:
        names = ", ".join(str(row["produto"]) for row in risks[:3])
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

    if is_daily_revenue_series(question):
        return answer_daily_revenue_series(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_monthly_revenue_series(question):
        return answer_monthly_revenue_series(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_store_revenue_question(question):
        return answer_store_revenue(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_total_revenue_question(question):
        return answer_total_revenue(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_discount_return_question(question):
        return answer_discounts_returns(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_seller_question(question):
        return answer_seller_performance(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_hour_question(question):
        return answer_hour_performance(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_alert_question(question):
        return answer_alerts(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_customer_question(question):
        return answer_customers(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

    if is_product_strategy_question(question):
        return answer_product_strategy(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

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

    if is_product_recommendation(question):
        return answer_product_recommendation(question, data_inicio, data_fim, cnpj, authorized_cnpjs)

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

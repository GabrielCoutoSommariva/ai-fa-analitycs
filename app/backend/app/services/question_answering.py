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


def cnpj_filter(cnpj: str | None) -> str:
    if not normalize_cnpj(cnpj):
        return ""
    return "and loja_id in (select filtro_loja.loja_id from analytics.dim_loja filtro_loja where regexp_replace(coalesce(filtro_loja.cnpj, ''), '\\D', '', 'g') = %(cnpj)s)"


def build_kpi_context(data_inicio: date | None, data_fim: date | None, cnpj: str | None = None) -> dict[str, Any]:
    if not data_inicio or not data_fim:
        return {"periodo": {"data_inicio": serialize(data_inicio), "data_fim": serialize(data_fim)}, "erro": "periodo ausente"}

    params: dict[str, Any] = {"data_inicio": data_inicio, "data_fim": data_fim}
    loja_filter = cnpj_filter(cnpj)
    normalized_cnpj = normalize_cnpj(cnpj)
    if normalized_cnpj:
        params["cnpj"] = normalized_cnpj

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

    return serialize({
        "periodo": {"data_inicio": data_inicio, "data_fim": data_fim, "cnpj": cnpj},
        "resumo": execute_select(summary_sql, params)[0],
        "faturamento_mensal": execute_select(monthly_sql, params),
        "top_lojas": execute_select(stores_sql, params),
        "produtos_mais_lucrativos": execute_select(profit_sql, params),
        "produtos_com_prejuizo": execute_select(loss_sql, params),
        "tendencia_diaria": execute_select(trend_sql, params),
        "observacoes": [
            "faturamento = vlr_liquido - vlr_devolucao",
            "faturamento_mensal contem ate os ultimos 36 meses do periodo filtrado, em ordem cronologica",
            "lucro e margem sao estimados a partir dos custos disponiveis",
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


def answer_total_revenue(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    normalized_cnpj = normalize_cnpj(cnpj)
    if normalized_cnpj:
        params["cnpj"] = normalized_cnpj

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

    loja_filter = cnpj_filter(cnpj)
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


def answer_store_revenue(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    normalized_cnpj = normalize_cnpj(cnpj)
    if normalized_cnpj:
        params["cnpj"] = normalized_cnpj

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

    loja_filter = cnpj_filter(cnpj)
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


def answer_daily_revenue_series(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    normalized_cnpj = normalize_cnpj(cnpj)
    if normalized_cnpj:
        params["cnpj"] = normalized_cnpj

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

    loja_filter = cnpj_filter(cnpj)
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


def answer_monthly_revenue_series(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    normalized_cnpj = normalize_cnpj(cnpj)
    if normalized_cnpj:
        params["cnpj"] = normalized_cnpj

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

    loja_filter = cnpj_filter(cnpj)
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


def answer_product_recommendation(question: str, data_inicio: date | None, data_fim: date | None, cnpj: str | None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    normalized_cnpj = normalize_cnpj(cnpj)
    if normalized_cnpj:
        params["cnpj"] = normalized_cnpj

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

    loja_filter = cnpj_filter(cnpj)
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


def answer_question(question: str, data_inicio: date | None = None, data_fim: date | None = None, cnpj: str | None = None, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    params = parse_period(question, data_inicio, data_fim)
    context_start = params.get("data_inicio") or data_inicio
    context_end = params.get("data_fim") or data_fim

    if is_daily_revenue_series(question):
        return answer_daily_revenue_series(question, data_inicio, data_fim, cnpj)

    if is_monthly_revenue_series(question):
        return answer_monthly_revenue_series(question, data_inicio, data_fim, cnpj)

    if is_store_revenue_question(question):
        return answer_store_revenue(question, data_inicio, data_fim, cnpj)

    if is_total_revenue_question(question):
        return answer_total_revenue(question, data_inicio, data_fim, cnpj)

    if has_openai_key():
        kpi_context = build_kpi_context(context_start, context_end, cnpj)
        ai_answer = answer_with_kpis(question, history or [], kpi_context)
        if ai_answer:
            return {
                "status": "answered",
                "question": question,
                "answer": ai_answer,
                "openai_enabled": True,
                "rows": [],
                "route": {"status": "openai_kpi_context", "mode": "conversation"},
                "params": serialize({"data_inicio": context_start, "data_fim": context_end, "cnpj": cnpj}),
                "kpi_context": kpi_context,
            }

    if is_product_recommendation(question):
        return answer_product_recommendation(question, data_inicio, data_fim, cnpj)

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
    normalized_cnpj = normalize_cnpj(cnpj)
    if normalized_cnpj:
        params["cnpj"] = normalized_cnpj

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

    sql = template_to_psycopg(template["sql_template"])
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

from app.db import fetch_all, fetch_one
from app.sql_guard import is_safe_select


def get_context() -> list[dict]:
    return fetch_all(
        """
        select context_type, context_key, context_payload
        from analytics.ai_context_export
        order by context_type, context_key
        """
    )


def find_question_route(question: str) -> dict:
    normalized = question.lower().strip()
    templates = fetch_all(
        """
        select template_key, metric_key, question_pattern, required_slots, sql_template, answer_guidance
        from analytics.ai_query_templates
        order by template_key
        """
    )

    keyword_map = [
        ("margem_bruta", ["margem"]),
        ("produtos_prejuizo", ["preju", "abaixo do custo", "perda"]),
        ("lucro_produto", ["lucro", "lucrativo", "margem por produto"]),
        ("faturamento_loja", ["loja", "filial"]),
        ("ticket_medio", ["ticket"]),
        ("itens_vendidos", ["itens", "item"]),
        ("quantidade_cupons", ["cupom", "cupons"]),
        ("faturamento_mensal", ["mes", "mensal"]),
        ("faturamento_diario", ["vendi", "faturamento", "venda"]),
    ]

    metric_key = None
    for candidate, words in keyword_map:
        if any(word in normalized for word in words):
            metric_key = candidate
            break

    template = next((item for item in templates if item["metric_key"] == metric_key), None)
    if not template:
        return {
            "status": "needs_ai",
            "message": "Nao encontrei template direto. Enviar pergunta e contexto para a OpenAI.",
            "question": question,
        }

    return {
        "status": "template_matched",
        "question": question,
        "template": template,
        "safe_sql_template": is_safe_select(template["sql_template"]),
    }


def get_metric(metric_key: str) -> dict | None:
    return fetch_one(
        """
        select *
        from analytics.ai_metric_catalog
        where metric_key = %(metric_key)s
        """,
        {"metric_key": metric_key},
    )

import json
from typing import Any

from openai import OpenAI

from app.config import get_settings


def has_openai_key() -> bool:
    return bool(get_settings().openai_api_key)


def get_ai_client(settings: Any) -> OpenAI:
    kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**kwargs)


def summarize_with_openai(question: str, route: dict[str, Any], rows: list[dict[str, Any]]) -> str | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    try:
        client = get_ai_client(settings)
        payload = {
            "question": question,
            "route": route,
            "rows": rows[:50],
        }
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": "Voce e um analista de BI de farmacias. Responda em portugues, direto, com valor, periodo, fonte e ressalvas. Se lucro/margem for estimado, diga isso.",
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, default=str),
                },
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content
    except Exception:
        return None


def answer_with_kpis(question: str, history: list[dict[str, str]], kpi_context: dict[str, Any]) -> str | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    safe_history = [
        {"role": item.get("role", "user"), "content": item.get("content", "")[:2000]}
        for item in history[-12:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]

    system = """
Voce e um analista de BI para a Farmacias Associadas.
Use somente os KPIs e o historico enviados. Nao invente dados.
Continue a conversa considerando perguntas anteriores.
Se a pergunta atual for follow-up, preserve o assunto anterior.
Nao repita a mesma resposta anterior; complemente, compare ou aprofunde.
Se faltar dado no pacote de KPIs, diga objetivamente o que falta.
Se a pergunta pedir faturamento por mes, mensal, mes a mes ou cada mes, use o campo faturamento_mensal do pacote de KPIs.
Quando falar de lucro, margem ou produtos recomendados, informe que sao estimados ate homologacao final de custo.
Responda em portugues, de forma executiva e curta.
""".strip()

    user_payload = {
        "pergunta_atual": question,
        "kpis_disponiveis": kpi_context,
        "instrucao": "Responda a pergunta atual usando o contexto e mantenha continuidade conversacional.",
    }

    try:
        client = get_ai_client(settings)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                *safe_history,
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
            temperature=0.25,
        )
        return response.choices[0].message.content
    except Exception:
        return None

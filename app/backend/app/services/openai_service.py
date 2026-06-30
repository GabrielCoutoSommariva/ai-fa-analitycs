import json
from typing import Any
import urllib.request

from openai import OpenAI

from app.config import get_settings


def has_openai_key() -> bool:
    return bool(get_settings().openai_api_key)


def get_ai_client(settings: Any) -> OpenAI:
    kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**kwargs)


def _chat_completion_http(settings: Any, messages: list[dict[str, str]], temperature: float) -> str | None:
    base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base_url}/chat/completions"
    payload = json.dumps(
        {
            "model": settings.openai_model,
            "messages": messages,
            "temperature": temperature,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


def _chat_completion(settings: Any, messages: list[dict[str, str]], temperature: float) -> str | None:
    try:
        client = get_ai_client(settings)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=temperature,
            timeout=60,
        )
        return response.choices[0].message.content
    except Exception:
        return _chat_completion_http(settings, messages, temperature)


def summarize_with_openai(question: str, route: dict[str, Any], rows: list[dict[str, Any]]) -> str | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    try:
        payload = {
            "question": question,
            "route": route,
            "rows": rows[:50],
        }
        return _chat_completion(
            settings,
            [
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
Se a pergunta pedir vendedores/equipe, use ranking_vendedores.
Se a pergunta pedir horarios/faixas de movimento, use vendas_por_horario.
Se a pergunta pedir problemas, riscos ou prioridades, use alertas_operacionais e executivo.
Se a pergunta pedir clientes, recorrencia, VIP, inativos ou LTV, use clientes e clientes_vip.
Se a pergunta pedir curva ABC, produtos lideres, crescimento, queda ou sazonalidade, use produtos_estrategicos e tendencias_produtos.
Se a pergunta pedir descontos, desconto manual/sistema, devolucoes ou produtos devolvidos, use descontos_devolucoes e produtos_com_desconto_devolucao.
Quando falar de lucro, margem ou produtos recomendados, informe que sao estimados ate homologacao final de custo.
Responda em portugues, de forma executiva e curta.
""".strip()

    user_payload = {
        "pergunta_atual": question,
        "kpis_disponiveis": kpi_context,
        "instrucao": "Responda a pergunta atual usando o contexto e mantenha continuidade conversacional.",
    }

    try:
        return _chat_completion(
            settings,
            [
                {"role": "system", "content": system},
                *safe_history,
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
            temperature=0.25,
        )
    except Exception:
        return None

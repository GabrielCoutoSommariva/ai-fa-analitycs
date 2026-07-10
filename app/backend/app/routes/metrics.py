from datetime import date
from typing import Literal

from fastapi import APIRouter, Query, Request

from app.routes.dependencies import authorized_cnpj_scope, current_user
from app.services import metrics as service

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/catalog")
def catalog(request: Request) -> list[dict]:
    current_user(request)
    return service.get_catalog()


@router.get("/periodo-vendas")
def periodo_vendas(request: Request) -> dict:
    user = current_user(request)
    return service.periodo_vendas(user.allowed_cnpjs if user else None)


@router.get("/lojas-cnpj")
def lojas_cnpj(request: Request) -> list[dict]:
    user = current_user(request)
    return service.lojas_cnpj(user.allowed_cnpjs if user else None)


@router.get("/summary")
def summary(request: Request, data_inicio: date | None = None, data_fim: date | None = None, cnpj: str | None = None) -> dict:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.get_summary(data_inicio, data_fim, scoped_cnpj, scoped_cnpjs)


@router.get("/summary-matriz")
def summary_matriz(request: Request, data_inicio: date | None = None, data_fim: date | None = None) -> dict:
    current_user(request)
    return service.get_summary_matriz(data_inicio, data_fim)


@router.get("/operacional-summary")
def operacional_summary(request: Request, data_inicio: date | None = None, data_fim: date | None = None, cnpj: str | None = None) -> dict:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.operacional_summary(data_inicio, data_fim, scoped_cnpj, scoped_cnpjs)


@router.get("/operacional-summary-matriz")
def operacional_summary_matriz(request: Request, data_inicio: date | None = None, data_fim: date | None = None) -> dict:
    current_user(request)
    return service.operacional_summary_matriz(data_inicio, data_fim)


@router.get("/faturamento-diario")
def faturamento_diario(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.faturamento_diario(data_inicio, data_fim, scoped_cnpj, limit, scoped_cnpjs)


@router.get("/faturamento-tendencia")
def faturamento_tendencia(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    granularidade: Literal["auto", "dia", "mes", "ano"] = "auto",
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.faturamento_tendencia(data_inicio, data_fim, scoped_cnpj, granularidade, scoped_cnpjs)


@router.get("/faturamento-mensal")
def faturamento_mensal(
    request: Request,
    mes_inicio: date | None = None,
    mes_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.faturamento_mensal(mes_inicio, mes_fim, scoped_cnpj, limit, scoped_cnpjs)


@router.get("/faturamento-loja")
def faturamento_loja(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.faturamento_loja(data_inicio, data_fim, scoped_cnpj, limit, scoped_cnpjs)


@router.get("/cupons")
def cupons(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.cupons(data_inicio, data_fim, scoped_cnpj, limit, scoped_cnpjs)


@router.get("/itens-vendidos")
def itens_vendidos(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.itens_vendidos(data_inicio, data_fim, scoped_cnpj, limit, scoped_cnpjs)


@router.get("/lucro-produto")
def lucro_produto(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.lucro_produto(data_inicio, data_fim, scoped_cnpj, order, limit, scoped_cnpjs)


@router.get("/produtos-prejuizo")
def produtos_prejuizo(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.produtos_prejuizo(data_inicio, data_fim, scoped_cnpj, limit, scoped_cnpjs)


@router.get("/descontos-devolucoes")
def descontos_devolucoes(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.descontos_devolucoes(data_inicio, data_fim, scoped_cnpj, limit, scoped_cnpjs)


@router.get("/produtos-descontos-devolucoes")
def produtos_descontos_devolucoes(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    order: Literal["desconto", "devolucao"] = "devolucao",
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.produtos_descontos_devolucoes(data_inicio, data_fim, scoped_cnpj, order, limit, scoped_cnpjs)


@router.get("/sazonalidade-dia-semana")
def sazonalidade_dia_semana(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.sazonalidade_dia_semana(data_inicio, data_fim, scoped_cnpj, scoped_cnpjs)


@router.get("/vendas-horario")
def vendas_horario(
    request: Request,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(24, ge=1, le=24),
) -> list[dict]:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(cnpj, user)
    return service.vendas_horario(data_inicio, data_fim, scoped_cnpj, limit, scoped_cnpjs)

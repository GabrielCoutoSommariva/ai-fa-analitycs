from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from app.services import metrics as service

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/catalog")
def catalog() -> list[dict]:
    return service.get_catalog()


@router.get("/periodo-vendas")
def periodo_vendas() -> dict:
    return service.periodo_vendas()


@router.get("/lojas-cnpj")
def lojas_cnpj() -> list[dict]:
    return service.lojas_cnpj()


@router.get("/summary")
def summary(data_inicio: date | None = None, data_fim: date | None = None, cnpj: str | None = None) -> dict:
    return service.get_summary(data_inicio, data_fim, cnpj)


@router.get("/faturamento-diario")
def faturamento_diario(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return service.faturamento_diario(data_inicio, data_fim, cnpj, limit)


@router.get("/faturamento-mensal")
def faturamento_mensal(
    mes_inicio: date | None = None,
    mes_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return service.faturamento_mensal(mes_inicio, mes_fim, cnpj, limit)


@router.get("/faturamento-loja")
def faturamento_loja(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    return service.faturamento_loja(data_inicio, data_fim, cnpj, limit)


@router.get("/cupons")
def cupons(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return service.cupons(data_inicio, data_fim, cnpj, limit)


@router.get("/itens-vendidos")
def itens_vendidos(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    return service.itens_vendidos(data_inicio, data_fim, cnpj, limit)


@router.get("/lucro-produto")
def lucro_produto(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    return service.lucro_produto(data_inicio, data_fim, cnpj, order, limit)


@router.get("/produtos-prejuizo")
def produtos_prejuizo(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    cnpj: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    return service.produtos_prejuizo(data_inicio, data_fim, cnpj, limit)

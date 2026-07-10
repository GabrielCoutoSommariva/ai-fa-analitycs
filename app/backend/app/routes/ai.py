from pydantic import BaseModel, Field
from fastapi import APIRouter, Request
from datetime import date

from app.routes.dependencies import authorized_cnpj_scope, current_user
from app.services.question_answering import answer_question
from app.services.semantic import get_context, get_metric

router = APIRouter(prefix="/ai", tags=["ai"])


class QuestionRequest(BaseModel):
    question: str
    data_inicio: date | None = None
    data_fim: date | None = None
    cnpj: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)
    thread_id: str | None = None


@router.get("/context")
def context(request: Request) -> list[dict]:
    current_user(request)
    return get_context()


@router.get("/metric/{metric_key}")
def metric(metric_key: str, request: Request) -> dict | None:
    current_user(request)
    return get_metric(metric_key)


@router.post("/question")
def question(payload: QuestionRequest, request: Request) -> dict:
    user = current_user(request)
    scoped_cnpj, scoped_cnpjs = authorized_cnpj_scope(payload.cnpj, user)
    result = answer_question(payload.question, payload.data_inicio, payload.data_fim, scoped_cnpj, payload.history, scoped_cnpjs)
    result["thread_id"] = payload.thread_id
    return result

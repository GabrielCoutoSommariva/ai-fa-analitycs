from pydantic import BaseModel, Field
from fastapi import APIRouter
from datetime import date

from app.services.question_answering import answer_question
from app.services.semantic import get_context, get_metric

router = APIRouter(prefix="/ai", tags=["ai"])


class QuestionRequest(BaseModel):
    question: str
    data_inicio: date | None = None
    data_fim: date | None = None
    cnpj: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)


@router.get("/context")
def context() -> list[dict]:
    return get_context()


@router.get("/metric/{metric_key}")
def metric(metric_key: str) -> dict | None:
    return get_metric(metric_key)


@router.post("/question")
def question(payload: QuestionRequest) -> dict:
    return answer_question(payload.question, payload.data_inicio, payload.data_fim, payload.cnpj, payload.history)

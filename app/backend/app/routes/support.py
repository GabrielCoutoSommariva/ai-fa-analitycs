from email.message import EmailMessage
from datetime import UTC, datetime
import json
import re
import smtplib
from typing import Any
from urllib import error, request

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.routes.dependencies import current_user
from app.services.auth import SessionUser


router = APIRouter(prefix="/support", tags=["support"])


class ProblemReportRequest(BaseModel):
    title: str = Field(min_length=4, max_length=140)
    description: str = Field(min_length=12, max_length=4000)
    category: str = Field(default="problema", max_length=40)
    severity: str = Field(default="media", max_length=20)
    contact_email: str | None = Field(default=None, max_length=180)
    page_url: str | None = Field(default=None, max_length=800)
    filters: dict[str, Any] | None = None
    attachment_name: str | None = Field(default=None, max_length=180)
    attachment_type: str | None = Field(default=None, max_length=80)
    attachment_content: str | None = Field(default=None, max_length=3_000_000)


class ProblemReportResponse(BaseModel):
    status: str
    message: str


def is_valid_email(value: str | None) -> bool:
    if not value:
        return True
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", value))


def render_report_body(report: ProblemReportRequest, user: SessionUser | None, user_agent: str | None) -> str:
    user_lines = ["Usuario: anonimo/local"]
    if user:
        user_lines = [
            f"Usuario: {user.name or user.username or user.id}",
            f"Email do usuario: {user.email or 'nao informado'}",
            f"ID: {user.id}",
            f"CNPJs autorizados: {', '.join(user.allowed_cnpjs)}",
        ]

    filters = report.filters or {}
    filter_lines = [f"{key}: {value}" for key, value in filters.items() if value]

    return "\n".join([
        "Novo reporte de problema no BI Farmacias Associadas",
        "",
        f"Titulo: {report.title}",
        f"Categoria: {report.category}",
        f"Severidade: {report.severity}",
        f"Contato informado: {report.contact_email or 'nao informado'}",
        f"Pagina: {report.page_url or 'nao informada'}",
        f"Imagem anexada: {report.attachment_name or 'nao'}",
        f"User-Agent: {user_agent or 'nao informado'}",
        "",
        *user_lines,
        "",
        "Filtros:",
        *(filter_lines or ["nenhum filtro informado"]),
        "",
        "Descricao:",
        report.description,
    ])


def emailjs_template_params(report: ProblemReportRequest, user: SessionUser | None, user_agent: str | None) -> dict[str, str]:
    filters = report.filters or {}
    filters_text = ", ".join(f"{key}: {value}" for key, value in filters.items() if value) or "nenhum filtro informado"
    user_name = user.name or user.username or user.id if user else "anonimo/local"
    user_email = user.email if user and user.email else "nao informado"
    contact_email = report.contact_email or (user.email if user and user.email else "")
    cnpjs = ", ".join(user.allowed_cnpjs) if user else "nao informado"
    body = render_report_body(report, user, user_agent)

    params = {
        "title": report.title,
        "description": report.description,
        "category": report.category,
        "severity": report.severity,
        "contact_email": contact_email,
        "user_name": user_name,
        "user_email": user_email,
        "page_url": report.page_url or "nao informada",
        "filters": filters_text,
        "cnpjs": cnpjs,
        "user_agent": user_agent or "nao informado",
        "time": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "name": user_name,
        "email": contact_email,
        "message": body,
        "has_attachment": "sim" if report.attachment_content else "nao",
        "attachment_name": report.attachment_name or "",
        "attachment_type": report.attachment_type or "",
        "report_image": report.attachment_content or "",
    }
    return params


def validate_attachment(report: ProblemReportRequest) -> None:
    if not report.attachment_content:
        return
    if not report.attachment_name or not report.attachment_type:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dados do anexo incompletos.")
    if not report.attachment_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Apenas imagens podem ser anexadas.")
    if not report.attachment_content.startswith("data:image/"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Imagem anexada em formato invalido.")


def send_emailjs_report(report: ProblemReportRequest, user: SessionUser | None, user_agent: str | None) -> None:
    settings = get_settings()
    if not settings.emailjs_service_id or not settings.emailjs_template_id or not settings.emailjs_public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EmailJS ainda nao configurado.",
        )

    payload: dict[str, Any] = {
        "service_id": settings.emailjs_service_id,
        "template_id": settings.emailjs_template_id,
        "user_id": settings.emailjs_public_key,
        "template_params": emailjs_template_params(report, user, user_agent),
    }
    if settings.emailjs_private_key:
        payload["accessToken"] = settings.emailjs_private_key

    data = json.dumps(payload).encode("utf-8")
    emailjs_request = request.Request(
        "https://api.emailjs.com/api/v1.0/email/send",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://dash.farmaciasassociadas.com.br",
            "Referer": "https://dash.farmaciasassociadas.com.br/",
            "User-Agent": "Mozilla/5.0 farmacia-bi-backend",
        },
        method="POST",
    )

    try:
        with request.urlopen(emailjs_request, timeout=settings.emailjs_timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="EmailJS recusou o envio do reporte.")
    except error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300] or "EmailJS recusou o envio do reporte."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"EmailJS recusou o envio do reporte: {detail}") from exc
    except error.URLError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="EmailJS indisponivel.") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Timeout ao enviar reporte pelo EmailJS.") from exc


def send_problem_report(report: ProblemReportRequest, user: SessionUser | None, user_agent: str | None) -> None:
    settings = get_settings()
    provider = settings.support_email_provider.strip().lower()
    if provider == "emailjs":
        send_emailjs_report(report, user, user_agent)
        return

    if provider != "smtp":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Provedor de email de suporte invalido.")

    recipients = settings.support_report_recipients
    sender = settings.support_report_from or settings.smtp_username

    if not settings.smtp_host or not sender or not recipients:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Envio de reportes ainda nao configurado.",
        )

    message = EmailMessage()
    message["Subject"] = f"[BI Farmacias] {report.severity.upper()} - {report.title}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    if report.contact_email and is_valid_email(report.contact_email):
        message["Reply-To"] = report.contact_email
    elif user and user.email and is_valid_email(user.email):
        message["Reply-To"] = user.email
    message.set_content(render_report_body(report, user, user_agent))
    if report.attachment_content and report.attachment_name and report.attachment_type:
        try:
            import base64

            _, encoded = report.attachment_content.split(",", 1)
            maintype, subtype = report.attachment_type.split("/", 1)
            message.add_attachment(base64.b64decode(encoded), maintype=maintype, subtype=subtype, filename=report.attachment_name)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nao foi possivel processar a imagem anexada.") from exc

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
            return

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except smtplib.SMTPException as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Falha ao encaminhar o email de suporte.") from exc
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Servidor SMTP indisponivel.") from exc


@router.post("/problem-report", response_model=ProblemReportResponse)
def create_problem_report(report: ProblemReportRequest, request: Request, user: SessionUser | None = Depends(current_user)) -> ProblemReportResponse:
    if report.contact_email and not is_valid_email(report.contact_email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email de contato invalido.")
    validate_attachment(report)

    send_problem_report(report, user, request.headers.get("user-agent"))
    return ProblemReportResponse(status="sent", message="Reporte encaminhado para o suporte.")

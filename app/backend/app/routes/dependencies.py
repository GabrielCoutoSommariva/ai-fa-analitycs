from fastapi import HTTPException, Request, status

from app.config import get_settings
from app.services.auth import AuthError, SessionUser, normalize_cnpj, user_from_session_token


def current_user(request: Request) -> SessionUser | None:
    settings = get_settings()
    if not settings.external_auth_enabled:
        return None

    try:
        user = user_from_session_token(request.cookies.get(settings.session_cookie_name))
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao invalida ou expirada.") from exc

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessao obrigatoria.")
    return user


def authorized_cnpj_scope(cnpj: str | None, user: SessionUser | None) -> tuple[str | None, list[str] | None]:
    if user is None:
        return cnpj, None

    selected = normalize_cnpj(cnpj)
    if selected:
        if selected not in user.allowed_cnpjs:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CNPJ fora do escopo autorizado.")
        return selected, None

    return None, user.allowed_cnpjs

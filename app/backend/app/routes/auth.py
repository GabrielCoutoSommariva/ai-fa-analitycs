from fastapi import APIRouter, HTTPException, Request, Response, status

from app.config import get_settings
from app.services.auth import AuthError, create_session_token, public_auth_state, user_from_external_token, user_from_session_token


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/session")
def create_session(token: str, response: Response) -> dict:
    settings = get_settings()
    if not settings.external_auth_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Autenticacao externa nao configurada.")

    try:
        user = user_from_external_token(token)
        session_token = create_session_token(user)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return public_auth_state(user)


@router.get("/me")
def me(request: Request) -> dict:
    settings = get_settings()
    if not settings.external_auth_enabled:
        return public_auth_state()

    try:
        user = user_from_session_token(request.cookies.get(settings.session_cookie_name))
    except AuthError:
        user = None
    return public_auth_state(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return public_auth_state()

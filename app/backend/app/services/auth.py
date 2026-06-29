from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
import re
from typing import Any

from app.config import get_settings


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class SessionStore:
    nomeFantasia: str
    cnpj: str
    acode: str


@dataclass(frozen=True)
class SessionUser:
    id: str
    name: str
    email: str
    username: str
    type: str
    stores: list[SessionStore]
    allowed_cnpjs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "username": self.username,
            "type": self.type,
            "stores": [store.__dict__ for store in self.stores],
            "allowed_cnpjs": self.allowed_cnpjs,
        }


def normalize_cnpj(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _json_b64(value: dict[str, Any]) -> str:
    return _b64url_encode(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _sign(message: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def is_auth_enabled() -> bool:
    return get_settings().external_auth_enabled


def decode_hs256_jwt(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.external_auth_jwt_secret:
        raise AuthError("Autenticacao externa nao configurada.")

    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Token invalido.")

    header_raw, payload_raw, signature = parts
    message = f"{header_raw}.{payload_raw}"
    expected = _sign(message, settings.external_auth_jwt_secret)
    if not hmac.compare_digest(signature, expected):
        raise AuthError("Assinatura do token invalida.")

    try:
        header = json.loads(_b64url_decode(header_raw))
        payload = json.loads(_b64url_decode(payload_raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Token malformado.") from exc

    if header.get("alg") != "HS256":
        raise AuthError("Algoritmo do token nao suportado.")

    exp = payload.get("exp")
    if exp is not None and datetime.now(UTC).timestamp() > float(exp):
        raise AuthError("Token expirado.")

    return payload


def create_hs256_jwt(payload: dict[str, Any]) -> str:
    settings = get_settings()
    if not settings.external_auth_jwt_secret:
        raise AuthError("Autenticacao externa nao configurada.")

    header = {"alg": "HS256", "typ": "JWT"}
    header_raw = _json_b64(header)
    payload_raw = _json_b64(payload)
    signature = _sign(f"{header_raw}.{payload_raw}", settings.external_auth_jwt_secret)
    return f"{header_raw}.{payload_raw}.{signature}"


def user_from_payload(payload: dict[str, Any]) -> SessionUser:
    stores: list[SessionStore] = []
    allowed_cnpjs: list[str] = []
    seen_cnpjs: set[str] = set()

    for raw_store in payload.get("stores") or []:
        cnpj = normalize_cnpj(raw_store.get("cnpj"))
        if not cnpj:
            continue
        stores.append(
            SessionStore(
                nomeFantasia=str(raw_store.get("nomeFantasia") or raw_store.get("nome") or ""),
                cnpj=cnpj,
                acode=str(raw_store.get("acode") or "false"),
            )
        )
        if cnpj not in seen_cnpjs:
            seen_cnpjs.add(cnpj)
            allowed_cnpjs.append(cnpj)

    if not allowed_cnpjs:
        raise AuthError("Token sem lojas autorizadas.")

    return SessionUser(
        id=str(payload.get("id") or ""),
        name=str(payload.get("name") or ""),
        email=str(payload.get("email") or ""),
        username=str(payload.get("username") or ""),
        type=str(payload.get("type") or ""),
        stores=stores,
        allowed_cnpjs=allowed_cnpjs,
    )


def create_session_token(user: SessionUser) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.session_max_age_seconds)
    payload = {**user.to_dict(), "session": True, "exp": int(expires_at.timestamp())}
    return create_hs256_jwt(payload)


def user_from_external_token(token: str) -> SessionUser:
    return user_from_payload(decode_hs256_jwt(token))


def user_from_session_token(token: str | None) -> SessionUser | None:
    if not token:
        return None
    payload = decode_hs256_jwt(token)
    if payload.get("session") is not True:
        raise AuthError("Sessao invalida.")
    return user_from_payload(payload)


def public_auth_state(user: SessionUser | None = None) -> dict[str, Any]:
    settings = get_settings()
    return {
        "auth_enabled": settings.external_auth_enabled,
        "authenticated": user is not None,
        "login_url": settings.external_auth_login_url,
        "user": user.to_dict() if user else None,
    }

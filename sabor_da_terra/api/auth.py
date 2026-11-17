"""Autenticação demonstrativa stateless (token HMAC) e controle de acesso por perfil."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from typing import Literal, Optional

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("sabor_da_terra.auth")

_FALLBACK_SECRET: Optional[str] = None
_WARNED_SECRET = False
_TOKEN_PREFIX = "v1"
_DEFAULT_TTL_SECONDS = 86400


class IdentidadeSessao(BaseModel):
    """Identidade autenticada extraída exclusivamente do token assinado."""

    user_id: str
    perfil: Literal["operador", "produtor"]
    produtor_id: Optional[str] = None


def normalizar_perfil(perfil: Optional[str]) -> Literal["operador", "produtor"]:
    """Normaliza o perfil de acesso aceitando o alias legado 'cooperado' como 'operador'."""
    bruto = str(perfil or "").strip().lower()
    if bruto in {"operador", "cooperado"}:
        return "operador"
    if bruto == "produtor":
        return "produtor"
    raise HTTPException(
        status_code=422,
        detail="Perfil inválido. Utilize 'operador' ou 'produtor'.",
    )


def _obter_segredo_auth() -> bytes:
    global _FALLBACK_SECRET, _WARNED_SECRET
    env_secret = os.environ.get("SABOR_AUTH_SECRET", "").strip()
    if env_secret:
        return env_secret.encode("utf-8")

    if _FALLBACK_SECRET is None:
        _FALLBACK_SECRET = secrets.token_urlsafe(32)
    if not _WARNED_SECRET:
        _WARNED_SECRET = True
        logger.warning(
            "SABOR_AUTH_SECRET não definida; usando segredo temporário em memória "
            "(tokens existentes serão invalidados ao reiniciar o servidor)."
        )
    return _FALLBACK_SECRET.encode("utf-8")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    pad = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode((encoded + pad).encode("ascii"))


def _carregar_codigos_produtores() -> dict[str, str]:
    raw = os.environ.get("SABOR_CODIGOS_PRODUTORES_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {
                str(k).strip().upper(): str(v).strip()
                for k, v in parsed.items()
                if str(v).strip()
            }
    except json.JSONDecodeError:
        logger.warning("SABOR_CODIGOS_PRODUTORES_JSON inválido; ignorando mapa de códigos.")
    return {}


def requer_codigo_acesso() -> bool:
    """Indica se a instância exige código de acesso/PIN na entrada demonstrativa."""
    flag = os.environ.get("SABOR_EXIGIR_CODIGO_ACESSO", "").strip().lower()
    if flag in {"1", "true", "sim", "yes"}:
        return True
    return bool(
        os.environ.get("SABOR_CODIGO_OPERADOR", "").strip()
        or os.environ.get("SABOR_CODIGO_PRODUTOR", "").strip()
        or _carregar_codigos_produtores()
    )


def verificar_codigo_acesso(
    perfil: Literal["operador", "produtor"],
    produtor_id: Optional[str],
    codigo_acesso: Optional[str],
) -> None:
    """Valida código de acesso quando configurado via variáveis de ambiente."""
    if not requer_codigo_acesso():
        return

    informado = str(codigo_acesso or "").strip()
    esperado = ""
    if perfil == "operador":
        esperado = os.environ.get("SABOR_CODIGO_OPERADOR", "").strip()
    elif perfil == "produtor" and produtor_id:
        mapa = _carregar_codigos_produtores()
        esperado = mapa.get(produtor_id.upper(), "") or os.environ.get(
            "SABOR_CODIGO_PRODUTOR", ""
        ).strip()

    if not esperado:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Código de acesso habilitado, mas não configurado para o perfil '{perfil}'."
            ),
        )

    if not informado or not hmac.compare_digest(informado, esperado):
        raise HTTPException(
            status_code=401,
            detail="Código de acesso inválido para o perfil selecionado.",
        )


def emitir_token_sessao(
    identidade: IdentidadeSessao,
    *,
    ttl_segundos: Optional[int] = None,
) -> tuple[str, int]:
    """Emite token HMAC-SHA256 assinado contendo o perfil e o produtor autorizados."""
    ttl = ttl_segundos or int(os.environ.get("SABOR_TOKEN_TTL_SECONDS", _DEFAULT_TTL_SECONDS))
    ttl = max(60, ttl)
    agora = int(time.time())
    payload = {
        "sub": identidade.user_id,
        "perfil": identidade.perfil,
        "produtor_id": identidade.produtor_id,
        "iat": agora,
        "exp": agora + ttl,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_bytes)
    assinatura = hmac.new(
        _obter_segredo_auth(),
        f"{_TOKEN_PREFIX}.{payload_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    token = f"{_TOKEN_PREFIX}.{payload_b64}.{_b64url_encode(assinatura)}"
    return token, ttl


def validar_token_sessao(token: str) -> IdentidadeSessao:
    """Valida assinatura HMAC, validade temporal e estrutura do token de sessão."""
    partes = (token or "").strip().split(".")
    if len(partes) != 3 or partes[0] != _TOKEN_PREFIX:
        raise HTTPException(
            status_code=401,
            detail="Token de acesso inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _, payload_b64, sig_b64 = partes
    try:
        assinatura_esperada = hmac.new(
            _obter_segredo_auth(),
            f"{_TOKEN_PREFIX}.{payload_b64}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        assinatura_recebida = _b64url_decode(sig_b64)
        if not hmac.compare_digest(assinatura_recebida, assinatura_esperada):
            raise ValueError("Assinatura divergente.")
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Token de acesso inválido ou corrompido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    exp = int(payload.get("exp") or 0)
    if exp <= int(time.time()):
        raise HTTPException(
            status_code=401,
            detail="Sessão de acesso expirada. Selecione o perfil novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    perfil_raw = str(payload.get("perfil") or "").strip().lower()
    if perfil_raw not in {"operador", "produtor"}:
        raise HTTPException(
            status_code=401,
            detail="Token sem perfil autorizado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    produtor_id: Optional[str] = payload.get("produtor_id")
    if perfil_raw == "produtor":
        pid = str(produtor_id or "").strip().upper()
        if not re.match(r"^P\d{3}$", pid):
            raise HTTPException(
                status_code=401,
                detail="Token de produtor sem identificador válido.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        produtor_id = pid
        user_id = f"produtor_{pid}"
    else:
        produtor_id = None
        user_id = "operador"

    return IdentidadeSessao(
        user_id=user_id,
        perfil=perfil_raw,  # type: ignore[arg-type]
        produtor_id=produtor_id,
    )


def exigir_identidade(
    authorization: Optional[str] = Header(default=None),
) -> IdentidadeSessao:
    """Dependência FastAPI que exige Bearer Token válido."""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Autenticação de perfil obrigatória (cabeçalho Authorization: Bearer).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    esquema, _, token = authorization.strip().partition(" ")
    if esquema.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Cabeçalho Authorization inválido. Use 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return validar_token_sessao(token.strip())


def exigir_operador(
    identidade: IdentidadeSessao = Depends(exigir_identidade),
) -> IdentidadeSessao:
    """Dependência FastAPI que restringe a rota exclusivamente ao Operador da Cooperativa."""
    if identidade.perfil != "operador":
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao Operador da Cooperativa.",
        )
    return identidade

"""Criptografia simétrica (Fernet/AES) e hashing determinístico para proteção LGPD no banco."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("sabor_da_terra.database.crypto")

PREFIXO_CIFRADO = "enc:v1:"
_FALLBACK_KEY_SEED = "sabor-da-terra-dev-local-encryption-seed-2026"
_WARNED_FALLBACK = False


def _obter_semente_chave() -> str:
    global _WARNED_FALLBACK
    semente = (
        os.environ.get("SABOR_DB_ENCRYPTION_KEY", "").strip()
        or os.environ.get("SABOR_AUTH_SECRET", "").strip()
    )
    if semente:
        return semente

    if not _WARNED_FALLBACK:
        _WARNED_FALLBACK = True
        logger.warning(
            "SABOR_DB_ENCRYPTION_KEY e SABOR_AUTH_SECRET não definidas; "
            "usando chave derivada de desenvolvimento local para criptografia de colunas LGPD."
        )
    return _FALLBACK_KEY_SEED


def _derivar_chave_fernet(semente: Optional[str] = None) -> bytes:
    raw = (semente or _obter_semente_chave()).strip()
    if len(raw) == 44:
        try:
            decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
            if len(decoded) == 32:
                return raw.encode("ascii")
        except Exception:
            pass
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def obter_fernet(semente: Optional[str] = None) -> Fernet:
    """Retorna instância Fernet configurada com a chave do ambiente."""
    return Fernet(_derivar_chave_fernet(semente))


def esta_cifrado(valor: Optional[str]) -> bool:
    """Verifica se a string já possui o prefixo de criptografia em nível de coluna."""
    return bool(valor and str(valor).startswith(PREFIXO_CIFRADO))


def cifrar_valor_sensivel(
    valor: Optional[str],
    *,
    semente: Optional[str] = None,
) -> Optional[str]:
    """Cifra um dado sensível (CPF, PIX, conta corrente, nascimento) de forma idempotente."""
    if valor is None:
        return None
    limpo = str(valor).strip()
    if not limpo:
        return None
    if esta_cifrado(limpo):
        return limpo
    token = obter_fernet(semente).encrypt(limpo.encode("utf-8")).decode("ascii")
    return f"{PREFIXO_CIFRADO}{token}"


def decifrar_valor_sensivel(
    valor_cifrado: Optional[str],
    *,
    semente: Optional[str] = None,
) -> Optional[str]:
    """Decifra um valor sensível (uso restrito a rotinas administrativas/testes de auditoria)."""
    if valor_cifrado is None:
        return None
    bruto = str(valor_cifrado).strip()
    if not bruto:
        return None
    if not esta_cifrado(bruto):
        return bruto
    token = bruto[len(PREFIXO_CIFRADO) :]
    try:
        return obter_fernet(semente).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Não foi possível decifrar o valor com a chave atual.") from exc


def gerar_hash_deterministico(
    valor: Optional[str],
    *,
    semente: Optional[str] = None,
) -> Optional[str]:
    """Gera HMAC-SHA256 determinístico para indexação cega sem expor o texto original."""
    if valor is None:
        return None
    limpo = str(valor).strip()
    if not limpo:
        return None
    chave = (semente or _obter_semente_chave()).encode("utf-8")
    return hmac.new(chave, limpo.encode("utf-8"), hashlib.sha256).hexdigest()

"""Utilitários compartilhados de normalização e sanitização LGPD."""

from __future__ import annotations

import re
import unicodedata

CAMPOS_SENSIVEIS_LGPD = {
    "cpf",
    "produtor_cpf",
    "data_nascimento",
    "chave_pix",
    "chave_pix_deposito",
    "banco",
    "agencia",
    "conta_corrente",
}

CAMPOS_CONTATO_PESSOAL = {"telefone", "email", "endereco"}

_RE_CPF_FORMATADO = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_RE_CPF_ROTULADO = re.compile(r"(?i)\b(cpf(?:/cnpj)?\s*[:\-]?\s*)\d{11}\b")
_RE_RG_ROTULADO = re.compile(r"(?i)\b(rg\s*[:\-]?\s*)[\d.\-xX]{5,15}(?:\s+[A-Za-z/]{2,12})?")
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_TELEFONE = re.compile(
    r"(?:\+55\s*)?\(\d{2}\)\s*\d{4,5}-\d{4}(?:\s*ramal\s*\d+)?"
)
_RE_LINHA_PIX = re.compile(r"(?im)^(\s*chave\s*pix[^\n:]*:\s*).*$")
_RE_PIX_INLINE = re.compile(
    r"(?i)\b(chave\s*pix\s*[:\-]\s*)(?:\[[^\]]+\]|[^\s,;]+)"
)
_RE_LINHA_BANCO = re.compile(
    r"(?im)^(\s*)(?:banco\s+[^\n]*ag\.?[^\n]*|ag[êe]ncia\s*[:\-].*|c/c\s*[:\-].*)$"
)
_RE_AGENCIA_CC_INLINE = re.compile(
    r"(?i)\b(ag[êe]ncia|ag\.|c/c|conta\s+corrente)\s*[:\-]?\s*[\d.\-]+"
)
_RE_LINHA_ENDERECO = re.compile(r"(?im)^(\s*(?:endere[çc]o|cep)\s*:\s*).*$")


def norm_texto(txt: str) -> str:
    """Normaliza texto removendo acentos, espaços extras e convertendo para minúsculas."""
    s = unicodedata.normalize("NFKD", str(txt or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def sanitizar_pii_texto(
    texto: str,
    *,
    mascarar_contato: bool = True,
    mascarar_endereco: bool = False,
) -> str:
    """Mascara dados pessoais/sensíveis (CPF, RG, PIX, conta bancária, contatos)."""
    if not texto:
        return texto

    limpo = _RE_CPF_FORMATADO.sub("[CPF OMITIDO]", texto)
    limpo = _RE_CPF_ROTULADO.sub(r"\1[CPF OMITIDO]", limpo)
    limpo = _RE_RG_ROTULADO.sub(r"\1[RG OMITIDO]", limpo)
    limpo = _RE_LINHA_BANCO.sub(r"\1[DADOS BANCÁRIOS OMITIDOS]", limpo)
    limpo = _RE_AGENCIA_CC_INLINE.sub(r"\1 [OMITIDO]", limpo)

    if mascarar_contato:
        limpo = _RE_EMAIL.sub("[EMAIL OMITIDO]", limpo)
        limpo = _RE_TELEFONE.sub("[TELEFONE OMITIDO]", limpo)

    limpo = _RE_LINHA_PIX.sub(r"\1[PIX OMITIDO]", limpo)
    limpo = _RE_PIX_INLINE.sub(r"\1[PIX OMITIDO]", limpo)

    if mascarar_endereco:
        limpo = _RE_LINHA_ENDERECO.sub(r"\1[ENDEREÇO OMITIDO]", limpo)

    return limpo

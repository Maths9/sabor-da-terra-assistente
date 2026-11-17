"""Utilitários compartilhados de normalização, detecção e sanitização LGPD."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

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
CHAVES_BLOQUEADAS_LGPD = CAMPOS_SENSIVEIS_LGPD | CAMPOS_CONTATO_PESSOAL

_MARCADORES_OMITIDOS_RE = re.compile(
    r"\[(?:CPF|RG|EMAIL|TELEFONE|PIX|ENDEREÇO|DATA|DADOS BANCÁRIOS|OMITIDO)"
    r"(?:\s+OMITID[OA])?\]"
)

_RE_CPF_FORMATADO = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}[-\s]?\d{2}(?!\d)")
_RE_CPF_ROTULADO = re.compile(
    r"(?i)\b(cpf(?:/cnpj)?\s*[:\-]?\s*)(?:\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}|\d{11})\b"
)
_RE_CPF_SOLTO_11 = re.compile(r"(?<!\d)\d{11}(?!\d)")

_RE_RG_ROTULADO = re.compile(
    r"(?i)\b(rg\s*[:\-]?\s*)\d[\d.\-]{3,13}[\dxX]"
    r"(?:\s+(?:(?:SSP|SDS|SESP|DETRAN|PC|IFP|IGP|PM)[/\-\s]?[A-Za-z]{2}"
    r"|[A-Za-z]{2,5}[/\-][A-Za-z]{2}))?"
)
_RE_DATA_NASC = re.compile(
    r"(?i)\b((?:nascid[oa]\s+em|data\s+de\s+nascimento|nascimento)\s*[:\-]?\s*)"
    r"(?:\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})\b"
)

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_TELEFONE = re.compile(
    r"(?:\+55\s*)?\(\d{2}\)\s*\d{4,5}-\d{4}(?:\s*ramal\s*\d+)?"
)

_RE_PIX_COPIA_COLA = re.compile(r"\b000201\S{20,}")
_RE_UUID_EVP = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)
_RE_PIX_PROXIMA_LINHA = re.compile(
    r"(?im)^([ \t]*chave\s*pix[^\n:]*:[ \t]*\n[ \t]*(?:cnpj[ \t]*:[ \t]*)?)"
    r"(?![^\n]*\[PIX OMITIDO\])[^\n]+$"
)
_RE_PIX_INLINE = re.compile(
    r"(?i)\b(chave[ \t]+pix(?:[ \t]+(?:do|da|de)[ \t]+[A-Za-zÀ-ÿ0-9_\- ]{1,30})?[ \t]*"
    r"(?::|[ \t]+(?:é|eh)[ \t]+)[ \t]*)"
    r"(?:\[[^\]]+\]|(?:\+?55[ \t]*)?\(\d{2}\)[ \t]*\d{4,5}[-\s]?\d{4}|[^\s,;]+)"
)
_RE_PIX_CONTEXTO_PROXIMO = re.compile(
    r"(?i)(\bpix\b[^\n.!?,;\[\]]{0,25}?(?:\b(?:para|pra|em|é|eh|chave)\b)?[ \t]*[:\-]?[ \t]*)"
    r"("
    r"[0-9a-f]{32}"
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"|(?:\+?55[ \t]*)?\(?\d{2}\)?[ \t]?9?\d{4}[-\s]?\d{4}"
    r"|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"
    r"|\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}"
    r"|\d{11}"
    r")\b"
)

_RE_LINHA_BANCO = re.compile(
    r"(?im)^([ \t]*)(?:"
    r"banco\s+[^\n]*?\b(?:ag\.?|ag[êe]ncia|c/c|cc|conta)\b[^\n]*"
    r"|(?:ag[êe]ncia|c/c)\s*[:\-][^\n]*"
    r")$"
)
_RE_CONTA_INLINE = re.compile(
    r"(?i)\b("
    r"(?:ag[êe]ncia|ag\.?)\s*[:\-]?\s*\d{3,5}(?:[-\s]?\d)?\s*[,;/\-]?\s*"
    r"(?:c/c|cc|conta(?:\s+(?:corrente|poupan[çc]a))?)\s*[:\-]?\s*[\d.]+\d(?:-[\dxX])?"
    r"|(?:c/c|cc|conta\s+(?:corrente|poupan[çc]a))\s*[:\-]?\s*[\d.]+\d(?:-[\dxX])?"
    r")"
)
_RE_AGENCIA_ISOLADA = re.compile(
    r"(?i)\b(ag[êe]ncia|ag\.)\s*[:\-]?\s*\d{3,5}(?:-\d)?\b"
)
_RE_LINHA_ENDERECO = re.compile(r"(?im)^([ \t]*(?:endere[çc]o|cep)\s*:\s*).*$")


def norm_texto(txt: str) -> str:
    """Normaliza texto removendo acentos, espaços extras e convertendo para minúsculas."""
    s = unicodedata.normalize("NFKD", str(txt or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def cpf_digitos_validos(digitos: str) -> bool:
    """Valida dígitos verificadores de CPF para sequências numéricas sem formatação."""
    if len(digitos) != 11 or not digitos.isdigit() or digitos == digitos[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11 % 10
        if dv != int(digitos[tamanho]):
            return False
    return True


def _tem_cpf_solto_valido(texto: str) -> bool:
    return any(cpf_digitos_validos(m.group(0)) for m in _RE_CPF_SOLTO_11.finditer(texto))


def _mascarar_cpfs_soltos(texto: str) -> str:
    matches = [m for m in _RE_CPF_SOLTO_11.finditer(texto) if cpf_digitos_validos(m.group(0))]
    for m in reversed(matches):
        texto = texto[: m.start()] + "[CPF OMITIDO]" + texto[m.end() :]
    return texto


def detectar_dados_sensiveis(
    texto: str,
    *,
    incluir_agencia_isolada: bool = True,
) -> list[str]:
    """Retorna categorias de dados sensíveis LGPD presentes no texto."""
    if not texto:
        return []

    achados: list[str] = []

    if (
        _RE_CPF_FORMATADO.search(texto)
        or _RE_CPF_ROTULADO.search(texto)
        or _tem_cpf_solto_valido(texto)
    ):
        achados.append("cpf")

    if _RE_RG_ROTULADO.search(texto) or _RE_DATA_NASC.search(texto):
        achados.append("documento_pessoal")

    if (
        _RE_PIX_COPIA_COLA.search(texto)
        or _RE_UUID_EVP.search(texto)
        or _RE_PIX_PROXIMA_LINHA.search(texto)
        or any(
            not m.group(0).rstrip().endswith("]")
            for m in _RE_PIX_INLINE.finditer(texto)
        )
        or _RE_PIX_CONTEXTO_PROXIMO.search(texto)
    ):
        achados.append("pix")

    if (
        _RE_LINHA_BANCO.search(texto)
        or _RE_CONTA_INLINE.search(texto)
        or (incluir_agencia_isolada and _RE_AGENCIA_ISOLADA.search(texto))
    ):
        achados.append("conta_bancaria")

    return achados


def sanitizar_pii_texto(
    texto: str,
    *,
    mascarar_contato: bool = True,
    mascarar_endereco: bool = False,
    mascarar_agencia_isolada: bool = True,
) -> str:
    """Mascara dados pessoais/sensíveis (CPF, RG, nascimento, PIX, banco/conta, contatos)."""
    if not texto:
        return texto

    limpo = _RE_PIX_COPIA_COLA.sub("[PIX OMITIDO]", texto)
    limpo = _RE_UUID_EVP.sub("[PIX OMITIDO]", limpo)
    limpo = _RE_PIX_PROXIMA_LINHA.sub(r"\1[PIX OMITIDO]", limpo)
    limpo = _RE_PIX_INLINE.sub(
        lambda m: (
            m.group(0)
            if m.group(0).rstrip().endswith("]")
            else f"{m.group(1)}[PIX OMITIDO]"
        ),
        limpo,
    )
    limpo = _RE_PIX_CONTEXTO_PROXIMO.sub(r"\1[PIX OMITIDO]", limpo)

    limpo = _RE_CPF_ROTULADO.sub(r"\1[CPF OMITIDO]", limpo)
    limpo = _RE_CPF_FORMATADO.sub("[CPF OMITIDO]", limpo)
    limpo = _mascarar_cpfs_soltos(limpo)

    limpo = _RE_RG_ROTULADO.sub(r"\1[RG OMITIDO]", limpo)
    limpo = _RE_DATA_NASC.sub(r"\1[DATA OMITIDA]", limpo)

    limpo = _RE_LINHA_BANCO.sub(r"\1[DADOS BANCÁRIOS OMITIDOS]", limpo)
    limpo = _RE_CONTA_INLINE.sub("[DADOS BANCÁRIOS OMITIDOS]", limpo)
    if mascarar_agencia_isolada:
        limpo = _RE_AGENCIA_ISOLADA.sub(r"\1 [OMITIDO]", limpo)

    if mascarar_contato:
        limpo = _RE_EMAIL.sub("[EMAIL OMITIDO]", limpo)
        limpo = _RE_TELEFONE.sub("[TELEFONE OMITIDO]", limpo)

    if mascarar_endereco:
        limpo = _RE_LINHA_ENDERECO.sub(r"\1[ENDEREÇO OMITIDO]", limpo)

    return limpo


def sanitizar_estrutura(
    valor: Any,
    *,
    mascarar_contato: bool = False,
    mascarar_endereco: bool = False,
    mascarar_agencia_isolada: bool = True,
) -> Any:
    """Remove chaves LGPD e mascara strings recursivamente em estruturas aninhadas."""
    if isinstance(valor, str):
        return sanitizar_pii_texto(
            valor,
            mascarar_contato=mascarar_contato,
            mascarar_endereco=mascarar_endereco,
            mascarar_agencia_isolada=mascarar_agencia_isolada,
        )
    if isinstance(valor, list):
        return [
            sanitizar_estrutura(
                item,
                mascarar_contato=mascarar_contato,
                mascarar_endereco=mascarar_endereco,
                mascarar_agencia_isolada=mascarar_agencia_isolada,
            )
            for item in valor
        ]
    if isinstance(valor, dict):
        limpo: dict[str, Any] = {}
        for k, v in valor.items():
            if str(k).lower() in CHAVES_BLOQUEADAS_LGPD:
                continue
            limpo[k] = sanitizar_estrutura(
                v,
                mascarar_contato=mascarar_contato,
                mascarar_endereco=mascarar_endereco,
                mascarar_agencia_isolada=mascarar_agencia_isolada,
            )
        return limpo
    return valor


def texto_apenas_pii_ou_vazio(texto_mascarado: str) -> bool:
    """Indica se, após mascarar PII, não restou demanda operacional/comercial real."""
    sem_tags = _MARCADORES_OMITIDOS_RE.sub(" ", texto_mascarado)
    sem_labels = re.sub(
        r"(?i)\b(?:meu|minha|o|a|os|as|de|do|da|dos|das|e|é|eh|para|pra|com|em|no|na|"
        r"cpf|rg|pix|chave|chave\s+pix|banco|nubank|bradesco|ita[úu]|santander|caixa|"
        r"sicoob|brasil|nordeste|bb|ag[êe]ncia|ag|conta|corrente|poupan[çc]a|"
        r"c/c|cc|data|nascimento|segue|aqui|está|esta|cadastrad[oa]|dep[óo]sito|"
        r"favor|por\s+favor|numero|n[úu]mero)\b",
        " ",
        sem_tags,
    )
    palavras_restantes = re.findall(r"[A-Za-zÀ-ÿ0-9]{2,}", sem_labels)
    return len(palavras_restantes) < 3

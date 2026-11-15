"""Mascaramento de dados pessoais (LGPD) antes de indexar ou expor textos.

Mascara: CPF, CEP, e-mail, telefone, dados bancários, chave PIX, RG e data de nascimento.
Mantém: CNPJ (pessoa jurídica), nomes, municípios e registros profissionais (CRMV, CREA, CRN),
que são necessários para responder perguntas e citar fontes.
"""
from __future__ import annotations

import re
from collections import Counter

_PADROES: list[tuple[str, re.Pattern, str]] = [
    ("CPF", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"), "[CPF]"),
    ("CEP", re.compile(r"(CEP:\s*)\d{2}\.?\d{3}-\d{3}\b", re.I), r"\1[CEP]"),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    ("TELEFONE", re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}-\d{4}\b"), "[TELEFONE]"),
    (
        "BANCO",
        re.compile(r"Banco[^\n]*?-\s*Ag\.?\s*[\d.\-]+\s*-\s*C/C\s*[\d.\-]+", re.I),
        "[DADOS BANCÁRIOS]",
    ),
    ("PIX", re.compile(r"(Chave PIX[^\n:]*:)(?![ \t]*\n?[ \t]*\[)([ \t]*\n?[ \t]*)([^\n]+)", re.I), r"\1\2[PIX]"),
    ("RG", re.compile(r"\b(RG:\s*)[\w.\-]+", re.I), r"\1[RG]"),
    (
        "NASCIMENTO",
        re.compile(r"(Data de nascimento|Nascimento):\s*[\d/\-]+", re.I),
        r"\1: [DATA DE NASCIMENTO]",
    ),
]

# Padrões que NÃO podem sobrar em nenhum texto indexado.
_RESIDUAIS = {
    "CPF": _PADROES[0][1],
    "EMAIL": _PADROES[2][1],
    "TELEFONE": _PADROES[3][1],
    "BANCO": _PADROES[4][1],
}


def mascarar(texto: str) -> tuple[str, Counter]:
    """Devolve (texto mascarado, contagem de substituições por tipo)."""
    contagem: Counter = Counter()
    for nome, padrao, troca in _PADROES:
        texto, n = padrao.subn(troca, texto)
        if n:
            contagem[nome] += n
    return texto, contagem


def pii_residual(texto: str) -> list[str]:
    """Lista os tipos de dado pessoal que ainda aparecem no texto (deve ser vazia)."""
    return [nome for nome, padrao in _RESIDUAIS.items() if padrao.search(texto)]

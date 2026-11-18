"""Utilitários compartilhados das tools (envelope T10, leitura CSV segura, datas e sessão)."""

from __future__ import annotations

import csv
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sabor_da_terra.config import obter_data_referencia
from sabor_da_terra.database.repositories import repositorio
from sabor_da_terra.seguranca import CAMPOS_CONTATO_PESSOAL, CAMPOS_SENSIVEIS_LGPD

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    ToolContext = Any  # type: ignore

DATA_REFERENCIA_PADRAO = "2026-10-30"
MESES_COL = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}


class EntradaInvalida(ValueError):
    """Parâmetro informado à tool fora do formato esperado."""


def resposta(
    status: str,
    dados: Any = None,
    mensagem: Optional[str] = None,
) -> dict[str, Any]:
    """Padroniza retornos das ferramentas no envelope {status, dados, mensagem}."""
    return {"status": status, "dados": dados, "mensagem": mensagem}


def parse_data_iso(valor: Optional[str]) -> Optional[date]:
    """Converte string AAAA-MM-DD (ou timestamp ISO) para `date`."""
    if not valor:
        return None
    return date.fromisoformat(valor.strip()[:10])


def validar_data(data_referencia: str) -> date:
    """Valida `data_referencia` em AAAA-MM-DD lançando `EntradaInvalida` se inválida."""
    try:
        return date.fromisoformat(str(data_referencia).strip()[:10])
    except ValueError as exc:
        raise EntradaInvalida(
            f"data_referencia '{data_referencia}' inválida; use o formato AAAA-MM-DD."
        ) from exc


def resolver_data_ref(data_referencia: Optional[str]) -> date:
    """Resolve `data_referencia` explícita ou cai na data corrente do sistema."""
    if data_referencia:
        return parse_data_iso(data_referencia) or date.fromisoformat(obter_data_referencia())
    return date.fromisoformat(obter_data_referencia())


def fmt_decimal(valor: Decimal) -> str:
    """Formata valor monetário Decimal com duas casas decimais."""
    return f"{valor.quantize(Decimal('0.01'))}"


def ler_csv(
    caminho: Path,
    *,
    filtrar_lgpd: bool = True,
    remover_contato: bool = True,
) -> list[dict[str, str]]:
    """Consulta a tabela correspondente no banco (ou CSV no modo fallback) removendo colunas LGPD e contato."""
    return repositorio.ler_tabela_por_caminho(
        caminho,
        filtrar_lgpd=filtrar_lgpd,
        remover_contato=remover_contato,
    )


def ler_csv_bruto(caminho: Path) -> list[dict[str, str]]:
    """Leitura interna apenas para validações locais sem retorno direto ao LLM."""
    return repositorio.ler_tabela_por_caminho(
        caminho,
        filtrar_lgpd=False,
        remover_contato=False,
    )


def registrar_estado(
    tool_context: Optional[ToolContext],
    chave: str,
    valor: Any,
) -> None:
    """Grava uma chave em `tool_context.state` quando executado dentro de sessão ADK."""
    if tool_context is not None and hasattr(tool_context, "state"):
        tool_context.state[chave] = valor


def validar_produtor_id(produtor_id: str) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Normaliza e valida ID de produtor no formato P001; retorna erro padrão se inválido."""
    pid = (produtor_id or "").strip().upper()
    if not pid or not re.match(r"^P\d{3}$", pid):
        return None, resposta(
            "entrada_invalida",
            mensagem="Informe um produtor_id válido no formato P001 (ex.: P001, P003).",
        )
    return pid, None

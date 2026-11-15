"""Configuração central: caminhos, modelo de embeddings e data de referência."""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATA_RAW = RAIZ / "data" / "raw"
DATA_DOCS = RAIZ / "data" / "documentos"
DATA_CLEAN = RAIZ / "data" / "clean"
INDEX_DIR = Path(os.environ.get("SABOR_INDEX_DIR", RAIZ / "data" / "index"))

EMBED_MODELO = os.environ.get("SABOR_EMBED_MODELO", "gemini-embedding-001")
EMBED_DIM = int(os.environ.get("SABOR_EMBED_DIM", "768"))
COLECAO = "sabor_da_terra_docs"
# Relevância mínima (similaridade de cosseno, 0 a 1) para considerar um trecho como fonte.
# O valor 0.45 é um ponto de partida: calibrar com o evalset do Integrante 6.
LIMIAR_RELEVANCIA = float(os.environ.get("SABOR_LIMIAR", "0.60"))


def parse_data(texto: str) -> date:
    texto = texto.strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida: {texto!r} (use AAAA-MM-DD ou DD/MM/AAAA)")


def data_referencia(valor: str | None = None) -> date:
    """Data usada para calcular validade e atraso.

    Ordem: argumento > variável SABOR_DATA_REFERENCIA > data de hoje.
    """
    texto = valor or os.environ.get("SABOR_DATA_REFERENCIA")
    return parse_data(texto) if texto else date.today()

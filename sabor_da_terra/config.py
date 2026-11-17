"""Configurações centralizadas do Assistente Sabor da Terra."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DADOS_DIR = Path(os.getenv("SABOR_DADOS_DIR", str(PROJECT_ROOT / "dados"))).resolve()

_DEFAULT_INDEX_DIR = PROJECT_ROOT / "index"
_LEGACY_RAG_STORE_DIR = PACKAGE_DIR / "rag_store"
_RAG_DIR_PADRAO = (
    _DEFAULT_INDEX_DIR
    if (_DEFAULT_INDEX_DIR / "index_info.json").exists()
    else _LEGACY_RAG_STORE_DIR
)

RAG_STORE_DIR = Path(
    os.getenv("SABOR_INDEX_DIR")
    or os.getenv("SABOR_RAG_DIR")
    or str(_RAG_DIR_PADRAO)
).resolve()

# Carrega .env da raiz (quando executado localmente fora do Docker) sem sobrescrever variáveis já definidas.
load_dotenv(PROJECT_ROOT / ".env", override=False)

SABOR_MODEL = os.getenv("SABOR_MODEL", "gemini-3.5-flash")
SABOR_EMBEDDING_MODEL = os.getenv(
    "SABOR_EMBED_MODELO", os.getenv("SABOR_EMBEDDING_MODEL", "gemini-embedding-001")
)
SABOR_EMBEDDING_DIM = int(os.getenv("SABOR_EMBED_DIM", "768"))
RAG_MIN_RELEVANCE = float(os.getenv("SABOR_LIMIAR", "0.65"))
RAG_COLLECTION_NAME = "sabor_da_terra_docs"


def obter_data_referencia() -> str:
    """Retorna a data atual do sistema no formato ISO (AAAA-MM-DD)."""
    return date.today().isoformat()

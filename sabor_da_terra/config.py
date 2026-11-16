"""Configurações centralizadas do Assistente Sabor da Terra."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DADOS_DIR = Path(os.getenv("SABOR_DADOS_DIR", str(PROJECT_ROOT / "dados"))).resolve()
RAG_STORE_DIR = Path(
    os.getenv("SABOR_RAG_DIR", str(PACKAGE_DIR / "rag_store"))
).resolve()

# Carrega .env da raiz (quando executado localmente fora do Docker) sem sobrescrever variáveis já definidas.
load_dotenv(PROJECT_ROOT / ".env", override=False)

SABOR_MODEL = os.getenv("SABOR_MODEL", "gemini-3.5-flash")
SABOR_EMBEDDING_MODEL = os.getenv("SABOR_EMBEDDING_MODEL", "gemini-embedding-001")
RAG_COLLECTION_NAME = "sabor_da_terra_docs"


def obter_data_referencia() -> str:
    """Retorna a data atual do sistema no formato ISO (AAAA-MM-DD)."""
    return date.today().isoformat()

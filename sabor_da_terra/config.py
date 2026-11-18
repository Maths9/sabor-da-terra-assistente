"""Configurações centralizadas do Assistente Sabor da Terra."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

# Carrega .env da raiz e do pacote (quando executado localmente fora do Docker) sem sobrescrever variáveis já definidas.
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(PACKAGE_DIR / ".env", override=False)

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

SABOR_MODEL = os.getenv("SABOR_MODEL", "gemini-3.5-flash")
SABOR_EMBEDDING_MODEL = os.getenv(
    "SABOR_EMBED_MODELO", os.getenv("SABOR_EMBEDDING_MODEL", "gemini-embedding-001")
)
SABOR_EMBEDDING_DIM = int(os.getenv("SABOR_EMBED_DIM", "768"))
RAG_MIN_RELEVANCE = float(os.getenv("SABOR_LIMIAR", "0.65"))
RAG_COLLECTION_NAME = "sabor_da_terra_docs"

# Configurações de Banco de Dados Operacional (PostgreSQL / Cloud SQL)
SABOR_DATA_BACKEND = os.getenv("SABOR_DATA_BACKEND", "postgres").strip().lower()
DB_HOST = os.getenv("DB_HOST", "127.0.0.1").strip()
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "sabor_terra").strip()
DB_USER = os.getenv("DB_USER", "sabor_app").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
TABELA_PRECOS_VIGENCIA_PADRAO = os.getenv("SABOR_PRECOS_VIGENCIA", "2026-10").strip()


def obter_data_referencia() -> str:
    """Retorna a data atual do sistema no formato ISO (AAAA-MM-DD)."""
    return date.today().isoformat()


def obter_backend_dados() -> str:
    """Retorna o backend de dados ativo ('postgres' ou 'csv') lendo o ambiente atual."""
    raw = os.environ.get("SABOR_DATA_BACKEND", "").strip().lower()
    if raw in {"csv", "postgres"}:
        return raw
    return "postgres"

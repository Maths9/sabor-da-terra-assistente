"""Script CLI para gerar/atualizar o índice vetorial ChromaDB do RAG."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sabor_da_terra.config import DADOS_DIR, RAG_STORE_DIR
from sabor_da_terra.rag import indexar_corpus_rag


def main() -> None:
    manifest = indexar_corpus_rag(dados_dir=DADOS_DIR, store_dir=RAG_STORE_DIR)
    print(
        json.dumps(
            {
                "status": "ok",
                "rag_store_dir": str(RAG_STORE_DIR),
                "total_arquivos": manifest["total_arquivos"],
                "total_chunks": manifest["total_chunks"],
                "modelo_embedding": manifest["modelo_embedding"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

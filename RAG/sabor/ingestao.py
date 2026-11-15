"""Pipeline de ingestão do RAG: documentos -> deduplicar -> mascarar PII -> chunks -> embeddings -> índice.

Uso (na raiz do projeto):
    py -m sabor.ingestao --embedder gemini --backend chroma
    py -m sabor.ingestao --embedder offline --backend memory     # teste sem chave de API
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import config
from .armazenamento import MemoryStore, criar_store
from .chunking import criar_chunks
from .embeddings import criar_embedder
from .mascara import mascarar, pii_residual


def _hash(texto: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", texto).strip().encode("utf-8")).hexdigest()


def listar_documentos(pasta: Path) -> list[Path]:
    return sorted(Path(pasta).rglob("*.txt"))


def ingerir(
    docs_dir: Path = config.DATA_DOCS,
    index_dir: Path = config.INDEX_DIR,
    backend: str = "chroma",
    embedder=None,
    resetar: bool = True,
    verbose: bool = True,
) -> dict:
    docs_dir, index_dir = Path(docs_dir), Path(index_dir)
    embedder = embedder or criar_embedder()
    log = print if verbose else (lambda *a, **k: None)

    vistos: dict[str, str] = {}
    duplicados: list[dict] = []
    chunks = []
    mascaramento: Counter = Counter()
    arquivos = []

    for caminho in listar_documentos(docs_dir):
        rel = caminho.relative_to(docs_dir).as_posix()
        bruto = caminho.read_text(encoding="utf-8")
        h = _hash(bruto)
        if h in vistos:
            duplicados.append({"arquivo": rel, "igual_a": vistos[h]})
            log(f"  duplicado ignorado: {rel} (igual a {vistos[h]})")
            continue
        vistos[h] = rel
        texto, contagem = mascarar(bruto)
        sobra = pii_residual(texto)
        if sobra:
            raise RuntimeError(f"Dado pessoal restante em {rel}: {sobra}. Ajuste sabor/mascara.py.")
        mascaramento.update(contagem)
        novos = criar_chunks(rel, texto)
        chunks.extend(novos)
        arquivos.append({"arquivo": rel, "sha256": h, "chunks": len(novos)})
        log(f"  {rel}: {len(novos)} chunk(s)")

    if not chunks:
        raise RuntimeError(f"Nenhum documento .txt encontrado em {docs_dir}")

    log(f"Gerando embeddings de {len(chunks)} chunks com {embedder.nome} (dim {embedder.dim})...")
    vetores = embedder.embed_documentos([c.texto_indexado for c in chunks])

    loja = criar_store(backend, index_dir, resetar=resetar)
    loja.adicionar([c.id for c in chunks], [c.texto for c in chunks], vetores, [c.metadata for c in chunks])
    if isinstance(loja, MemoryStore):
        loja.salvar(index_dir)

    info = {
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "backend": backend,
        "colecao": config.COLECAO,
        "embedder": {"nome": embedder.nome, "dim": embedder.dim},
        "n_documentos": len(arquivos),
        "n_chunks": len(chunks),
        "duplicados_ignorados": duplicados,
        "mascaramento": dict(mascaramento),
        "arquivos": arquivos,
    }
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "index_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    log(
        f"Índice pronto em {index_dir}: {len(arquivos)} documentos, {len(chunks)} chunks, "
        f"{sum(mascaramento.values())} dados pessoais mascarados {dict(mascaramento)}."
    )
    return info


def main():
    ap = argparse.ArgumentParser(description="Gera o índice vetorial do RAG.")
    ap.add_argument("--docs", default=str(config.DATA_DOCS))
    ap.add_argument("--saida", default=str(config.INDEX_DIR))
    ap.add_argument("--backend", choices=["chroma", "memory"], default="chroma")
    ap.add_argument("--embedder", choices=["gemini", "offline"], default="gemini")
    ap.add_argument("--sem-resetar", action="store_true", help="não apagar a coleção existente")
    a = ap.parse_args()
    ingerir(a.docs, a.saida, a.backend, criar_embedder(a.embedder), resetar=not a.sem_resetar)


if __name__ == "__main__":
    main()

"""Armazenamento vetorial: ChromaDB (produção) e um índice em memória/arquivo (testes e plano B)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config


@dataclass
class Resultado:
    id: str
    texto: str
    metadata: dict
    relevancia: float  # similaridade de cosseno (1 = idêntico)


def _casa(meta: dict, filtros: dict | None) -> bool:
    for campo, cond in (filtros or {}).items():
        valor = meta.get(campo)
        if isinstance(cond, dict):
            for op, ref in cond.items():
                if op == "$gte" and not (valor is not None and valor >= ref):
                    return False
                if op == "$lte" and not (valor is not None and valor <= ref):
                    return False
                if op == "$eq" and valor != ref:
                    return False
        elif valor != cond:
            return False
    return True


class MemoryStore:
    """Índice em memória com persistência em disco (JSON + NumPy). Não depende do Chroma."""

    nome = "memory"
    _JSON, _NPY = "memory_index.json", "memory_vectors.npy"

    def __init__(self):
        self.ids: list[str] = []
        self.textos: list[str] = []
        self.metas: list[dict] = []
        self.vetores = np.zeros((0, 0), dtype=np.float32)

    def adicionar(self, ids, textos, vetores, metadatas):
        novos = np.asarray(vetores, dtype=np.float32)
        self.vetores = novos if self.vetores.size == 0 else np.vstack([self.vetores, novos])
        self.ids += list(ids)
        self.textos += list(textos)
        self.metas += list(metadatas)

    def contar(self) -> int:
        return len(self.ids)

    def consultar(self, vetor, k: int, filtros: dict | None = None) -> list[Resultado]:
        if not self.ids:
            return []
        q = np.asarray(vetor, dtype=np.float32)
        q = q / (np.linalg.norm(q) or 1.0)
        base = self.vetores / (np.linalg.norm(self.vetores, axis=1, keepdims=True) + 1e-12)
        sims = base @ q
        ordem = np.argsort(-sims)
        saida: list[Resultado] = []
        for i in ordem:
            if _casa(self.metas[i], filtros):
                saida.append(Resultado(self.ids[i], self.textos[i], self.metas[i], float(sims[i])))
            if len(saida) >= k:
                break
        return saida

    def salvar(self, pasta: Path) -> None:
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / self._JSON).write_text(
            json.dumps({"ids": self.ids, "textos": self.textos, "metas": self.metas}, ensure_ascii=False),
            encoding="utf-8",
        )
        np.save(pasta / self._NPY, self.vetores)

    @classmethod
    def carregar(cls, pasta: Path) -> "MemoryStore":
        pasta = Path(pasta)
        dados = json.loads((pasta / cls._JSON).read_text(encoding="utf-8"))
        loja = cls()
        loja.ids, loja.textos, loja.metas = dados["ids"], dados["textos"], dados["metas"]
        loja.vetores = np.load(pasta / cls._NPY)
        return loja


def _where_chroma(filtros: dict | None):
    if not filtros:
        return None
    itens = [{k: v} for k, v in filtros.items()]
    return itens[0] if len(itens) == 1 else {"$and": itens}


class ChromaStore:
    """ChromaDB em modo persistente (arquivos em disco, sem servidor)."""

    nome = "chroma"

    def __init__(self, pasta: Path, colecao: str = config.COLECAO, resetar: bool = False):
        try:
            import chromadb
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "ChromaDB não instalado. Rode: py -m pip install chromadb "
                "(se falhar, use --backend memory ou o Python 3.12/3.13)."
            ) from e
        Path(pasta).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(pasta))
        if resetar:
            try:
                self._client.delete_collection(colecao)
            except Exception:
                pass
        try:
            self._col = self._client.get_or_create_collection(name=colecao, configuration={"hnsw": {"space": "cosine"}})
        except (TypeError, ValueError):  # versões antigas do Chroma
            self._col = self._client.get_or_create_collection(name=colecao, metadata={"hnsw:space": "cosine"})

    def adicionar(self, ids, textos, vetores, metadatas):
        for i in range(0, len(ids), 100):
            self._col.add(
                ids=list(ids[i : i + 100]),
                documents=list(textos[i : i + 100]),
                embeddings=[list(map(float, v)) for v in vetores[i : i + 100]],
                metadatas=list(metadatas[i : i + 100]),
            )

    def contar(self) -> int:
        return self._col.count()

    def consultar(self, vetor, k: int, filtros: dict | None = None) -> list[Resultado]:
        total = self.contar()
        if total == 0:
            return []
        args = dict(
            query_embeddings=[list(map(float, vetor))],
            n_results=min(k, total),
            include=["documents", "metadatas", "distances"],
        )
        where = _where_chroma(filtros)
        if where:
            args["where"] = where
        r = self._col.query(**args)
        return [
            Resultado(i, d, m, 1.0 - float(dist))
            for i, d, m, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])
        ]


def criar_store(backend: str, pasta: Path, resetar: bool = False, carregar: bool = False):
    backend = backend.lower()
    if backend == "memory":
        return MemoryStore.carregar(pasta) if carregar else MemoryStore()
    if backend == "chroma":
        return ChromaStore(pasta, resetar=resetar)
    raise ValueError(f"Backend desconhecido: {backend!r} (use 'chroma' ou 'memory')")

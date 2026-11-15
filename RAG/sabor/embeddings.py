"""Geração de embeddings: Gemini (produção) e um embedder offline determinístico (testes/demo)."""
from __future__ import annotations

import hashlib
import math
import os
import re
import time
import unicodedata

from . import config

_STOPWORDS = set(
    "para com uma dos das que por como sao foi nos nas aos seu sua mais tem pelo pela este esta "
    "isso ser ter nao sim ate sobre entre quando onde qual quais".split()
)


def _normalizar(vetor: list[float]) -> list[float]:
    n = math.sqrt(sum(v * v for v in vetor)) or 1.0
    return [v / n for v in vetor]


class OfflineEmbedder:
    """Embedder lexical (hashing de palavras e bigramas). NÃO use em produção: serve para testes
    e para demonstrar o pipeline sem chave de API."""

    nome = "offline-hash"

    def __init__(self, dim: int = 512):
        self.dim = dim

    @staticmethod
    def _tokens(texto: str) -> list[str]:
        texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
        palavras = [p for p in re.findall(r"[a-z0-9]{3,}", texto) if p not in _STOPWORDS]
        return palavras + [f"{a}_{b}" for a, b in zip(palavras, palavras[1:])]

    def _vetor(self, texto: str) -> list[float]:
        contagem: dict[int, int] = {}
        for tok in self._tokens(texto):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
            contagem[h % self.dim] = contagem.get(h % self.dim, 0) + 1
        v = [0.0] * self.dim
        for i, c in contagem.items():
            v[i] = 1.0 + math.log(c)
        return _normalizar(v)

    def embed_documentos(self, textos: list[str]) -> list[list[float]]:
        return [self._vetor(t) for t in textos]

    def embed_consulta(self, texto: str) -> list[float]:
        return self._vetor(texto)


class GeminiEmbedder:
    """Embeddings via Gemini API (SDK google-genai). Lê a chave de GEMINI_API_KEY ou GOOGLE_API_KEY."""

    def __init__(self, modelo: str | None = None, dim: int | None = None, api_key: str | None = None):
        self.nome = modelo or config.EMBED_MODELO
        self.dim = dim or config.EMBED_DIM
        self._api_key = api_key
        self._client = None

    def _cliente(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError as e:  # pragma: no cover
                raise RuntimeError("Instale o SDK: py -m pip install google-genai") from e
            chave = self._api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
            if not chave and not vertex:
                raise RuntimeError(
                    "Chave do Gemini não encontrada. Defina GEMINI_API_KEY (PowerShell: "
                    "$env:GEMINI_API_KEY='sua-chave') ou use --embedder offline só para testes."
                )
            self._client = genai.Client(api_key=chave) if chave else genai.Client()
        return self._client

    def _embed(self, textos: list[str], tarefa: str) -> list[list[float]]:
        from google.genai import types

        saida: list[list[float]] = []
        for i in range(0, len(textos), 50):
            lote = textos[i : i + 50]
            for tentativa in range(4):
                try:
                    res = self._cliente().models.embed_content(
                        model=self.nome,
                        contents=lote,
                        config=types.EmbedContentConfig(task_type=tarefa, output_dimensionality=self.dim),
                    )
                    saida.extend(_normalizar(list(e.values)) for e in res.embeddings)
                    break
                except Exception:
                    if tentativa == 3:
                        raise
                    time.sleep(2**tentativa)
        return saida

    def embed_documentos(self, textos: list[str]) -> list[list[float]]:
        return self._embed(textos, "RETRIEVAL_DOCUMENT")

    def embed_consulta(self, texto: str) -> list[float]:
        return self._embed([texto], "RETRIEVAL_QUERY")[0]


def criar_embedder(nome: str | None = None, dim: int | None = None):
    nome = (nome or os.environ.get("SABOR_EMBEDDER") or "gemini").lower()
    if nome == "offline":
        return OfflineEmbedder(dim or 512)
    if nome == "gemini":
        return GeminiEmbedder(dim=dim)
    raise ValueError(f"Embedder desconhecido: {nome!r} (use 'gemini' ou 'offline')")

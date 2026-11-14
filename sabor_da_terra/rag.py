"""Pipeline de RAG vetorial (ChromaDB + gemini-embedding-001) e FunctionTool documental."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

import chromadb
from google import genai
from google.genai import types

from sabor_da_terra.config import (
    DADOS_DIR,
    RAG_COLLECTION_NAME,
    RAG_STORE_DIR,
    SABOR_EMBEDDING_MODEL,
)
from sabor_da_terra.seguranca import norm_texto, sanitizar_pii_texto

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    ToolContext = Any  # type: ignore

SUBPASTAS_RAG = ("certificacoes", "contratos", "fichas_tecnicas")
DISTANCIA_COSENO_MAX = 0.36

_TIPO_ALIASES = {
    "certificado": "certificacao",
    "certificacao": "certificacao",
    "certificacao_organica": "certificacao",
    "organico": "certificacao",
    "laudo": "laudo",
    "laudo_sanitario": "laudo",
    "inspecao": "inspecao",
    "adagro": "inspecao",
    "contrato": "contrato",
    "ficha": "ficha_tecnica",
    "ficha_tecnica": "ficha_tecnica",
}

_PRODUTOS_CHAVE = [
    "goiaba",
    "manga",
    "acerola",
    "banana",
    "maracuja",
    "caja",
    "umbu",
    "graviola",
    "morango",
    "amora",
    "mirtilo",
    "framboesa",
    "queijo coalho",
    "queijo manteiga",
    "ricota",
    "manteiga de garrafa",
    "nata",
    "iogurte",
    "leite",
    "mel silvestre",
    "mel de jandaira",
    "mel",
    "propolis",
    "polen",
    "cera de abelha",
    "alface",
    "coentro",
    "cebolinha",
    "rucula",
    "espinafre",
    "couve",
    "hortela",
    "manjericao",
    "tomate",
    "pimentao",
    "pepino",
    "berinjela",
    "quiabo",
    "macaxeira",
    "inhame",
    "batata doce",
    "farinha de mandioca",
    "tapioca",
    "goma",
    "rapadura",
    "frango caipira",
    "ovos caipira",
    "hortalicas",
    "geleia",
    "doce de goiaba",
]

_genai_client: Optional[genai.Client] = None
_chroma_clients: dict[str, Any] = {}


def _get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client()
    return _genai_client


def _get_chroma_collection(store_dir: Path, create: bool = False):
    key = str(store_dir.resolve())
    if key not in _chroma_clients or create:
        _chroma_clients[key] = chromadb.PersistentClient(path=str(store_dir))
    client = _chroma_clients[key]
    if create:
        try:
            client.delete_collection(name=RAG_COLLECTION_NAME)
        except Exception:
            pass
        return client.create_collection(
            name=RAG_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return client.get_collection(name=RAG_COLLECTION_NAME)


def _inferir_tipo_documento(rel_path: Path) -> str:
    pasta = rel_path.parts[0]
    nome = rel_path.name.lower()
    if pasta == "contratos":
        return "contrato"
    if pasta == "fichas_tecnicas":
        return "ficha_tecnica"
    if nome.startswith("laudo_sanitario"):
        return "laudo"
    if nome.startswith("inspecao_"):
        return "inspecao"
    return "certificacao"


def _extrair_produtor_id(rel_path: Path) -> str:
    m = re.search(r"_(P\d{3})\.txt$", rel_path.name, flags=re.IGNORECASE)
    return m.group(1).upper() if m else ""


def _extrair_validade_ate(texto: str) -> tuple[int, str]:
    m_val = re.search(r"(?i)data\s+de\s+validade\s*:\s*(\d{2})/(\d{2})/(\d{4})", texto)
    if m_val:
        d, m, y = m_val.groups()
        return int(f"{y}{m}{d}"), f"{y}-{m}-{d}"
    m_vig = re.search(
        r"(?i)vig[êe]ncia\s*:\s*\d{2}/\d{2}/\d{4}\s*a\s*(\d{2})/(\d{2})/(\d{4})",
        texto,
    )
    if m_vig:
        d, m, y = m_vig.groups()
        return int(f"{y}{m}{d}"), f"{y}-{m}-{d}"
    return 99991231, "nao_aplicavel"


def _extrair_produtos_texto(texto: str) -> str:
    txt_n = norm_texto(texto)
    encontrados = [
        p for p in _PRODUTOS_CHAVE if re.search(rf"\b{re.escape(p)}\b", txt_n)
    ]
    return "|" + "|".join(encontrados) + "|" if encontrados else ""


def _eh_cabecalho_secao(linha: str) -> bool:
    s = linha.strip()
    if not s or set(s) <= set("=-_ ") or s.startswith(("-", "*", "[")):
        return False
    if s[0].islower():
        return False
    prefixo_dois_pontos = s.split(":", 1)[0].strip().lower()
    if ":" in s[:-1] and prefixo_dois_pontos in {
        "cpf",
        "rg",
        "cnpj",
        "dap/caf",
        "crea-pe",
        "crmv-pe",
        "cep",
        "chave pix",
        "titular",
        "nome",
        "endereco",
        "endereço",
        "municipio",
        "município",
    }:
        return False
    if len(s) <= 85 and s.endswith(":"):
        return True
    if len(s) <= 75 and s == s.upper() and any(c.isalpha() for c in s):
        return True
    return False


def _dividir_em_secoes(texto_sanitizado: str) -> list[tuple[str, str]]:
    """Divide documento por seções lógicas preservando cabeçalhos e limites de tamanho."""
    linhas = [
        l.rstrip()
        for l in texto_sanitizado.splitlines()
        if not (l.strip() and set(l.strip()) <= set("=-_"))
    ]
    blocos: list[tuple[str, list[str]]] = []
    secao_atual = "Cabeçalho / Identificação"
    buffer: list[str] = []

    for linha in linhas:
        if _eh_cabecalho_secao(linha):
            conteudo = "\n".join(buffer).strip()
            if conteudo:
                blocos.append((secao_atual, buffer))
            secao_atual = linha.strip().rstrip(":")
            buffer = [linha.strip()]
        else:
            buffer.append(linha)

    if "\n".join(buffer).strip():
        blocos.append((secao_atual, buffer))

    # Mescla seções muito pequenas (< 260 chars) e quebra blocos grandes (> 1200 chars)
    chunks: list[tuple[str, str]] = []
    acum_titulo: Optional[str] = None
    acum_texto: list[str] = []

    for titulo, linhas_bloco in blocos:
        texto_bloco = "\n".join(linhas_bloco).strip()
        if not texto_bloco:
            continue
        if acum_titulo is None:
            acum_titulo = titulo
            acum_texto = [texto_bloco]
        elif len("\n\n".join(acum_texto)) < 260:
            acum_titulo = f"{acum_titulo} / {titulo}"
            acum_texto.append(texto_bloco)
        else:
            chunks.append((acum_titulo, "\n\n".join(acum_texto)))
            acum_titulo = titulo
            acum_texto = [texto_bloco]

    if acum_titulo is not None and acum_texto:
        chunks.append((acum_titulo, "\n\n".join(acum_texto)))

    chunks_finais: list[tuple[str, str]] = []
    for titulo, corpo in chunks:
        if len(corpo) <= 1250:
            chunks_finais.append((titulo, corpo))
            continue
        parte: list[str] = []
        tam = 0
        sub_idx = 1
        for linha in corpo.splitlines():
            if tam + len(linha) + 1 > 1100 and parte:
                chunks_finais.append((f"{titulo} (parte {sub_idx})", "\n".join(parte)))
                sub_idx += 1
                parte = [linha]
                tam = len(linha)
            else:
                parte.append(linha)
                tam += len(linha) + 1
        if parte:
            suf = f" (parte {sub_idx})" if sub_idx > 1 else ""
            chunks_finais.append((f"{titulo}{suf}", "\n".join(parte)))

    return chunks_finais


def preparar_chunks_corpus(dados_dir: Path = DADOS_DIR) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Lê os 20 .txt, aplica sanitização LGPD, extrai metadados e gera chunks estruturados."""
    chunks: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}

    for subpasta in SUBPASTAS_RAG:
        pasta = dados_dir / subpasta
        if not pasta.exists():
            continue
        for arq in sorted(pasta.glob("*.txt")):
            rel = arq.relative_to(dados_dir)
            bruto = arq.read_text(encoding="utf-8")
            hashes[rel.as_posix()] = hashlib.sha256(bruto.encode("utf-8")).hexdigest()

            tipo_doc = _inferir_tipo_documento(rel)
            produtor_id = _extrair_produtor_id(rel)
            validade_int, validade_iso = _extrair_validade_ate(bruto)
            texto_limpo = sanitizar_pii_texto(
                bruto,
                mascarar_contato=True,
                mascarar_endereco=(tipo_doc in {"certificacao", "laudo"}),
            )
            produtos_meta = _extrair_produtos_texto(texto_limpo)

            secoes = _dividir_em_secoes(texto_limpo)
            for idx, (secao_nome, corpo) in enumerate(secoes):
                cabecalho = (
                    f"[Documento: {arq.name} | Referência: {rel.as_posix()} | "
                    f"Tipo: {tipo_doc} | Produtor: {produtor_id or 'Cooperativa'} | "
                    f"Validade: {validade_iso} | Seção: {secao_nome}]"
                )
                chunks.append(
                    {
                        "id": f"{arq.stem}__chunk_{idx:02d}",
                        "texto": f"{cabecalho}\n{corpo}",
                        "metadata": {
                            "documento_id": arq.stem,
                            "nome": arq.name,
                            "referencia": rel.as_posix(),
                            "tipo_documento": tipo_doc,
                            "produtor_id": produtor_id,
                            "validade_ate": validade_int,
                            "validade_iso": validade_iso,
                            "produtos": produtos_meta,
                            "localizacao": f"Seção: {secao_nome}",
                        },
                    }
                )

    return chunks, hashes


def _gerar_embeddings(
    textos: list[str], *, task_type: str
) -> list[list[float]]:
    client = _get_genai_client()
    vetores: list[list[float]] = []
    # Lotes pequenos para respeitar limites de payload da API
    for i in range(0, len(textos), 20):
        lote = textos[i : i + 20]
        res = client.models.embed_content(
            model=SABOR_EMBEDDING_MODEL,
            contents=lote,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        vetores.extend(list(emb.values) for emb in res.embeddings)
    return vetores


def indexar_corpus_rag(
    dados_dir: Path = DADOS_DIR, store_dir: Path = RAG_STORE_DIR
) -> dict[str, Any]:
    """Constrói e persiste o índice ChromaDB completo a partir dos documentos textuais."""
    store_dir.mkdir(parents=True, exist_ok=True)
    chunks, hashes = preparar_chunks_corpus(dados_dir)
    if not chunks:
        raise RuntimeError(f"Nenhum documento .txt encontrado em {dados_dir}.")

    textos = [c["texto"] for c in chunks]
    embeddings = _gerar_embeddings(textos, task_type="RETRIEVAL_DOCUMENT")

    colecao = _get_chroma_collection(store_dir, create=True)
    colecao.add(
        ids=[c["id"] for c in chunks],
        documents=textos,
        metadatas=[c["metadata"] for c in chunks],
        embeddings=embeddings,
    )

    manifest = {
        "modelo_embedding": SABOR_EMBEDDING_MODEL,
        "total_arquivos": len(hashes),
        "total_chunks": len(chunks),
        "arquivos_sha256": hashes,
    }
    (store_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def _montar_filtro_chroma(
    tipo_documento: Optional[str],
    produtor_id: Optional[str],
    validade_min_int: Optional[int],
) -> Optional[dict[str, Any]]:
    clausulas: list[dict[str, Any]] = []
    if tipo_documento:
        clausulas.append({"tipo_documento": tipo_documento})
    if produtor_id:
        clausulas.append({"produtor_id": produtor_id})
    if validade_min_int is not None:
        clausulas.append({"validade_ate": {"$gte": validade_min_int}})
    if not clausulas:
        return None
    if len(clausulas) == 1:
        return clausulas[0]
    return {"$and": clausulas}


def consultar_documentos(
    pergunta: str,
    tipo_documento: Optional[str] = None,
    produtor_id: Optional[str] = None,
    apenas_vigentes_em: Optional[str] = None,
    top_k: int = 5,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Consulta certificações, laudos sanitários, inspeção ADAGRO, contratos e fichas técnicas no RAG vetorial, devolvendo texto e fontes."""
    q = (pergunta or "").strip()
    if not q:
        return {
            "status": "entrada_invalida",
            "dados": None,
            "mensagem": "Informe uma pergunta ou termo de busca documental.",
        }

    tipo_norm: Optional[str] = None
    if tipo_documento:
        chave = norm_texto(tipo_documento).replace(" ", "_")
        tipo_norm = _TIPO_ALIASES.get(chave)
        if not tipo_norm:
            return {
                "status": "entrada_invalida",
                "dados": None,
                "mensagem": "tipo_documento inválido. Use: certificacao, laudo, inspecao, contrato ou ficha_tecnica.",
            }

    pid_norm: Optional[str] = None
    if produtor_id:
        pid_norm = produtor_id.strip().upper()
        if not re.match(r"^P\d{3}$", pid_norm):
            return {
                "status": "entrada_invalida",
                "dados": None,
                "mensagem": "produtor_id inválido. Utilize o formato P001.",
            }

    val_int: Optional[int] = None
    if apenas_vigentes_em:
        try:
            dt = date.fromisoformat(apenas_vigentes_em.strip()[:10])
            val_int = int(dt.strftime("%Y%m%d"))
        except ValueError:
            return {
                "status": "entrada_invalida",
                "dados": None,
                "mensagem": "apenas_vigentes_em inválido. Utilize o formato AAAA-MM-DD.",
            }

    try:
        colecao = _get_chroma_collection(RAG_STORE_DIR, create=False)
        total = colecao.count()
    except Exception as exc:
        return {
            "status": "erro",
            "dados": None,
            "mensagem": f"Índice vetorial indisponível em {RAG_STORE_DIR}: {exc}",
        }

    if total == 0:
        return {
            "status": "erro",
            "dados": None,
            "mensagem": "Índice vetorial vazio. Execute scripts/indexar_rag.py.",
        }

    try:
        q_emb = _gerar_embeddings([q], task_type="RETRIEVAL_QUERY")[0]
    except Exception as exc:
        return {
            "status": "erro",
            "dados": None,
            "mensagem": f"Falha ao gerar embedding da consulta: {exc}",
        }

    where = _montar_filtro_chroma(tipo_norm, pid_norm, val_int)
    n_res = min(max(top_k * 3, 12), total)
    res = colecao.query(
        query_embeddings=[q_emb],
        n_results=n_res,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    selecionados: list[tuple[str, dict[str, Any], float]] = []
    for doc, meta, dist in zip(docs, metas, dists):
        if dist <= DISTANCIA_COSENO_MAX:
            selecionados.append((doc, meta, dist))

    # Se a pergunta citar um código específico (ex. 2024-089) inexistente nos trechos, não forçar falso positivo
    codigos_pergunta = re.findall(r"\b(?:lot-)?\d{4}-\d{3,4}\b", q.lower())
    if codigos_pergunta and selecionados:
        texto_unido_n = norm_texto(" ".join(d for d, _, _ in selecionados))
        if not any(cod in texto_unido_n for cod in codigos_pergunta):
            selecionados = []

    if not selecionados:
        return {
            "status": "nao_encontrado",
            "dados": None,
            "mensagem": (
                "Não foi encontrada evidência suficiente nos documentos indexados da cooperativa "
                "(certificações, laudos, inspeção ADAGRO, contratos e fichas técnicas) para responder a essa consulta."
            ),
        }

    selecionados = selecionados[: max(1, min(top_k, 8))]
    trechos_formatados = [doc for doc, _, _ in selecionados]
    fontes: list[dict[str, Any]] = []
    vistos: set[tuple[str, str]] = set()
    for _, meta, _ in selecionados:
        chave_fonte = (meta["documento_id"], meta.get("localizacao") or "")
        if chave_fonte in vistos:
            continue
        vistos.add(chave_fonte)
        fontes.append(
            {
                "documento_id": meta["documento_id"],
                "nome": meta["nome"],
                "localizacao": meta.get("localizacao"),
                "referencia": meta["referencia"],
            }
        )

    if tool_context is not None and hasattr(tool_context, "state"):
        tool_context.state["ultimas_fontes_rag"] = fontes

    return {
        "status": "ok",
        "dados": {
            "texto": "\n\n---\n\n".join(trechos_formatados),
            "fontes": fontes,
        },
        "mensagem": None,
    }


LISTA_TOOLS_RAG = [consultar_documentos]

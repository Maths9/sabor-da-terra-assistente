"""Ferramenta de busca documental do agente: buscar_documentos(...).

A função é escrita para ser usada como FunctionTool do ADK: parâmetros simples (str/int), docstring
em português (vira a descrição da ferramenta para o modelo) e retorno em dict com o campo "status".
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import config
from .armazenamento import criar_store
from .embeddings import criar_embedder

_estado: dict = {"store": None, "embedder": None, "info": None, "limiar": None}


def configurar(index_dir=None, store=None, embedder=None, limiar: float | None = None) -> None:
    """Configura a busca. Sem argumentos, carrega o índice de SABOR_INDEX_DIR (padrão data/index)."""
    index_dir = Path(index_dir or config.INDEX_DIR)
    info = None
    info_arq = index_dir / "index_info.json"
    if info_arq.exists():
        info = json.loads(info_arq.read_text(encoding="utf-8"))
    if store is None:
        if info is None:
            raise RuntimeError(f"Índice não encontrado em {index_dir}. Rode: py -m sabor.ingestao")
        store = criar_store(info["backend"], index_dir, carregar=True)
    if embedder is None:
        nome = "offline" if info and info["embedder"]["nome"] == "offline-hash" else "gemini"
        embedder = criar_embedder(nome, info["embedder"]["dim"] if info else None)
    if info and (embedder.nome != info["embedder"]["nome"] or embedder.dim != info["embedder"]["dim"]):
        raise RuntimeError(
            f"Embedder incompatível com o índice: índice={info['embedder']}, atual={embedder.nome}/{embedder.dim}. "
            "Use o mesmo modelo e dimensão da ingestão."
        )
    _estado.update(store=store, embedder=embedder, info=info, limiar=limiar)


def _garantir() -> None:
    if _estado["store"] is None:
        configurar()


def situacao_validade(validade_ate: int, referencia: date) -> str:
    """'sem_validade_definida', 'vigente' ou 'vencido' para uma validade AAAAMMDD."""
    if not validade_ate:
        return "sem_validade_definida"
    ano, mes, dia = validade_ate // 10000, validade_ate // 100 % 100, validade_ate % 100
    return "vigente" if date(ano, mes, dia) >= referencia else "vencido"


def _iso(validade_ate: int) -> str:
    return f"{validade_ate // 10000:04d}-{validade_ate // 100 % 100:02d}-{validade_ate % 100:02d}" if validade_ate else ""


def buscar_documentos(consulta: str, tipo: str = "", produtor_id: str = "", valido_em: str = "", k: int = 5) -> dict:
    """Busca trechos nos documentos da cooperativa (certificados orgânicos, laudos sanitários,
    inspeção ADAGRO, contratos e fichas técnicas) e devolve as fontes exatas.

    Use para perguntas sobre selo orgânico, validade de certificação, registro sanitário (SIE),
    cláusulas de contrato, ficha técnica e capacidade de produção. Para perguntas sobre um lote
    específico, use consultar_lote. Responda SOMENTE com o que estiver nos trechos devolvidos e
    cite o campo "fonte". Se o status for "nao_encontrado", diga que não há fonte e não invente.

    Args:
        consulta: pergunta ou termos de busca em português.
        tipo: filtro opcional: "certificacao_organica", "laudo_sanitario", "inspecao", "contrato"
            ou "ficha_tecnica". Deixe vazio para buscar em todos.
        produtor_id: filtro opcional, por exemplo "P008". Deixe vazio para todos.
        valido_em: filtro opcional (AAAA-MM-DD): descarta documentos com validade anterior a essa data.
        k: quantidade de trechos (1 a 10).

    Returns:
        dict com "status" ("ok", "nao_encontrado" ou "erro"), "data_referencia" e "resultados"
        (cada um com fonte, secao, tipo, produtor_id, situacao_validade, validade_ate, trecho, relevancia).
    """
    if not consulta or not consulta.strip():
        return {"status": "erro", "mensagem": "Informe o que deseja buscar."}
    try:
        _garantir()
        referencia = config.data_referencia()
        k = max(1, min(int(k), 10))
        limiar = _estado["limiar"] if _estado["limiar"] is not None else config.LIMIAR_RELEVANCIA
        corte = config.parse_data(valido_em) if valido_em else None
        corte_int = int(corte.strftime("%Y%m%d")) if corte else None

        vetor = _estado["embedder"].embed_consulta(consulta)
        filtros = {"tipo": tipo} if tipo else None
        brutos = _estado["store"].consultar(vetor, min(max(k * 4, 12), 50), filtros)
    except Exception as e:  # o agente recebe o erro como dado, sem derrubar a conversa
        return {"status": "erro", "mensagem": f"Falha na busca documental: {e}"}

    alvo = f"|{produtor_id.strip().upper()}|" if produtor_id else None
    resultados = []
    for r in brutos:
        m = r.metadata
        if r.relevancia < limiar:
            continue
        if alvo and alvo not in m.get("produtores", ""):
            continue
        if corte_int and m.get("validade_ate") and m["validade_ate"] < corte_int:
            continue
        resultados.append(
            {
                "fonte": m["arquivo"],
                "secao": m["secao"],
                "tipo": m["tipo"],
                "produtor_id": m.get("produtor_id", ""),
                "situacao_validade": situacao_validade(m.get("validade_ate", 0), referencia),
                "validade_ate": _iso(m.get("validade_ate", 0)),
                "trecho": r.texto,
                "relevancia": round(r.relevancia, 3),
            }
        )
        if len(resultados) >= k:
            break

    if not resultados:
        return {
            "status": "nao_encontrado",
            "data_referencia": referencia.isoformat(),
            "mensagem": "Não encontrei fonte nos documentos indexados. Informe que não há registro e não invente.",
        }
    return {"status": "ok", "data_referencia": referencia.isoformat(), "resultados": resultados}

"""Ferramentas de consulta às tabelas limpas (lotes e situação do produtor).

Escritas como FunctionTools do ADK: parâmetros simples, docstring em português e retorno em dict
com "status". Nenhuma função devolve CPF, PIX, conta, telefone, e-mail ou endereço.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import config

_pasta: Path = config.DATA_CLEAN
FOLHOSAS = {"alface", "rúcula", "couve", "coentro", "espinafre", "cebolinha", "hortelã", "manjericão"}


def usar_pasta(pasta) -> None:
    """Troca a pasta das tabelas limpas (usado em testes)."""
    global _pasta
    _pasta = Path(pasta)
    _tabela.cache_clear()


@lru_cache(maxsize=None)
def _tabela(nome: str) -> pd.DataFrame:
    return pd.read_csv(_pasta / f"{nome}.csv", dtype=str, keep_default_na=False)


def _limpo(valor):
    return None if valor in ("", None) or (isinstance(valor, float) and pd.isna(valor)) else valor


def consultar_lote(lote_id: str) -> dict:
    """Consulta um lote de produto (rastreabilidade) pelo código, por exemplo "LOT-2026-0089".

    Use para perguntas sobre origem, produtor, comprador, entrega, temperatura e validade de um lote.
    Se o código não existir, o status é "nao_encontrado": diga isso ao usuário, mostre as
    sugestões de códigos parecidos apenas como pergunta de confirmação e NÃO assuma que são o mesmo lote.

    Args:
        lote_id: código do lote informado pelo usuário (aceita formatos parecidos, como "2024-089").

    Returns:
        dict com "status" ("ok" ou "nao_encontrado"), "lote" (detalhes e "alertas") ou "sugestoes".
    """
    cod = (lote_id or "").strip().upper()
    if not cod:
        return {"status": "erro", "mensagem": "Informe o código do lote."}
    lotes = _tabela("lotes_limpo")
    achado = lotes[lotes["lote_id"].str.upper() == cod]
    if not achado.empty:
        r = achado.iloc[0]
        alertas = []
        temp = _limpo(r["temperatura_c"])
        if temp is not None and r["produto"] in FOLHOSAS and float(temp) > 5:
            alertas.append(f"Folhosa transportada a {float(temp):g} °C (ficha técnica: 2 a 5 °C).")
        pr = _tabela("produtores_publico")
        p = pr[pr["id"] == r["produtor_id"]]
        if not p.empty and p.iloc[0]["certificacao_organica_declarada"] == "sim":
            val = p.iloc[0]["validade_certificacao"]
            if val and val < r["data_entrega"]:
                alertas.append(f"Certificação orgânica do produtor venceu em {val}, antes da entrega ({r['data_entrega']}).")
        lote = {c: _limpo(r[c]) for c in lotes.columns}
        lote["alertas"] = alertas
        return {"status": "ok", "lote": lote}
    numeros = re.findall(r"\d+", cod)
    sugestoes = []
    if numeros:
        alvo = int(numeros[-1])
        for _, r in lotes.iterrows():
            fim = re.findall(r"\d+", r["lote_id"])
            if fim and int(fim[-1]) == alvo:
                sugestoes.append({c: r[c] for c in ("lote_id", "produto", "produtor_id", "comprador", "data_entrega")})
    return {
        "status": "nao_encontrado",
        "mensagem": f"Não existe lote com o código {lote_id!r}. Os códigos válidos têm o formato LOT-AAAA-NNNN.",
        "sugestoes": sugestoes,
    }


def situacao_produtor(produtor_id: str, data_referencia: str = "") -> dict:
    """Situação de um produtor: certificação orgânica (vigente, vencida, vence em breve), registro
    sanitário (SIE), DAP/CAF e restrições de venda, sempre com a fonte da informação.

    Use antes de aceitar ou alocar um pedido que dependa de selo orgânico, SIE ou DAP/CAF.
    A coluna "sim/não" de certificação do cadastro NÃO basta: o status é calculado pela validade.

    Args:
        produtor_id: código do produtor, por exemplo "P008".
        data_referencia: data AAAA-MM-DD para o cálculo (vazio = data de hoje).

    Returns:
        dict com "status" ("ok" ou "nao_encontrado"), "produtor" (situação e "alertas").
    """
    ref = config.data_referencia(data_referencia or None)
    pid = (produtor_id or "").strip().upper()
    pr = _tabela("produtores_publico")
    linha = pr[pr["id"] == pid]
    if linha.empty:
        return {"status": "nao_encontrado", "mensagem": f"Produtor {produtor_id!r} não consta no cadastro."}
    p = linha.iloc[0]
    alertas = []
    validade = p["validade_certificacao"]
    if p["certificacao_organica_declarada"] == "sim" and validade:
        dias = (pd.Timestamp(validade) - pd.Timestamp(ref)).days
        if dias < 0:
            cert = "vencida"
            alertas.append(f"Certificação orgânica vencida há {-dias} dia(s): não vender como orgânico até a renovação.")
        elif dias <= 60:
            cert = "vence_em_breve"
            alertas.append(f"Certificação orgânica vence em {dias} dia(s) ({validade}).")
        else:
            cert = "vigente"
    else:
        cert, dias = "sem_certificacao_organica", None
    if p["status"] != "ativo":
        alertas.append(f"Produtor com status {p['status']!r} no cadastro.")
    rest = _tabela("restricoes_produtor")
    r = rest[rest["produtor_id"] == pid]
    registro = {}
    if not r.empty:
        registro = {c: _limpo(r.iloc[0][c]) for c in ("sie_situacao", "sie_registro", "dap_caf", "venda_restrita", "fonte")}
        if registro.get("venda_restrita"):
            alertas.append(f"Restrição de venda: {registro['venda_restrita']}.")
    return {
        "status": "ok",
        "data_referencia": ref.isoformat(),
        "produtor": {
            "id": pid,
            "nome": p["nome_completo"],
            "municipio": p["municipio"],
            "cadastro": p["status"],
            "produtos": p["produtos"].split("|"),
            "certificacao_organica": cert,
            "validade_certificacao": validade or None,
            "dias_para_vencer": dias,
            "registro": registro,
            "alertas": alertas,
        },
    }

"""Comunicação com produtores: extrato de vendas e pagamentos, só com os dados do próprio produtor.

Função escrita como FunctionTool do ADK (parâmetros simples, docstring em português, retorno em dict
com "status"). Não devolve CPF, PIX, conta, telefone, e-mail nem endereço, e nada de outros produtores.
"""
from __future__ import annotations

import pandas as pd

from . import config
from .dados import _tabela, situacao_produtor

PAPEL_DIRETORIA = "DIRETORIA"


def _reais(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dia(iso: str) -> str:
    return pd.Timestamp(iso).strftime("%d/%m/%Y") if iso else ""


def extrato_produtor(produtor_id: str, solicitante: str, periodo: str = "", data_referencia: str = "") -> dict:
    """Gera o extrato de vendas e pagamentos de UM produtor, em linguagem simples.

    Use quando um produtor perguntar quanto vendeu, o que já foi pago ou o que ainda tem a receber.
    Informe em "solicitante" quem está pedindo: o código do próprio produtor (ex.: "P001") ou
    "diretoria". Se o solicitante for outra pessoa, o acesso é negado: dados financeiros de um
    produtor nunca são mostrados a outro. Nunca há CPF, PIX nem conta bancária no retorno.

    Args:
        produtor_id: código do produtor dono do extrato, por exemplo "P001".
        solicitante: código de quem pede ("P001") ou "diretoria". Obrigatório.
        periodo: mês no formato AAAA-MM para filtrar as vendas (vazio = todas).
        data_referencia: AAAA-MM-DD para decidir o que está em atraso (vazio = data de hoje).

    Returns:
        dict com "status" ("ok", "negado" ou "nao_encontrado"), "resumo", "vendas", "alertas" e
        "mensagem_simples" (texto pronto para o produtor).
    """
    pid = (produtor_id or "").strip().upper()
    quem = (solicitante or "").strip().upper()
    if not quem:
        return {"status": "negado", "mensagem": "Não consegui identificar quem está pedindo. Confirme a identidade antes de mostrar valores."}
    if quem not in (pid, PAPEL_DIRETORIA):
        return {"status": "negado", "mensagem": "Por segurança, o extrato só pode ser mostrado ao próprio produtor ou à diretoria."}

    prod = _tabela("produtores_publico")
    linha = prod[prod["id"] == pid]
    if linha.empty:
        return {"status": "nao_encontrado", "mensagem": f"Produtor {produtor_id!r} não consta no cadastro."}

    ref = config.data_referencia(data_referencia or None)
    ref_ts = pd.Timestamp(ref)
    fin = _tabela("financeiro_limpo")
    fin = fin[fin["produtor_id"] == pid].copy()
    if periodo:
        fin = fin[fin["data"].str.startswith(periodo.strip())]
    fin["valor"] = fin["valor_total"].astype(float)

    vendas = []
    for _, r in fin.sort_values("data").iterrows():
        pendente = r["status_pagamento"] != "pago"
        atrasada = pendente and bool(r["data_vencimento"]) and pd.Timestamp(r["data_vencimento"]) < ref_ts
        vendas.append(
            {
                "id": r["id_transacao"],
                "data": r["data"],
                "comprador": r["comprador"],
                "produto": r["produto"],
                "quantidade": float(r["quantidade"]) if r["quantidade"] else None,
                "unidade": r["unidade"],
                "valor_total": round(r["valor"], 2),
                "situacao": "atrasado" if atrasada else ("a_receber" if pendente else "pago"),
                "vencimento": r["data_vencimento"] or None,
                "pago_em": r["data_pagamento"] or None,
            }
        )

    total = sum(v["valor_total"] for v in vendas)
    pago = sum(v["valor_total"] for v in vendas if v["situacao"] == "pago")
    atraso = sum(v["valor_total"] for v in vendas if v["situacao"] == "atrasado")
    a_vencer = sum(v["valor_total"] for v in vendas if v["situacao"] == "a_receber")
    resumo = {
        "produtor": pid,
        "nome": linha.iloc[0]["nome_completo"],
        "periodo": periodo or "todos",
        "data_referencia": ref.isoformat(),
        "n_vendas": len(vendas),
        "total_vendido": round(total, 2),
        "total_pago": round(pago, 2),
        "a_receber_em_dia": round(a_vencer, 2),
        "em_atraso": round(atraso, 2),
        "saldo_a_receber": round(a_vencer + atraso, 2),
    }

    alertas = []
    sit = situacao_produtor(pid, ref.isoformat())
    if sit.get("status") == "ok":
        alertas = list(sit["produtor"].get("alertas", []))
    if atraso:
        compradores = sorted({v["comprador"] for v in vendas if v["situacao"] == "atrasado"})
        alertas.append(f"Pagamento em atraso de {', '.join(compradores)}: {_reais(atraso)}. Encaminhe à tesouraria da cooperativa.")

    primeiro = resumo["nome"].split()[0]
    if not vendas:
        texto = f"{primeiro}, não encontrei vendas registradas {'em ' + periodo if periodo else 'para você'}."
    else:
        texto = f"{primeiro}, até {_dia(ref.isoformat())} você tem {len(vendas)} venda(s) registrada(s), somando {_reais(total)}. "
        texto += f"Já foram pagos {_reais(pago)}. "
        if resumo["saldo_a_receber"]:
            texto += f"Ainda falta receber {_reais(resumo['saldo_a_receber'])}"
            if not atraso:
                texto += ", todos dentro do prazo."
            elif atraso == resumo["saldo_a_receber"]:
                texto += ", e todo esse valor já passou do vencimento."
            else:
                texto += f", dos quais {_reais(atraso)} já passaram do vencimento."
        else:
            texto += "Não há nada pendente."
    for a in alertas:
        texto += " Atenção: " + a

    return {"status": "ok", "resumo": resumo, "vendas": vendas, "alertas": alertas, "mensagem_simples": texto}

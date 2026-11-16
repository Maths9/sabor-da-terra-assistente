"""Consultas de rastreabilidade de lotes e caixa de pedidos pendentes."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from sabor_da_terra.config import DADOS_DIR
from sabor_da_terra.seguranca import norm_texto, sanitizar_pii_texto
from sabor_da_terra.tools.comum import ToolContext, ler_csv, registrar_estado, resposta

_FOLHOSAS = {"alface", "coentro", "cebolinha", "rucula", "espinafre", "couve"}


def _alertas_lote(lote: dict[str, str]) -> list[str]:
    alertas: list[str] = []
    prod_n = norm_texto(lote.get("produto", ""))
    temp_raw = norm_texto(lote.get("temperatura_transporte_c", ""))
    if any(f in prod_n for f in _FOLHOSAS):
        try:
            temp_val = float(temp_raw)
            if temp_val > 5.0:
                alertas.append(
                    f"Temperatura de transporte ({temp_val:g}°C) acima da faixa da ficha técnica de folhosas (2–5°C)."
                )
        except ValueError:
            pass
    if lote.get("produtor_id", "").upper() == "P008" and "organica" in norm_texto(
        lote.get("observacao", "")
    ):
        alertas.append(
            "Atenção: lote registra certificação orgânica anexa de P008, mas o certificado venceu em 2026-09-30."
        )
    return alertas


def consultar_lotes(
    lote_id: Optional[str] = None,
    produtor_id: Optional[str] = None,
    produto: Optional[str] = None,
    comprador: Optional[str] = None,
) -> dict[str, Any]:
    """Consulta rastreabilidade de lotes entregues em lotes.csv sem expor CPF."""
    lotes = ler_csv(DADOS_DIR / "lotes.csv")

    if lote_id:
        alvo = lote_id.strip().upper()
        exatos = [l for l in lotes if l["lote_id"].upper() == alvo]
        if exatos:
            alertas: list[str] = []
            for item in exatos:
                alertas.extend(_alertas_lote(item))
            return resposta("ok", dados={"lotes": exatos, "alertas_rastreabilidade": alertas})

        digitos_fim = re.findall(r"\d+$", alvo)
        sufixo = digitos_fim[0].lstrip("0") if digitos_fim else ""
        parecidos = (
            [l for l in lotes if l["lote_id"].split("-")[-1].lstrip("0") == sufixo]
            if sufixo
            else []
        )
        msg_parecido = ""
        if parecidos:
            p0 = parecidos[0]
            msg_parecido = (
                f" Registro mais parecido na base (NÃO presumir que seja o mesmo, confirmar com o solicitante): "
                f"{p0['lote_id']} ({p0['produto']}, {p0['produtor_id']} - {p0['produtor_nome']}, "
                f"{p0['quantidade_kg']} kg, {p0['comprador']}, entregue em {p0['data_entrega']})."
            )
        return resposta(
            "nao_encontrado",
            mensagem=(
                f"Lote '{lote_id}' não existe em lotes.csv (o padrão oficial da cooperativa é LOT-AAAA-NNNN)."
                f"{msg_parecido}"
            ),
        )

    filtrados = lotes
    if produtor_id:
        pid = produtor_id.strip().upper()
        filtrados = [l for l in filtrados if l["produtor_id"].upper() == pid]
    if produto:
        q_prod = norm_texto(produto)
        filtrados = [l for l in filtrados if q_prod in norm_texto(l["produto"])]
    if comprador:
        q_comp = norm_texto(comprador)
        filtrados = [l for l in filtrados if q_comp in norm_texto(l["comprador"])]

    if not filtrados:
        return resposta(
            "nao_encontrado",
            mensagem="Nenhum lote encontrado para os filtros informados.",
        )

    filtrados = sorted(filtrados, key=lambda x: x.get("data_entrega", ""), reverse=True)
    alertas = []
    for item in filtrados:
        alertas.extend(_alertas_lote(item))

    return resposta(
        "ok",
        dados={"total": len(filtrados), "lotes": filtrados, "alertas_rastreabilidade": alertas},
    )


def consultar_pedidos_pendentes(
    id_pedido: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Lista os pedidos pendentes de pedidos.json ou retorna o texto sanitizado de um pedido específico."""
    caminho = DADOS_DIR / "pedidos.json"
    with caminho.open("r", encoding="utf-8") as f:
        pedidos = json.load(f)

    if id_pedido:
        alvo = id_pedido.strip().upper()
        achado = next((p for p in pedidos if p["id"].upper() == alvo), None)
        if not achado:
            return resposta(
                "nao_encontrado",
                mensagem=f"Pedido '{id_pedido}' não encontrado em pedidos.json.",
            )
        pedido_limpo = {
            "id": achado["id"],
            "data_recebimento": achado["data_recebimento"],
            "canal": achado["canal"],
            "remetente": sanitizar_pii_texto(achado["remetente"], mascarar_contato=False),
            "comprador": achado["comprador"],
            "mensagem_original": sanitizar_pii_texto(
                achado["mensagem_original"], mascarar_contato=False
            ),
            "status": achado["status"],
        }
        registrar_estado(
            tool_context,
            "ultimo_pedido",
            {
                "id_pedido": pedido_limpo["id"],
                "comprador": pedido_limpo["comprador"],
                "canal": pedido_limpo["canal"],
                "data_recebimento": pedido_limpo["data_recebimento"],
            },
        )
        return resposta("ok", dados=pedido_limpo)

    resumo = [
        {
            "id": p["id"],
            "data_recebimento": p["data_recebimento"],
            "canal": p["canal"],
            "comprador": p["comprador"],
            "status": p["status"],
        }
        for p in pedidos
    ]
    return resposta("ok", dados={"total": len(resumo), "pedidos": resumo})

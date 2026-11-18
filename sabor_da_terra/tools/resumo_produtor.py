"""Resumo operacional e financeiro de produtor cooperado."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sabor_da_terra.database.repositories import repositorio
from sabor_da_terra.seguranca import norm_texto
from sabor_da_terra.tools.comum import (
    ToolContext,
    fmt_decimal,
    parse_data_iso,
    registrar_estado,
    resolver_data_ref,
    resposta,
    validar_produtor_id,
)
from sabor_da_terra.tools.regras_cooperativa import (
    avaliar_sie_produtor,
    inferir_unidade,
    mapa_unidades_produtos,
    status_certificacao_produtor,
)


def _coletar_financeiro_produtor(
    pid: str,
    dt_inicio: date,
    dt_fim: date,
    data_ref: date,
    mapa_unidades: dict[str, str],
) -> dict[str, Any]:
    vendas_total = Decimal("0.00")
    total_pago = Decimal("0.00")
    total_pendente = Decimal("0.00")
    total_vencido = Decimal("0.00")
    transacoes: list[dict[str, Any]] = []
    pendencias: list[dict[str, Any]] = []

    for row in repositorio.listar_transacoes_financeiras(
        produtor_id=pid,
        data_inicio=dt_inicio,
        data_fim=dt_fim,
    ):
        dt_venda = parse_data_iso(row.get("data"))
        if dt_venda is None or not (dt_inicio <= dt_venda <= dt_fim):
            continue

        valor = Decimal(row.get("valor_total") or "0.00")
        status_pag = norm_texto(row.get("status_pagamento", ""))
        unidade = inferir_unidade(row.get("produto", ""), mapa_unidades)
        vendas_total += valor

        transacoes.append(
            {
                "id_transacao": row["id_transacao"],
                "data": row["data"],
                "comprador": row["comprador"],
                "produto": row["produto"],
                "quantidade": float(row.get("quantidade_kg") or 0),
                "unidade": unidade,
                "valor_total": fmt_decimal(valor),
                "status_pagamento": status_pag,
                "data_vencimento": row.get("data_vencimento") or None,
                "data_pagamento": row.get("data_pagamento") or None,
            }
        )

        if status_pag == "pago":
            total_pago += valor
        elif status_pag == "pendente":
            total_pendente += valor
            dt_venc = parse_data_iso(row.get("data_vencimento"))
            em_atraso = bool(dt_venc and dt_venc < data_ref)
            dias_atraso = (data_ref - dt_venc).days if (em_atraso and dt_venc) else 0
            if em_atraso:
                total_vencido += valor
            pendencias.append(
                {
                    "id_transacao": row["id_transacao"],
                    "comprador": row["comprador"],
                    "produto": row["produto"],
                    "descricao": f"{row['comprador']} ({row['produto']})",
                    "valor": fmt_decimal(valor),
                    "data_vencimento": row.get("data_vencimento") or None,
                    "em_atraso": em_atraso,
                    "dias_atraso": dias_atraso,
                    "observacao": row.get("observacao") or None,
                }
            )

    return {
        "vendas_total": fmt_decimal(vendas_total),
        "total_pago": fmt_decimal(total_pago),
        "total_pendente": fmt_decimal(total_pendente),
        "total_vencido": fmt_decimal(total_vencido),
        "transacoes": transacoes,
        "pendencias": pendencias,
    }


def _coletar_pedidos_alocados(
    pid: str,
    dt_inicio: date,
    dt_fim: date,
    mapa_unidades: dict[str, str],
    tool_context: Optional[ToolContext],
) -> list[dict[str, Any]]:
    pedidos_alocados: list[dict[str, Any]] = []
    for lote in repositorio.listar_lotes(
        produtor_id=pid,
        data_entrega_inicio=dt_inicio,
        data_entrega_fim=dt_fim,
    ):
        dt_ent = parse_data_iso(lote.get("data_entrega"))
        if dt_ent is None or not (dt_inicio <= dt_ent <= dt_fim):
            continue
        pedidos_alocados.append(
            {
                "origem": "lote_entregue",
                "lote_id": lote["lote_id"],
                "pedido_id": lote["pedido_id"],
                "data_entrega": lote["data_entrega"],
                "comprador": lote["comprador"],
                "produto": lote["produto"],
                "quantidade": float(lote.get("quantidade_kg") or 0),
                "unidade": inferir_unidade(lote.get("produto", ""), mapa_unidades),
            }
        )

    if tool_context is not None and hasattr(tool_context, "state"):
        triagem = tool_context.state.get("resultado_triagem")
        if isinstance(triagem, dict):
            for it in triagem.get("itens") or []:
                aptos = it.get("produtores_aptos") or []
                if any(a.startswith(f"{pid} ") or a == pid for a in aptos):
                    pedidos_alocados.append(
                        {
                            "origem": "triagem_sessao",
                            "pedido_id": triagem.get("id_pedido") or "SESSAO_ATUAL",
                            "comprador": triagem.get("remetente_identificado"),
                            "produto": it.get("produto_catalogo")
                            or it.get("produto_mencionado"),
                            "quantidade": it.get("quantidade"),
                            "unidade": it.get("unidade"),
                        }
                    )
    return pedidos_alocados


def _verificar_agencia(
    prod_raw: dict[str, str], agencia_informada: Optional[str]
) -> Optional[bool]:
    if not agencia_informada:
        return None
    inf_digits = re.sub(r"\D", "", agencia_informada)
    real_digits = re.sub(r"\D", "", prod_raw.get("agencia", ""))
    return bool(real_digits and inf_digits) and inf_digits.zfill(4) == real_digits.zfill(4)


def obter_resumo_produtor(
    produtor_id: str,
    inicio: Optional[str] = None,
    fim: Optional[str] = None,
    data_referencia: Optional[str] = None,
    agencia_informada: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Retorna resumo financeiro, vendas, pendências e alocações de um produtor cooperado no período."""
    pid, erro_id = validar_produtor_id(produtor_id)
    if erro_id or pid is None:
        return erro_id  # type: ignore[return-value]

    try:
        data_ref = resolver_data_ref(data_referencia)
        dt_inicio = parse_data_iso(inicio) or date(2026, 9, 1)
        dt_fim = parse_data_iso(fim) or data_ref
    except ValueError:
        return resposta("entrada_invalida", mensagem="Formato de data inválido. Utilize AAAA-MM-DD.")

    if dt_inicio > dt_fim:
        return resposta(
            "entrada_invalida",
            mensagem="A data de início não pode ser posterior à data de fim.",
        )

    prod_raw = repositorio.obter_produtor_por_id(
        pid, remover_contato=True, incluir_agencia_interna=True
    )
    if not prod_raw:
        return resposta("nao_encontrado", mensagem=f"Produtor '{pid}' não encontrado no cadastro.")

    mapa_unidades = mapa_unidades_produtos()
    fin = _coletar_financeiro_produtor(pid, dt_inicio, dt_fim, data_ref, mapa_unidades)
    alocados = _coletar_pedidos_alocados(pid, dt_inicio, dt_fim, mapa_unidades, tool_context)
    agencia_confere = _verificar_agencia(prod_raw, agencia_informada)

    dados = {
        "produtor_id": pid,
        "nome": prod_raw["nome_completo"],
        "municipio": prod_raw["municipio"],
        "status_cadastro": norm_texto(prod_raw.get("status", "")),
        "produtos": [p.strip() for p in prod_raw.get("produtos", "").split(",") if p.strip()],
        "data_referencia": data_ref.isoformat(),
        "periodo": {"inicio": dt_inicio.isoformat(), "fim": dt_fim.isoformat()},
        "moeda": "BRL",
        "vendas_total": fin["vendas_total"],
        "total_pago": fin["total_pago"],
        "total_pendente": fin["total_pendente"],
        "total_vencido": fin["total_vencido"],
        "pedidos_alocados": alocados,
        "pendencias_financeiras": fin["pendencias"],
        "transacoes_periodo": fin["transacoes"],
        "compliance": {
            "certificacao_organica": status_certificacao_produtor(prod_raw, data_ref),
            "sie": avaliar_sie_produtor(pid),
        },
    }
    if agencia_confere is not None:
        dados["agencia_informada_confere"] = agencia_confere

    registrar_estado(tool_context, "produtor_em_foco", pid)
    return resposta("ok", dados=dados)

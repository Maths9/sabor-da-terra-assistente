"""Verificação de inadimplência do comprador, contrato formal, SIE e certificações."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sabor_da_terra.config import DADOS_DIR
from sabor_da_terra.database.repositories import repositorio
from sabor_da_terra.seguranca import norm_texto
from sabor_da_terra.tools.comum import (
    fmt_decimal,
    parse_data_iso,
    resolver_data_ref,
    resposta,
)
from sabor_da_terra.tools.regras_cooperativa import (
    PRODUTORES_SEM_SIE,
    PRODUTORES_SIE_PENDENTE,
    avaliar_sie_produtor,
    cliente_exige_sie,
    produto_casa_catalogo,
    status_certificacao_produtor,
)

_STOPWORDS_COMPRADOR = {"ltda", "rede", "atacado", "prefeitura", "unidade"}
_STOPWORDS_CONTRATO = {"rede", "ltda", "prefeitura", "garanhuns"}
_TERMOS_GENERICOS = {"hortalicas", "frutas", "hortalicas variadas", "frutas variadas"}


def _tem_contrato_formal(comprador: str) -> Optional[str]:
    q = norm_texto(comprador)
    contratos_dir = DADOS_DIR / "contratos"
    if not contratos_dir.exists():
        return None
    nome_tokens = [
        t for t in re.split(r"\W+", q) if len(t) > 3 and t not in _STOPWORDS_CONTRATO
    ]
    if not nome_tokens:
        return None
    for arq in sorted(contratos_dir.glob("*.txt")):
        conteudo_n = norm_texto(arq.read_text(encoding="utf-8"))
        if all(t in conteudo_n for t in nome_tokens):
            return f"contratos/{arq.name}"
    return None


def _analisar_credito_comprador(
    comprador: str,
    exige_sie: bool,
    data_ref: date,
    alertas: list[dict[str, str]],
) -> dict[str, Any]:
    q_comp = norm_texto(comprador)
    tokens_comp = [
        t for t in re.split(r"[\s\-]+", q_comp) if len(t) > 2 and t not in _STOPWORDS_COMPRADOR
    ]
    faturas_pendentes = []
    total_pendente = Decimal("0.00")
    total_vencido = Decimal("0.00")

    for row in repositorio.listar_transacoes_financeiras(status_pagamento="pendente"):
        comp_row = norm_texto(row.get("comprador", ""))
        casa = q_comp in comp_row or comp_row in q_comp or (
            bool(tokens_comp) and all(t in comp_row for t in tokens_comp)
        )
        if not casa:
            continue
        val = Decimal(row.get("valor_total") or "0.00")
        dt_venc = parse_data_iso(row.get("data_vencimento"))
        vencido = bool(dt_venc and dt_venc < data_ref)
        total_pendente += val
        if vencido:
            total_vencido += val
        faturas_pendentes.append(
            {
                "id_transacao": row["id_transacao"],
                "produtor_id": row["produtor_id"],
                "produto": row["produto"],
                "valor": fmt_decimal(val),
                "data_vencimento": row.get("data_vencimento"),
                "vencido": vencido,
                "observacao": row.get("observacao") or None,
            }
        )

    contrato = _tem_contrato_formal(comprador)
    if total_vencido > Decimal("0.00"):
        alertas.append(
            {
                "codigo": "COMPRADOR_INADIMPLENTE",
                "severidade": "critico",
                "mensagem": (
                    f"Comprador '{comprador}' possui R$ {fmt_decimal(total_vencido)} em títulos vencidos "
                    f"(total pendente: R$ {fmt_decimal(total_pendente)}). Escalar para diretoria antes de aprovar crédito."
                ),
            }
        )
    if not contrato and exige_sie:
        alertas.append(
            {
                "codigo": "SEM_CONTRATO_ARQUIVADO",
                "severidade": "atencao",
                "mensagem": f"Não há contrato formalizado para '{comprador}' em dados/contratos/.",
            }
        )

    return {
        "comprador": comprador,
        "contrato_encontrado": contrato,
        "total_pendente": fmt_decimal(total_pendente),
        "total_vencido": fmt_decimal(total_vencido),
        "faturas_pendentes": faturas_pendentes,
    }


def _avaliar_produtores_compliance(
    prods_alvo: list[str],
    produtores_raw: list[dict[str, str]],
    tipo_n: str,
    exige_sie: bool,
    data_ref: date,
    alertas: list[dict[str, str]],
) -> list[dict[str, Any]]:
    verificados = []
    for pid in prods_alvo:
        p_row = next((p for p in produtores_raw if p["id"].upper() == pid), None)
        if not p_row:
            continue
        cert = status_certificacao_produtor(p_row, data_ref)
        sie = avaliar_sie_produtor(pid)
        verificados.append(
            {
                "produtor_id": pid,
                "nome": p_row["nome_completo"],
                "status": norm_texto(p_row.get("status", "")),
                "certificacao_organica": cert,
                "sie": sie,
            }
        )
        if cert["situacao"] == "vence_em_breve":
            alertas.append(
                {
                    "codigo": "CERTIFICACAO_PROXIMA_VENCIMENTO",
                    "severidade": "atencao",
                    "mensagem": f"Certificação orgânica de {pid} ({p_row['nome_completo']}) vence em {cert['validade']} ({cert['dias_restantes']} dias).",
                }
            )
        if exige_sie and pid in PRODUTORES_SEM_SIE:
            alertas.append(
                {
                    "codigo": "BLOQUEIO_SIE_PRODUTOR",
                    "severidade": "critico",
                    "mensagem": f"{pid} ({p_row['nome_completo']}): {PRODUTORES_SEM_SIE[pid]}.",
                }
            )
        elif ("pnae" in tipo_n or "institucional" in tipo_n) and pid in PRODUTORES_SIE_PENDENTE:
            alertas.append(
                {
                    "codigo": "SIE_PENDENTE_INSTITUCIONAL",
                    "severidade": "critico",
                    "mensagem": f"{pid} ({p_row['nome_completo']}): {PRODUTORES_SIE_PENDENTE[pid]}.",
                }
            )
    return verificados


def verificar_compliance_e_credito(
    comprador: Optional[str] = None,
    tipo_cliente: Optional[str] = None,
    produtos: Optional[list[str]] = None,
    produtores_ids: Optional[list[str]] = None,
    data_referencia: Optional[str] = None,
) -> dict[str, Any]:
    """Verifica inadimplência do comprador, contrato vigente, exigências de SIE por produtor/produto e certificações próximas do vencimento."""
    try:
        data_ref = resolver_data_ref(data_referencia)
    except ValueError:
        return resposta("entrada_invalida", mensagem="data_referencia inválida (use AAAA-MM-DD).")

    alertas: list[dict[str, str]] = []
    tipo_n = norm_texto(tipo_cliente or "")
    exige_sie = cliente_exige_sie(tipo_cliente or "")
    info_financeira = (
        _analisar_credito_comprador(comprador, exige_sie, data_ref, alertas)
        if comprador
        else None
    )

    produtores_raw = repositorio.listar_produtores(
        filtrar_lgpd=True, remover_contato=True
    )
    prods_alvo = [p.strip().upper() for p in (produtores_ids or []) if p and p.strip()]
    for prod_item in (norm_texto(x) for x in (produtos or []) if x and x.strip()):
        if prod_item in _TERMOS_GENERICOS:
            alertas.append(
                {
                    "codigo": "PRODUTO_GENERICO",
                    "severidade": "atencao",
                    "mensagem": f"Termo '{prod_item}' é genérico e requer especificação dos itens do catálogo.",
                }
            )
            continue
        for p_row in produtores_raw:
            cadastrados = [x.strip() for x in p_row.get("produtos", "").split(",") if x.strip()]
            if produto_casa_catalogo(prod_item, cadastrados) and p_row["id"] not in prods_alvo:
                prods_alvo.append(p_row["id"])

    produtores_verificados = _avaliar_produtores_compliance(
        prods_alvo, produtores_raw, tipo_n, exige_sie, data_ref, alertas
    )
    return resposta(
        "ok",
        dados={
            "data_referencia": data_ref.isoformat(),
            "exige_sie": exige_sie,
            "comprador_credito": info_financeira,
            "produtores_compliance": produtores_verificados,
            "alertas": alertas,
        },
    )

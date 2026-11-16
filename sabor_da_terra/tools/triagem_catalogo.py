"""Avaliação individual de item no catálogo (preço, desconto, safra e limite semanal)."""

from __future__ import annotations

import re
from typing import Any, Optional

from sabor_da_terra.config import DADOS_DIR
from sabor_da_terra.seguranca import norm_texto
from sabor_da_terra.tools.comum import (
    DATA_REFERENCIA_PADRAO,
    MESES_COL,
    EntradaInvalida,
    ler_csv,
    resposta,
    validar_data,
)
from sabor_da_terra.tools.triagem_validacao import (
    ALIASES_RAPIDOS,
    buscar_produtores_aptos,
    buscar_sazonalidade,
    tabela_precos_vigente,
    validar_mes,
    validar_quantidade,
)


def _avaliar_safra_e_limite(
    item_p: dict[str, str],
    sazonalidade: dict[str, dict[str, str]],
    mes_safra: int,
    quantidade: Optional[float],
    exige_sie: bool,
) -> tuple[str, Optional[float], str, list[dict[str, Any]]]:
    nome_cat = item_p["produto"]
    col_mes = MESES_COL[mes_safra]
    saz_row = buscar_sazonalidade(nome_cat, sazonalidade)
    obs_unificada = " | ".join(
        filter(None, [item_p.get("observacao", "").strip(), (saz_row or {}).get("observacao", "").strip()])
    )
    alertas: list[dict[str, Any]] = []

    if saz_row is None:
        disp_safra = "nenhuma"
        alertas.append(
            {
                "codigo": "FORA_DE_SAFRA",
                "severidade": "critico",
                "produto_relacionado": nome_cat,
                "mensagem": f"'{nome_cat}' não possui sazonalidade cadastrada e não está disponível para venda.",
            }
        )
    else:
        disp_safra = norm_texto(saz_row.get(col_mes, ""))
        if disp_safra == "nenhuma":
            alertas.append(
                {
                    "codigo": "FORA_DE_SAFRA",
                    "severidade": "critico",
                    "produto_relacionado": nome_cat,
                    "mensagem": f"'{nome_cat}' indisponível (entressafra) no mês {mes_safra} ({col_mes}). {obs_unificada}",
                }
            )
        elif disp_safra == "baixa":
            alertas.append(
                {
                    "codigo": "SAFRA_BAIXA",
                    "severidade": "atencao",
                    "produto_relacionado": nome_cat,
                    "mensagem": f"'{nome_cat}' com disponibilidade baixa no mês {mes_safra} ({col_mes}). {obs_unificada}",
                }
            )

    m_lim = re.search(r"~?\s*(\d+)\s*(kg|d[uú]zias?)/semana", norm_texto(obs_unificada))
    limite_sem = float(m_lim.group(1)) if m_lim else None
    if quantidade is None:
        alertas.append(
            {
                "codigo": "QUANTIDADE_NAO_INFORMADA",
                "severidade": "atencao",
                "produto_relacionado": nome_cat,
                "mensagem": f"Quantidade de '{nome_cat}' não informada. Pergunte ao cliente quantos {item_p['unidade']} deseja.",
            }
        )
    elif limite_sem and quantidade > limite_sem:
        alertas.append(
            {
                "codigo": "ACIMA_DA_CAPACIDADE",
                "severidade": "critico",
                "produto_relacionado": nome_cat,
                "mensagem": f"Quantidade ({quantidade}) excede limite semanal de {limite_sem} para '{nome_cat}'.",
            }
        )
    elif limite_sem and quantidade >= 0.8 * limite_sem:
        alertas.append(
            {
                "codigo": "CAPACIDADE_PROXIMA_DO_LIMITE",
                "severidade": "atencao",
                "produto_relacionado": nome_cat,
                "mensagem": f"Quantidade ({quantidade}) consome >=80% do limite semanal ({limite_sem}) de '{nome_cat}'.",
            }
        )

    if "sem sie" in norm_texto(obs_unificada) and exige_sie:
        alertas.append(
            {
                "codigo": "RESTRICAO_SIE",
                "severidade": "critico",
                "produto_relacionado": nome_cat,
                "mensagem": f"Restrição sanitária para '{nome_cat}': {obs_unificada}",
            }
        )

    return disp_safra, limite_sem, obs_unificada, alertas


def _calcular_precos(
    item_p: dict[str, str],
    exige_organico: bool,
    quantidade: Optional[float],
    alertas: list[dict[str, Any]],
) -> tuple[Optional[float], float, Optional[float]]:
    nome_cat = item_p["produto"]
    raw_org = item_p.get("preco_organico", "n/d").strip()
    raw_conv = item_p.get("preco_convencional", "n/d").strip()

    if exige_organico and norm_texto(raw_org) == "n/d":
        alertas.append(
            {
                "codigo": "SEM_PRODUTOR_ORGANICO",
                "severidade": "critico",
                "produto_relacionado": nome_cat,
                "mensagem": f"'{nome_cat}' não possui oferta orgânica certificada (apenas convencional a R$ {raw_conv}).",
            }
        )
        preco_base = round(float(raw_conv), 2) if norm_texto(raw_conv) != "n/d" else None
    else:
        escolhido = raw_org if (exige_organico or norm_texto(raw_conv) == "n/d") else raw_conv
        preco_base = round(float(escolhido), 2) if norm_texto(escolhido) != "n/d" else None

    vol_min = float(item_p.get("volume_minimo_atacado_kg") or 0)
    desc_pct = (
        float(item_p.get("desconto_atacado_pct") or 0)
        if (quantidade is not None and vol_min > 0 and quantidade >= vol_min)
        else 0.0
    )
    preco_final = round(preco_base * (1 - desc_pct / 100.0), 2) if preco_base is not None else None
    subtotal = (
        round(preco_final * quantidade, 2)
        if (preco_final is not None and quantidade is not None)
        else None
    )
    return preco_final, desc_pct, subtotal


def avaliar_item_catalogo(
    produto: str,
    quantidade: Optional[float] = None,
    unidade: Optional[str] = None,
    exige_organico: bool = False,
    exige_sie: bool = False,
    mes_entrega: Optional[int] = None,
    data_referencia: str = DATA_REFERENCIA_PADRAO,
) -> dict[str, Any]:
    """Valida preço, desconto de atacado, safra do mês, limite semanal e produtores aptos para um item.

    Deixe `quantidade`, `unidade` e `mes_entrega` como None quando o cliente não os informou (nunca invente valores).
    """
    try:
        dt_ref = validar_data(data_referencia)
        validar_mes(mes_entrega)
        validar_quantidade(quantidade)
        termo = ALIASES_RAPIDOS.get(norm_texto(produto), norm_texto(produto))
        precos = tabela_precos_vigente()
        sazonalidade = {
            norm_texto(r["produto"]): r
            for r in ler_csv(DADOS_DIR / "sazonalidade.csv", filtrar_lgpd=False, remover_contato=False)
        }

        if any(g in termo for g in ("variada", "variado", "queijo q vcs", "mais artesanal")):
            return resposta(
                "ok",
                dados={
                    "produto_mencionado": produto,
                    "status_item": "ambiguo",
                    "alertas": [
                        {
                            "codigo": "PRODUTO_AMBIGUO",
                            "severidade": "atencao",
                            "produto_relacionado": produto,
                            "mensagem": f"Termo genérico '{produto}' requer especificação dos itens exatos do catálogo.",
                        }
                    ],
                },
            )

        exatos = [r for r in precos if norm_texto(r["produto"]) == termo]
        matches = exatos or [r for r in precos if termo in norm_texto(r["produto"])]

        if len(matches) > 1:
            opcoes = [r["produto"] for r in matches]
            return resposta(
                "ok",
                dados={
                    "produto_mencionado": produto,
                    "quantidade": quantidade,
                    "unidade": unidade,
                    "exige_organico": exige_organico,
                    "status_item": "ambiguo",
                    "opcoes_catalogo": opcoes,
                    "observacao": f"Opções: {', '.join(opcoes)}",
                    "alertas": [
                        {
                            "codigo": "PRODUTO_AMBIGUO",
                            "severidade": "atencao",
                            "produto_relacionado": produto,
                            "mensagem": f"'{produto}' é ambíguo no catálogo. Opções: {', '.join(opcoes)}.",
                        }
                    ],
                },
            )

        if not matches:
            return resposta("nao_encontrado", mensagem=f"'{produto}' não encontrado no catálogo.")

        item_p = matches[0]
        nome_cat = item_p["produto"]
        mes_safra = mes_entrega if mes_entrega is not None else dt_ref.month

        disp_safra, limite_sem, obs_unificada, alertas = _avaliar_safra_e_limite(
            item_p, sazonalidade, mes_safra, quantidade, exige_sie
        )
        preco_final, desc_pct, subtotal = _calcular_precos(
            item_p, exige_organico, quantidade, alertas
        )
        aptos, bloqueados, alertas_prod = buscar_produtores_aptos(
            nome_cat, exige_organico, exige_sie, data_referencia
        )
        alertas.extend(alertas_prod)

        tem_critico = (
            any(
                a["severidade"] == "critico" and a["codigo"] != "CERTIFICACAO_VENCIDA"
                for a in alertas
            )
            or not aptos
        )
        status_item = (
            "indisponivel"
            if disp_safra == "nenhuma"
            else ("parcial" if (quantidade is None or tem_critico or disp_safra == "baixa") else "viavel")
        )

        return resposta(
            "ok",
            dados={
                "produto_mencionado": produto,
                "produto_catalogo": nome_cat,
                "quantidade": quantidade,
                "unidade": item_p["unidade"],
                "exige_organico": exige_organico,
                "status_item": status_item,
                "disponibilidade_safra": disp_safra,
                "preco_unitario": preco_final,
                "desconto_atacado_pct": desc_pct,
                "subtotal_estimado": subtotal,
                "limite_semanal": limite_sem,
                "produtores_aptos": aptos,
                "produtores_bloqueados": bloqueados,
                "observacao": obs_unificada or None,
                "alertas": alertas,
            },
        )
    except EntradaInvalida as exc:
        return resposta("entrada_invalida", mensagem=str(exc))
    except OSError as exc:
        return resposta("erro", mensagem=f"Falha ao acessar os dados da cooperativa: {exc}")
    except Exception as exc:  # noqa: BLE001 - a tool nunca deve derrubar o agente
        return resposta("erro", mensagem=f"Erro inesperado na avaliação do item: {exc}")

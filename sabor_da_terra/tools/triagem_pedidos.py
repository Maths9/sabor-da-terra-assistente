"""Orquestração da triagem completa de um pedido nos CSVs operacionais."""

from __future__ import annotations

from typing import Any, Optional

from sabor_da_terra.tools.comum import (
    DATA_REFERENCIA_PADRAO,
    EntradaInvalida,
    ToolContext,
    registrar_estado,
    resposta,
    validar_data,
)
from sabor_da_terra.tools.regras_cooperativa import cliente_exige_sie
from sabor_da_terra.tools.schemas import ItemPedidoInput, TipoDemanda, TriagemPedidoOutput
from sabor_da_terra.tools.triagem_catalogo import avaliar_item_catalogo
from sabor_da_terra.tools.triagem_consultas import consultar_produtores_ou_organicos
from sabor_da_terra.tools.triagem_validacao import (
    DEMANDAS_COM_ENTREGA,
    normalizar_tipo_demanda,
    validar_mes,
)


def realizar_triagem_completa_pedido(
    remetente_identificado: str,
    tipo_cliente: str,
    tipo_demanda: TipoDemanda,
    itens: list[ItemPedidoInput],
    id_pedido: Optional[str] = None,
    canal: Optional[str] = None,
    data_referencia: str = DATA_REFERENCIA_PADRAO,
    mes_entrega: Optional[int] = None,
    urgente_no_texto: bool = False,
    exige_organico_global: bool = False,
    solicita_dados_sensiveis: bool = False,
    termo_identificacao_produtor: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Executa a triagem completa do pedido, valida itens nos CSVs e salva o TriagemPedidoOutput em session.state['resultado_triagem'].

    Deixe `quantidade` dos itens e `mes_entrega` como None enquanto o cliente não os informar; consulte `campos_pendentes` no retorno.
    """
    try:
        validar_data(data_referencia)
        validar_mes(mes_entrega)
        tipo_demanda_norm = normalizar_tipo_demanda(tipo_demanda)
        exige_sie = cliente_exige_sie(tipo_cliente)
        itens_triados: list[dict[str, Any]] = []
        alertas_gerais: list[dict[str, Any]] = []
        campos_pendentes: list[str] = []
        total = 0.0

        if solicita_dados_sensiveis:
            alertas_gerais.append(
                {
                    "codigo": "SOLICITACAO_DADOS_SENSIVEIS",
                    "severidade": "critico",
                    "mensagem": "Solicitação de CPF ou dados bancários bloqueada por política de privacidade (LGPD).",
                }
            )

        prod_id = None
        if termo_identificacao_produtor or tipo_demanda_norm == "comunicacao_produtor":
            achados = consultar_produtores_ou_organicos(
                termo_identificacao_produtor or remetente_identificado,
                data_referencia=data_referencia,
            )
            if achados["status"] in {"entrada_invalida", "erro"}:
                return achados
            if achados["status"] == "ok" and achados["dados"]["produtores_encontrados"]:
                prod_id = achados["dados"]["produtores_encontrados"][0]["id"]

        for raw_it in itens:
            it = raw_it.model_dump() if hasattr(raw_it, "model_dump") else dict(raw_it)
            prod_menc = it.get("produto_mencionado", "")
            qtd = it.get("quantidade")
            exige_org_item = bool(it.get("exige_organico", False) or exige_organico_global)
            res = avaliar_item_catalogo(
                produto=prod_menc,
                quantidade=float(qtd) if qtd is not None else None,
                unidade=it.get("unidade"),
                exige_organico=exige_org_item,
                exige_sie=exige_sie,
                mes_entrega=mes_entrega,
                data_referencia=data_referencia,
            )
            if res["status"] in {"entrada_invalida", "erro"}:
                return res
            if res["status"] == "nao_encontrado":
                alertas_gerais.append(
                    {
                        "codigo": "PRODUTO_NAO_ENCONTRADO",
                        "severidade": "atencao",
                        "produto_relacionado": prod_menc,
                        "mensagem": res["mensagem"] or f"'{prod_menc}' não encontrado no catálogo.",
                    }
                )
                itens_triados.append(
                    {
                        "produto_mencionado": prod_menc,
                        "quantidade": float(qtd) if qtd is not None else None,
                        "unidade": it.get("unidade"),
                        "exige_organico": exige_org_item,
                        "status_item": "nao_encontrado",
                    }
                )
                continue

            item_dados = dict(res["dados"])
            alertas_gerais.extend(item_dados.pop("alertas", []))
            total = round(total + float(item_dados.get("subtotal_estimado") or 0.0), 2)
            itens_triados.append(item_dados)
            if (
                item_dados.get("produto_catalogo")
                and item_dados.get("quantidade") is None
                and "quantidade" not in campos_pendentes
            ):
                campos_pendentes.append("quantidade")

        if itens_triados and tipo_demanda_norm in DEMANDAS_COM_ENTREGA and mes_entrega is None:
            campos_pendentes.append("prazo_entrega")
            alertas_gerais.append(
                {
                    "codigo": "PRAZO_NAO_INFORMADO",
                    "severidade": "atencao",
                    "mensagem": "Prazo de entrega não informado. A safra do mês atual é apenas prévia; pergunte ao cliente para quando deseja a entrega.",
                }
            )

        urgencia = (
            "critica"
            if (tipo_demanda_norm == "notificacao_fiscalizacao" or urgente_no_texto)
            else ("alta" if exige_sie else "media")
        )
        modulos = _recomendar_modulos(
            itens_triados, tipo_demanda_norm, exige_organico_global, exige_sie, alertas_gerais
        )
        status_viab = _definir_status_viabilidade(itens_triados, campos_pendentes)
        pendentes_txt = f" | Pendentes: {', '.join(campos_pendentes)}" if campos_pendentes else ""

        saida = TriagemPedidoOutput(
            id_pedido=id_pedido,
            canal=canal,
            remetente_identificado=remetente_identificado,
            produtor_remetente_id=prod_id,
            tipo_cliente=tipo_cliente,
            tipo_demanda=tipo_demanda_norm,
            urgencia=urgencia,
            status_viabilidade=status_viab,
            data_referencia=data_referencia,
            mes_entrega=mes_entrega,
            campos_pendentes=campos_pendentes,
            itens=itens_triados,
            valor_total_estimado=round(total, 2),
            alertas_operacionais=alertas_gerais,
            modulos_recomendados=modulos,
            resumo_executivo_triagem=(
                f"[{urgencia.upper()}] {remetente_identificado} ({tipo_demanda_norm}) -> "
                f"Status: {status_viab} | Total estimado: R$ {total:.2f} | "
                f"Alertas: {len(alertas_gerais)}{pendentes_txt}"
            ),
        ).model_dump()
        registrar_estado(tool_context, "resultado_triagem", saida)
        return resposta("ok", dados=saida)
    except EntradaInvalida as exc:
        return resposta("entrada_invalida", mensagem=str(exc))
    except OSError as exc:
        return resposta("erro", mensagem=f"Falha ao acessar os dados da cooperativa: {exc}")
    except Exception as exc:  # noqa: BLE001 - a tool nunca deve derrubar o agente
        return resposta("erro", mensagem=f"Erro inesperado na triagem do pedido: {exc}")


def _recomendar_modulos(
    itens_triados: list[dict[str, Any]],
    tipo_demanda: str,
    exige_organico_global: bool,
    exige_sie: bool,
    alertas_gerais: list[dict[str, Any]],
) -> list[str]:
    modulos = ["estoque_safra"] if itens_triados else []
    if (
        exige_organico_global
        or exige_sie
        or tipo_demanda in {"notificacao_fiscalizacao", "consulta_comercial"}
        or any(a["codigo"] in {"CERTIFICACAO_VENCIDA", "RESTRICAO_SIE"} for a in alertas_gerais)
    ):
        modulos.append("rastreabilidade_compliance")
    if tipo_demanda in {"comunicacao_produtor", "pedido_compra"}:
        modulos.append("comunicacao_produtores")
    return modulos


def _definir_status_viabilidade(
    itens_triados: list[dict[str, Any]], campos_pendentes: list[str]
) -> str:
    status_itens = {i["status_item"] for i in itens_triados}
    if not itens_triados:
        return "encaminhar_modulo_especialista"
    if "ambiguo" in status_itens or campos_pendentes:
        return "requer_esclarecimento"
    if status_itens == {"viavel"}:
        return "viavel"
    if status_itens == {"indisponivel"}:
        return "inviavel"
    return "parcialmente_viavel"

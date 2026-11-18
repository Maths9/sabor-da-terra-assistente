"""Redação em modo rascunho de notificações de alocação para produtores."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sabor_da_terra.database.repositories import repositorio
from sabor_da_terra.seguranca import norm_texto, sanitizar_pii_texto
from sabor_da_terra.tools.comum import (
    ToolContext,
    registrar_estado,
    resolver_data_ref,
    resposta,
    validar_produtor_id,
)
from sabor_da_terra.tools.regras_cooperativa import (
    PRODUTORES_SEM_SIE,
    PRODUTORES_SIE_PENDENTE,
    cliente_exige_sie,
    match_produtor_em_lista,
    produto_casa_catalogo,
    status_certificacao_produtor,
)
from sabor_da_terra.tools.schemas import PedidoNotificacaoInput


def _resolver_pedido_referencia(
    pedido: Optional[PedidoNotificacaoInput],
    tool_context: Optional[ToolContext],
) -> Optional[dict[str, Any]]:
    if pedido is not None:
        return pedido.model_dump() if hasattr(pedido, "model_dump") else dict(pedido)
    if tool_context is not None and hasattr(tool_context, "state"):
        ref = tool_context.state.get("resultado_triagem") or tool_context.state.get("ultimo_pedido")
        if isinstance(ref, dict):
            return ref
    return None


def _filtrar_itens_para_produtor(
    pid: str,
    prod: dict[str, str],
    itens_brutos: list[Any],
    comprador: str,
    tipo_cliente: str,
    exige_sie: bool,
    data_ref: date,
) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    prods_produtor = [norm_texto(x) for x in prod.get("produtos", "").split(",") if x.strip()]
    itens_produtor: list[dict[str, Any]] = []

    for it in itens_brutos:
        if not isinstance(it, dict):
            continue
        aptos = it.get("produtores_aptos") or []
        bloqueados = it.get("produtores_bloqueados") or []
        nome_prod = (
            it.get("produto_catalogo")
            or it.get("produto_mencionado")
            or it.get("produto")
            or ""
        )
        exige_org = bool(it.get("exige_organico", False))

        if match_produtor_em_lista(pid, bloqueados):
            return [], resposta(
                "dados_insuficientes",
                mensagem=(
                    f"O produtor {pid} está bloqueado para '{nome_prod}' neste pedido "
                    "(verifique certificação orgânica ou status)."
                ),
            )

        eh_apto = match_produtor_em_lista(pid, aptos)
        match_catalogo = produto_casa_catalogo(nome_prod, prods_produtor)
        if (aptos and not eh_apto) or (not aptos and not match_catalogo):
            continue

        cert_info = status_certificacao_produtor(prod, data_ref)
        if exige_org and not cert_info["possui_certificacao_organica"]:
            return [], resposta(
                "dados_insuficientes",
                mensagem=(
                    f"Bloqueio de compliance: o pedido exige orgânico para '{nome_prod}', "
                    f"mas {pid} ({prod['nome_completo']}) está com certificação '{cert_info['situacao']}'."
                ),
            )
        if exige_sie and pid in PRODUTORES_SEM_SIE:
            return [], resposta(
                "dados_insuficientes",
                mensagem=f"Bloqueio sanitário (SIE): {pid} - {PRODUTORES_SEM_SIE[pid]}. Não pode ser notificado para cliente '{comprador}'.",
            )
        if "pnae" in tipo_cliente and pid in PRODUTORES_SIE_PENDENTE:
            return [], resposta(
                "dados_insuficientes",
                mensagem=f"Bloqueio sanitário (SIE): {pid} - {PRODUTORES_SIE_PENDENTE[pid]}.",
            )

        itens_produtor.append(
            {
                "produto": nome_prod,
                "quantidade": it.get("quantidade"),
                "unidade": it.get("unidade") or "kg",
                "exige_organico": exige_org,
            }
        )

    return itens_produtor, None


def redigir_notificacao(
    produtor_id: str,
    pedido: Optional[PedidoNotificacaoInput] = None,
    observacoes_adicionais: Optional[str] = None,
    data_referencia: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Redige (sem enviar externamente) uma notificação clara para o produtor sobre um pedido."""
    pid, erro_id = validar_produtor_id(produtor_id)
    if erro_id or pid is None:
        return erro_id  # type: ignore[return-value]

    try:
        data_ref = resolver_data_ref(data_referencia)
    except ValueError:
        return resposta("entrada_invalida", mensagem="data_referencia inválida (use AAAA-MM-DD).")

    prod = repositorio.obter_produtor_por_id(pid, remover_contato=True)
    if not prod:
        return resposta("nao_encontrado", mensagem=f"Produtor '{pid}' não encontrado no cadastro.")

    if norm_texto(prod.get("status", "")) != "ativo":
        return resposta(
            "dados_insuficientes",
            mensagem=f"Não é possível redigir alocação: o produtor {pid} ({prod['nome_completo']}) está INATIVO.",
        )

    pedido_ref = _resolver_pedido_referencia(pedido, tool_context)
    if not pedido_ref:
        return resposta(
            "dados_insuficientes",
            mensagem="Nenhum pedido estruturado foi informado nem encontrado no contexto da sessão. Realize ou informe o pedido antes de redigir a notificação.",
        )

    itens_brutos = pedido_ref.get("itens") or []
    if not itens_brutos:
        return resposta(
            "dados_insuficientes",
            mensagem="O pedido informado não possui itens definidos para alocar ao produtor.",
        )

    comprador = (
        pedido_ref.get("remetente_identificado")
        or pedido_ref.get("comprador")
        or "Comprador não informado"
    )
    tipo_cliente = norm_texto(pedido_ref.get("tipo_cliente", ""))
    exige_sie = cliente_exige_sie(tipo_cliente)
    id_pedido = pedido_ref.get("id_pedido") or "Pedido em triagem"

    itens_produtor, erro_item = _filtrar_itens_para_produtor(
        pid, prod, itens_brutos, comprador, tipo_cliente, exige_sie, data_ref
    )
    if erro_item:
        return erro_item
    if not itens_produtor:
        return resposta(
            "dados_insuficientes",
            mensagem=f"Nenhum item do pedido '{id_pedido}' corresponde aos produtos aptos de {pid} ({prod['nome_completo']}).",
        )

    primeiro_nome = prod["nome_completo"].split()[0]
    linhas_itens = []
    for it in itens_produtor:
        qtd = it["quantidade"]
        qtd_str = f"{qtd:g}" if isinstance(qtd, (int, float)) else str(qtd or "a confirmar")
        tag_org = " (orgânico certificado)" if it["exige_organico"] else ""
        linhas_itens.append(f"- {it['produto']}: {qtd_str} {it['unidade']}{tag_org}")

    obs_extra = (
        f"\nObservações: {sanitizar_pii_texto(observacoes_adicionais)}\n"
        if observacoes_adicionais
        else ""
    )
    aviso_sie = (
        f"\nAtenção: confirmar regularidade do SIE ({PRODUTORES_SIE_PENDENTE[pid]})."
        if exige_sie and pid in PRODUTORES_SIE_PENDENTE
        else ""
    )

    texto = (
        f"Olá, {primeiro_nome}! Tudo bem? Aqui é da Cooperativa Sabor da Terra.\n\n"
        f"Temos uma nova demanda vinculada aos seus produtos ({id_pedido}):\n"
        f"Comprador: {comprador}\n"
        + "\n".join(linhas_itens)
        + f"{aviso_sie}{obs_extra}\n\n"
        "Por favor, confirme até amanhã se consegue atender essa quantidade e a previsão de entrega no CD para organizarmos o lote e a nota fiscal."
    )

    registrar_estado(tool_context, "produtor_em_foco", pid)
    return resposta(
        "ok",
        dados={
            "produtor_id": pid,
            "produtor_nome": prod["nome_completo"],
            "municipio": prod["municipio"],
            "id_pedido": id_pedido,
            "somente_rascunho": True,
            "envio_automatico": False,
            "itens_relacionados": itens_produtor,
            "texto": texto,
        },
    )

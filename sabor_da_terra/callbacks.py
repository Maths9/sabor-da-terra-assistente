"""Callbacks do agente coordenador (injeção temporal, estado de sessão e defesa LGPD)."""

from __future__ import annotations

from datetime import date
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from sabor_da_terra.config import obter_data_referencia
from sabor_da_terra.seguranca import (
    CAMPOS_CONTATO_PESSOAL,
    CAMPOS_SENSIVEIS_LGPD,
    sanitizar_pii_texto,
)

_DIAS_SEMANA_PT = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

_CHAVES_BLOQUEADAS = CAMPOS_SENSIVEIS_LGPD | CAMPOS_CONTATO_PESSOAL


def _sanitizar_estrutura(valor: Any) -> Any:
    """Sanitiza strings e remove eventuais chaves LGPD de estruturas aninhadas."""
    if isinstance(valor, str):
        return sanitizar_pii_texto(valor, mascarar_contato=False, mascarar_endereco=False)
    if isinstance(valor, list):
        return [_sanitizar_estrutura(item) for item in valor]
    if isinstance(valor, dict):
        limpo: dict[str, Any] = {}
        for k, v in valor.items():
            if str(k).lower() in _CHAVES_BLOQUEADAS:
                continue
            limpo[k] = _sanitizar_estrutura(v)
        return limpo
    return valor


def injetar_contexto_temporal(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> LlmResponse | None:
    """Injeta a data corrente do sistema e resumo seguro do estado da sessão no prompt."""
    data_ref = obter_data_referencia()
    dt = date.fromisoformat(data_ref)
    dia_semana = _DIAS_SEMANA_PT[dt.weekday()]

    instrucoes = [
        (
            f"[CONTEXTO TEMPORAL DA REQUISIÇÃO] Data atual do sistema: {data_ref} "
            f"({dia_semana}), mês corrente: {dt.month}. "
            f"Passe explicitamente data_referencia='{data_ref}' ao chamar ferramentas com data_referencia. "
            "Para triagem de pedidos/itens, deixe quantidade, unidade e mes_entrega como None se o cliente não os informou "
            "(nunca invente 1 kg nem assuma o mês atual como prazo de entrega)."
        )
    ]

    state = getattr(callback_context, "state", None)
    if state:
        linhas_estado: list[str] = []
        perfil = state.get("perfil_usuario")
        produtor_foco = state.get("produtor_em_foco")
        produtor_id_str = (
            produtor_foco.strip()
            if isinstance(produtor_foco, str) and produtor_foco.strip()
            else (
                str(produtor_foco.get("produtor_id") or "").strip()
                if isinstance(produtor_foco, dict)
                else ""
            )
        )
        if perfil == "produtor" and produtor_id_str:
            instrucoes.append(
                f"[PERFIL NA INTERFACE] Usuário operando no PORTAL DO PRODUTOR como {produtor_id_str}. "
                f"Perguntas em primeira pessoa ('meus pagamentos', 'minha certificação', 'minhas vendas', 'meus produtos') "
                f"referem-se a {produtor_id_str}, mantendo integralmente o bloqueio LGPD."
            )
        elif perfil == "cooperado":
            linhas_estado.append("perfil=cooperado (gestão cooperativa)")

        if produtor_id_str:
            linhas_estado.append(f"produtor_em_foco={produtor_id_str}")
        ultimo_pedido = state.get("ultimo_pedido")
        if isinstance(ultimo_pedido, dict):
            comprador_ped = (
                ultimo_pedido.get("comprador")
                or ultimo_pedido.get("remetente_identificado")
                or "não informado"
            )
            status_ped = (
                ultimo_pedido.get("status_viabilidade")
                or ultimo_pedido.get("id_pedido")
                or "em contexto"
            )
            linhas_estado.append(
                f"ultimo_pedido={comprador_ped} ({status_ped})"
            )
        fontes = state.get("ultimas_fontes_rag")
        if isinstance(fontes, list) and fontes:
            nomes_fontes = ", ".join(
                str(f.get("nome", "")) for f in fontes[:3] if isinstance(f, dict)
            )
            if nomes_fontes:
                linhas_estado.append(f"ultimas_fontes_rag=[{nomes_fontes}]")
        if linhas_estado:
            instrucoes.append(
                "[ESTADO ATUAL DA SESSÃO] " + " | ".join(linhas_estado) + "."
            )

    llm_request.append_instructions(instrucoes)
    return None


def processar_retorno_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    """Sincroniza session.state pós-tool e aplica sanitização defensiva no retorno."""
    if not isinstance(tool_response, dict):
        return None

    limpo = _sanitizar_estrutura(tool_response)

    state = getattr(tool_context, "state", None)
    if state is not None and tool.name == "realizar_triagem_completa_pedido":
        dados = (
            limpo.get("dados")
            if limpo.get("status") == "ok" and isinstance(limpo.get("dados"), dict)
            else (limpo if "status_viabilidade" in limpo else None)
        )
        if isinstance(dados, dict) and "status_viabilidade" in dados:
            state["ultimo_pedido"] = _sanitizar_estrutura(
                {
                    "id_pedido": dados.get("id_pedido"),
                    "comprador": dados.get("remetente_identificado")
                    or args.get("remetente_identificado"),
                    "tipo_cliente": dados.get("tipo_cliente")
                    or args.get("tipo_cliente"),
                    "data_referencia": dados.get("data_referencia"),
                    "mes_entrega": dados.get("mes_entrega"),
                    "status_viabilidade": dados.get("status_viabilidade"),
                    "campos_pendentes": dados.get("campos_pendentes") or [],
                    "valor_total_estimado": dados.get("valor_total_estimado"),
                    "itens": args.get("itens"),
                }
            )
            if "resultado_triagem" in state and state["resultado_triagem"] is not None:
                state["resultado_triagem"] = _sanitizar_estrutura(
                    state["resultado_triagem"]
                )

    return limpo


def sanitizar_resposta_modelo(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> LlmResponse | None:
    """Camada final de defesa LGPD sobre o texto emitido pelo modelo."""
    del callback_context
    content = getattr(llm_response, "content", None)
    if not content or not getattr(content, "parts", None):
        return None

    alterado = False
    for part in content.parts:
        texto = getattr(part, "text", None)
        if not texto:
            continue
        sanitizado = sanitizar_pii_texto(
            texto, mascarar_contato=False, mascarar_endereco=False
        )
        if sanitizado != texto:
            part.text = sanitizado
            alterado = True

    return llm_response if alterado else None

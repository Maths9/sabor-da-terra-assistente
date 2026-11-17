"""Callbacks e guardrails determinísticos do agente coordenador (Google ADK)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from sabor_da_terra.config import obter_data_referencia
from sabor_da_terra.seguranca import (
    detectar_dados_sensiveis,
    norm_texto,
    sanitizar_estrutura,
    sanitizar_pii_texto,
    texto_apenas_pii_ou_vazio,
)

MENSAGEM_RECUSA_PII = (
    "Por política de segurança e proteção de dados (LGPD), não posso receber, "
    "confirmar nem tratar CPF, RG, data de nascimento, chave PIX ou dados de conta "
    "bancária por este chat. Assuntos cadastrais ou bancários devem ser tratados "
    "diretamente com o setor administrativo/financeiro da cooperativa pelos canais oficiais. "
    "Se desejar, reenvie sua solicitação sem essas informações."
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

_PERFIS_OPERADOR = {"operador", "cooperado"}
_PERFIS_VALIDOS = _PERFIS_OPERADOR | {"produtor"}

_TOOLS_EXCLUSIVAS_OPERADOR = {
    "consultar_pedidos_pendentes",
    "redigir_notificacao",
    "consultar_produtores_ou_organicos",
    "realizar_triagem_completa_pedido",
    "verificar_compliance_e_credito",
}
_TOOLS_EXCLUSIVAS_COOPERADO = _TOOLS_EXCLUSIVAS_OPERADOR

_TOOLS_ESCOPO_PRODUTOR = {
    "obter_resumo_produtor",
    "consultar_lotes",
}

_TIPOS_DOC_PUBLICOS_PRODUTOR = {"ficha", "ficha_tecnica"}
_TIPOS_DOC_RESTRITOS_OPERADOR = {"contrato", "inspecao", "adagro"}
_TIPOS_DOC_RESTRITOS_COOPERADO = _TIPOS_DOC_RESTRITOS_OPERADOR


def _sanitizar_estrutura(valor: Any) -> Any:
    """Compatibilidade: sanitiza strings e remove chaves LGPD recursivamente."""
    return sanitizar_estrutura(
        valor,
        mascarar_contato=False,
        mascarar_endereco=False,
        mascarar_agencia_isolada=True,
    )


def _extrair_produtor_id_estado(state: Any) -> str:
    if not state:
        return ""
    produtor_foco = state.get("produtor_em_foco")
    raw = (
        produtor_foco.strip().upper()
        if isinstance(produtor_foco, str)
        else (
            str(produtor_foco.get("produtor_id") or "").strip().upper()
            if isinstance(produtor_foco, dict)
            else ""
        )
    )
    return raw if re.match(r"^P\d{3}$", raw) else ""


def _negar_acesso(mensagem: str) -> dict[str, Any]:
    return {"status": "acesso_negado", "dados": None, "mensagem": mensagem}


def _match_produtor_rotulo(rotulo: str, pid: str) -> bool:
    s = str(rotulo or "").strip().upper()
    return s == pid or s.startswith(f"{pid} ") or s.startswith(f"{pid}-")


def _anonimizar_lista_produtores(lista: Any, pid: str, rotulo_grupo: str) -> list[str]:
    if not isinstance(lista, list) or not lista:
        return []
    proprios = [str(item) for item in lista if _match_produtor_rotulo(str(item), pid)]
    outros = len(lista) - len(proprios)
    if outros > 0:
        proprios.append(
            f"{outros} outro(s) produtor(es) {rotulo_grupo} (identificação restrita à gestão)"
        )
    return proprios


def _aplicar_guardrail_entrada(
    llm_request: LlmRequest,
) -> tuple[LlmResponse | None, list[str]]:
    """Mascara PII no histórico da requisição e barra envio puro de dados sensíveis."""
    contents = getattr(llm_request, "contents", None) or []
    ultimo_usuario = next(
        (c for c in reversed(contents) if getattr(c, "role", None) == "user"),
        None,
    )
    texto_ultima_msg = " ".join(
        getattr(p, "text", "")
        for p in (getattr(ultimo_usuario, "parts", None) or [])
        if getattr(p, "text", None)
    )

    tipos_pii = detectar_dados_sensiveis(
        texto_ultima_msg, incluir_agencia_isolada=False
    )

    for c in contents:
        for p in getattr(c, "parts", None) or []:
            texto_parte = getattr(p, "text", None)
            if texto_parte:
                p.text = sanitizar_pii_texto(
                    texto_parte,
                    mascarar_contato=False,
                    mascarar_endereco=False,
                    mascarar_agencia_isolada=False,
                )

    if not tipos_pii:
        return None, []

    texto_ultimo_mascarado = " ".join(
        getattr(p, "text", "")
        for p in (getattr(ultimo_usuario, "parts", None) or [])
        if getattr(p, "text", None)
    )
    if texto_apenas_pii_ou_vazio(texto_ultimo_mascarado):
        return (
            LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=MENSAGEM_RECUSA_PII)],
                )
            ),
            tipos_pii,
        )

    return None, tipos_pii


def injetar_contexto_temporal(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> LlmResponse | None:
    """Aplica guardrail de entrada LGPD e injeta data/contexto seguro da sessão."""
    resposta_bloqueio, tipos_pii_entrada = _aplicar_guardrail_entrada(llm_request)
    if resposta_bloqueio is not None:
        return resposta_bloqueio

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

    if tipos_pii_entrada:
        instrucoes.append(
            "[GUARDRAIL LGPD NA ENTRADA] Dados sensíveis ("
            + ", ".join(tipos_pii_entrada)
            + ") foram omitidos automaticamente da mensagem antes do envio ao modelo. "
            "Recuse cadastrar, confirmar ou repassar CPF, RG, data de nascimento, chave PIX ou conta bancária pelo chat "
            "(oriente encaminhamento ao setor administrativo/financeiro), mas atenda normalmente a eventual pedido comercial ou dúvida operacional legítima."
        )

    state = getattr(callback_context, "state", None)
    if state:
        linhas_estado: list[str] = []
        perfil = str(state.get("perfil_usuario") or "").strip().lower()
        produtor_id_str = _extrair_produtor_id_estado(state)
        if perfil == "produtor" and produtor_id_str:
            instrucoes.append(
                f"[PERFIL NA INTERFACE] Usuário operando no PORTAL DO PRODUTOR como {produtor_id_str}. "
                f"Perguntas em primeira pessoa ('meus pagamentos', 'minha certificação', 'minhas vendas', 'meus produtos') "
                f"referem-se a {produtor_id_str}, mantendo integralmente o bloqueio LGPD e o isolamento entre produtores."
            )
        elif perfil in _PERFIS_OPERADOR:
            linhas_estado.append("perfil=operador (gestão cooperativa)")

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
            linhas_estado.append(f"ultimo_pedido={comprador_ped} ({status_ped})")
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


def validar_acesso_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any] | None:
    """Guardrail determinístico pré-tool (RBAC fail-closed e isolamento entre produtores)."""
    state = getattr(tool_context, "state", None)
    if not state:
        return _negar_acesso(
            "Sessão sem contexto de autenticação/perfil válido para executar ferramentas."
        )

    perfil = str(state.get("perfil_usuario") or "").strip().lower()
    if perfil in _PERFIS_OPERADOR:
        return None
    if perfil != "produtor":
        return _negar_acesso(
            "Perfil de usuário ausente ou não autorizado para executar esta ferramenta."
        )

    produtor_logado = _extrair_produtor_id_estado(state)
    if not produtor_logado:
        return _negar_acesso(
            "Sessão no Portal do Produtor sem identificação válida do produtor em foco."
        )

    if tool.name in _TOOLS_EXCLUSIVAS_OPERADOR:
        return _negar_acesso(
            f"A ferramenta '{tool.name}' é restrita ao operador da cooperativa."
        )

    if tool.name in _TOOLS_ESCOPO_PRODUTOR:
        pid_solicitado = str(args.get("produtor_id") or "").strip().upper()
        if pid_solicitado != produtor_logado:
            return _negar_acesso(
                f"Violação de isolamento LGPD: você está autenticado como {produtor_logado} "
                f"e só pode consultar seus próprios dados passando produtor_id='{produtor_logado}'."
            )
        return None

    if tool.name == "consultar_documentos":
        tipo_norm = norm_texto(str(args.get("tipo_documento") or "")).replace(" ", "_")
        pid_solicitado = str(args.get("produtor_id") or "").strip().upper()
        if pid_solicitado and pid_solicitado != produtor_logado:
            return _negar_acesso(
                f"Violação de isolamento LGPD: você não tem permissão para consultar documentos de {pid_solicitado}."
            )
        if tipo_norm in _TIPOS_DOC_RESTRITOS_COOPERADO:
            return _negar_acesso(
                "Contratos comerciais e relatórios internos da ADAGRO são restritos à gestão da cooperativa."
            )
        if tipo_norm not in _TIPOS_DOC_PUBLICOS_PRODUTOR and pid_solicitado != produtor_logado:
            return _negar_acesso(
                f"No Portal do Produtor, consulte fichas técnicas com tipo_documento='ficha_tecnica' "
                f"ou seus próprios certificados/laudos informando produtor_id='{produtor_logado}'."
            )
        return None

    return None


def _filtrar_retorno_perfil_produtor(
    tool_name: str,
    limpo: dict[str, Any],
    produtor_logado: str,
) -> dict[str, Any]:
    """Impede vazamento de dados de outros produtores em tools compartilhadas."""
    if not produtor_logado:
        return limpo

    dados = limpo.get("dados")
    if tool_name == "consultar_lotes":
        if isinstance(dados, dict) and isinstance(dados.get("lotes"), list):
            lotes_orig = dados["lotes"]
            lotes_proprios = [
                lote
                for lote in lotes_orig
                if str((lote or {}).get("produtor_id") or "").strip().upper()
                == produtor_logado
            ]
            if lotes_orig and not lotes_proprios:
                return _negar_acesso(
                    f"O lote consultado não pertence ao produtor autenticado ({produtor_logado})."
                )
            dados["lotes"] = lotes_proprios
            if "total" in dados:
                dados["total"] = len(lotes_proprios)
        elif limpo.get("status") == "nao_encontrado" and isinstance(
            limpo.get("mensagem"), str
        ):
            msg = limpo["mensagem"]
            if "Registro mais parecido" in msg and produtor_logado not in msg.upper():
                limpo["mensagem"] = msg.split(" Registro mais parecido", 1)[0]
        return limpo

    if tool_name == "avaliar_item_catalogo" and isinstance(dados, dict):
        if "produtores_aptos" in dados:
            dados["produtores_aptos"] = _anonimizar_lista_produtores(
                dados["produtores_aptos"], produtor_logado, "apto(s)"
            )
        if "produtores_bloqueados" in dados:
            dados["produtores_bloqueados"] = _anonimizar_lista_produtores(
                dados["produtores_bloqueados"], produtor_logado, "bloqueado(s)"
            )
        if isinstance(dados.get("alertas"), list):
            dados["alertas"] = [
                alerta
                for alerta in dados["alertas"]
                if not (
                    isinstance(alerta, dict)
                    and alerta.get("produtor_relacionado")
                    and str(alerta.get("produtor_relacionado")).strip().upper()
                    != produtor_logado
                )
            ]

    return limpo


def processar_retorno_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    """Sincroniza session.state pós-tool, aplica sanitização LGPD e isolamento de perfil."""
    if not isinstance(tool_response, dict):
        return None

    limpo = _sanitizar_estrutura(tool_response)

    state = getattr(tool_context, "state", None)
    if state is not None:
        perfil = str(state.get("perfil_usuario") or "").strip().lower()
        if perfil == "produtor":
            limpo = _filtrar_retorno_perfil_produtor(
                tool.name, limpo, _extrair_produtor_id_estado(state)
            )

        if tool.name == "realizar_triagem_completa_pedido":
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
                if (
                    "resultado_triagem" in state
                    and state["resultado_triagem"] is not None
                ):
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
            texto,
            mascarar_contato=False,
            mascarar_endereco=False,
            mascarar_agencia_isolada=True,
        )
        if sanitizado != texto:
            part.text = sanitizado
            alterado = True

    return llm_response if alterado else None

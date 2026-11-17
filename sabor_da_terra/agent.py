
"""Definição do agente coordenador da Cooperativa Sabor da Terra (Google ADK)."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from sabor_da_terra.callbacks import (
    injetar_contexto_temporal,
    processar_retorno_tool,
    sanitizar_resposta_modelo,
    validar_acesso_tool,
)

from sabor_da_terra.config import SABOR_MODEL

from sabor_da_terra.prompts import (
    COORDINATOR_DESCRIPTION,
    COORDINATOR_INSTRUCTION,
)

from sabor_da_terra.rag import LISTA_TOOLS_RAG

from sabor_da_terra.tools import (
    LISTA_TOOLS_DADOS,
    LISTA_TOOLS_TRIAGEM,
)


# ==========================================================
# FERRAMENTAS DISPONÍVEIS
# Mantém a organização modular do projeto original.
# ==========================================================

LISTA_TODAS_TOOLS = [
    *LISTA_TOOLS_TRIAGEM,
    *LISTA_TOOLS_DADOS,
    *LISTA_TOOLS_RAG,
]


# ==========================================================
# CONFIGURAÇÃO DO AGENTE PRINCIPAL
# ==========================================================

root_agent = LlmAgent(
    name="sabor_da_terra",
    model=SABOR_MODEL,

    description=COORDINATOR_DESCRIPTION,
    instruction=COORDINATOR_INSTRUCTION,

    tools=LISTA_TODAS_TOOLS,

    # Injeta data atual e aplica guardrail de entrada LGPD.
    before_model_callback=injetar_contexto_temporal,

    # Valida RBAC e isolamento de produtor antes de executar ferramentas.
    before_tool_callback=validar_acesso_tool,

    # Processa, filtra por perfil e sanitiza os retornos das ferramentas.
    after_tool_callback=processar_retorno_tool,

    # Sanitiza a resposta final do modelo.
    after_model_callback=sanitizar_resposta_modelo,

    # Configuração de geração.
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
    ),
)

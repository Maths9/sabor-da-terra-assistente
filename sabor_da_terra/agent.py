"""Definição do agente coordenador da Cooperativa Sabor da Terra (Google ADK)."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from sabor_da_terra.callbacks import (
    injetar_contexto_temporal,
    processar_retorno_tool,
    sanitizar_resposta_modelo,
)
from sabor_da_terra.config import SABOR_MODEL
from sabor_da_terra.prompts import COORDINATOR_DESCRIPTION, COORDINATOR_INSTRUCTION
from sabor_da_terra.rag import LISTA_TOOLS_RAG
from sabor_da_terra.tools import LISTA_TOOLS_DADOS, LISTA_TOOLS_TRIAGEM

LISTA_TODAS_TOOLS = [
    *LISTA_TOOLS_TRIAGEM,
    *LISTA_TOOLS_DADOS,
    *LISTA_TOOLS_RAG,
]

root_agent = LlmAgent(
    name="sabor_da_terra",
    model=SABOR_MODEL,
    description=COORDINATOR_DESCRIPTION,
    instruction=COORDINATOR_INSTRUCTION,
    tools=LISTA_TODAS_TOOLS,
    before_model_callback=injetar_contexto_temporal,
    after_tool_callback=processar_retorno_tool,
    after_model_callback=sanitizar_resposta_modelo,
)

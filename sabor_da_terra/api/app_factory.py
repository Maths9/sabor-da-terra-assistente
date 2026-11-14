"""Fábrica da aplicação FastAPI unificando rotas do ADK e rotas /api."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from sabor_da_terra.api.adk_runtime import criar_servidor_adk
from sabor_da_terra.api.rotas_chat import criar_router_chat
from sabor_da_terra.api.rotas_operacional import criar_router_operacional


def criar_app(
    *,
    session_service_uri: Optional[str] = None,
    artifact_service_uri: Optional[str] = None,
    memory_service_uri: Optional[str] = None,
    allow_origins: Optional[list[str]] = None,
    use_web_ui: Optional[bool] = None,
) -> FastAPI:
    """Constrói a instância FastAPI compartilhando o Runner e o session_service do ADK."""
    adk_server, origins, web_assets_dir, web = criar_servidor_adk(
        session_service_uri=session_service_uri,
        artifact_service_uri=artifact_service_uri,
        memory_service_uri=memory_service_uri,
        allow_origins=allow_origins,
        use_web_ui=use_web_ui,
    )

    app = adk_server.get_fast_api_app(
        allow_origins=origins,
        web_assets_dir=web_assets_dir,
        with_ui=web,
    )
    app.state.adk_server = adk_server

    app.include_router(criar_router_operacional())
    app.include_router(criar_router_chat(adk_server))

    return app


app = criar_app()

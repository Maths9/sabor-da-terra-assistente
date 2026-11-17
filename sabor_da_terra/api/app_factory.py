"""Fábrica da aplicação FastAPI unificando rotas protegidas /api e runtime ADK."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from sabor_da_terra.api.adk_runtime import criar_servidor_adk
from sabor_da_terra.api.rotas_auth import criar_router_auth
from sabor_da_terra.api.rotas_chat import criar_router_chat
from sabor_da_terra.api.rotas_operacional import criar_router_operacional
from sabor_da_terra.config import PROJECT_ROOT

_PREFIXOS_ADK_RESTRITOS = (
    "/apps/",
    "/run",
    "/agent-identity",
)


def _desabilitar_rotas_nativas_abertas(app: FastAPI) -> None:
    """Remove rotas nativas de execução/sessão do ADK para evitar bypass da autenticação /api/*."""
    app.router.routes = [
        rota
        for rota in app.router.routes
        if not str(getattr(rota, "path", "") or "").startswith(_PREFIXOS_ADK_RESTRITOS)
    ]


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

    if not web:
        _desabilitar_rotas_nativas_abertas(app)

    app.include_router(criar_router_auth())
    app.include_router(criar_router_operacional())
    app.include_router(criar_router_chat(adk_server))

    adk_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _lifespan(fastapi_app: FastAPI):
        async with adk_lifespan(fastapi_app) as state:
            try:
                yield state
            finally:
                aclose = getattr(adk_server.session_service, "aclose", None)
                if callable(aclose):
                    await aclose()

    app.router.lifespan_context = _lifespan

    if not web:
        frontend_dist = Path(
            os.environ.get("SABOR_FRONTEND_DIST_DIR", str(PROJECT_ROOT / "frontend" / "dist"))
        ).resolve()
        if (frontend_dist / "index.html").is_file():
            app.mount(
                "/",
                StaticFiles(directory=str(frontend_dist), html=True),
                name="frontend",
            )

    return app


app = criar_app()

"""Rotas de configuração e emissão de token de sessão por perfil."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from sabor_da_terra.api.auth import (
    IdentidadeSessao,
    emitir_token_sessao,
    normalizar_perfil,
    requer_codigo_acesso,
    verificar_codigo_acesso,
)
from sabor_da_terra.api.helpers import listar_produtores_publicos
from sabor_da_terra.api.schemas import (
    AuthConfigResponse,
    AuthSessaoRequest,
    AuthSessaoResponse,
)


def criar_router_auth() -> APIRouter:
    """Cria rotas de entrada demonstrativa com token HMAC assinado."""
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.get("/config", response_model=AuthConfigResponse)
    async def api_auth_config() -> AuthConfigResponse:
        return AuthConfigResponse(
            requer_codigo=requer_codigo_acesso(),
            perfis_disponiveis=["operador", "produtor"],
        )

    @router.post("/sessao", response_model=AuthSessaoResponse)
    async def api_criar_sessao_acesso(req: AuthSessaoRequest) -> AuthSessaoResponse:
        perfil = normalizar_perfil(req.perfil)
        produtor_id: str | None = None

        if perfil == "produtor":
            pid = str(req.produtor_id or "").strip().upper()
            if not re.match(r"^P\d{3}$", pid):
                raise HTTPException(
                    status_code=400,
                    detail="Informe um produtor_id válido (ex.: P001) para acessar o portal do produtor.",
                )
            produtores = {p["id"].upper() for p in listar_produtores_publicos()}
            if pid not in produtores:
                raise HTTPException(
                    status_code=404,
                    detail=f"Produtor '{pid}' não encontrado no cadastro da cooperativa.",
                )
            produtor_id = pid
            user_id = f"produtor_{pid}"
        else:
            user_id = "operador"

        verificar_codigo_acesso(perfil, produtor_id, req.codigo_acesso)

        identidade = IdentidadeSessao(
            user_id=user_id,
            perfil=perfil,
            produtor_id=produtor_id,
        )
        token, ttl = emitir_token_sessao(identidade)
        return AuthSessaoResponse(
            access_token=token,
            user_id=identidade.user_id,
            perfil=identidade.perfil,
            produtor_id=identidade.produtor_id,
            expires_in=ttl,
        )

    return router

"""Rotas operacionais diretas para saúde, caixa de pedidos e painel do produtor."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from sabor_da_terra.api.adk_runtime import APP_NAME
from sabor_da_terra.api.auth import (
    IdentidadeSessao,
    exigir_identidade,
    exigir_operador,
)
from sabor_da_terra.api.helpers import (
    formatar_painel_produtor,
    listar_produtores_publicos,
)
from sabor_da_terra.api.schemas import PainelProdutorResponse
from sabor_da_terra.callbacks import _sanitizar_estrutura
from sabor_da_terra.tools import (
    consultar_pedidos_pendentes,
    obter_resumo_produtor,
)


def criar_router_operacional() -> APIRouter:
    """Cria endpoints REST determinísticos usados pela interface sem gastar LLM."""
    router = APIRouter(prefix="/api", tags=["operacional"])

    @router.get("/health")
    async def api_health() -> dict[str, str]:
        return {"status": "ok", "agent": APP_NAME}

    @router.get("/pedidos-pendentes")
    async def api_pedidos_pendentes(
        _identidade: IdentidadeSessao = Depends(exigir_operador),
    ) -> dict[str, Any]:
        return _sanitizar_estrutura(consultar_pedidos_pendentes())

    @router.get("/produtores")
    async def api_listar_produtores() -> dict[str, Any]:
        produtores = listar_produtores_publicos()
        return {"total": len(produtores), "produtores": produtores}

    @router.get("/produtores/{produtor_id}", response_model=PainelProdutorResponse)
    async def api_painel_produtor(
        produtor_id: str,
        identidade: IdentidadeSessao = Depends(exigir_identidade),
    ) -> PainelProdutorResponse:
        if identidade.perfil != "produtor":
            raise HTTPException(
                status_code=403,
                detail="Acesso negado: operadores não têm acesso às informações financeiras individuais dos produtores.",
            )
        pid = produtor_id.strip().upper()
        if pid != identidade.produtor_id:
            raise HTTPException(
                status_code=403,
                detail="Acesso negado: o produtor só pode consultar o próprio painel.",
            )

        res = obter_resumo_produtor(produtor_id=produtor_id)
        if res["status"] == "entrada_invalida":
            raise HTTPException(status_code=400, detail=res["mensagem"])
        if res["status"] == "nao_encontrado":
            raise HTTPException(status_code=404, detail=res["mensagem"])
        if res["status"] != "ok" or not res.get("dados"):
            raise HTTPException(
                status_code=500, detail=res.get("mensagem") or "Falha ao montar painel."
            )
        painel = _sanitizar_estrutura(formatar_painel_produtor(res["dados"]))
        return PainelProdutorResponse(**painel)

    return router

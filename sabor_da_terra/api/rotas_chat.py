"""Rotas de chat e gerenciamento de sessão integradas ao Runner ADK."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from google.adk.cli.api_server import ApiServer
from google.adk.utils.context_utils import Aclosing
from google.genai import types

from sabor_da_terra.api.adk_runtime import APP_NAME
from sabor_da_terra.api.helpers import extrair_fontes_dos_eventos, extrair_texto_final
from sabor_da_terra.api.schemas import ChatRequest, ChatResponse
from sabor_da_terra.callbacks import _sanitizar_estrutura


def criar_router_chat(adk_server: ApiServer) -> APIRouter:
    """Cria rotas de conversa multi-turno e inspeção/limpeza de sessão."""
    router = APIRouter(prefix="/api", tags=["chat"])

    @router.post("/chat", response_model=ChatResponse)
    async def api_chat(req: ChatRequest) -> ChatResponse:
        mensagem = req.message.strip()
        if not mensagem:
            raise HTTPException(
                status_code=422, detail="O campo 'message' não pode estar vazio."
            )

        user_id = req.user_id.strip() or "operador"
        session_id = (req.session_id or "").strip() or uuid4().hex

        sessao = await adk_server.session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if sessao is None:
            await adk_server.session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
            )

        state_delta: dict[str, Any] = {}
        if req.user_type:
            state_delta["perfil_usuario"] = req.user_type
        if req.produtor_id:
            pid = req.produtor_id.strip().upper()
            if re.match(r"^P\d{3}$", pid):
                state_delta["produtor_em_foco"] = pid

        runner = await adk_server.get_runner_async(APP_NAME)
        new_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=mensagem)],
        )

        run_kwargs: dict[str, Any] = {
            "user_id": user_id,
            "session_id": session_id,
            "new_message": new_message,
        }
        if state_delta:
            run_kwargs["state_delta"] = state_delta

        eventos: list[Any] = []
        async with Aclosing(runner.run_async(**run_kwargs)) as agen:
            async for event in agen:
                eventos.append(event)

        resposta = extrair_texto_final(eventos)
        fontes = extrair_fontes_dos_eventos(eventos)

        sessao_atual = await adk_server.session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        estado = (
            _sanitizar_estrutura(dict(sessao_atual.state or {}))
            if sessao_atual is not None
            else {}
        )

        produtor_foco = estado.get("produtor_em_foco")
        if isinstance(produtor_foco, dict):
            produtor_foco = produtor_foco.get("produtor_id")

        return ChatResponse(
            session_id=session_id,
            user_id=user_id,
            resposta=resposta,
            fontes=fontes,
            resultado_triagem=estado.get("resultado_triagem"),
            produtor_em_foco=produtor_foco if isinstance(produtor_foco, str) else None,
            ultimo_pedido=estado.get("ultimo_pedido"),
        )

    @router.get("/sessoes/{user_id}/{session_id}")
    async def api_obter_sessao(user_id: str, session_id: str) -> dict[str, Any]:
        sessao = await adk_server.session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if sessao is None:
            raise HTTPException(
                status_code=404,
                detail=f"Sessão '{session_id}' não encontrada para user_id='{user_id}'.",
            )
        estado_limpo = _sanitizar_estrutura(dict(sessao.state or {}))
        return {
            "app_name": APP_NAME,
            "user_id": user_id,
            "session_id": sessao.id,
            "state": estado_limpo,
            "total_eventos": len(sessao.events or []),
        }

    @router.delete("/sessoes/{user_id}/{session_id}")
    async def api_remover_sessao(user_id: str, session_id: str) -> dict[str, str]:
        await adk_server.session_service.delete_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        return {"status": "ok", "session_id": session_id}

    return router

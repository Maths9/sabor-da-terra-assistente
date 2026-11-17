"""Rotas de chat e gerenciamento de sessão integradas ao Runner ADK e protegidas por token."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from google.adk.cli.api_server import ApiServer
from google.adk.utils.context_utils import Aclosing
from google.genai import types

from sabor_da_terra.api.adk_runtime import APP_NAME
from sabor_da_terra.api.auth import (
    IdentidadeSessao,
    exigir_identidade,
    normalizar_perfil,
)
from sabor_da_terra.api.helpers import (
    extrair_fontes_dos_eventos,
    extrair_mensagens_dos_eventos,
    extrair_texto_final,
)
from sabor_da_terra.api.schemas import ChatRequest, ChatResponse
from sabor_da_terra.callbacks import _sanitizar_estrutura


def _validar_consistencia_requisicao(req: ChatRequest, identidade: IdentidadeSessao) -> None:
    if req.user_id and req.user_id.strip() and req.user_id.strip() != identidade.user_id:
        raise HTTPException(
            status_code=403,
            detail="user_id informado diverge da identidade autenticada.",
        )
    if req.user_type is not None:
        if normalizar_perfil(req.user_type) != identidade.perfil:
            raise HTTPException(
                status_code=403,
                detail="user_type informado diverge do perfil autenticado.",
            )
    if req.produtor_id and req.produtor_id.strip():
        pid_req = req.produtor_id.strip().upper()
        if identidade.perfil == "produtor" and pid_req != identidade.produtor_id:
            raise HTTPException(
                status_code=403,
                detail="produtor_id informado diverge do produtor autenticado.",
            )


def _validar_consistencia_sessao(
    state: dict[str, Any], identidade: IdentidadeSessao
) -> None:
    perfil_raw = str(state.get("perfil_usuario") or "").strip().lower()
    if perfil_raw:
        perfil_sessao = "operador" if perfil_raw in {"operador", "cooperado"} else perfil_raw
        if perfil_sessao != identidade.perfil:
            raise HTTPException(
                status_code=403,
                detail="Sessão pertence a outro perfil e não pode ser reutilizada.",
            )
    if identidade.perfil == "produtor":
        pid_sessao = str(state.get("produtor_em_foco") or "").strip().upper()
        if pid_sessao and pid_sessao != identidade.produtor_id:
            raise HTTPException(
                status_code=403,
                detail="Sessão pertence a outro produtor.",
            )


def criar_router_chat(adk_server: ApiServer) -> APIRouter:
    """Cria rotas autenticadas de conversa multi-turno e inspeção/limpeza de sessão."""
    router = APIRouter(prefix="/api", tags=["chat"])

    @router.post("/chat", response_model=ChatResponse)
    async def api_chat(
        req: ChatRequest,
        identidade: IdentidadeSessao = Depends(exigir_identidade),
    ) -> ChatResponse:
        mensagem = req.message.strip()
        if not mensagem:
            raise HTTPException(
                status_code=422, detail="O campo 'message' não pode estar vazio."
            )

        _validar_consistencia_requisicao(req, identidade)

        user_id = identidade.user_id
        session_id = (req.session_id or "").strip() or uuid4().hex

        sessao = await adk_server.session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )

        state_delta: dict[str, Any] = {}
        if sessao is None:
            estado_inicial: dict[str, Any] = {"perfil_usuario": identidade.perfil}
            if identidade.perfil == "produtor" and identidade.produtor_id:
                estado_inicial["produtor_em_foco"] = identidade.produtor_id
            elif identidade.perfil == "operador" and req.produtor_id:
                pid = req.produtor_id.strip().upper()
                if re.match(r"^P\d{3}$", pid):
                    estado_inicial["produtor_em_foco"] = pid

            await adk_server.session_service.create_session(
                app_name=APP_NAME,
                user_id=user_id,
                session_id=session_id,
                state=estado_inicial,
            )
        else:
            estado_existente = dict(sessao.state or {})
            _validar_consistencia_sessao(estado_existente, identidade)
            if not estado_existente.get("perfil_usuario"):
                state_delta["perfil_usuario"] = identidade.perfil
            if (
                identidade.perfil == "produtor"
                and identidade.produtor_id
                and not estado_existente.get("produtor_em_foco")
            ):
                state_delta["produtor_em_foco"] = identidade.produtor_id

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

    @router.get("/sessoes")
    async def api_listar_sessoes(
        identidade: IdentidadeSessao = Depends(exigir_identidade),
    ) -> dict[str, Any]:
        resp = await adk_server.session_service.list_sessions(
            app_name=APP_NAME,
            user_id=identidade.user_id,
        )
        sessoes_ordenadas = sorted(
            resp.sessions or [],
            key=lambda s: float(getattr(s, "last_update_time", 0.0) or 0.0),
            reverse=True,
        )
        itens = []
        for s in sessoes_ordenadas:
            estado = _sanitizar_estrutura(dict(s.state or {}))
            itens.append(
                {
                    "session_id": s.id,
                    "user_id": s.user_id,
                    "last_update_time": s.last_update_time,
                    "perfil_usuario": estado.get("perfil_usuario"),
                    "produtor_em_foco": estado.get("produtor_em_foco"),
                    "ultimo_pedido": estado.get("ultimo_pedido"),
                }
            )
        return {"user_id": identidade.user_id, "sessoes": itens}

    @router.get("/sessoes/{user_id}/{session_id}")
    async def api_obter_sessao(
        user_id: str,
        session_id: str,
        identidade: IdentidadeSessao = Depends(exigir_identidade),
    ) -> dict[str, Any]:
        if user_id != identidade.user_id:
            raise HTTPException(
                status_code=403,
                detail="Acesso negado: você só pode consultar suas próprias sessões.",
            )

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
        _validar_consistencia_sessao(estado_limpo, identidade)
        mensagens = extrair_mensagens_dos_eventos(sessao.events or [])

        return {
            "app_name": APP_NAME,
            "user_id": user_id,
            "session_id": sessao.id,
            "state": estado_limpo,
            "total_eventos": len(sessao.events or []),
            "last_update_time": sessao.last_update_time,
            "mensagens": mensagens,
        }

    @router.delete("/sessoes/{user_id}/{session_id}")
    async def api_remover_sessao(
        user_id: str,
        session_id: str,
        identidade: IdentidadeSessao = Depends(exigir_identidade),
    ) -> dict[str, str]:
        if user_id != identidade.user_id:
            raise HTTPException(
                status_code=403,
                detail="Acesso negado: você só pode remover suas próprias sessões.",
            )

        await adk_server.session_service.delete_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        return {"status": "ok", "session_id": session_id}

    return router

"""Testes unitários e de integração dos módulos do coordenador Sabor da Terra."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

from sabor_da_terra.agent import LISTA_TODAS_TOOLS, root_agent
from sabor_da_terra.api import APP_NAME, criar_app
from sabor_da_terra.callbacks import (
    injetar_contexto_temporal,
    processar_retorno_tool,
    sanitizar_resposta_modelo,
)
from sabor_da_terra.config import DADOS_DIR, RAG_STORE_DIR, obter_data_referencia
from sabor_da_terra.rag import consultar_documentos, preparar_chunks_corpus
from sabor_da_terra.seguranca import norm_texto, sanitizar_pii_texto
from sabor_da_terra.tools import (
    ItemNotificacaoInput,
    ItemPedidoInput,
    PedidoNotificacaoInput,
    consultar_lotes,
    consultar_pedidos_pendentes,
    obter_resumo_produtor,
    realizar_triagem_completa_pedido,
    redigir_notificacao,
    verificar_compliance_e_credito,
)


def _dummy_context(state: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(state=state if state is not None else {})


# ---------------------------------------------------------------------------
# Segurança LGPD e normalização
# ---------------------------------------------------------------------------


def test_sanitizacao_lgpd_idempotente_e_completa() -> None:
    texto = (
        "Produtor: Maria\n"
        "CPF: 831.452.674-90 | RG: 12.345.678 SSP/PE\n"
        "Banco do Brasil - Ag. 0437 - C/C 28901-3\n"
        "Chave PIX: 831.452.674-90\n"
        "Telefone: (87) 99812-3456 | E-mail: maria@email.com\n"
        "Endereço: Sítio Boa Vista, s/n\n"
    )
    limpo = sanitizar_pii_texto(texto, mascarar_contato=True, mascarar_endereco=True)
    assert "831.452.674-90" not in limpo
    assert "12.345.678" not in limpo
    assert "28901-3" not in limpo
    assert "99812-3456" not in limpo
    assert "maria@email.com" not in limpo
    assert "Sítio Boa Vista" not in limpo
    assert "OMITIDO] OMITIDO]" not in limpo
    assert sanitizar_pii_texto(limpo, mascarar_contato=True, mascarar_endereco=True) == limpo


def test_norm_texto() -> None:
    assert norm_texto("  Café Orgânico / Maçã  ") == "cafe organico / maca"


# ---------------------------------------------------------------------------
# Tools determinísticas de dados (T10)
# ---------------------------------------------------------------------------


def test_obter_resumo_produtor_p001_setembro_e_agencia_segura() -> None:
    ctx = _dummy_context()
    res = obter_resumo_produtor(
        "p001",
        inicio="2026-09-01",
        fim="2026-09-30",
        data_referencia="2026-11-14",
        agencia_informada="0437",
        tool_context=ctx,
    )
    assert res["status"] == "ok"
    dados = res["dados"]
    assert dados["produtor_id"] == "P001"
    assert dados["vendas_total"] == "1090.00"
    assert dados["total_pago"] == "1090.00"
    assert dados["total_pendente"] == "0.00"
    assert dados["agencia_informada_confere"] is True
    assert ctx.state["produtor_em_foco"] == "P001"

    serial = str(dados)
    assert "831.452.674-90" not in serial
    assert "28901-3" not in serial
    assert "maria.graca@email.com" not in serial

    res_err = obter_resumo_produtor("P001", agencia_informada="9999")
    assert res_err["dados"]["agencia_informada_confere"] is False
    assert obter_resumo_produtor("INVALIDO")["status"] == "entrada_invalida"
    assert obter_resumo_produtor("P999")["status"] == "nao_encontrado"


def test_verificar_compliance_e_credito_superbom_e_produtores() -> None:
    res = verificar_compliance_e_credito(
        comprador="SuperBom",
        tipo_cliente="supermercado",
        produtos=["queijo coalho", "frango caipira", "alface"],
        data_referencia="2026-11-14",
    )
    assert res["status"] == "ok"
    dados = res["dados"]
    cred = dados["comprador_credito"]
    assert cred["contrato_encontrado"] is None
    assert float(cred["total_vencido"]) == 6020.00
    codigos = {a["codigo"] for a in dados["alertas"]}
    assert "COMPRADOR_INADIMPLENTE" in codigos
    assert "BLOQUEIO_SIE_PRODUTOR" in codigos
    assert "CERTIFICACAO_PROXIMA_VENCIMENTO" in codigos


def test_consultar_lotes_exato_inexistente_e_alerta_temperatura() -> None:
    res_inex = consultar_lotes(lote_id="2024-089")
    assert res_inex["status"] == "nao_encontrado"
    assert "LOT-2026-0089" in res_inex["mensagem"]

    res_exato = consultar_lotes(lote_id="LOT-2026-0089")
    assert res_exato["status"] == "ok"
    assert res_exato["dados"]["lotes"][0]["lote_id"] == "LOT-2026-0089"

    res_folhosa = consultar_lotes(produto="alface")
    assert res_folhosa["status"] == "ok"
    assert any("2–5°C" in a for a in res_folhosa["dados"]["alertas_rastreabilidade"])


def test_consultar_pedidos_pendentes() -> None:
    res_lista = consultar_pedidos_pendentes()
    assert res_lista["status"] == "ok"
    assert res_lista["dados"]["total"] == 15

    ctx = _dummy_context()
    res_item = consultar_pedidos_pendentes("PED-2026-004", tool_context=ctx)
    assert res_item["status"] == "ok"
    assert res_item["dados"]["id"] == "PED-2026-004"
    assert ctx.state["ultimo_pedido"]["id_pedido"] == "PED-2026-004"


def test_redigir_notificacao_somente_rascunho_e_bloqueios() -> None:
    pedido = PedidoNotificacaoInput(
        id_pedido="PED-TESTE-01",
        comprador="Restaurante Raízes",
        tipo_cliente="restaurante",
        itens=[ItemNotificacaoInput(produto="goiaba", quantidade=30, unidade="kg", exige_organico=True)],
    )
    res_ok = redigir_notificacao("P001", pedido=pedido, data_referencia="2026-11-14")
    assert res_ok["status"] == "ok"
    assert res_ok["dados"]["somente_rascunho"] is True
    assert res_ok["dados"]["envio_automatico"] is False
    assert "goiaba" in res_ok["dados"]["texto"].lower()

    # Usa estado resultado_triagem da sessão sem reenviar pedido
    ctx = _dummy_context(
        {
            "resultado_triagem": {
                "id_pedido": "PED-SESSAO",
                "remetente_identificado": "PNAE Garanhuns",
                "tipo_cliente": "pnae",
                "itens": [
                    {
                        "produto_catalogo": "goiaba",
                        "quantidade": 20,
                        "unidade": "kg",
                        "exige_organico": True,
                        "produtores_aptos": ["P001 - Maria"],
                        "produtores_bloqueados": [],
                    }
                ],
            }
        }
    )
    res_sessao = redigir_notificacao("P001", tool_context=ctx, data_referencia="2026-11-14")
    assert res_sessao["status"] == "ok"
    assert ctx.state["produtor_em_foco"] == "P001"

    # Bloqueios determinísticos
    assert redigir_notificacao("P015", pedido=pedido)["status"] == "dados_insuficientes"
    pedido_queijo = PedidoNotificacaoInput(
        comprador="Supermercado Bom Preço",
        tipo_cliente="supermercado",
        itens=[ItemNotificacaoInput(produto="frango caipira", quantidade=20, unidade="kg")],
    )
    assert redigir_notificacao("P017", pedido=pedido_queijo)["status"] == "dados_insuficientes"


# ---------------------------------------------------------------------------
# RAG vetorial (chunking, sanitização, validações e filtro negativo)
# ---------------------------------------------------------------------------


def test_rag_chunks_sem_pii_e_validacao_parametros() -> None:
    chunks, hashes = preparar_chunks_corpus(DADOS_DIR)
    assert len(hashes) == 20
    assert len(chunks) >= 50

    for c in chunks:
        txt = c["texto"]
        assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", txt)
        assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
        assert not re.search(r"(?i)(?:ag\.|ag[êe]ncia|c/c)\s*[:\-]?\s*\d{2,}", txt)
        assert "OMITIDO] OMITIDO]" not in txt

    p008_chunks = [c for c in chunks if c["metadata"]["produtor_id"] == "P008"]
    assert p008_chunks and p008_chunks[0]["metadata"]["validade_ate"] == 20260930

    assert consultar_documentos("")["status"] == "entrada_invalida"
    assert consultar_documentos("teste", tipo_documento="invalido")["status"] == "entrada_invalida"
    assert consultar_documentos("teste", produtor_id="XYZ")["status"] == "entrada_invalida"
    assert consultar_documentos("teste", apenas_vigentes_em="31/10/2026")["status"] == "entrada_invalida"


def test_rag_consulta_com_indice_real_e_embedding_mockado(monkeypatch) -> None:
    assert (RAG_STORE_DIR / "manifest.json").exists()

    class _FakeCollection:
        def count(self) -> int:
            return 1

        def query(self, **kwargs):
            return {
                "documents": [["[Documento: inspecao_adagro_2026.txt] NC-001 Laticinio Serra Dourada"]],
                "metadatas": [[{
                    "documento_id": "inspecao_adagro_2026",
                    "nome": "inspecao_adagro_2026.txt",
                    "localizacao": "Seção: NÃO CONFORMIDADES",
                    "referencia": "certificacoes/inspecao_adagro_2026.txt",
                }]],
                "distances": [[0.20]],
            }

    monkeypatch.setattr("sabor_da_terra.rag._get_chroma_collection", lambda *a, **k: _FakeCollection())
    monkeypatch.setattr("sabor_da_terra.rag._gerar_embeddings", lambda *a, **k: [[0.1] * 10])

    ctx = _dummy_context()
    res = consultar_documentos("Qual a NC-001 da ADAGRO?", tool_context=ctx)
    assert res["status"] == "ok"
    assert res["dados"]["fontes"][0]["documento_id"] == "inspecao_adagro_2026"
    assert len(ctx.state["ultimas_fontes_rag"]) == 1

    # Filtro anti falso-positivo para código de lote inexistente
    res_falso = consultar_documentos("Qual o status do lote 2024-089?")
    assert res_falso["status"] == "nao_encontrado"


# ---------------------------------------------------------------------------
# Callbacks, Agente ADK e Endpoint FastAPI
# ---------------------------------------------------------------------------


def test_triagem_v2_envelope_e_campos_pendentes() -> None:
    ctx = _dummy_context()
    res_amb = realizar_triagem_completa_pedido(
        remetente_identificado="Restaurante Sabor Regional",
        tipo_cliente="restaurante",
        tipo_demanda="pedido_compra",
        itens=[ItemPedidoInput(produto_mencionado="goiaba", quantidade=None, unidade=None)],
        mes_entrega=None,
        data_referencia="2026-11-14",
        tool_context=ctx,
    )
    assert res_amb["status"] == "ok"
    assert res_amb["dados"]["status_viabilidade"] == "requer_esclarecimento"
    assert res_amb["dados"]["itens"][0]["status_item"] == "ambiguo"
    assert len(res_amb["dados"]["itens"][0]["opcoes_catalogo"]) > 1
    assert res_amb["dados"]["campos_pendentes"] == ["prazo_entrega"]

    res = realizar_triagem_completa_pedido(
        remetente_identificado="Restaurante Sabor Regional",
        tipo_cliente="restaurante",
        tipo_demanda="pedido_compra",
        itens=[ItemPedidoInput(produto_mencionado="queijo coalho", quantidade=None, unidade=None)],
        mes_entrega=None,
        data_referencia="2026-11-14",
        tool_context=ctx,
    )
    assert res["status"] == "ok"
    dados = res["dados"]
    assert dados["status_viabilidade"] == "requer_esclarecimento"
    assert dados["campos_pendentes"] == ["quantidade", "prazo_entrega"]
    assert ctx.state["resultado_triagem"]["status_viabilidade"] == "requer_esclarecimento"
    assert "cpf" not in str(dados).lower()


def test_callbacks_temporal_tool_state_e_lgpd() -> None:
    req = LlmRequest()
    ctx = SimpleNamespace(
        state={
            "perfil_usuario": "produtor",
            "produtor_em_foco": "P001",
            "ultimo_pedido": {"comprador": "PNAE", "status_viabilidade": "viavel"},
            "ultimas_fontes_rag": [{"nome": "contrato_pnae_garanhuns.txt"}],
        }
    )
    assert injetar_contexto_temporal(ctx, req) is None
    sys_inst = str(req.config.system_instruction)
    assert obter_data_referencia() in sys_inst
    assert "produtor_em_foco=P001" in sys_inst
    assert "PORTAL DO PRODUTOR" in sys_inst

    tool_ctx = _dummy_context({"resultado_triagem": {"cpf": "123", "status_viabilidade": "viavel"}})
    fake_tool = SimpleNamespace(name="realizar_triagem_completa_pedido")
    ret = processar_retorno_tool(
        fake_tool,
        {"itens": [{"produto_mencionado": "goiaba", "quantidade": 10}]},
        tool_ctx,
        {
            "status": "ok",
            "dados": {
                "id_pedido": "PED-1",
                "remetente_identificado": "PNAE",
                "tipo_cliente": "pnae",
                "data_referencia": "2026-11-14",
                "mes_entrega": None,
                "campos_pendentes": ["prazo_entrega"],
                "status_viabilidade": "requer_esclarecimento",
                "valor_total_estimado": 65.0,
                "cpf": "123.456.789-00",
            },
            "mensagem": None,
        },
    )
    assert "cpf" not in ret["dados"]
    assert tool_ctx.state["ultimo_pedido"]["comprador"] == "PNAE"
    assert tool_ctx.state["ultimo_pedido"]["campos_pendentes"] == ["prazo_entrega"]
    assert "cpf" not in tool_ctx.state["resultado_triagem"]

    resp_suja = LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="Seu CPF é 831.452.674-90 e PIX 831.452.674-90.")],
        )
    )
    resp_limpa = sanitizar_resposta_modelo(ctx, resp_suja)
    assert resp_limpa is not None
    assert "831.452.674-90" not in resp_limpa.content.parts[0].text

    resp_ok = LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="Pedido viável com Maria P001.")],
        )
    )
    assert sanitizar_resposta_modelo(ctx, resp_ok) is None


def test_agent_e_declarations_adk() -> None:
    assert root_agent.name == APP_NAME
    assert len(LISTA_TODAS_TOOLS) == 9
    for fn in LISTA_TODAS_TOOLS:
        decl = FunctionTool(fn)._get_declaration()
        assert decl is not None and decl.name == fn.__name__


def test_api_endpoints_e_chat_sessao() -> None:
    app = criar_app(session_service_uri="memory://", use_web_ui=False)
    adk_server = app.state.adk_server

    class _FakeRunner:
        async def run_async(
            self,
            *,
            user_id: str,
            session_id: str,
            new_message: types.Content,
            state_delta: dict[str, Any] | None = None,
        ):
            sessao = await adk_server.session_service.get_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
            if state_delta:
                ev_delta = Event(
                    author="user",
                    actions=EventActions(state_delta=state_delta),
                )
                await adk_server.session_service.append_event(sessao, ev_delta)
                sessao = await adk_server.session_service.get_session(
                    app_name=APP_NAME, user_id=user_id, session_id=session_id
                )
            ev_fontes = Event(
                author=APP_NAME,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name="consultar_documentos",
                                response={
                                    "status": "ok",
                                    "dados": {
                                        "texto": "...",
                                        "fontes": [
                                            {
                                                "documento_id": "contrato_pnae_garanhuns",
                                                "nome": "contrato_pnae_garanhuns.txt",
                                                "localizacao": "Seção: CONDIÇÕES OBRIGATÓRIAS",
                                                "referencia": "contratos/contrato_pnae_garanhuns.txt",
                                            }
                                        ],
                                    },
                                },
                            )
                        )
                    ],
                ),
                actions=EventActions(
                    state_delta={
                        "produtor_em_foco": "P001",
                        "resultado_triagem": {"status_viabilidade": "viavel"},
                        "ultimo_pedido": {"comprador": "PNAE Garanhuns"},
                    }
                ),
            )
            await adk_server.session_service.append_event(sessao, ev_fontes)
            yield ev_fontes
            ev_final = Event(
                author=APP_NAME,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text="Resposta verificada. CPF 831.452.674-90 nunca aparece.")],
                ),
            )
            await adk_server.session_service.append_event(sessao, ev_final)
            yield ev_final

    async def _fake_get_runner(app_name: str):
        assert app_name == APP_NAME
        return _FakeRunner()

    adk_server.get_runner_async = _fake_get_runner

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok", "agent": APP_NAME}
    assert client.get("/list-apps").json() == [APP_NAME]
    assert client.get("/api/pedidos-pendentes").json()["dados"]["total"] == 15
    assert client.get("/api/sessoes/operador/nao-existe").status_code == 404
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422

    res = client.post(
        "/api/chat",
        headers={"Origin": "http://localhost:5173"},
        json={"message": "Verifique PNAE", "session_id": "sess-int-1", "user_id": "operador"},
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
    body = res.json()
    assert body["session_id"] == "sess-int-1"
    assert "831.452.674-90" not in body["resposta"]
    assert "[CPF OMITIDO]" in body["resposta"]
    assert len(body["fontes"]) == 1
    assert body["fontes"][0]["documento_id"] == "contrato_pnae_garanhuns"
    assert body["produtor_em_foco"] == "P001"
    assert body["resultado_triagem"]["status_viabilidade"] == "viavel"

    res_sess = client.get("/api/sessoes/operador/sess-int-1")
    assert res_sess.status_code == 200
    assert res_sess.json()["state"]["produtor_em_foco"] == "P001"

    # Endpoints reais de produtores e isolamento LGPD no painel do produtor
    res_prods = client.get("/api/produtores")
    assert res_prods.status_code == 200
    lista_prods = res_prods.json()
    assert lista_prods["total"] >= 18
    assert any(p["id"] == "P001" for p in lista_prods["produtores"])
    assert "831.452" not in res_prods.text

    res_p001 = client.get("/api/produtores/P001")
    assert res_p001.status_code == 200
    p001 = res_p001.json()
    assert p001["codigo"] == "P001"
    assert p001["municipio"] == "Garanhuns"
    assert p001["situacaoCadastral"] == "Ativo"
    assert "cpf" not in res_p001.text.lower()
    assert "831.452" not in res_p001.text
    assert "28901-3" not in res_p001.text

    assert client.get("/api/produtores/P999").status_code == 404
    assert client.get("/api/produtores/BAD").status_code == 400

    # Sessão em perfil produtor com limpeza via DELETE /api/sessoes
    res_chat_prod = client.post(
        "/api/chat",
        json={
            "message": "Como está meu cadastro?",
            "session_id": "sess-prod-1",
            "user_id": "produtor_P001",
            "user_type": "produtor",
            "produtor_id": "P001",
        },
    )
    assert res_chat_prod.status_code == 200
    res_sess_prod = client.get("/api/sessoes/produtor_P001/sess-prod-1")
    assert res_sess_prod.status_code == 200
    assert res_sess_prod.json()["state"]["perfil_usuario"] == "produtor"
    assert res_sess_prod.json()["state"]["produtor_em_foco"] == "P001"

    res_del = client.delete("/api/sessoes/produtor_P001/sess-prod-1")
    assert res_del.status_code == 200
    assert res_del.json() == {"status": "ok", "session_id": "sess-prod-1"}
    assert client.get("/api/sessoes/produtor_P001/sess-prod-1").status_code == 404

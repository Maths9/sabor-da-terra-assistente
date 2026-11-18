"""Testes unitários e de integração dos módulos do coordenador Sabor da Terra."""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest
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
    MENSAGEM_RECUSA_PII,
    injetar_contexto_temporal,
    processar_retorno_tool,
    sanitizar_resposta_modelo,
    validar_acesso_tool,
)
from sabor_da_terra.config import DADOS_DIR, RAG_STORE_DIR, obter_data_referencia
from sabor_da_terra.rag import consultar_documentos, preparar_chunks_corpus
from sabor_da_terra.seguranca import (
    detectar_dados_sensiveis,
    norm_texto,
    sanitizar_pii_texto,
)
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


@pytest.fixture(autouse=True)
def _isolar_ambiente_banco_nos_testes(monkeypatch) -> None:
    """Garante que os testes automatizados não dependam nem alterem o PostgreSQL configurado no .env local."""
    from sabor_da_terra.database.connection import limpar_cache_conexoes

    for var in (
        "DATABASE_URL",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SABOR_DATA_BACKEND", "postgres")
    limpar_cache_conexoes()


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


def test_deteccao_e_mascaramento_pii_avancado() -> None:
    # CPFs sintéticos do dataset real, RG sem capturar texto posterior e nascimento ISO/BR
    amostra = (
        "CPF: 034.567.891-23 | Data de nascimento: 1975-03-12 | "
        "RG 1234567 SSP-PE de Maria | Nubank ag 0001 cc 7843291-0"
    )
    assert set(detectar_dados_sensiveis(amostra)) == {
        "cpf",
        "documento_pessoal",
        "conta_bancaria",
    }
    limpo = sanitizar_pii_texto(amostra)
    assert "034.567.891-23" not in limpo
    assert "1975-03-12" not in limpo
    assert "1234567" not in limpo
    assert "de Maria" in limpo
    assert "7843291-0" not in limpo
    assert detectar_dados_sensiveis(limpo) == []

    # PIX copia-e-cola, chave inline sem dois-pontos e hex32 apenas com contexto PIX
    pix_txt = (
        "Minha chave PIX é 831.452.674-90 | Copia e cola: "
        "00020126580014br.gov.bcb.pix0136123e4567-e89b-12d3-a456-426614174000"
    )
    assert "pix" in detectar_dados_sensiveis(pix_txt)
    pix_limpo = sanitizar_pii_texto(pix_txt)
    assert "831.452.674-90" not in pix_limpo
    assert "000201" not in pix_limpo

    # UUID hex de sessão sem contexto PIX não deve gerar falso positivo
    sess_txt = "Sessão ativa: a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert detectar_dados_sensiveis(sess_txt) == []

    # PED-2026-012: agência isolada preservada na entrada/pedido, mascarada na saída
    ped12 = consultar_pedidos_pendentes("PED-2026-012")["dados"]
    assert "0437" in ped12["mensagem_original"]
    assert "0437" not in sanitizar_pii_texto(
        "Sua conta é agência 0437.", mascarar_agencia_isolada=True
    )


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


def test_rag_consulta_com_indice_real_e_embedding_mockado(monkeypatch, tmp_path) -> None:
    import shutil
    import chromadb

    assert (RAG_STORE_DIR / "index_info.json").exists()
    idx_copia = tmp_path / "index_copia"
    shutil.copytree(RAG_STORE_DIR, idx_copia)
    monkeypatch.setattr("sabor_da_terra.rag.RAG_STORE_DIR", idx_copia)

    col_real = chromadb.PersistentClient(path=str(idx_copia)).get_collection(
        "sabor_da_terra_docs"
    )
    assert col_real.count() == 33
    amostra = col_real.get(include=["embeddings", "metadatas"])

    def _vetor_do_arquivo(subpath: str) -> list[float]:
        for emb, meta in zip(amostra["embeddings"], amostra["metadatas"]):
            if meta.get("arquivo") == subpath:
                return [float(x) for x in emb]
        raise AssertionError(f"Arquivo não encontrado no índice: {subpath}")

    vetor_ativo = {"atual": _vetor_do_arquivo("certificacoes/inspecao_adagro_2026.txt")}
    chamadas_embed: list[dict[str, Any]] = []

    def _fake_embed(textos: list[str], **kwargs: Any) -> list[list[float]]:
        chamadas_embed.append(dict(kwargs))
        return [vetor_ativo["atual"] for _ in textos]

    monkeypatch.setattr("sabor_da_terra.rag._gerar_embeddings", _fake_embed)

    ctx_op = _dummy_context({"perfil_usuario": "operador"})
    res = consultar_documentos(
        "Qual a NC-001 da ADAGRO?",
        tipo_documento="inspecao",
        tool_context=ctx_op,
    )
    assert res["status"] == "ok"
    assert chamadas_embed[-1]["modelo"] == "gemini-embedding-001"
    assert chamadas_embed[-1]["dim"] == 768
    assert chamadas_embed[-1]["normalizar"] is True
    assert res["dados"]["fontes"][0]["documento_id"] == "inspecao_adagro_2026"
    assert res["dados"]["fontes"][0]["referencia"] == "certificacoes/inspecao_adagro_2026.txt"
    assert len(ctx_op.state["ultimas_fontes_rag"]) >= 1
    assert all(
        f["documento_id"] == "inspecao_adagro_2026"
        for f in ctx_op.state["ultimas_fontes_rag"]
    )

    # Operador consegue localizar menção a P017 na inspeção ADAGRO via campo `produtores`
    res_p017 = consultar_documentos(
        "Restrições sanitárias de P017",
        produtor_id="P017",
        tool_context=ctx_op,
    )
    assert res_p017["status"] == "ok"
    assert res_p017["dados"]["fontes"][0]["documento_id"] == "inspecao_adagro_2026"

    # Certificado vencido de P008 (2026-09-30) é filtrado por apenas_vigentes_em="2026-10-30"
    vetor_ativo["atual"] = _vetor_do_arquivo(
        "certificacoes/cert_organica_josefa_souza_P008.txt"
    )
    assert (
        consultar_documentos(
            "Certificado orgânico de P008",
            tipo_documento="certificacao",
            produtor_id="P008",
            apenas_vigentes_em="2026-10-30",
            tool_context=ctx_op,
        )["status"]
        == "nao_encontrado"
    )

    # Laudo sanitário sem validade definida (validade_ate=0) continua válido com apenas_vigentes_em
    vetor_ativo["atual"] = _vetor_do_arquivo(
        "certificacoes/laudo_sanitario_apiario_jose_P002.txt"
    )
    res_laudo = consultar_documentos(
        "Laudo sanitário P002",
        tipo_documento="laudo",
        apenas_vigentes_em="2026-10-30",
        tool_context=ctx_op,
    )
    assert res_laudo["status"] == "ok"
    assert res_laudo["dados"]["fontes"][0]["documento_id"] == "laudo_sanitario_apiario_jose_P002"

    # Isolamento estrito no Portal do Produtor: P001 só vê seus próprios certificados/laudos (nunca ADAGRO ou P002)
    vetor_ativo["atual"] = _vetor_do_arquivo("certificacoes/inspecao_adagro_2026.txt")
    ctx_p001 = _dummy_context({"perfil_usuario": "produtor", "produtor_em_foco": "P001"})
    res_p001_adagro = consultar_documentos(
        "Inspeção ADAGRO",
        produtor_id="P001",
        tool_context=ctx_p001,
    )
    if res_p001_adagro["status"] == "ok":
        assert all(
            f["documento_id"] == "cert_organica_maria_silva_P001"
            for f in res_p001_adagro["dados"]["fontes"]
        )
    vetor_ativo["atual"] = _vetor_do_arquivo(
        "certificacoes/cert_organica_maria_silva_P001.txt"
    )
    res_p001 = consultar_documentos(
        "Meu certificado orgânico",
        produtor_id="P001",
        tool_context=ctx_p001,
    )
    assert res_p001["status"] == "ok"
    assert (
        res_p001["dados"]["fontes"][0]["documento_id"]
        == "cert_organica_maria_silva_P001"
    )

    # Filtro anti falso-positivo para código de lote inexistente
    vetor_ativo["atual"] = _vetor_do_arquivo("certificacoes/inspecao_adagro_2026.txt")
    res_falso = consultar_documentos("Qual o status do lote 2024-089?", tool_context=ctx_op)
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
    assert root_agent.before_tool_callback is validar_acesso_tool
    assert len(LISTA_TODAS_TOOLS) == 9
    for fn in LISTA_TODAS_TOOLS:
        decl = FunctionTool(fn)._get_declaration()
        assert decl is not None and decl.name == fn.__name__


def test_guardrail_entrada_before_model() -> None:
    ctx = _dummy_context({"perfil_usuario": "cooperado"})

    # 1) Envio puro de dados sensíveis é barrado deterministicamente sem chamar LLM
    req_pii = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text="Meu CPF é 831.452.674-90 e minha chave PIX é 831.452.674-90"
                    )
                ],
            )
        ]
    )
    resp_bloqueio = injetar_contexto_temporal(ctx, req_pii)
    assert resp_bloqueio is not None
    assert resp_bloqueio.content.parts[0].text == MENSAGEM_RECUSA_PII
    assert "831.452.674-90" not in req_pii.contents[0].parts[0].text

    # 2) Pedido comercial com CPF na assinatura mascara o CPF, mas permite triagem
    req_pedido_com_cpf = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text="Pedido PNAE: 200kg banana prata e 100kg goiaba. Att Dr. Fernando CPF: 034.567.891-23"
                    )
                ],
            )
        ]
    )
    assert injetar_contexto_temporal(ctx, req_pedido_com_cpf) is None
    assert "034.567.891-23" not in req_pedido_com_cpf.contents[0].parts[0].text
    assert "[CPF OMITIDO]" in req_pedido_com_cpf.contents[0].parts[0].text
    assert "GUARDRAIL LGPD NA ENTRADA" in str(req_pedido_com_cpf.config.system_instruction)

    # 3) Conferência de agência isolada (PED-2026-012) não é bloqueada
    req_agencia = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text="Minha conta é no BB agência 0437. Quanto vendi esse mês?"
                    )
                ],
            )
        ]
    )
    assert injetar_contexto_temporal(ctx, req_agencia) is None
    assert "0437" in req_agencia.contents[0].parts[0].text


def test_rbac_before_e_after_tool_portal_produtor() -> None:
    # Fail-closed se não houver estado ou perfil autorizado
    assert (
        validar_acesso_tool(
            SimpleNamespace(name="consultar_pedidos_pendentes"), {}, _dummy_context({})
        )["status"]
        == "acesso_negado"
    )
    assert (
        validar_acesso_tool(
            SimpleNamespace(name="consultar_pedidos_pendentes"),
            {},
            _dummy_context({"perfil_usuario": "visitante"}),
        )["status"]
        == "acesso_negado"
    )

    for perfil_op in ("operador", "cooperado"):
        ctx_op = _dummy_context({"perfil_usuario": perfil_op})
        assert (
            validar_acesso_tool(
                SimpleNamespace(name="consultar_pedidos_pendentes"), {}, ctx_op
            )
            is None
        )

    # Fail-closed se perfil produtor estiver sem produtor_em_foco válido
    ctx_sem_id = _dummy_context({"perfil_usuario": "produtor"})
    neg_sem_id = validar_acesso_tool(
        SimpleNamespace(name="obter_resumo_produtor"),
        {"produtor_id": "P001"},
        ctx_sem_id,
    )
    assert neg_sem_id is not None and neg_sem_id["status"] == "acesso_negado"

    ctx_p001 = _dummy_context({"perfil_usuario": "produtor", "produtor_em_foco": "P001"})

    # Ferramentas restritas à equipe administrativa
    for nome_restrita in (
        "consultar_pedidos_pendentes",
        "redigir_notificacao",
        "consultar_produtores_ou_organicos",
        "realizar_triagem_completa_pedido",
        "verificar_compliance_e_credito",
    ):
        res_neg = validar_acesso_tool(SimpleNamespace(name=nome_restrita), {}, ctx_p001)
        assert res_neg is not None and res_neg["status"] == "acesso_negado"

    # Isolamento entre produtores em resumo e lotes
    assert (
        validar_acesso_tool(
            SimpleNamespace(name="obter_resumo_produtor"),
            {"produtor_id": "P002"},
            ctx_p001,
        )["status"]
        == "acesso_negado"
    )
    assert (
        validar_acesso_tool(
            SimpleNamespace(name="obter_resumo_produtor"),
            {"produtor_id": "P001"},
            ctx_p001,
        )
        is None
    )
    assert (
        validar_acesso_tool(
            SimpleNamespace(name="consultar_lotes"),
            {"lote_id": "LOT-2026-0089"},
            ctx_p001,
        )["status"]
        == "acesso_negado"
    )
    assert (
        validar_acesso_tool(
            SimpleNamespace(name="consultar_lotes"),
            {"produtor_id": "P001", "lote_id": "LOT-2026-0089"},
            ctx_p001,
        )
        is None
    )

    # Filtro pós-tool impede acesso a lote de P003 mesmo se passar produtor_id=P001 junto com lote_id
    ret_lote_p003 = processar_retorno_tool(
        SimpleNamespace(name="consultar_lotes"),
        {"produtor_id": "P001", "lote_id": "LOT-2026-0089"},
        ctx_p001,
        consultar_lotes(lote_id="LOT-2026-0089"),
    )
    assert ret_lote_p003["status"] == "acesso_negado"

    ret_lote_inex = processar_retorno_tool(
        SimpleNamespace(name="consultar_lotes"),
        {"produtor_id": "P001", "lote_id": "2024-089"},
        ctx_p001,
        consultar_lotes(lote_id="2024-089"),
    )
    assert "P003" not in ret_lote_inex["mensagem"]

    # Escopo de documentos RAG no Portal do Produtor
    assert (
        validar_acesso_tool(
            SimpleNamespace(name="consultar_documentos"),
            {"pergunta": "armazenamento goiaba", "tipo_documento": "ficha_tecnica"},
            ctx_p001,
        )
        is None
    )
    assert (
        validar_acesso_tool(
            SimpleNamespace(name="consultar_documentos"),
            {"pergunta": "meu certificado", "produtor_id": "P001"},
            ctx_p001,
        )
        is None
    )
    for args_neg in (
        {"pergunta": "certificado P002", "produtor_id": "P002"},
        {"pergunta": "clausulas pnae", "tipo_documento": "contrato"},
        {"pergunta": "nao conformidades", "tipo_documento": "inspecao"},
        {"pergunta": "certificados gerais"},
    ):
        assert (
            validar_acesso_tool(
                SimpleNamespace(name="consultar_documentos"), args_neg, ctx_p001
            )["status"]
            == "acesso_negado"
        )

    # Anonimização de terceiros em avaliar_item_catalogo para produtor
    ret_cat = processar_retorno_tool(
        SimpleNamespace(name="avaliar_item_catalogo"),
        {"produto": "mel silvestre", "exige_organico": True},
        ctx_p001,
        {
            "status": "ok",
            "dados": {
                "produtores_aptos": ["P002 - José", "P001 - Maria"],
                "produtores_bloqueados": ["P008 - Josefa [CERTIFICAÇÃO VENCIDA]"],
                "alertas": [
                    {"codigo": "CERTIFICACAO_VENCIDA", "produtor_relacionado": "P008"},
                    {"codigo": "QUANTIDADE_NAO_INFORMADA", "produtor_relacionado": None},
                ],
            },
        },
    )
    dados_cat = ret_cat["dados"]
    assert any("P001" in item for item in dados_cat["produtores_aptos"])
    assert not any("P002" in item for item in dados_cat["produtores_aptos"])
    assert not any("P008" in item for item in dados_cat["produtores_bloqueados"])
    assert len(dados_cat["alertas"]) == 1
    assert dados_cat["alertas"][0]["codigo"] == "QUANTIDADE_NAO_INFORMADA"


def test_api_endpoints_e_chat_sessao(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SABOR_AUTH_SECRET", "segredo-teste-integracao-32-bytes")
    db_path = tmp_path / "sessoes_teste.db"
    sqlite_uri = f"sqlite:///{db_path}"

    def _instalar_fake_runner(app_instance):
        adk_srv = app_instance.state.adk_server

        class _FakeRunner:
            async def run_async(
                self,
                *,
                user_id: str,
                session_id: str,
                new_message: types.Content,
                state_delta: dict[str, Any] | None = None,
            ):
                sessao = await adk_srv.session_service.get_session(
                    app_name=APP_NAME, user_id=user_id, session_id=session_id
                )
                ev_user = Event(author="user", content=new_message)
                await adk_srv.session_service.append_event(sessao, ev_user)
                if state_delta:
                    ev_delta = Event(
                        author="user",
                        actions=EventActions(state_delta=state_delta),
                    )
                    await adk_srv.session_service.append_event(sessao, ev_delta)
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
                await adk_srv.session_service.append_event(sessao, ev_fontes)
                yield ev_fontes
                ev_final = Event(
                    author=APP_NAME,
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(
                                text="Resposta verificada. CPF 831.452.674-90 nunca aparece."
                            )
                        ],
                    ),
                )
                await adk_srv.session_service.append_event(sessao, ev_final)
                yield ev_final

        async def _fake_get_runner(app_name: str):
            assert app_name == APP_NAME
            return _FakeRunner()

        adk_srv.get_runner_async = _fake_get_runner

    app = criar_app(session_service_uri=sqlite_uri, use_web_ui=False)
    _instalar_fake_runner(app)

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok", "agent": APP_NAME}
    assert client.get("/list-apps").json() == [APP_NAME]
    assert client.get("/api/auth/config").json() == {
        "requer_codigo": False,
        "perfis_disponiveis": ["operador", "produtor"],
    }

    # Rotas nativas do ADK ficam bloqueadas quando use_web_ui=False
    assert client.post("/run", json={}).status_code in {404, 405}
    assert client.get("/apps/sabor_da_terra/users/operador/sessions").status_code == 404

    # Endpoints sensíveis exigem Bearer Token
    assert client.get("/api/pedidos-pendentes").status_code == 401
    assert client.get("/api/produtores/P001").status_code == 401
    assert client.post("/api/chat", json={"message": "Olá"}).status_code == 401
    assert client.get("/api/sessoes").status_code == 401

    # Login como Operador (aceitando alias legado 'cooperado' e canônico 'operador')
    auth_op = client.post("/api/auth/sessao", json={"perfil": "operador"})
    assert auth_op.status_code == 200
    token_op = auth_op.json()["access_token"]
    hdr_op = {"Authorization": f"Bearer {token_op}"}

    assert client.get("/api/pedidos-pendentes", headers=hdr_op).json()["dados"]["total"] == 15
    assert client.get("/api/sessoes/operador/nao-existe", headers=hdr_op).status_code == 404
    assert client.post("/api/chat", headers=hdr_op, json={"message": "   "}).status_code == 422

    res = client.post(
        "/api/chat",
        headers={**hdr_op, "Origin": "http://localhost:5173"},
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

    # Persistência após "novo deploy" (nova instância FastAPI apontando para o mesmo banco)
    app_redeploy = criar_app(session_service_uri=sqlite_uri, use_web_ui=False)
    client_redeploy = TestClient(app_redeploy)
    res_lista = client_redeploy.get("/api/sessoes", headers=hdr_op)
    assert res_lista.status_code == 200
    assert any(s["session_id"] == "sess-int-1" for s in res_lista.json()["sessoes"])

    res_sess = client_redeploy.get("/api/sessoes/operador/sess-int-1", headers=hdr_op)
    assert res_sess.status_code == 200
    sess_body = res_sess.json()
    assert sess_body["state"]["produtor_em_foco"] == "P001"
    assert len(sess_body["mensagens"]) == 2
    assert sess_body["mensagens"][0]["role"] == "user"
    assert sess_body["mensagens"][1]["role"] == "assistant"
    assert "831.452.674-90" not in sess_body["mensagens"][1]["content"]
    assert len(sess_body["mensagens"][1]["fontes"]) == 1

    # Endpoints públicos de listagem de produtores (sem PII/financeiro)
    res_prods = client.get("/api/produtores")
    assert res_prods.status_code == 200
    lista_prods = res_prods.json()
    assert lista_prods["total"] >= 18
    assert any(p["id"] == "P001" for p in lista_prods["produtores"])
    assert "831.452" not in res_prods.text

    # Autenticação como Produtor P001 e isolamento estrito entre produtores/operador
    auth_p001 = client.post(
        "/api/auth/sessao", json={"perfil": "produtor", "produtor_id": "P001"}
    )
    assert auth_p001.status_code == 200
    token_p001 = auth_p001.json()["access_token"]
    hdr_p001 = {"Authorization": f"Bearer {token_p001}"}

    res_p001 = client.get("/api/produtores/P001", headers=hdr_p001)
    assert res_p001.status_code == 200
    p001 = res_p001.json()
    assert p001["codigo"] == "P001"
    assert p001["municipio"] == "Garanhuns"
    assert p001["situacaoCadastral"] == "Ativo"
    assert "cpf" not in res_p001.text.lower()
    assert "831.452" not in res_p001.text
    assert "28901-3" not in res_p001.text

    # Produtor P001 NÃO acessa painel de P002, pedidos pendentes nem sessões de terceiros
    assert client.get("/api/produtores/P002", headers=hdr_p001).status_code == 403
    assert client.get("/api/pedidos-pendentes", headers=hdr_p001).status_code == 403
    assert client.get("/api/sessoes/operador/sess-int-1", headers=hdr_p001).status_code == 403
    assert client.delete("/api/sessoes/operador/sess-int-1", headers=hdr_p001).status_code == 403

    # Operador pode consultar painel de P001/P999 (404 para inexistente, 400 para inválido)
    assert client.get("/api/produtores/P001", headers=hdr_op).status_code == 200
    assert client.get("/api/produtores/P999", headers=hdr_op).status_code == 404
    assert client.get("/api/produtores/BAD", headers=hdr_op).status_code == 400

    # Tentativa de spoofing no POST /api/chat é barrada com 403
    assert (
        client.post(
            "/api/chat",
            headers=hdr_p001,
            json={"message": "Listar pedidos", "user_type": "operador"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/chat",
            headers=hdr_p001,
            json={"message": "Resumo P002", "produtor_id": "P002"},
        ).status_code
        == 403
    )

    # Sessão em perfil produtor com limpeza via DELETE /api/sessoes
    res_chat_prod = client.post(
        "/api/chat",
        headers=hdr_p001,
        json={
            "message": "Como está meu cadastro?",
            "session_id": "sess-prod-1",
            "user_id": "produtor_P001",
            "user_type": "produtor",
            "produtor_id": "P001",
        },
    )
    assert res_chat_prod.status_code == 200
    res_sess_prod = client.get("/api/sessoes/produtor_P001/sess-prod-1", headers=hdr_p001)
    assert res_sess_prod.status_code == 200
    assert res_sess_prod.json()["state"]["perfil_usuario"] == "produtor"
    assert res_sess_prod.json()["state"]["produtor_em_foco"] == "P001"

    res_del = client.delete("/api/sessoes/produtor_P001/sess-prod-1", headers=hdr_p001)
    assert res_del.status_code == 200
    assert res_del.json() == {"status": "ok", "session_id": "sess-prod-1"}
    assert client.get("/api/sessoes/produtor_P001/sess-prod-1", headers=hdr_p001).status_code == 404

    # Código de acesso opcional quando configurado em ambiente
    monkeypatch.setenv("SABOR_CODIGO_OPERADOR", "op-2026")
    monkeypatch.setenv("SABOR_CODIGO_PRODUTOR", "prod-2026")
    assert client.get("/api/auth/config").json()["requer_codigo"] is True
    assert client.post("/api/auth/sessao", json={"perfil": "operador"}).status_code == 401
    assert (
        client.post(
            "/api/auth/sessao",
            json={"perfil": "operador", "codigo_acesso": "op-2026"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/sessao",
            json={"perfil": "produtor", "produtor_id": "P001", "codigo_acesso": "errado"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/sessao",
            json={"perfil": "produtor", "produtor_id": "P001", "codigo_acesso": "prod-2026"},
        ).status_code
        == 200
    )

    # Validação de token em GET /api/auth/sessao
    assert client.get("/api/auth/sessao").status_code == 401
    assert client.get("/api/auth/sessao", headers={"Authorization": "Bearer invalido"}).status_code == 401
    res_check_op = client.get("/api/auth/sessao", headers=hdr_op)
    assert res_check_op.status_code == 200
    assert res_check_op.json() == {"user_id": "operador", "perfil": "operador", "produtor_id": None}
    res_check_p1 = client.get("/api/auth/sessao", headers=hdr_p001)
    assert res_check_p1.status_code == 200
    assert res_check_p1.json() == {
        "user_id": "produtor_P001",
        "perfil": "produtor",
        "produtor_id": "P001",
    }


def test_api_com_runner_adk_real_e_callbacks(monkeypatch, tmp_path) -> None:
    import shutil
    import chromadb
    from google.adk.models.base_llm import BaseLlm
    import sabor_da_terra.rag as rag_mod

    monkeypatch.setenv("SABOR_AUTH_SECRET", "segredo-runner-real-integracao-32-bytes")

    idx_copia = tmp_path / "index_runner_real"
    shutil.copytree(RAG_STORE_DIR, idx_copia)
    monkeypatch.setattr(rag_mod, "RAG_STORE_DIR", idx_copia)

    col = chromadb.PersistentClient(path=str(idx_copia)).get_collection("sabor_da_terra_docs")
    amostra = col.get(include=["embeddings", "metadatas"])
    adagro_emb = [
        float(x)
        for x in amostra["embeddings"][
            next(i for i, m in enumerate(amostra["metadatas"]) if "inspecao_adagro_2026" in m.get("arquivo", ""))
        ]
    ]
    monkeypatch.setattr(rag_mod, "_gerar_embeddings", lambda textos, **kw: [adagro_emb for _ in textos])

    class _StubRunnerLlm(BaseLlm):
        model: str = "stub-runner-llm"

        async def generate_content_async(self, llm_request, stream=False):
            user_txt = " ".join(
                p.text
                for c in llm_request.contents
                if c.role == "user"
                for p in (c.parts or [])
                if p.text
            )
            has_tool_resp = any(
                p.function_response for c in llm_request.contents for p in (c.parts or [])
            )
            if not has_tool_resp and "adagro" in user_txt.lower():
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="consultar_documentos",
                                args={"pergunta": "ADAGRO NC-001", "tipo_documento": "inspecao"},
                            )
                        ],
                    )
                )
            elif not has_tool_resp and "p002" in user_txt.lower():
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_function_call(
                                name="obter_resumo_produtor",
                                args={"produtor_id": "P002"},
                            )
                        ],
                    )
                )
            elif has_tool_resp:
                tool_resp = [
                    p.function_response.response
                    for c in llm_request.contents
                    for p in (c.parts or [])
                    if p.function_response
                ][-1]
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part.from_text(
                                text=f"Status={tool_resp.get('status')} | {tool_resp.get('mensagem') or 'ok'}"
                            )
                        ],
                    )
                )
            else:
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text="Atendimento concluído.")],
                    )
                )

    monkeypatch.setattr(root_agent, "model", _StubRunnerLlm())
    db_path = tmp_path / "sessoes_runner_real.db"
    app = criar_app(session_service_uri=f"sqlite:///{db_path}", use_web_ui=False)
    client = TestClient(app)

    tok_op = client.post("/api/auth/sessao", json={"perfil": "operador"}).json()["access_token"]
    hdr_op = {"Authorization": f"Bearer {tok_op}"}

    # 1) RAG real com extração de fontes pelo Runner ADK
    r_rag = client.post(
        "/api/chat",
        headers=hdr_op,
        json={"message": "Consulte a inspeção da ADAGRO", "session_id": "real-rag-1"},
    )
    assert r_rag.status_code == 200
    body_rag = r_rag.json()
    assert body_rag["resposta"].startswith("Status=ok")
    assert len(body_rag["fontes"]) >= 1
    assert body_rag["fontes"][0]["documento_id"] == "inspecao_adagro_2026"

    # 2) Bloqueio determinístico de PII no before_model_callback sem acionar o LLM
    r_pii = client.post(
        "/api/chat",
        headers=hdr_op,
        json={"message": "Meu CPF é 831.452.674-90", "session_id": "real-rag-1"},
    )
    assert r_pii.status_code == 200
    assert r_pii.json()["resposta"] == MENSAGEM_RECUSA_PII

    # 3) Histórico persistido sanitiza entrada do usuário e preserva fontes
    r_hist = client.get("/api/sessoes/operador/real-rag-1", headers=hdr_op)
    assert r_hist.status_code == 200
    msgs = r_hist.json()["mensagens"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert "831.452.674-90" not in msgs[2]["content"]
    assert len(msgs[1]["fontes"]) >= 1

    # 4) RBAC fail-closed no Portal do Produtor via Runner real: P001 não consulta P002
    tok_p1 = client.post(
        "/api/auth/sessao", json={"perfil": "produtor", "produtor_id": "P001"}
    ).json()["access_token"]
    hdr_p1 = {"Authorization": f"Bearer {tok_p1}"}
    r_rbac = client.post(
        "/api/chat",
        headers=hdr_p1,
        json={"message": "Veja os dados de P002", "session_id": "real-prod-1"},
    )
    assert r_rbac.status_code == 200
    assert "Status=acesso_negado" in r_rbac.json()["resposta"]

    # 5) Delete idempotente mesmo se sessão ainda não existir no banco SQLite
    assert client.delete("/api/sessoes/operador/sessao-nao-criada", headers=hdr_op).status_code == 200


def test_firestore_session_service_roundtrip_emulado() -> None:
    import asyncio
    import json as _json
    import httpx
    from sabor_da_terra.api.session_firestore import FirestoreSessionService

    store: dict[str, dict[str, Any]] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        prefix = "/v1/projects/proj-teste/databases/(default)/documents"
        assert path.startswith(prefix)
        rel = path[len(prefix) :]

        if request.method == "POST" and rel == "/adk_sessions":
            doc_id = request.url.params["documentId"]
            key = f"adk_sessions/{doc_id}"
            if key in store:
                return httpx.Response(409, json={"error": {"status": "ALREADY_EXISTS"}})
            body = _json.loads(request.content.decode("utf-8"))
            doc = {"name": f"{prefix[4:]}/{key}", "fields": body["fields"]}
            store[key] = doc
            return httpx.Response(200, json=doc)

        if request.method == "GET" and rel.endswith("/events"):
            sess_key = rel[1 : -len("/events")]
            docs = [
                v for k, v in sorted(store.items()) if k.startswith(f"{sess_key}/events/")
            ]
            return httpx.Response(200, json={"documents": docs})

        if request.method == "GET" and rel.startswith("/adk_sessions/"):
            key = rel[1:]
            if key not in store:
                return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})
            return httpx.Response(200, json=store[key])

        if request.method == "POST" and rel == ":runQuery":
            body = _json.loads(request.content.decode("utf-8"))
            ff = body["structuredQuery"]["where"]["fieldFilter"]
            campo = ff["field"]["fieldPath"]
            valor = ff["value"]["stringValue"]
            matches = [
                {"document": doc}
                for k, doc in store.items()
                if "/events/" not in k
                and doc["fields"].get(campo, {}).get("stringValue") == valor
            ]
            return httpx.Response(200, json=matches or [{"readTime": "now"}])

        if request.method == "POST" and rel == ":commit":
            body = _json.loads(request.content.decode("utf-8"))
            for w in body.get("writes", []):
                if "delete" in w:
                    key = w["delete"].split("/documents/", 1)[1]
                    store.pop(key, None)
                elif "update" in w:
                    upd = w["update"]
                    key = upd["name"].split("/documents/", 1)[1]
                    if w.get("currentDocument", {}).get("exists") and key not in store:
                        return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})
                    if key in store:
                        store[key]["fields"].update(upd["fields"])
                    else:
                        store[key] = {"name": upd["name"], "fields": upd["fields"]}
            return httpx.Response(200, json={"writeResults": []})

        return httpx.Response(500, json={"error": f"Unhandled {request.method} {rel}"})

    async def _run() -> None:
        transport = httpx.MockTransport(_handler)
        client_a = httpx.AsyncClient(transport=transport)
        svc_a = FirestoreSessionService(
            project_id="proj-teste",
            emulator_host="127.0.0.1:8085",
            http_client=client_a,
        )
        sess = await svc_a.create_session(
            app_name=APP_NAME,
            user_id="produtor_P001",
            session_id="sess-fs-1",
            state={"perfil_usuario": "produtor", "produtor_em_foco": "P001"},
        )
        ev1 = Event(
            author="user",
            content=types.Content(role="user", parts=[types.Part.from_text(text="Olá")]),
        )
        ev2 = Event(
            author=APP_NAME,
            content=types.Content(role="model", parts=[types.Part.from_text(text="Oi P001!")]),
            actions=EventActions(state_delta={"ultimo_pedido": {"comprador": "PNAE"}}),
        )
        await svc_a.append_event(sess, ev1)
        await svc_a.append_event(sess, ev2)
        await client_a.aclose()

        # Nova instância simulando container após redeploy
        client_b = httpx.AsyncClient(transport=transport)
        svc_b = FirestoreSessionService(
            project_id="proj-teste",
            emulator_host="127.0.0.1:8085",
            http_client=client_b,
        )
        rec = await svc_b.get_session(
            app_name=APP_NAME, user_id="produtor_P001", session_id="sess-fs-1"
        )
        assert rec is not None
        assert rec.state["perfil_usuario"] == "produtor"
        assert rec.state["produtor_em_foco"] == "P001"
        assert rec.state["ultimo_pedido"]["comprador"] == "PNAE"
        assert [e.author for e in rec.events] == ["user", APP_NAME]

        lista = await svc_b.list_sessions(app_name=APP_NAME, user_id="produtor_P001")
        assert [s.id for s in lista.sessions] == ["sess-fs-1"]

        await svc_b.delete_session(
            app_name=APP_NAME, user_id="produtor_P001", session_id="sess-fs-1"
        )
        assert (
            await svc_b.get_session(
                app_name=APP_NAME, user_id="produtor_P001", session_id="sess-fs-1"
            )
            is None
        )
        await client_b.aclose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Banco de Dados Operacional (SQLAlchemy 2.0, Criptografia LGPD e Paridade)
# ---------------------------------------------------------------------------


def test_database_url_tcp_e_unix_socket_cloud_run() -> None:
    from sabor_da_terra.database.connection import construir_database_url

    url_tcp = construir_database_url(
        database_url="",
        db_host="127.0.0.1",
        db_port=5433,
        db_name="sabor_terra",
        db_user="sabor_app",
        db_password="segredo",
    )
    assert url_tcp.drivername == "postgresql+psycopg"
    assert url_tcp.host == "127.0.0.1"
    assert url_tcp.port == 5433
    assert url_tcp.database == "sabor_terra"

    url_socket = construir_database_url(
        database_url="",
        db_host="/cloudsql/meu-projeto:us-central1:sabor-postgres-demo",
        db_port=5432,
        db_name="sabor_terra",
        db_user="sabor_app",
        db_password="segredo",
    )
    assert url_socket.drivername == "postgresql+psycopg"
    assert url_socket.host is None
    assert url_socket.query.get("host") == "/cloudsql/meu-projeto:us-central1:sabor-postgres-demo"


def test_importacao_idempotente_criptografia_lgpd_e_paridade_tools(
    monkeypatch, tmp_path
) -> None:
    from sqlalchemy import select
    from scripts.importar_dados import importar_todos_os_dados
    from sabor_da_terra.database import (
        PREFIXO_CIFRADO,
        ProdutorModel,
        RepositorioOperacional,
        cifrar_valor_sensivel,
        decifrar_valor_sensivel,
        get_engine,
        limpar_cache_conexoes,
        session_scope,
    )
    from sabor_da_terra.tools import (
        avaliar_item_catalogo,
        consultar_produtores_ou_organicos,
    )

    monkeypatch.setenv("SABOR_DB_ENCRYPTION_KEY", "chave-teste-criptografia-lgpd-2026")
    cifrado = cifrar_valor_sensivel("831.452.674-90")
    assert cifrado is not None and cifrado.startswith(PREFIXO_CIFRADO)
    assert "831.452.674-90" not in cifrado
    # Idempotência: cifrar valor já cifrado não duplica
    assert cifrar_valor_sensivel(cifrado) == cifrado
    assert decifrar_valor_sensivel(cifrado) == "831.452.674-90"

    db_file = tmp_path / "sabor_operacional_teste.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SABOR_DATA_BACKEND", "postgres")
    limpar_cache_conexoes()

    eng = get_engine(db_url)
    res1 = importar_todos_os_dados(dados_dir=DADOS_DIR, engine=eng, criar_tabelas=True)
    # Segunda execução deve ser 100% idempotente (UPSERT sem duplicar linhas)
    res2 = importar_todos_os_dados(dados_dir=DADOS_DIR, engine=eng, criar_tabelas=False)
    assert res1["contagens"] == {
        "produtores": 18,
        "sazonalidade": 50,
        "precos": 53,
        "pedidos": 15,
        "lotes": 20,
        "transacoes_financeiras": 30,
    }
    assert res2["contagens"] == res1["contagens"]
    assert res2["totais_financeiros"] == {
        "vendas_total": "24634.00",
        "total_pago": "11254.00",
        "total_pendente": "13380.00",
    }

    # Verifica no banco que CPF, PIX, conta e nascimento estão cifrados e não em texto aberto
    with session_scope(eng) as session:
        p001 = session.scalar(select(ProdutorModel).where(ProdutorModel.id == "P001"))
        assert p001 is not None
        assert p001.cpf_cifrado.startswith(PREFIXO_CIFRADO)
        assert "831.452.674-90" not in p001.cpf_cifrado
        assert decifrar_valor_sensivel(p001.cpf_cifrado) == "831.452.674-90"
        assert p001.chave_pix_cifrada is not None and p001.chave_pix_cifrada.startswith(PREFIXO_CIFRADO)
        assert "831.452.674-90" not in p001.chave_pix_cifrada
        assert p001.conta_corrente_cifrada is not None and p001.conta_corrente_cifrada.startswith(PREFIXO_CIFRADO)
        assert "28901-3" not in p001.conta_corrente_cifrada

    repo_db = RepositorioOperacional(engine=eng)
    assert repo_db.verificar_agencia_produtor("P001", "0437") is True
    assert repo_db.verificar_agencia_produtor("P001", "9999") is False

    # Compara paridade exata entre SABOR_DATA_BACKEND=postgres e SABOR_DATA_BACKEND=csv nas tools
    def _coletar_snapshot_tools() -> dict[str, Any]:
        return {
            "resumo_p001": obter_resumo_produtor(
                "P001",
                inicio="2026-09-01",
                fim="2026-10-31",
                data_referencia="2026-11-14",
                agencia_informada="0437",
            ),
            "compliance_superbom": verificar_compliance_e_credito(
                comprador="SuperBom",
                tipo_cliente="supermercado",
                produtos=["queijo coalho", "frango caipira", "alface"],
                data_referencia="2026-11-14",
            ),
            "lote_exato": consultar_lotes(lote_id="LOT-2026-0089"),
            "lote_inex": consultar_lotes(lote_id="2024-089"),
            "pedidos_lista": consultar_pedidos_pendentes(),
            "pedido_004": consultar_pedidos_pendentes("PED-2026-004"),
            "item_mel_org": avaliar_item_catalogo(
                "mel silvestre", 20, "kg", exige_organico=True, data_referencia="2026-10-28"
            ),
            "organicos": consultar_produtores_ou_organicos(
                apenas_listar_organicos_vigentes=True, data_referencia="2026-10-28"
            ),
        }

    snap_postgres = _coletar_snapshot_tools()
    monkeypatch.setenv("SABOR_DATA_BACKEND", "csv")
    snap_csv = _coletar_snapshot_tools()
    assert snap_postgres == snap_csv

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SABOR_DATA_BACKEND", "postgres")
    limpar_cache_conexoes()


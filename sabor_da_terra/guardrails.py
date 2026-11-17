"""
Guardrail determinístico de segurança e LGPD — Cooperativa Sabor da Terra.

Alinhado 100% às assinaturas, campos e ferramentas reais do projeto:
  - `sabor_da_terra/seguranca.py` (CAMPOS_SENSIVEIS_LGPD, CAMPOS_CONTATO_PESSOAL, MASCARA)
  - `sabor_da_terra/callbacks.py` (`injetar_contexto_temporal`, `processar_retorno_tool`,
    `sanitizar_resposta_modelo`, `validar_acesso_tool`)
  - `sabor_da_terra/tools/dados_operacionais.py` (`consultar_pagamentos_produtor`,
    `obter_resumo_produtor`, `listar_produtores`, `consultar_lote`, `consultar_pedidos_pendentes`)
  - `sabor_da_terra/agent.py` (Google ADK LlmAgent)
"""
from __future__ import annotations

import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# --- Constantes alinhadas ao sabor_da_terra/seguranca.py ---------------------
MASCARA = "[DADO SENSÍVEL REMOVIDO]"

MENSAGEM_RECUSA_PII = (
    "Com licença! Por segurança, eu não posso receber nem usar CPF, RG, "
    "data de nascimento, chave PIX ou dados de conta bancária por aqui. "
    "Peço que não envie esse tipo de informação pelo chat e trate assuntos "
    "cadastrais ou de pagamento diretamente com o setor financeiro da "
    "cooperativa pelos canais oficiais. Se quiser, pode reenviar sua mensagem "
    "sem esses dados que eu continuo ajudando, tá certo?"
)

# Campos reais existentes nos CSVs e documentos RAG da cooperativa
CAMPOS_SENSIVEIS_LGPD = {
    "cpf",
    "produtor_cpf",
    "data_nascimento",
    "chave_pix",
    "chave_pix_deposito",
    "banco",
    "agencia",
    "conta_corrente",
}
CAMPOS_CONTATO_PESSOAL = {"telefone", "email", "endereco"}
_CHAVES_BLOQUEADAS = CAMPOS_SENSIVEIS_LGPD | CAMPOS_CONTATO_PESSOAL

# Ferramentas reais de sabor_da_terra/tools/dados_operacionais.py
_TOOLS_EXCLUSIVAS_COOPERADO = {
    "consultar_pedidos_pendentes",
    "redigir_notificacao",
}

_TOOLS_INDIVIDUAIS_PRODUTOR = {
    "consultar_pagamentos_produtor",
    "obter_resumo_produtor",
}

# --- Expressões Regulares Determinísticas ------------------------------------
_CPF_RE = re.compile(r"(?<!\d)(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})[-\s]?(\d{2})(?!\d)")
_CNPJ_RE = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
_RG_ROTULADO_RE = re.compile(
    r"(?i)\b(rg\s*[:\-]?\s*)[\d.\-xX]{5,15}(?:\s+[A-Za-z/]{2,12})?"
)
_DATA_NASC_RE = re.compile(
    r"(?i)\b(?:nascid[oa]\s+em|data\s+de\s+nascimento|nascimento)\s*[:\-]?\s*\d{2}/\d{2}/\d{4}\b"
)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)  # chave PIX aleatória (EVP com hífens)
_UUID_SEM_HIFEN_RE = re.compile(r"\b[0-9a-f]{32}\b", re.I)  # chave PIX EVP sem hífens
_PIX_COPIA_COLA_RE = re.compile(r"\b000201[0-9a-zA-Z]{20,}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)")
_PIX_RE = re.compile(r"\bpix\b", re.I)
_BANCO_RE = re.compile(
    r"(?:ag[eê]ncia|\bag\b\.?|\bconta(?:\s+corrente|\s+poupan[cç]a)?\b|\bc/c\b)"
    r"\D{0,15}\d{3,}",
    re.I,
)
_RE_LINHA_PIX = re.compile(r"(?im)^(\s*chave\s*pix[^\n:]*:\s*).*$")


# --- Validação e Mascaramento ------------------------------------------------
def _cpf_valido(digitos: str) -> bool:
    """Valida os dígitos verificadores do CPF (evita falso positivo em lotes)."""
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11 % 10
        if dv != int(digitos[tamanho]):
            return False
    return True


def _cpfs_validos(texto: str):
    """Itera apenas sobre ocorrências de CPF matematicamente válidas."""
    for m in _CPF_RE.finditer(texto):
        if _cpf_valido("".join(m.groups())):
            yield m


def detectar_dados_sensiveis(texto: str) -> list[str]:
    """Retorna os tipos de dado sensível encontrados no texto."""
    if not texto:
        return []
    achados: list[str] = []

    if any(_cpfs_validos(texto)):
        achados.append("cpf")

    if _RG_ROTULADO_RE.search(texto) or _DATA_NASC_RE.search(texto):
        achados.append("documento_pessoal")

    # Telefone e CNPJ isolados são permitidos em pedidos comerciais.
    # Só disparam como chave PIX se houver EVP (com/sem hífen), copia-e-cola ou contexto PIX.
    if (
        _UUID_RE.search(texto)
        or _UUID_SEM_HIFEN_RE.search(texto)
        or _PIX_COPIA_COLA_RE.search(texto)
        or (
            _PIX_RE.search(texto)
            and (
                _PHONE_RE.search(texto)
                or _EMAIL_RE.search(texto)
                or _CNPJ_RE.search(texto)
                or any(_cpfs_validos(texto))
            )
        )
    ):
        achados.append("pix")

    if _BANCO_RE.search(texto):
        achados.append("conta_bancaria")

    return achados


def mascarar_dados_sensiveis(texto: str) -> str:
    """Substitui dados sensíveis por MASCARA (usado na entrada, histórico e saída)."""
    if not texto:
        return texto

    for m in sorted(_cpfs_validos(texto), key=lambda x: x.start(), reverse=True):
        texto = texto[: m.start()] + MASCARA + texto[m.end() :]

    texto = _UUID_RE.sub(MASCARA, texto)
    texto = _UUID_SEM_HIFEN_RE.sub(MASCARA, texto)
    texto = _PIX_COPIA_COLA_RE.sub(MASCARA, texto)
    texto = _BANCO_RE.sub(MASCARA, texto)
    texto = _RG_ROTULADO_RE.sub(rf"\1{MASCARA}", texto)
    texto = _DATA_NASC_RE.sub(MASCARA, texto)
    texto = _RE_LINHA_PIX.sub(rf"\1{MASCARA}", texto)

    if _PIX_RE.search(texto):
        texto = _EMAIL_RE.sub(MASCARA, texto)
        texto = _PHONE_RE.sub(MASCARA, texto)
        texto = _CNPJ_RE.sub(MASCARA, texto)

    return texto


def _sanitizar_estrutura(valor: Any) -> Any:
    """Remove chaves LGPD reais e mascara strings recursivamente em retornos de tools."""
    if isinstance(valor, str):
        return mascarar_dados_sensiveis(valor)
    if isinstance(valor, list):
        return [_sanitizar_estrutura(item) for item in valor]
    if isinstance(valor, dict):
        limpo: dict[str, Any] = {}
        for k, v in valor.items():
            if str(k).lower() in _CHAVES_BLOQUEADAS:
                continue
            limpo[k] = _sanitizar_estrutura(v)
        return limpo
    return valor


# --- Callbacks do Google ADK -------------------------------------------------
def verificar_entrada_segura(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> LlmResponse | None:
    """
    Guardrail de entrada (integrável ao `injetar_contexto_temporal`):
      - Verifica se a última mensagem do usuário contém CPF, RG, data de nascimento,
        chave PIX ou conta bancária.
      - Mascara todo o histórico (`llm_request.contents`) antes de chegar ao modelo.
      - Se detectado na mensagem atual, interrompe a chamada ao LLM com `MENSAGEM_RECUSA_PII`.
    """
    del callback_context
    contents = getattr(llm_request, "contents", None) or []
    ultimo_usuario = next(
        (c for c in reversed(contents) if getattr(c, "role", None) == "user"),
        None,
    )
    texto_ultima_msg = " ".join(
        getattr(p, "text", "")
        for p in (getattr(ultimo_usuario, "parts", None) or [])
        if getattr(p, "text", None)
    )

    achou_pii = bool(detectar_dados_sensiveis(texto_ultima_msg))

    for c in contents:
        for p in getattr(c, "parts", None) or []:
            if getattr(p, "text", None):
                p.text = mascarar_dados_sensiveis(p.text)

    if achou_pii:
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=MENSAGEM_RECUSA_PII)],
            )
        )
    return None


def validar_acesso_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any] | None:
    """
    Guardrail determinístico pré-execução de tool (RBAC e isolamento de produtor):
      - Usa exclusivamente os estados reais do projeto: `perfil_usuario` ('cooperado' | 'produtor')
        e `produtor_em_foco` (ex: 'P001').
      - Impede que um produtor execute tools administrativas da cooperativa.
      - Impede que um produtor consulte `produtor_id` de outro cooperado.
    """
    state = getattr(tool_context, "state", None)
    if not state:
        return None

    perfil = str(state.get("perfil_usuario") or "").strip().lower()
    produtor_foco = state.get("produtor_em_foco")
    produtor_logado = (
        produtor_foco.strip().upper()
        if isinstance(produtor_foco, str)
        else (
            str(produtor_foco.get("produtor_id") or "").strip().upper()
            if isinstance(produtor_foco, dict)
            else ""
        )
    )

    if perfil == "produtor" and produtor_logado:
        if tool.name in _TOOLS_EXCLUSIVAS_COOPERADO:
            return {
                "status": "acesso_negado",
                "dados": None,
                "mensagem": (
                    f"A ferramenta '{tool.name}' é restrita à equipe administrativa da cooperativa."
                ),
            }

        if tool.name in _TOOLS_INDIVIDUAIS_PRODUTOR:
            pid_solicitado = str(args.get("produtor_id") or "").strip().upper()
            if pid_solicitado and pid_solicitado != produtor_logado:
                return {
                    "status": "acesso_negado",
                    "dados": None,
                    "mensagem": (
                        f"Violação de isolamento LGPD: você está autenticado como {produtor_logado} "
                        f"e não tem permissão para consultar dados de {pid_solicitado}."
                    ),
                }

    return None


def sanitizar_retorno_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Guardrail pós-tool:
      - Remove chaves LGPD reais e mascara dados sensíveis no dicionário retornado.
      - Oculta identificação nominal de produtores na triagem se `perfil_usuario != 'cooperado'`.
    """
    del tool, args
    if not isinstance(tool_response, dict):
        return None

    limpo = _sanitizar_estrutura(tool_response)
    state = getattr(tool_context, "state", None)
    perfil = str((state or {}).get("perfil_usuario") or "").strip().lower()

    if perfil and perfil != "cooperado" and isinstance(limpo.get("dados"), dict):
        itens = limpo["dados"].get("itens")
        if isinstance(itens, list):
            for it in itens:
                if isinstance(it, dict) and "produtores_aptos" in it:
                    qtd = len(it["produtores_aptos"])
                    it["produtores_aptos"] = (
                        [
                            f"{qtd} produtor(es) cooperado(s) apto(s) "
                            "(identificação restrita à gestão)"
                        ]
                        if qtd
                        else []
                    )

    return limpo


def sanitizar_resposta_modelo(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> LlmResponse | None:
    """Última barreira: mascara qualquer dado sensível caso o modelo tente emití-lo."""
    del callback_context
    content = getattr(llm_response, "content", None)
    if not content or not getattr(content, "parts", None):
        return None

    alterado = False
    for part in content.parts:
        texto = getattr(part, "text", None)
        if texto and detectar_dados_sensiveis(texto):
            part.text = mascarar_dados_sensiveis(texto)
            alterado = True

    return llm_response if alterado else None

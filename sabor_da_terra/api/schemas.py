"""Schemas Pydantic de entrada e saída da API HTTP Sabor da Terra."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AuthConfigResponse(BaseModel):
    """Configuração pública de autenticação demonstrativa da interface."""

    requer_codigo: bool = False
    perfis_disponiveis: list[Literal["operador", "produtor"]] = Field(
        default_factory=lambda: ["operador", "produtor"]
    )


class AuthSessaoRequest(BaseModel):
    """Solicitação de emissão de token para o perfil selecionado na interface."""

    perfil: Literal["operador", "cooperado", "produtor"]
    produtor_id: Optional[str] = Field(
        default=None,
        description="Código do produtor (ex.: P001) quando perfil='produtor'.",
    )
    codigo_acesso: Optional[str] = Field(
        default=None,
        description="Código/PIN opcional quando habilitado no ambiente.",
    )


class AuthSessaoResponse(BaseModel):
    """Token assinado emitido para autenticação das rotas /api/*."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user_id: str
    perfil: Literal["operador", "produtor"]
    produtor_id: Optional[str] = None
    expires_in: int


class AuthSessaoInfoResponse(BaseModel):
    """Identidade autenticada validada a partir do Bearer Token."""

    user_id: str
    perfil: Literal["operador", "produtor"]
    produtor_id: Optional[str] = None


class ChatRequest(BaseModel):
    """Payload enviado pela interface para conversar com o assistente."""

    message: str = Field(..., min_length=1, description="Mensagem do usuário.")
    session_id: Optional[str] = Field(
        default=None, description="ID da sessão para manter histórico multi-turno."
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Opcional (derivado do token autenticado; se informado, deve coincidir).",
    )
    user_type: Optional[Literal["operador", "cooperado", "produtor"]] = Field(
        default=None,
        description="Opcional (derivado do token autenticado; se informado, deve coincidir).",
    )
    produtor_id: Optional[str] = Field(
        default=None,
        description="Opcional (derivado do token autenticado; se informado, deve coincidir).",
    )


class MensagemSessaoSchema(BaseModel):
    """Mensagem reconstruída a partir dos eventos persistidos da sessão ADK."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    fontes: list[dict[str, Any]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Resposta consolidada do coordenador com fontes RAG e estado da sessão."""

    session_id: str
    user_id: str
    resposta: str
    fontes: list[dict[str, Any]] = Field(default_factory=list)
    resultado_triagem: Optional[dict[str, Any]] = None
    produtor_em_foco: Optional[str] = None
    ultimo_pedido: Optional[dict[str, Any]] = None


class PagamentoItemSchema(BaseModel):
    """Item pendente no painel financeiro do produtor."""

    descricao: str
    valor: str
    previsao: str


class PagamentosPendentesSchema(BaseModel):
    """Resumo de valores pendentes no painel do produtor."""

    total: str
    itens: list[PagamentoItemSchema] = Field(default_factory=list)


class CertificacaoPainelSchema(BaseModel):
    """Resumo da certificação orgânica exibida no painel do produtor."""

    tipo: str
    situacao: str
    validade: str
    diasRestantes: int


class MovimentacaoSchema(BaseModel):
    """Lançamento resumido para o painel do produtor."""

    data: str
    descricao: str
    valor: str


class AvisoPainelSchema(BaseModel):
    """Alerta operacional ou sanitário exibido no painel do produtor."""

    id: str
    texto: str
    nivel: Literal["info", "atencao"]


class PainelProdutorResponse(BaseModel):
    """Estrutura esperada pelo componente InfoPanel da interface React."""

    codigo: str
    nome: str
    municipio: str
    situacaoCadastral: Literal["Ativo", "Pendente", "Inativo"]
    produtos: list[str] = Field(default_factory=list)
    certificacao: CertificacaoPainelSchema
    pagamentosPendentes: PagamentosPendentesSchema
    movimentacoes: list[MovimentacaoSchema] = Field(default_factory=list)
    avisos: list[AvisoPainelSchema] = Field(default_factory=list)

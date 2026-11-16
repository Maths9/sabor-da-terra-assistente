"""Schemas Pydantic de entrada e saída da API HTTP Sabor da Terra."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Payload enviado pela interface para conversar com o assistente."""

    message: str = Field(..., min_length=1, description="Mensagem do usuário.")
    session_id: Optional[str] = Field(
        default=None, description="ID da sessão para manter histórico multi-turno."
    )
    user_id: str = Field(
        default="operador", description="Identificador do usuário da interface."
    )
    user_type: Optional[Literal["cooperado", "produtor"]] = Field(
        default=None,
        description="Perfil ativo na interface ('cooperado' ou 'produtor').",
    )
    produtor_id: Optional[str] = Field(
        default=None,
        description="ID do produtor (ex.: P001) quando operando no portal do produtor.",
    )


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

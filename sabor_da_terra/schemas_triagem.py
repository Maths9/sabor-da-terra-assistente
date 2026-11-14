"""Schemas Pydantic enxutos para o Módulo de Triagem (Integrante 2 - José Portela)."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

TipoDemanda = Literal[
    "pedido_compra",
    "cotacao_evento",
    "consulta_comercial",
    "comunicacao_produtor",
    "notificacao_fiscalizacao",
]
NivelUrgencia = Literal["critica", "alta", "media", "baixa"]
StatusViabilidade = Literal[
    "viavel",
    "parcialmente_viavel",
    "inviavel",
    "requer_esclarecimento",
    "encaminhar_modulo_especialista",
]
ModuloRecomendado = Literal[
    "estoque_safra",
    "rastreabilidade_compliance",
    "comunicacao_produtores",
]
StatusExecucao = Literal["ok", "nao_encontrado", "dados_insuficientes", "entrada_invalida", "erro"]


class ItemPedidoInput(BaseModel):
    """Item extraído da mensagem do cliente para entrada na tool de triagem."""

    produto_mencionado: str
    quantidade: Optional[float] = Field(default=None, description="None quando o cliente não informou a quantidade (nunca assumir 1.0).")
    unidade: Optional[str] = Field(default=None, description="None usa a unidade oficial da tabela de preços.")
    exige_organico: bool = False


class AlertaOperacional(BaseModel):
    """Alerta determinístico gerado na triagem."""

    codigo: str = Field(description="Ex: PRODUTO_AMBIGUO, FORA_DE_SAFRA, ACIMA_DA_CAPACIDADE, CERTIFICACAO_VENCIDA, RESTRICAO_SIE, SEM_PRODUTOR_ORGANICO, SOLICITACAO_DADOS_SENSIVEIS, QUANTIDADE_NAO_INFORMADA, PRAZO_NAO_INFORMADO.")
    severidade: Literal["critico", "atencao", "informativo"]
    produto_relacionado: Optional[str] = None
    produtor_relacionado: Optional[str] = None
    mensagem: str


class ItemTriado(BaseModel):
    """Resultado da validação de um item nos CSVs operacionais."""

    produto_mencionado: str
    produto_catalogo: Optional[str] = None
    quantidade: Optional[float] = None
    unidade: Optional[str] = None
    exige_organico: bool = False
    status_item: Literal["viavel", "parcial", "indisponivel", "ambiguo", "nao_encontrado"]
    disponibilidade_safra: Optional[str] = Field(default=None, description="alta, media, baixa ou nenhuma.")
    preco_unitario: Optional[float] = None
    desconto_atacado_pct: float = 0.0
    subtotal_estimado: Optional[float] = None
    limite_semanal: Optional[float] = None
    produtores_aptos: list[str] = Field(default_factory=list)
    produtores_bloqueados: list[str] = Field(default_factory=list)
    opcoes_catalogo: list[str] = Field(default_factory=list, description="Opções do catálogo quando o produto é ambíguo.")
    observacao: Optional[str] = None


class TriagemPedidoOutput(BaseModel):
    """Contrato final de saída do Módulo de Triagem (output_schema no ADK)."""

    id_pedido: Optional[str] = None
    canal: Optional[str] = None
    remetente_identificado: str
    produtor_remetente_id: Optional[str] = Field(default=None, description="ID do produtor (ex: P001, P003) quando o remetente é cooperado.")
    tipo_cliente: str
    tipo_demanda: TipoDemanda
    urgencia: NivelUrgencia
    status_viabilidade: StatusViabilidade
    data_referencia: str
    mes_entrega: Optional[int] = Field(default=None, ge=1, le=12, description="None enquanto o cliente não informar o prazo de entrega.")
    campos_pendentes: list[str] = Field(default_factory=list, description="Ex: ['quantidade', 'prazo_entrega'].")
    itens: list[ItemTriado] = Field(default_factory=list)
    valor_total_estimado: float = 0.0
    alertas_operacionais: list[AlertaOperacional] = Field(default_factory=list)
    modulos_recomendados: list[ModuloRecomendado] = Field(default_factory=list)
    resumo_executivo_triagem: str

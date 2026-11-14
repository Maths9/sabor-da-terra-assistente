"""Pacote modular com as ferramentas de triagem e dados operacionais."""

from sabor_da_terra.tools.compliance import verificar_compliance_e_credito
from sabor_da_terra.tools.comum import DATA_REFERENCIA_PADRAO, ler_csv
from sabor_da_terra.tools.notificacoes import redigir_notificacao
from sabor_da_terra.tools.rastreabilidade import (
    consultar_lotes,
    consultar_pedidos_pendentes,
)
from sabor_da_terra.tools.resumo_produtor import obter_resumo_produtor
from sabor_da_terra.tools.schemas import (
    AlertaOperacional,
    ItemNotificacaoInput,
    ItemPedidoInput,
    ItemTriado,
    ModuloRecomendado,
    NivelUrgencia,
    PedidoNotificacaoInput,
    StatusExecucao,
    StatusViabilidade,
    TipoDemanda,
    TriagemPedidoOutput,
)
from sabor_da_terra.tools.triagem_catalogo import avaliar_item_catalogo
from sabor_da_terra.tools.triagem_consultas import consultar_produtores_ou_organicos
from sabor_da_terra.tools.triagem_pedidos import realizar_triagem_completa_pedido

LISTA_TOOLS_TRIAGEM = [
    avaliar_item_catalogo,
    consultar_produtores_ou_organicos,
    realizar_triagem_completa_pedido,
]

LISTA_TOOLS_DADOS = [
    obter_resumo_produtor,
    redigir_notificacao,
    consultar_lotes,
    consultar_pedidos_pendentes,
    verificar_compliance_e_credito,
]

__all__ = [
    "AlertaOperacional",
    "DATA_REFERENCIA_PADRAO",
    "ItemNotificacaoInput",
    "ItemPedidoInput",
    "ItemTriado",
    "LISTA_TOOLS_DADOS",
    "LISTA_TOOLS_TRIAGEM",
    "ModuloRecomendado",
    "NivelUrgencia",
    "PedidoNotificacaoInput",
    "StatusExecucao",
    "StatusViabilidade",
    "TipoDemanda",
    "TriagemPedidoOutput",
    "avaliar_item_catalogo",
    "consultar_lotes",
    "consultar_pedidos_pendentes",
    "consultar_produtores_ou_organicos",
    "ler_csv",
    "obter_resumo_produtor",
    "realizar_triagem_completa_pedido",
    "redigir_notificacao",
    "verificar_compliance_e_credito",
]

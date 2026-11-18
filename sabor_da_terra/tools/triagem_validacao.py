"""Validadores e leituras de apoio à triagem (catálogo vigente, sazonalidade e aptos)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional, get_args

from sabor_da_terra.database.repositories import repositorio
from sabor_da_terra.seguranca import norm_texto
from sabor_da_terra.tools.comum import EntradaInvalida, validar_data
from sabor_da_terra.tools.schemas import TipoDemanda

MESES_VALIDOS = set(range(1, 13))
TIPOS_DEMANDA = set(get_args(TipoDemanda))
DEMANDAS_COM_ENTREGA = {"pedido_compra", "cotacao_evento"}
ALIASES_RAPIDOS = {
    "aipim": "macaxeira",
    "mandioca": "macaxeira",
    "jerimum": "abobora",
    "tapioca": "tapioca/goma",
    "goma": "tapioca/goma",
    "banana": "banana prata",
    "manga": "manga tommy",
    "mango": "manga tommy",
    "guava": "goiaba",
    "passion fruit": "maracuja",
    "mel": "mel silvestre",
    "mel puro": "mel silvestre",
}
_STOPWORDS_PRODUTO = {
    "extra",
    "especial",
    "santa",
    "cruz",
    "prata",
    "tommy",
    "paluma",
    "verde",
    "colorido",
}


def validar_mes(mes_entrega: Optional[int]) -> None:
    """Garante que `mes_entrega` (quando informado) esteja entre 1 e 12."""
    if mes_entrega is not None and mes_entrega not in MESES_VALIDOS:
        raise EntradaInvalida(
            f"mes_entrega '{mes_entrega}' inválido; use um número de 1 a 12."
        )


def validar_quantidade(quantidade: Optional[float]) -> None:
    """Garante quantidade positiva quando o cliente informou volume."""
    if quantidade is not None and quantidade <= 0:
        raise EntradaInvalida(
            f"quantidade '{quantidade}' inválida; deve ser maior que zero."
        )


def normalizar_tipo_demanda(valor: str) -> str:
    """Normaliza variações textuais para um dos valores de `TipoDemanda`."""
    chave = (
        re.sub(r"[\s\-]+", "_", norm_texto(valor))
        .replace("_de_", "_")
        .replace("_para_", "_")
    )
    if chave in TIPOS_DEMANDA:
        return chave
    for termo, tipo in (
        ("pedido", "pedido_compra"),
        ("compra", "pedido_compra"),
        ("cotacao", "cotacao_evento"),
        ("evento", "cotacao_evento"),
        ("consulta", "consulta_comercial"),
        ("comunicacao", "comunicacao_produtor"),
        ("notificacao", "notificacao_fiscalizacao"),
        ("fiscalizacao", "notificacao_fiscalizacao"),
    ):
        if termo in chave:
            return tipo
    raise EntradaInvalida(
        f"tipo_demanda '{valor}' inválido; use um de: {', '.join(sorted(TIPOS_DEMANDA))}."
    )


def tabela_precos_vigente() -> list[dict[str, str]]:
    """Carrega a tabela de preços vigente a partir do repositório operacional."""
    return repositorio.obter_tabela_precos_vigente()


def buscar_sazonalidade(
    nome_cat: str, sazonalidade: dict[str, dict[str, str]]
) -> Optional[dict[str, str]]:
    """Busca pelo nome exato e, se não houver, pelo nome-base (ex.: 'tomate santa cruz' -> 'tomate')."""
    partes = norm_texto(nome_cat).split()
    while partes:
        chave = " ".join(partes)
        if chave in sazonalidade:
            return sazonalidade[chave]
        partes.pop()
    return None


def buscar_produtores_aptos(
    produto_cat: str, exige_organico: bool, exige_sie: bool, data_ref: str
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Separa produtores aptos e bloqueados para o item segundo status e certificação orgânica."""
    del exige_sie  # Restrição detalhada de SIE é verificada por verificar_compliance_e_credito.
    tokens_cat = {
        t
        for t in re.split(r"[\s/]+", norm_texto(produto_cat))
        if len(t) > 2 and t not in _STOPWORDS_PRODUTO
    }
    aptos, bloqueados, alertas = [], [], []
    dt_ref = validar_data(data_ref)

    for p in repositorio.listar_produtores(filtrar_lgpd=True, remover_contato=True):
        prods_p = norm_texto(p.get("produtos", ""))
        if not any(t in prods_p for t in tokens_cat):
            continue
        label = f"{p['id']} - {p['nome_completo']} ({p['municipio']})"
        if norm_texto(p.get("status", "")) != "ativo":
            bloqueados.append(f"{label} [INATIVO]")
            continue
        if exige_organico:
            if norm_texto(p.get("certificacao_organica", "")) != "sim":
                bloqueados.append(f"{label} [SEM CERTIFICAÇÃO ORGÂNICA]")
                continue
            val = (p.get("validade_certificacao") or "").strip()
            if val and date.fromisoformat(val) < dt_ref:
                bloqueados.append(f"{label} [CERTIFICAÇÃO VENCIDA EM {val}]")
                alertas.append(
                    {
                        "codigo": "CERTIFICACAO_VENCIDA",
                        "severidade": "critico",
                        "produto_relacionado": produto_cat,
                        "produtor_relacionado": p["id"],
                        "mensagem": f"Produtor {label} bloqueado: certificação orgânica venceu em {val}.",
                    }
                )
                continue
        aptos.append(label)
    return aptos, bloqueados, alertas

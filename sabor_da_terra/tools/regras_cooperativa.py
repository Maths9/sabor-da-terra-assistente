"""Regras operacionais da cooperativa (SIE, certificações, unidades e matching)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sabor_da_terra.config import DADOS_DIR
from sabor_da_terra.seguranca import norm_texto
from sabor_da_terra.tools.comum import ler_csv_bruto

PRODUTORES_COM_SIE = {"P002", "P003", "P007"}
PRODUTORES_SEM_SIE = {
    "P011": "Sem registro SIE (venda restrita a consumidor final)",
    "P017": "Sem registro SIE e com suspensão ADAGRO NC-001 para comercialização intermediada",
}
PRODUTORES_SIE_PENDENTE = {
    "P008": "SIE pendente (não apto para canais institucionais como PNAE)",
    "P018": "SIE pendente (não apto para canais institucionais como PNAE)",
}
TIPOS_EXIGEM_SIE = {
    "pnae",
    "supermercado",
    "atacado",
    "hotel",
    "hospital",
    "sesc",
    "restaurante",
    "lanchonete",
    "institucional",
    "exportadora",
    "varejo",
}


def cliente_exige_sie(tipo_cliente: str) -> bool:
    """Verifica se o tipo de cliente comercial/institucional exige registro SIE."""
    tipo_n = norm_texto(tipo_cliente)
    return tipo_n in TIPOS_EXIGEM_SIE or any(t in tipo_n for t in TIPOS_EXIGEM_SIE)


def mapa_unidades_produtos() -> dict[str, str]:
    """Monta mapa produto -> unidade oficial a partir da tabela de preços vigente."""
    arquivos = sorted(DADOS_DIR.glob("tabela_precos_*.csv"))
    if not arquivos:
        return {}
    unidades: dict[str, str] = {}
    for row in ler_csv_bruto(arquivos[-1]):
        prod_n = norm_texto(row.get("produto", ""))
        uni = (row.get("unidade") or "kg").strip()
        unidades[prod_n] = uni
        base = prod_n.split()[0] if prod_n else ""
        if base and base not in unidades:
            unidades[base] = uni
    return unidades


def inferir_unidade(produto: str, mapa_unidades: dict[str, str]) -> str:
    """Infere a unidade oficial de venda do produto com fallback para `'kg'`."""
    p = norm_texto(produto)
    if p in mapa_unidades:
        return mapa_unidades[p]
    for k, uni in mapa_unidades.items():
        if k and (k in p or p in k):
            return uni
    return "kg"


def status_certificacao_produtor(produtor: dict[str, str], data_ref: date) -> dict[str, Any]:
    """Avalia se a certificação orgânica do produtor está vigente, vencida ou próxima do fim."""
    possui_flag = norm_texto(produtor.get("certificacao_organica", "")) == "sim"
    val_str = (produtor.get("validade_certificacao") or "").strip()
    if not possui_flag or not val_str:
        return {
            "possui_certificacao_organica": False,
            "situacao": "nao_possui",
            "validade": None,
        }
    val_dt = date.fromisoformat(val_str)
    if val_dt < data_ref:
        return {
            "possui_certificacao_organica": False,
            "situacao": "vencida",
            "validade": val_str,
        }
    dias_restantes = (val_dt - data_ref).days
    situacao = "vence_em_breve" if dias_restantes <= 30 else "vigente"
    return {
        "possui_certificacao_organica": True,
        "situacao": situacao,
        "validade": val_str,
        "dias_restantes": dias_restantes,
    }


def avaliar_sie_produtor(pid: str) -> dict[str, Any]:
    """Retorna a situação sanitária (SIE) consolidada para o produtor."""
    if pid in PRODUTORES_COM_SIE:
        return {"situacao": "vigente", "detalhe": "Registro SIE ativo."}
    if pid in PRODUTORES_SEM_SIE:
        return {"situacao": "sem_sie", "detalhe": PRODUTORES_SEM_SIE[pid]}
    if pid in PRODUTORES_SIE_PENDENTE:
        return {"situacao": "pendente", "detalhe": PRODUTORES_SIE_PENDENTE[pid]}
    return {
        "situacao": "nao_aplicavel_ou_nao_informado",
        "detalhe": "Sem registro SIE especificado nos dados cadastrais.",
    }


def match_produtor_em_lista(pid: str, lista_labels: list[str]) -> bool:
    """Confere se `pid` consta em uma lista de rótulos `'P001 - Nome'`."""
    return any(
        lbl.upper().startswith(f"{pid} ") or lbl.strip().upper() == pid
        for lbl in (lista_labels or [])
    )


def produto_casa_catalogo(produto_item: str, prods_cadastrados: list[str]) -> bool:
    """Verifica se um item pedido corresponde a algum produto fornecido pelo produtor."""
    item_n = norm_texto(produto_item).replace("mel de abelha jandaira", "mel de jandaira")
    if not item_n:
        return False
    for raw_pc in prods_cadastrados:
        pc = norm_texto(raw_pc).replace("mel de abelha jandaira", "mel de jandaira")
        if not pc:
            continue
        if (
            pc == item_n
            or re.search(rf"\b{re.escape(pc)}\b", item_n)
            or re.search(rf"\b{re.escape(item_n)}\b", pc)
        ):
            return True
    return False

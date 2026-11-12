"""FunctionTools enxutas e dinâmicas do Módulo de Triagem (Integrante 2 - José Portela)."""

from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Optional

from sabor_da_terra.schemas_triagem import ItemPedidoInput

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    ToolContext = Any  # type: ignore

DADOS_DIR = Path(__file__).resolve().parent.parent / "dados"
MESES_COL = {1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun", 7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez"}
CAMPOS_SENSIVEIS_LGPD = {"cpf", "chave_pix", "banco", "agencia", "conta_corrente", "data_nascimento"}
ALIASES_RAPIDOS = {
    "aipim": "macaxeira", "mandioca": "macaxeira", "jerimum": "abobora", "tapioca": "tapioca/goma",
    "goma": "tapioca/goma", "banana": "banana prata", "manga": "manga tommy", "mango": "manga tommy",
    "guava": "goiaba", "passion fruit": "maracuja", "mel": "mel silvestre", "mel puro": "mel silvestre",
}


def _norm(txt: str) -> str:
    s = unicodedata.normalize("NFKD", str(txt or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _ler_csv(caminho: Path, filtrar_lgpd: bool = False) -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    if not filtrar_lgpd:
        return linhas
    return [{k: v for k, v in row.items() if k.lower() not in CAMPOS_SENSIVEIS_LGPD} for row in linhas]


def _tabela_precos_vigente() -> list[dict[str, str]]:
    arquivos = sorted(DADOS_DIR.glob("tabela_precos_*.csv"))
    return _ler_csv(arquivos[-1]) if arquivos else []


def _buscar_produtores(produto_cat: str, exige_organico: bool, exige_sie: bool, data_ref: str) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    tokens_cat = {t for t in re.split(r"[\s/]+", _norm(produto_cat)) if len(t) > 2 and t not in {"extra", "especial", "santa", "cruz", "prata", "tommy", "paluma", "verde", "colorido"}}
    aptos, bloqueados, alertas = [], [], []
    dt_ref = date.fromisoformat(data_ref[:10])

    for p in _ler_csv(DADOS_DIR / "produtores.csv", filtrar_lgpd=True):
        prods_p = _norm(p.get("produtos", ""))
        if not any(t in prods_p for t in tokens_cat):
            continue
        label = f"{p['id']} - {p['nome_completo']} ({p['municipio']})"
        if _norm(p.get("status", "")) != "ativo":
            bloqueados.append(f"{label} [INATIVO]")
            continue
        if exige_organico:
            if _norm(p.get("certificacao_organica", "")) != "sim":
                bloqueados.append(f"{label} [SEM CERTIFICAÇÃO ORGÂNICA]")
                continue
            val = (p.get("validade_certificacao") or "").strip()
            if val and date.fromisoformat(val) < dt_ref:
                bloqueados.append(f"{label} [CERTIFICAÇÃO VENCIDA EM {val}]")
                alertas.append({"codigo": "CERTIFICACAO_VENCIDA", "severidade": "critico", "produto_relacionado": produto_cat, "produtor_relacionado": p["id"], "mensagem": f"Produtor {label} bloqueado: certificação orgânica venceu em {val}."})
                continue
        aptos.append(label)
    return aptos, bloqueados, alertas


def avaliar_item_catalogo(
    produto: str,
    quantidade: float = 1.0,
    unidade: str = "kg",
    exige_organico: bool = False,
    exige_sie: bool = False,
    mes_entrega: int = 10,
    data_referencia: str = "2026-10-28",
) -> dict[str, Any]:
    """Valida preço, desconto de atacado, safra do mês, limite semanal e produtores aptos para um item."""
    termo = ALIASES_RAPIDOS.get(_norm(produto), _norm(produto))
    precos = _tabela_precos_vigente()
    sazonalidade = { _norm(r["produto"]): r for r in _ler_csv(DADOS_DIR / "sazonalidade.csv") }

    if any(g in termo for g in ("variada", "variado", "queijo q vcs", "mais artesanal")):
        return {"produto_mencionado": produto, "status_item": "ambiguo", "alertas": [{"codigo": "PRODUTO_AMBIGUO", "severidade": "atencao", "produto_relacionado": produto, "mensagem": f"Termo genérico '{produto}' requer especificação dos itens exatos do catálogo."}]}

    exatos = [r for r in precos if _norm(r["produto"]) == termo]
    matches = exatos or [r for r in precos if termo in _norm(r["produto"])]

    if len(matches) > 1:
        opcoes = [r["produto"] for r in matches]
        return {"produto_mencionado": produto, "quantidade": quantidade, "unidade": unidade, "exige_organico": exige_organico, "status_item": "ambiguo", "opcoes_catalogo": opcoes, "observacao": f"Opções: {', '.join(opcoes)}", "alertas": [{"codigo": "PRODUTO_AMBIGUO", "severidade": "atencao", "produto_relacionado": produto, "mensagem": f"'{produto}' é ambíguo no catálogo. Opções: {', '.join(opcoes)}."}]}

    if not matches:
        catalogo_nomes = [r["produto"] for r in precos]
        return {"produto_mencionado": produto, "quantidade": quantidade, "unidade": unidade, "exige_organico": exige_organico, "status_item": "nao_encontrado", "catalogo_disponivel": catalogo_nomes, "alertas": [{"codigo": "PRODUTO_NAO_ENCONTRADO", "severidade": "atencao", "produto_relacionado": produto, "mensagem": f"'{produto}' não encontrado no catálogo."}]}

    item_p = matches[0]
    nome_cat = item_p["produto"]
    alertas: list[dict[str, Any]] = []

    # 1. Sazonalidade e limite semanal (lendo coluna observacao do CSV)
    saz_row = sazonalidade.get(_norm(nome_cat)) or next((v for k, v in sazonalidade.items() if k in _norm(nome_cat) or _norm(nome_cat) in k), {})
    col_mes = MESES_COL.get(mes_entrega, "out")
    disp_safra = _norm(saz_row.get(col_mes, "alta"))
    obs_unificada = " | ".join(filter(None, [item_p.get("observacao", "").strip(), saz_row.get("observacao", "").strip()]))

    if disp_safra == "nenhuma":
        alertas.append({"codigo": "FORA_DE_SAFRA", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"'{nome_cat}' indisponível (entressafra) no mês {mes_entrega} ({col_mes}). {obs_unificada}"})
    elif disp_safra == "baixa":
        alertas.append({"codigo": "SAFRA_BAIXA", "severidade": "atencao", "produto_relacionado": nome_cat, "mensagem": f"'{nome_cat}' com disponibilidade baixa no mês {mes_entrega} ({col_mes}). {obs_unificada}"})

    m_lim = re.search(r"~?\s*(\d+)\s*(kg|d[uú]zias?)/semana", _norm(obs_unificada))
    limite_sem = float(m_lim.group(1)) if m_lim else None
    if limite_sem and quantidade > limite_sem:
        alertas.append({"codigo": "ACIMA_DA_CAPACIDADE", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"Quantidade ({quantidade}) excede limite semanal de {limite_sem} para '{nome_cat}'."})
    elif limite_sem and quantidade >= 0.8 * limite_sem:
        alertas.append({"codigo": "CAPACIDADE_PROXIMA_DO_LIMITE", "severidade": "atencao", "produto_relacionado": nome_cat, "mensagem": f"Quantidade ({quantidade}) consome >=80% do limite semanal ({limite_sem}) de '{nome_cat}'."})

    if "sem sie" in _norm(obs_unificada) and exige_sie:
        alertas.append({"codigo": "RESTRICAO_SIE", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"Restrição sanitária para '{nome_cat}': {obs_unificada}"})

    # 2. Preço e desconto de atacado
    raw_org, raw_conv = item_p.get("preco_organico", "n/d").strip(), item_p.get("preco_convencional", "n/d").strip()
    if exige_organico and _norm(raw_org) == "n/d":
        alertas.append({"codigo": "SEM_PRODUTOR_ORGANICO", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"'{nome_cat}' não possui oferta orgânica certificada (apenas convencional a R$ {raw_conv})."})
        preco_base = float(raw_conv) if _norm(raw_conv) != "n/d" else None
    else:
        escolhido = raw_org if (exige_organico or _norm(raw_conv) == "n/d") else raw_conv
        preco_base = float(escolhido) if _norm(escolhido) != "n/d" else None

    vol_min = float(item_p.get("volume_minimo_atacado_kg") or 0)
    desc_pct = float(item_p.get("desconto_atacado_pct") or 0) if (vol_min > 0 and quantidade >= vol_min) else 0.0
    preco_final = round(preco_base * (1 - desc_pct / 100.0), 2) if preco_base is not None else None
    subtotal = round(preco_final * quantidade, 2) if preco_final is not None else None

    # 3. Produtores aptos e bloqueados
    aptos, bloqueados, alertas_prod = _buscar_produtores(nome_cat, exige_organico, exige_sie, data_referencia)
    alertas.extend(alertas_prod)

    tem_critico = any(a["severidade"] == "critico" and a["codigo"] != "CERTIFICACAO_VENCIDA" for a in alertas) or not aptos
    status_item = "indisponivel" if disp_safra == "nenhuma" else ("parcial" if (tem_critico or disp_safra == "baixa") else "viavel")

    return {
        "produto_mencionado": produto, "produto_catalogo": nome_cat, "quantidade": quantidade, "unidade": item_p["unidade"],
        "exige_organico": exige_organico, "status_item": status_item, "disponibilidade_safra": disp_safra,
        "preco_unitario": preco_final, "desconto_atacado_pct": desc_pct, "subtotal_estimado": subtotal,
        "limite_semanal": limite_sem, "produtores_aptos": aptos, "produtores_bloqueados": bloqueados,
        "observacao": obs_unificada or None, "alertas": alertas,
    }


def consultar_produtores_ou_organicos(
    termo_busca_produtor: Optional[str] = None,
    apenas_listar_organicos_vigentes: bool = False,
    data_referencia: str = "2026-10-28",
) -> dict[str, Any]:
    """Identifica produtor cooperado (por nome, telefone, município ou produto, sem expor CPF/PIX) ou lista todo o catálogo orgânico vigente."""
    dt_ref = date.fromisoformat(data_referencia[:10])
    produtores = _ler_csv(DADOS_DIR / "produtores.csv", filtrar_lgpd=True)

    if apenas_listar_organicos_vigentes:
        organicos = []
        for p in produtores:
            val = (p.get("validade_certificacao") or "").strip()
            if _norm(p.get("status", "")) == "ativo" and _norm(p.get("certificacao_organica", "")) == "sim" and val and date.fromisoformat(val) >= dt_ref:
                organicos.append({"id": p["id"], "nome": p["nome_completo"], "municipio": p["municipio"], "produtos": p["produtos"], "validade_certificacao": val})
        return {"data_referencia": data_referencia, "produtores_organicos_vigentes": organicos}

    q = _norm(termo_busca_produtor or "")
    encontrados = [p for p in produtores if q in _norm(" ".join(p.values()))]
    return {"termo_busca": termo_busca_produtor, "produtores_encontrados": encontrados}


def realizar_triagem_completa_pedido(
    remetente_identificado: str,
    tipo_cliente: str,
    tipo_demanda: str,
    itens: list[ItemPedidoInput],
    id_pedido: Optional[str] = None,
    canal: Optional[str] = None,
    data_referencia: str = "2026-10-28",
    mes_entrega: int = 10,
    urgente_no_texto: bool = False,
    exige_organico_global: bool = False,
    solicita_dados_sensiveis: bool = False,
    termo_identificacao_produtor: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Executa a triagem completa do pedido, valida itens nos CSVs e salva o TriagemPedidoOutput em session.state['resultado_triagem']."""
    exige_sie = _norm(tipo_cliente) in {"pnae", "supermercado", "atacado", "hotel", "hospital", "sesc", "institucional", "exportadora"}
    itens_triados, alertas_gerais, total = [], [], 0.0

    if solicita_dados_sensiveis:
        alertas_gerais.append({"codigo": "SOLICITACAO_DADOS_SENSIVEIS", "severidade": "critico", "mensagem": "Solicitação de CPF ou dados bancários bloqueada por política de privacidade (LGPD)."})

    prod_id = None
    if termo_identificacao_produtor or tipo_demanda == "comunicacao_produtor":
        achados = consultar_produtores_ou_organicos(termo_identificacao_produtor or remetente_identificado)["produtores_encontrados"]
        if achados:
            prod_id = achados[0]["id"]

    for raw_it in itens:
        it = raw_it.model_dump() if hasattr(raw_it, "model_dump") else dict(raw_it)
        res = avaliar_item_catalogo(
            produto=it.get("produto_mencionado", ""),
            quantidade=float(it.get("quantidade") or 1.0),
            unidade=it.get("unidade", "kg"),
            exige_organico=bool(it.get("exige_organico", False) or exige_organico_global),
            exige_sie=exige_sie,
            mes_entrega=mes_entrega,
            data_referencia=data_referencia,
        )
        alertas_gerais.extend(res.pop("alertas", []))
        total += float(res.get("subtotal_estimado") or 0.0)
        itens_triados.append(res)

    urgencia = "critica" if (tipo_demanda == "notificacao_fiscalizacao" or urgente_no_texto) else ("alta" if exige_sie else "media")
    modulos = []
    if itens_triados:
        modulos.append("estoque_safra")
    if exige_organico_global or exige_sie or tipo_demanda in {"notificacao_fiscalizacao", "consulta_comercial"} or any(a["codigo"] in {"CERTIFICACAO_VENCIDA", "RESTRICAO_SIE"} for a in alertas_gerais):
        modulos.append("rastreabilidade_compliance")
    if tipo_demanda in {"comunicacao_produtor", "pedido_compra"}:
        modulos.append("comunicacao_produtores")

    status_itens = {i["status_item"] for i in itens_triados}
    if not itens_triados:
        status_viab = "encaminhar_modulo_especialista"
    elif "ambiguo" in status_itens:
        status_viab = "requer_esclarecimento"
    elif status_itens == {"viavel"}:
        status_viab = "viavel"
    elif status_itens == {"indisponivel"}:
        status_viab = "inviavel"
    else:
        status_viab = "parcialmente_viavel"

    saida = {
        "id_pedido": id_pedido, "canal": canal, "remetente_identificado": remetente_identificado,
        "produtor_remetente_id": prod_id, "tipo_cliente": tipo_cliente, "tipo_demanda": tipo_demanda,
        "urgencia": urgencia, "status_viabilidade": status_viab, "data_referencia": data_referencia,
        "mes_entrega": mes_entrega, "itens": itens_triados, "valor_total_estimado": round(total, 2),
        "alertas_operacionais": alertas_gerais, "modulos_recomendados": modulos,
        "resumo_executivo_triagem": f"[{urgencia.upper()}] {remetente_identificado} ({tipo_demanda}) -> Status: {status_viab} | Total estimado: R$ {total:.2f} | Alertas: {len(alertas_gerais)}",
    }
    if tool_context is not None and hasattr(tool_context, "state"):
        tool_context.state["resultado_triagem"] = saida
    return saida


LISTA_TOOLS_TRIAGEM = [avaliar_item_catalogo, consultar_produtores_ou_organicos, realizar_triagem_completa_pedido]

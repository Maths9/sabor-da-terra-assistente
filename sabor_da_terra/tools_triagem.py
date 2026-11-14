"""FunctionTools enxutas e dinâmicas do Módulo de Triagem (Integrante 2 - José Portela)."""

from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Optional, get_args

from sabor_da_terra.schemas_triagem import ItemPedidoInput, TipoDemanda, TriagemPedidoOutput

try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    ToolContext = Any  # type: ignore

DADOS_DIR = Path(__file__).resolve().parent.parent / "dados"
DATA_REFERENCIA_PADRAO = "2026-10-30"  # Data-base do dataset simulado da cooperativa (usada se o coordenador não informar).
MESES_COL = {1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun", 7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez"}
CAMPOS_SENSIVEIS_LGPD = {"cpf", "chave_pix", "banco", "agencia", "conta_corrente", "data_nascimento"}
TIPOS_DEMANDA = set(get_args(TipoDemanda))
DEMANDAS_COM_ENTREGA = {"pedido_compra", "cotacao_evento"}
ALIASES_RAPIDOS = {
    "aipim": "macaxeira", "mandioca": "macaxeira", "jerimum": "abobora", "tapioca": "tapioca/goma",
    "goma": "tapioca/goma", "banana": "banana prata", "manga": "manga tommy", "mango": "manga tommy",
    "guava": "goiaba", "passion fruit": "maracuja", "mel": "mel silvestre", "mel puro": "mel silvestre",
}


class EntradaInvalida(ValueError):
    """Parâmetro informado à tool fora do formato esperado."""


def _norm(txt: str) -> str:
    s = unicodedata.normalize("NFKD", str(txt or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _validar_data(data_referencia: str) -> date:
    try:
        return date.fromisoformat(str(data_referencia)[:10])
    except ValueError as exc:
        raise EntradaInvalida(f"data_referencia '{data_referencia}' inválida; use o formato AAAA-MM-DD.") from exc


def _validar_mes(mes_entrega: Optional[int]) -> None:
    if mes_entrega is not None and mes_entrega not in MESES_COL:
        raise EntradaInvalida(f"mes_entrega '{mes_entrega}' inválido; use um número de 1 a 12.")


def _validar_quantidade(quantidade: Optional[float]) -> None:
    if quantidade is not None and quantidade <= 0:
        raise EntradaInvalida(f"quantidade '{quantidade}' inválida; deve ser maior que zero.")


def _normalizar_tipo_demanda(valor: str) -> str:
    chave = re.sub(r"[\s\-]+", "_", _norm(valor)).replace("_de_", "_").replace("_para_", "_")
    if chave in TIPOS_DEMANDA:
        return chave
    for termo, tipo in (("pedido", "pedido_compra"), ("compra", "pedido_compra"), ("cotacao", "cotacao_evento"),
                        ("evento", "cotacao_evento"), ("consulta", "consulta_comercial"), ("comunicacao", "comunicacao_produtor"),
                        ("notificacao", "notificacao_fiscalizacao"), ("fiscalizacao", "notificacao_fiscalizacao")):
        if termo in chave:
            return tipo
    raise EntradaInvalida(f"tipo_demanda '{valor}' inválido; use um de: {', '.join(sorted(TIPOS_DEMANDA))}.")


def _resposta_ok(dados: dict[str, Any], mensagem: Optional[str] = None) -> dict[str, Any]:
    return {"status": "ok", "dados": dados, "mensagem": mensagem}


def _resposta_falha(status: str, mensagem: str) -> dict[str, Any]:
    return {"status": status, "dados": None, "mensagem": mensagem}


def _ler_csv(caminho: Path, filtrar_lgpd: bool = False) -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    if not filtrar_lgpd:
        return linhas
    return [{k: v for k, v in row.items() if k.lower() not in CAMPOS_SENSIVEIS_LGPD} for row in linhas]


def _tabela_precos_vigente() -> list[dict[str, str]]:
    arquivos = sorted(DADOS_DIR.glob("tabela_precos_*.csv"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhuma tabela de preços (tabela_precos_*.csv) encontrada em {DADOS_DIR}.")
    return _ler_csv(arquivos[-1])


def _buscar_sazonalidade(nome_cat: str, sazonalidade: dict[str, dict[str, str]]) -> Optional[dict[str, str]]:
    """Busca pelo nome exato e, se não houver, pelo nome-base (ex.: 'tomate santa cruz' -> 'tomate')."""
    partes = _norm(nome_cat).split()
    while partes:
        chave = " ".join(partes)
        if chave in sazonalidade:
            return sazonalidade[chave]
        partes.pop()
    return None


def _buscar_produtores(produto_cat: str, exige_organico: bool, exige_sie: bool, data_ref: str) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    tokens_cat = {t for t in re.split(r"[\s/]+", _norm(produto_cat)) if len(t) > 2 and t not in {"extra", "especial", "santa", "cruz", "prata", "tommy", "paluma", "verde", "colorido"}}
    aptos, bloqueados, alertas = [], [], []
    dt_ref = _validar_data(data_ref)

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
    quantidade: Optional[float] = None,
    unidade: Optional[str] = None,
    exige_organico: bool = False,
    exige_sie: bool = False,
    mes_entrega: Optional[int] = None,
    data_referencia: str = DATA_REFERENCIA_PADRAO,
) -> dict[str, Any]:
    """Valida preço, desconto de atacado, safra do mês, limite semanal e produtores aptos para um item.

    Deixe `quantidade`, `unidade` e `mes_entrega` como None quando o cliente não os informou (nunca invente valores).
    """
    try:
        dt_ref = _validar_data(data_referencia)
        _validar_mes(mes_entrega)
        _validar_quantidade(quantidade)
        termo = ALIASES_RAPIDOS.get(_norm(produto), _norm(produto))
        precos = _tabela_precos_vigente()
        sazonalidade = { _norm(r["produto"]): r for r in _ler_csv(DADOS_DIR / "sazonalidade.csv") }

        if any(g in termo for g in ("variada", "variado", "queijo q vcs", "mais artesanal")):
            return _resposta_ok({
                "produto_mencionado": produto,
                "status_item": "ambiguo",
                "alertas": [{"codigo": "PRODUTO_AMBIGUO", "severidade": "atencao", "produto_relacionado": produto, "mensagem": f"Termo genérico '{produto}' requer especificação dos itens exatos do catálogo."}],
            })

        exatos = [r for r in precos if _norm(r["produto"]) == termo]
        matches = exatos or [r for r in precos if termo in _norm(r["produto"])]

        if len(matches) > 1:
            opcoes = [r["produto"] for r in matches]
            return _resposta_ok({
                "produto_mencionado": produto,
                "quantidade": quantidade,
                "unidade": unidade,
                "exige_organico": exige_organico,
                "status_item": "ambiguo",
                "opcoes_catalogo": opcoes,
                "observacao": f"Opções: {', '.join(opcoes)}",
                "alertas": [{"codigo": "PRODUTO_AMBIGUO", "severidade": "atencao", "produto_relacionado": produto, "mensagem": f"'{produto}' é ambíguo no catálogo. Opções: {', '.join(opcoes)}."}],
            })

        if not matches:
            return _resposta_falha("nao_encontrado", f"'{produto}' não encontrado no catálogo.")

        item_p = matches[0]
        nome_cat = item_p["produto"]
        alertas: list[dict[str, Any]] = []

        # 1. Sazonalidade e limite semanal (lendo coluna observacao do CSV)
        # Sem prazo informado, usa o mês da data de referência apenas como prévia.
        mes_safra = mes_entrega if mes_entrega is not None else dt_ref.month
        col_mes = MESES_COL[mes_safra]
        saz_row = _buscar_sazonalidade(nome_cat, sazonalidade)
        obs_unificada = " | ".join(filter(None, [item_p.get("observacao", "").strip(), (saz_row or {}).get("observacao", "").strip()]))

        if saz_row is None:
            disp_safra = "nenhuma"
            alertas.append({"codigo": "FORA_DE_SAFRA", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"'{nome_cat}' não possui sazonalidade cadastrada e não está disponível para venda."})
        else:
            disp_safra = _norm(saz_row.get(col_mes, ""))
            if disp_safra == "nenhuma":
                alertas.append({"codigo": "FORA_DE_SAFRA", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"'{nome_cat}' indisponível (entressafra) no mês {mes_safra} ({col_mes}). {obs_unificada}"})
            elif disp_safra == "baixa":
                alertas.append({"codigo": "SAFRA_BAIXA", "severidade": "atencao", "produto_relacionado": nome_cat, "mensagem": f"'{nome_cat}' com disponibilidade baixa no mês {mes_safra} ({col_mes}). {obs_unificada}"})

        m_lim = re.search(r"~?\s*(\d+)\s*(kg|d[uú]zias?)/semana", _norm(obs_unificada))
        limite_sem = float(m_lim.group(1)) if m_lim else None
        if quantidade is None:
            alertas.append({"codigo": "QUANTIDADE_NAO_INFORMADA", "severidade": "atencao", "produto_relacionado": nome_cat, "mensagem": f"Quantidade de '{nome_cat}' não informada. Pergunte ao cliente quantos {item_p['unidade']} deseja."})
        elif limite_sem and quantidade > limite_sem:
            alertas.append({"codigo": "ACIMA_DA_CAPACIDADE", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"Quantidade ({quantidade}) excede limite semanal de {limite_sem} para '{nome_cat}'."})
        elif limite_sem and quantidade >= 0.8 * limite_sem:
            alertas.append({"codigo": "CAPACIDADE_PROXIMA_DO_LIMITE", "severidade": "atencao", "produto_relacionado": nome_cat, "mensagem": f"Quantidade ({quantidade}) consome >=80% do limite semanal ({limite_sem}) de '{nome_cat}'."})

        if "sem sie" in _norm(obs_unificada) and exige_sie:
            alertas.append({"codigo": "RESTRICAO_SIE", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"Restrição sanitária para '{nome_cat}': {obs_unificada}"})

        # 2. Preço e desconto de atacado (round(…, 2) em cada etapa)
        raw_org, raw_conv = item_p.get("preco_organico", "n/d").strip(), item_p.get("preco_convencional", "n/d").strip()
        if exige_organico and _norm(raw_org) == "n/d":
            alertas.append({"codigo": "SEM_PRODUTOR_ORGANICO", "severidade": "critico", "produto_relacionado": nome_cat, "mensagem": f"'{nome_cat}' não possui oferta orgânica certificada (apenas convencional a R$ {raw_conv})."})
            preco_base = round(float(raw_conv), 2) if _norm(raw_conv) != "n/d" else None
        else:
            escolhido = raw_org if (exige_organico or _norm(raw_conv) == "n/d") else raw_conv
            preco_base = round(float(escolhido), 2) if _norm(escolhido) != "n/d" else None

        vol_min = float(item_p.get("volume_minimo_atacado_kg") or 0)
        desc_pct = float(item_p.get("desconto_atacado_pct") or 0) if (quantidade is not None and vol_min > 0 and quantidade >= vol_min) else 0.0
        preco_final = round(preco_base * (1 - desc_pct / 100.0), 2) if preco_base is not None else None
        subtotal = round(preco_final * quantidade, 2) if (preco_final is not None and quantidade is not None) else None

        # 3. Produtores aptos e bloqueados
        aptos, bloqueados, alertas_prod = _buscar_produtores(nome_cat, exige_organico, exige_sie, data_referencia)
        alertas.extend(alertas_prod)

        tem_critico = any(a["severidade"] == "critico" and a["codigo"] != "CERTIFICACAO_VENCIDA" for a in alertas) or not aptos
        status_item = "indisponivel" if disp_safra == "nenhuma" else ("parcial" if (quantidade is None or tem_critico or disp_safra == "baixa") else "viavel")

        return _resposta_ok({
            "produto_mencionado": produto, "produto_catalogo": nome_cat, "quantidade": quantidade, "unidade": item_p["unidade"],
            "exige_organico": exige_organico, "status_item": status_item, "disponibilidade_safra": disp_safra,
            "preco_unitario": preco_final, "desconto_atacado_pct": desc_pct, "subtotal_estimado": subtotal,
            "limite_semanal": limite_sem, "produtores_aptos": aptos, "produtores_bloqueados": bloqueados,
            "observacao": obs_unificada or None, "alertas": alertas,
        })
    except EntradaInvalida as exc:
        return _resposta_falha("entrada_invalida", str(exc))
    except OSError as exc:
        return _resposta_falha("erro", f"Falha ao acessar os dados da cooperativa: {exc}")
    except Exception as exc:  # noqa: BLE001 - a tool nunca deve derrubar o agente
        return _resposta_falha("erro", f"Erro inesperado na avaliação do item: {exc}")


def consultar_produtores_ou_organicos(
    termo_busca_produtor: Optional[str] = None,
    apenas_listar_organicos_vigentes: bool = False,
    data_referencia: str = DATA_REFERENCIA_PADRAO,
) -> dict[str, Any]:
    """Identifica produtor cooperado (por nome, telefone, município ou produto, sem expor CPF/PIX) ou lista todo o catálogo orgânico vigente."""
    try:
        dt_ref = _validar_data(data_referencia)
        produtores = _ler_csv(DADOS_DIR / "produtores.csv", filtrar_lgpd=True)

        if apenas_listar_organicos_vigentes:
            organicos = []
            for p in produtores:
                val = (p.get("validade_certificacao") or "").strip()
                if _norm(p.get("status", "")) == "ativo" and _norm(p.get("certificacao_organica", "")) == "sim" and val and date.fromisoformat(val) >= dt_ref:
                    organicos.append({"id": p["id"], "nome": p["nome_completo"], "municipio": p["municipio"], "produtos": p["produtos"], "validade_certificacao": val})
            if not organicos:
                return _resposta_falha("nao_encontrado", f"Nenhum produtor com certificação orgânica vigente encontrado na data {data_referencia}.")
            return _resposta_ok({"data_referencia": data_referencia, "produtores_organicos_vigentes": organicos})

        q = _norm(termo_busca_produtor or "")
        encontrados = [p for p in produtores if q in _norm(" ".join(p.values()))]
        if not encontrados:
            return _resposta_falha("nao_encontrado", f"Nenhum produtor encontrado para o termo '{termo_busca_produtor}'.")
        return _resposta_ok({"termo_busca": termo_busca_produtor, "produtores_encontrados": encontrados})
    except EntradaInvalida as exc:
        return _resposta_falha("entrada_invalida", str(exc))
    except OSError as exc:
        return _resposta_falha("erro", f"Falha ao acessar o cadastro de produtores: {exc}")
    except Exception as exc:  # noqa: BLE001 - a tool nunca deve derrubar o agente
        return _resposta_falha("erro", f"Erro inesperado na consulta de produtores: {exc}")


def realizar_triagem_completa_pedido(
    remetente_identificado: str,
    tipo_cliente: str,
    tipo_demanda: TipoDemanda,
    itens: list[ItemPedidoInput],
    id_pedido: Optional[str] = None,
    canal: Optional[str] = None,
    data_referencia: str = DATA_REFERENCIA_PADRAO,
    mes_entrega: Optional[int] = None,
    urgente_no_texto: bool = False,
    exige_organico_global: bool = False,
    solicita_dados_sensiveis: bool = False,
    termo_identificacao_produtor: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Executa a triagem completa do pedido, valida itens nos CSVs e salva o TriagemPedidoOutput em session.state['resultado_triagem'].

    Deixe `quantidade` dos itens e `mes_entrega` como None enquanto o cliente não os informar; consulte `campos_pendentes` no retorno.
    """
    try:
        _validar_data(data_referencia)
        _validar_mes(mes_entrega)
        tipo_demanda = _normalizar_tipo_demanda(tipo_demanda)
        exige_sie = _norm(tipo_cliente) in {"pnae", "supermercado", "atacado", "hotel", "hospital", "sesc", "institucional", "exportadora"}
        itens_triados, alertas_gerais, total = [], [], 0.0
        campos_pendentes: list[str] = []

        if solicita_dados_sensiveis:
            alertas_gerais.append({"codigo": "SOLICITACAO_DADOS_SENSIVEIS", "severidade": "critico", "mensagem": "Solicitação de CPF ou dados bancários bloqueada por política de privacidade (LGPD)."})

        prod_id = None
        if termo_identificacao_produtor or tipo_demanda == "comunicacao_produtor":
            achados = consultar_produtores_ou_organicos(termo_identificacao_produtor or remetente_identificado, data_referencia=data_referencia)
            if achados["status"] in {"entrada_invalida", "erro"}:
                return achados
            if achados["status"] == "ok" and achados["dados"]["produtores_encontrados"]:
                prod_id = achados["dados"]["produtores_encontrados"][0]["id"]

        for raw_it in itens:
            it = raw_it.model_dump() if hasattr(raw_it, "model_dump") else dict(raw_it)
            prod_menc = it.get("produto_mencionado", "")
            qtd = it.get("quantidade")
            exige_org_item = bool(it.get("exige_organico", False) or exige_organico_global)
            res = avaliar_item_catalogo(
                produto=prod_menc,
                quantidade=float(qtd) if qtd is not None else None,
                unidade=it.get("unidade"),
                exige_organico=exige_org_item,
                exige_sie=exige_sie,
                mes_entrega=mes_entrega,
                data_referencia=data_referencia,
            )
            if res["status"] in {"entrada_invalida", "erro"}:
                return res
            if res["status"] == "nao_encontrado":
                alertas_gerais.append({
                    "codigo": "PRODUTO_NAO_ENCONTRADO",
                    "severidade": "atencao",
                    "produto_relacionado": prod_menc,
                    "mensagem": res["mensagem"] or f"'{prod_menc}' não encontrado no catálogo.",
                })
                itens_triados.append({
                    "produto_mencionado": prod_menc,
                    "quantidade": float(qtd) if qtd is not None else None,
                    "unidade": it.get("unidade"),
                    "exige_organico": exige_org_item,
                    "status_item": "nao_encontrado",
                })
                continue
            item_dados = dict(res["dados"])
            alertas_gerais.extend(item_dados.pop("alertas", []))
            total = round(total + float(item_dados.get("subtotal_estimado") or 0.0), 2)
            itens_triados.append(item_dados)
            if item_dados.get("produto_catalogo") and item_dados.get("quantidade") is None and "quantidade" not in campos_pendentes:
                campos_pendentes.append("quantidade")

        if itens_triados and tipo_demanda in DEMANDAS_COM_ENTREGA and mes_entrega is None:
            campos_pendentes.append("prazo_entrega")
            alertas_gerais.append({"codigo": "PRAZO_NAO_INFORMADO", "severidade": "atencao", "mensagem": "Prazo de entrega não informado. A safra do mês atual é apenas prévia; pergunte ao cliente para quando deseja a entrega."})

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
        elif "ambiguo" in status_itens or campos_pendentes:
            status_viab = "requer_esclarecimento"
        elif status_itens == {"viavel"}:
            status_viab = "viavel"
        elif status_itens == {"indisponivel"}:
            status_viab = "inviavel"
        else:
            status_viab = "parcialmente_viavel"

        pendentes_txt = f" | Pendentes: {', '.join(campos_pendentes)}" if campos_pendentes else ""
        saida = {
            "id_pedido": id_pedido, "canal": canal, "remetente_identificado": remetente_identificado,
            "produtor_remetente_id": prod_id, "tipo_cliente": tipo_cliente, "tipo_demanda": tipo_demanda,
            "urgencia": urgencia, "status_viabilidade": status_viab, "data_referencia": data_referencia,
            "mes_entrega": mes_entrega, "campos_pendentes": campos_pendentes, "itens": itens_triados, "valor_total_estimado": round(total, 2),
            "alertas_operacionais": alertas_gerais, "modulos_recomendados": modulos,
            "resumo_executivo_triagem": f"[{urgencia.upper()}] {remetente_identificado} ({tipo_demanda}) -> Status: {status_viab} | Total estimado: R$ {total:.2f} | Alertas: {len(alertas_gerais)}{pendentes_txt}",
        }
        saida = TriagemPedidoOutput(**saida).model_dump()
        if tool_context is not None and hasattr(tool_context, "state"):
            tool_context.state["resultado_triagem"] = saida
        return _resposta_ok(saida)
    except EntradaInvalida as exc:
        return _resposta_falha("entrada_invalida", str(exc))
    except OSError as exc:
        return _resposta_falha("erro", f"Falha ao acessar os dados da cooperativa: {exc}")
    except Exception as exc:  # noqa: BLE001 - a tool nunca deve derrubar o agente
        return _resposta_falha("erro", f"Erro inesperado na triagem do pedido: {exc}")


LISTA_TOOLS_TRIAGEM = [avaliar_item_catalogo, consultar_produtores_ou_organicos, realizar_triagem_completa_pedido]

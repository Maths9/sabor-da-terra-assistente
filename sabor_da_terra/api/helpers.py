"""Funções auxiliares de formatação e extração de dados para a API HTTP."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sabor_da_terra.config import DADOS_DIR
from sabor_da_terra.seguranca import sanitizar_pii_texto
from sabor_da_terra.tools import ler_csv


def _fmt_brl(valor: str | Decimal) -> str:
    dec = Decimal(str(valor or "0.00")).quantize(Decimal("0.01"))
    inteiro, frac = f"{dec:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{frac}"


def _fmt_data_br(data_iso: str | None) -> str:
    if not data_iso:
        return "—"
    try:
        return date.fromisoformat(data_iso[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return data_iso


def extrair_fontes_dos_eventos(events: list[Any]) -> list[dict[str, Any]]:
    """Extrai fontes documentais retornadas por consultar_documentos no turno atual."""
    fontes: list[dict[str, Any]] = []
    vistos: set[tuple[str, str]] = set()

    for event in events:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            fn_resp = getattr(part, "function_response", None)
            if not fn_resp or getattr(fn_resp, "name", None) != "consultar_documentos":
                continue
            payload = getattr(fn_resp, "response", None) or {}
            dados = payload.get("dados") if isinstance(payload, dict) else None
            if not isinstance(dados, dict):
                continue
            for fonte in dados.get("fontes") or []:
                if not isinstance(fonte, dict):
                    continue
                chave = (
                    str(fonte.get("documento_id") or ""),
                    str(fonte.get("localizacao") or ""),
                )
                if chave in vistos:
                    continue
                vistos.add(chave)
                fontes.append(fonte)

    return fontes


def extrair_texto_final(events: list[Any]) -> str:
    """Extrai o texto final voltado ao usuário, ignorando blocos de pensamento."""
    candidatos_finais: list[str] = []
    todos_textos: list[str] = []

    for event in events:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        textos_evento = [
            part.text
            for part in parts
            if getattr(part, "text", None) and not getattr(part, "thought", False)
        ]
        if not textos_evento:
            continue
        bloco = "\n".join(textos_evento).strip()
        if not bloco:
            continue
        todos_textos.append(bloco)
        is_final = getattr(event, "is_final_response", None)
        if callable(is_final) and is_final():
            candidatos_finais.append(bloco)

    texto_bruto = (
        candidatos_finais[-1]
        if candidatos_finais
        else (todos_textos[-1] if todos_textos else "")
    )
    return sanitizar_pii_texto(
        texto_bruto, mascarar_contato=False, mascarar_endereco=False
    )


def _formatar_ts_evento(event: Any) -> str:
    ts = getattr(event, "timestamp", None)
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def extrair_mensagens_dos_eventos(events: list[Any]) -> list[dict[str, Any]]:
    """Reconstrói o histórico conversacional (user/assistant) a partir dos eventos ADK."""
    mensagens: list[dict[str, Any]] = []
    turn_fontes: list[dict[str, Any]] = []
    turn_fontes_keys: set[tuple[str, str]] = set()
    assist_text: Optional[str] = None
    assist_id: Optional[str] = None
    assist_ts: Optional[str] = None

    def _flush_assistant() -> None:
        nonlocal assist_text, assist_id, assist_ts, turn_fontes, turn_fontes_keys
        if assist_text:
            mensagens.append(
                {
                    "id": assist_id or f"msg-{len(mensagens) + 1}",
                    "role": "assistant",
                    "content": sanitizar_pii_texto(
                        assist_text,
                        mascarar_contato=False,
                        mascarar_endereco=False,
                    ),
                    "timestamp": assist_ts or datetime.now(timezone.utc).isoformat(),
                    "fontes": list(turn_fontes),
                }
            )
        assist_text = None
        assist_id = None
        assist_ts = None
        turn_fontes = []
        turn_fontes_keys = set()

    for idx, event in enumerate(events or []):
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        if not parts:
            continue

        author = str(getattr(event, "author", "") or "")
        textos = [
            p.text
            for p in parts
            if getattr(p, "text", None) and not getattr(p, "thought", False)
        ]
        bloco = "\n".join(textos).strip()
        has_fn_resp = any(getattr(p, "function_response", None) is not None for p in parts)
        has_fn_call = any(getattr(p, "function_call", None) is not None for p in parts)

        if author == "user" and bloco and not has_fn_resp:
            _flush_assistant()
            mensagens.append(
                {
                    "id": str(getattr(event, "id", None) or f"user-{idx}"),
                    "role": "user",
                    "content": sanitizar_pii_texto(
                        bloco,
                        mascarar_contato=False,
                        mascarar_endereco=False,
                        mascarar_agencia_isolada=False,
                    ),
                    "timestamp": _formatar_ts_evento(event),
                    "fontes": [],
                }
            )
            continue

        for fonte in extrair_fontes_dos_eventos([event]):
            chave = (
                str(fonte.get("documento_id") or ""),
                str(fonte.get("localizacao") or ""),
            )
            if chave not in turn_fontes_keys:
                turn_fontes_keys.add(chave)
                turn_fontes.append(fonte)

        if bloco and not has_fn_call and not has_fn_resp:
            assist_text = bloco
            assist_id = str(getattr(event, "id", None) or f"assist-{idx}")
            assist_ts = _formatar_ts_evento(event)

    _flush_assistant()
    return mensagens


def listar_produtores_publicos() -> list[dict[str, Any]]:
    """Lista produtores cooperados sem campos pessoais ou sensíveis (LGPD)."""
    linhas = ler_csv(DADOS_DIR / "produtores.csv", remover_contato=True)
    resultado = []
    for row in linhas:
        resultado.append(
            {
                "id": row["id"],
                "nome": row["nome_completo"],
                "municipio": row["municipio"],
                "produtos": [
                    p.strip() for p in (row.get("produtos") or "").split(",") if p.strip()
                ],
                "status": row.get("status", ""),
                "certificacao_organica": row.get("certificacao_organica", ""),
                "validade_certificacao": row.get("validade_certificacao") or None,
            }
        )
    return sorted(resultado, key=lambda x: x["id"])


def formatar_painel_produtor(dados: dict[str, Any]) -> dict[str, Any]:
    """Converte saída de obter_resumo_produtor no formato ProducerProfile do frontend."""
    status_raw = str(dados.get("status_cadastro") or "").lower()
    situacao = (
        "Ativo"
        if status_raw == "ativo"
        else ("Inativo" if status_raw == "inativo" else "Pendente")
    )

    comp = dados.get("compliance") or {}
    cert = comp.get("certificacao_organica") or {}
    cert_sit = cert.get("situacao", "nao_possui")
    val_iso = cert.get("validade")
    data_ref = date.fromisoformat(dados["data_referencia"])
    dias_restantes = (
        (date.fromisoformat(val_iso) - data_ref).days if val_iso else 0
    )

    pendencias = dados.get("pendencias_financeiras") or []
    itens_pend = [
        {
            "descricao": f"{p.get('produto', '')} · {p.get('comprador', '')}",
            "valor": _fmt_brl(p.get("valor", "0.00")),
            "previsao": (
                f"venc. {_fmt_data_br(p.get('data_vencimento'))}"
                if p.get("data_vencimento")
                else "a definir"
            ),
        }
        for p in pendencias
    ]

    transacoes = sorted(
        dados.get("transacoes_periodo") or [],
        key=lambda t: t.get("data", ""),
        reverse=True,
    )
    movimentacoes = [
        {
            "data": _fmt_data_br(t.get("data"))[:5],
            "descricao": (
                f"{t.get('produto', '')} ({t.get('quantidade', 0):g} {t.get('unidade', 'kg')}) — "
                f"{t.get('comprador', '')} [{t.get('status_pagamento', '')}]"
            ),
            "valor": f"+ {_fmt_brl(t.get('valor_total', '0.00'))}",
        }
        for t in transacoes[:6]
    ]

    avisos: list[dict[str, str]] = []
    if cert_sit == "vencida":
        avisos.append(
            {
                "id": "cert-vencida",
                "texto": f"Certificação orgânica vencida em {_fmt_data_br(val_iso)}.",
                "nivel": "atencao",
            }
        )
    elif cert_sit == "vence_em_breve":
        avisos.append(
            {
                "id": "cert-breve",
                "texto": f"Certificação orgânica vence em {dias_restantes} dias ({_fmt_data_br(val_iso)}).",
                "nivel": "atencao",
            }
        )
    sie = comp.get("sie") or {}
    if sie.get("situacao") in {"sem_sie", "pendente"}:
        avisos.append(
            {
                "id": "sie-status",
                "texto": str(sie.get("detalhe") or "Restrição de SIE."),
                "nivel": "atencao",
            }
        )
    if Decimal(str(dados.get("total_vencido") or "0.00")) > Decimal("0.00"):
        avisos.append(
            {
                "id": "fin-vencido",
                "texto": f"Há {_fmt_brl(dados['total_vencido'])} em repasses/títulos vencidos no período.",
                "nivel": "atencao",
            }
        )
    if not avisos:
        avisos.append(
            {
                "id": "cadastro-ok",
                "texto": "Cadastro regular na cooperativa sem alertas críticos no período.",
                "nivel": "info",
            }
        )

    return {
        "codigo": dados["produtor_id"],
        "nome": dados["nome"],
        "municipio": dados["municipio"],
        "situacaoCadastral": situacao,
        "produtos": dados.get("produtos") or [],
        "certificacao": {
            "tipo": "Orgânica (IBD/Ecocert)" if val_iso else "Não possui certificação orgânica",
            "situacao": cert_sit,
            "validade": _fmt_data_br(val_iso),
            "diasRestantes": dias_restantes,
        },
        "pagamentosPendentes": {
            "total": _fmt_brl(dados.get("total_pendente") or "0.00"),
            "itens": itens_pend,
        },
        "movimentacoes": movimentacoes,
        "avisos": avisos,
    }

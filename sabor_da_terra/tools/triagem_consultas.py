"""Consulta de produtores por termo/pista e listagem de orgânicos vigentes."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sabor_da_terra.config import DADOS_DIR
from sabor_da_terra.seguranca import norm_texto
from sabor_da_terra.tools.comum import (
    DATA_REFERENCIA_PADRAO,
    EntradaInvalida,
    ler_csv,
    resposta,
    validar_data,
)


def consultar_produtores_ou_organicos(
    termo_busca_produtor: Optional[str] = None,
    apenas_listar_organicos_vigentes: bool = False,
    data_referencia: str = DATA_REFERENCIA_PADRAO,
) -> dict[str, Any]:
    """Identifica produtor cooperado (por nome, telefone, município ou produto, sem expor CPF/PIX) ou lista todo o catálogo orgânico vigente."""
    try:
        dt_ref = validar_data(data_referencia)
        produtores = ler_csv(
            DADOS_DIR / "produtores.csv", filtrar_lgpd=True, remover_contato=False
        )

        if apenas_listar_organicos_vigentes:
            organicos = []
            for p in produtores:
                val = (p.get("validade_certificacao") or "").strip()
                if (
                    norm_texto(p.get("status", "")) == "ativo"
                    and norm_texto(p.get("certificacao_organica", "")) == "sim"
                    and val
                    and date.fromisoformat(val) >= dt_ref
                ):
                    organicos.append(
                        {
                            "id": p["id"],
                            "nome": p["nome_completo"],
                            "municipio": p["municipio"],
                            "produtos": p["produtos"],
                            "validade_certificacao": val,
                        }
                    )
            if not organicos:
                return resposta(
                    "nao_encontrado",
                    mensagem=(
                        "Nenhum produtor com certificação orgânica vigente encontrado na data "
                        f"{data_referencia}."
                    ),
                )
            return resposta(
                "ok",
                dados={
                    "data_referencia": data_referencia,
                    "produtores_organicos_vigentes": organicos,
                },
            )

        q = norm_texto(termo_busca_produtor or "")
        encontrados = [p for p in produtores if q in norm_texto(" ".join(p.values()))]
        if not encontrados:
            return resposta(
                "nao_encontrado",
                mensagem=f"Nenhum produtor encontrado para o termo '{termo_busca_produtor}'.",
            )
        return resposta(
            "ok",
            dados={"termo_busca": termo_busca_produtor, "produtores_encontrados": encontrados},
        )
    except EntradaInvalida as exc:
        return resposta("entrada_invalida", mensagem=str(exc))
    except OSError as exc:
        return resposta("erro", mensagem=f"Falha ao acessar o cadastro de produtores: {exc}")
    except Exception as exc:  # noqa: BLE001 - a tool nunca deve derrubar o agente
        return resposta("erro", mensagem=f"Erro inesperado na consulta de produtores: {exc}")

"""Script enxuto de validação offline do Módulo de Triagem (Sem Gasto de Tokens)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.tools import FunctionTool
from sabor_da_terra.tools import (
    LISTA_TOOLS_TRIAGEM,
    TriagemPedidoOutput,
    avaliar_item_catalogo,
    consultar_produtores_ou_organicos,
    realizar_triagem_completa_pedido,
)


def main() -> None:
    print("=== 0. TESTE DE COMPATIBILIDADE DAS TOOLS COM O GOOGLE ADK 2.x ===")
    for fn in LISTA_TOOLS_TRIAGEM:
        ft = FunctionTool(fn)
        decl = ft._get_declaration()
        assert decl is not None and decl.name == fn.__name__
        print(f"[OK] FunctionDeclaration gerada pelo ADK para: {decl.name}")

    print("\n=== 1. TESTE DE TOOLS INDIVIDUAIS E REGRAS DOS CSVs ===")

    # 1.1 Ambiguidade detectada dinamicamente pelo CSV ("goiaba" -> extra vs especial)
    res_goiaba = avaliar_item_catalogo("goiaba", 100, "kg")
    assert res_goiaba["status"] == "ok"
    dados_goiaba = res_goiaba["dados"]
    assert dados_goiaba["status_item"] == "ambiguo"
    print("[OK] Ambiguidade automática em 'goiaba':", dados_goiaba["opcoes_catalogo"])

    # 1.2 Entressafra em outubro vs safra baixa em novembro ("cajá" do PED-2026-007)
    res_caja_out = avaliar_item_catalogo("cajá", 10, "kg", mes_entrega=10)
    res_caja_nov = avaliar_item_catalogo("cajá", 10, "kg", mes_entrega=11)
    assert res_caja_out["status"] == "ok" and res_caja_nov["status"] == "ok"
    dados_caja_out, dados_caja_nov = res_caja_out["dados"], res_caja_nov["dados"]
    assert dados_caja_out["disponibilidade_safra"] == "nenhuma"
    assert dados_caja_nov["disponibilidade_safra"] == "baixa"
    print("[OK] Sazonalidade dinâmica de 'cajá': Outubro=", dados_caja_out["disponibilidade_safra"], "| Novembro=", dados_caja_nov["disponibilidade_safra"])

    # 1.3 Capacidade semanal lida de `observacao` ("ovos caipira" 200 dz > 120 dz/semana)
    res_ovos = avaliar_item_catalogo("ovos caipira", 200, "dúzia")
    assert res_ovos["status"] == "ok"
    dados_ovos = res_ovos["dados"]
    codigos_ovos = {a["codigo"] for a in dados_ovos["alertas"]}
    assert "ACIMA_DA_CAPACIDADE" in codigos_ovos
    print("[OK] Limite semanal de 'ovos caipira' extraído do CSV:", dados_ovos["limite_semanal"])

    # 1.4 Bloqueio de P008 (Josefa) com certificação vencida em 2026-09-30 e zero vazamento de CPF
    res_mel = avaliar_item_catalogo("mel silvestre", 20, "kg", exige_organico=True, data_referencia="2026-10-28")
    assert res_mel["status"] == "ok"
    dados_mel = res_mel["dados"]
    assert any("P008" in b for b in dados_mel["produtores_bloqueados"])
    assert not any("P008" in a for a in dados_mel["produtores_aptos"])
    print("[OK] P008 bloqueada em pedido orgânico de mel silvestre. Aptos:", dados_mel["produtores_aptos"])

    # 1.5 Identificação de Seu Cícero (P003) por pista de município ("Caetés") sem expor CPF/PIX
    res_cicero = consultar_produtores_ou_organicos(termo_busca_produtor="Caetés")
    assert res_cicero["status"] == "ok"
    dados_cicero = res_cicero["dados"]
    serializado = json.dumps(dados_cicero, ensure_ascii=False).lower()
    assert "P003" in [p["id"] for p in dados_cicero["produtores_encontrados"]]
    assert "cpf" not in serializado and "chave_pix" not in serializado
    print("[OK] Produtor P003 (Seu Cícero) identificado sem expor CPF/PIX.")

    print("\n=== 2. TESTE DE TRIAGEM COMPLETA + VALIDAÇÃO PYDANTIC (PED-2026-004 PNAE) ===")
    triagem_pnae = realizar_triagem_completa_pedido(
        id_pedido="PED-2026-004",
        canal="email",
        remetente_identificado="Prefeitura de Garanhuns - PNAE",
        tipo_cliente="PNAE",
        tipo_demanda="pedido_compra",
        data_referencia="2026-10-28",
        mes_entrega=11,
        itens=[
            {"produto_mencionado": "banana prata", "quantidade": 200, "unidade": "kg"},
            {"produto_mencionado": "goiaba", "quantidade": 100, "unidade": "kg"},
            {"produto_mencionado": "macaxeira", "quantidade": 150, "unidade": "kg"},
            {"produto_mencionado": "mel silvestre", "quantidade": 20, "unidade": "kg", "exige_organico": True},
            {"produto_mencionado": "ovos caipira", "quantidade": 100, "unidade": "dúzia"},
        ],
    )
    assert triagem_pnae["status"] == "ok"
    validado = TriagemPedidoOutput.model_validate(triagem_pnae["dados"])
    print("[OK] TriagemPedidoOutput validado:", validado.resumo_executivo_triagem)
    print("     Alertas:", [a.codigo for a in validado.alertas_operacionais])
    print("     Módulos recomendados:", validado.modulos_recomendados)


if __name__ == "__main__":
    main()

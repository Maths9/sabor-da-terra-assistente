"""Script enxuto de validação offline do Módulo de Triagem (Sem Gasto de Tokens)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.tools import FunctionTool
from sabor_da_terra.schemas_triagem import TriagemPedidoOutput
from sabor_da_terra.tools_triagem import (
    LISTA_TOOLS_TRIAGEM,
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
    assert res_goiaba["status_item"] == "ambiguo"
    print("[OK] Ambiguidade automática em 'goiaba':", res_goiaba["opcoes_catalogo"])

    # 1.2 Entressafra em outubro vs safra baixa em novembro ("cajá" do PED-2026-007)
    res_caja_out = avaliar_item_catalogo("cajá", 10, "kg", mes_entrega=10)
    res_caja_nov = avaliar_item_catalogo("cajá", 10, "kg", mes_entrega=11)
    assert res_caja_out["disponibilidade_safra"] == "nenhuma"
    assert res_caja_nov["disponibilidade_safra"] == "baixa"
    print("[OK] Sazonalidade dinâmica de 'cajá': Outubro=", res_caja_out["disponibilidade_safra"], "| Novembro=", res_caja_nov["disponibilidade_safra"])

    # 1.3 Capacidade semanal lida de `observacao` ("ovos caipira" 200 dz > 120 dz/semana)
    res_ovos = avaliar_item_catalogo("ovos caipira", 200, "dúzia")
    codigos_ovos = {a["codigo"] for a in res_ovos["alertas"]}
    assert "ACIMA_DA_CAPACIDADE" in codigos_ovos
    print("[OK] Limite semanal de 'ovos caipira' extraído do CSV:", res_ovos["limite_semanal"])

    # 1.4 Bloqueio de P008 (Josefa) com certificação vencida em 2026-09-30 e zero vazamento de CPF
    res_mel = avaliar_item_catalogo("mel silvestre", 20, "kg", exige_organico=True, data_referencia="2026-10-28")
    assert any("P008" in b for b in res_mel["produtores_bloqueados"])
    assert not any("P008" in a for a in res_mel["produtores_aptos"])
    print("[OK] P008 bloqueada em pedido orgânico de mel silvestre. Aptos:", res_mel["produtores_aptos"])

    # 1.5 Identificação de Seu Cícero (P003) por pista de município ("Caetés") sem expor CPF/PIX
    res_cicero = consultar_produtores_ou_organicos(termo_busca_produtor="Caetés")
    serializado = json.dumps(res_cicero, ensure_ascii=False).lower()
    assert "P003" in [p["id"] for p in res_cicero["produtores_encontrados"]]
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
    validado = TriagemPedidoOutput.model_validate(triagem_pnae)
    print("[OK] TriagemPedidoOutput validado:", validado.resumo_executivo_triagem)
    print("     Alertas:", [a.codigo for a in validado.alertas_operacionais])
    print("     Módulos recomendados:", validado.modulos_recomendados)


if __name__ == "__main__":
    main()

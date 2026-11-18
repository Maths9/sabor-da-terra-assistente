"""Script e funções idempotentes de carga dos dados operacionais (CSVs e JSON) para o PostgreSQL/SQLAlchemy."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from sabor_da_terra.config import DADOS_DIR, TABELA_PRECOS_VIGENCIA_PADRAO
from sabor_da_terra.database.connection import get_engine, session_scope
from sabor_da_terra.database.crypto import cifrar_valor_sensivel
from sabor_da_terra.database.models import (
    Base,
    LoteModel,
    PedidoModel,
    PrecoModel,
    ProdutorModel,
    SazonalidadeModel,
    TransacaoFinanceiraModel,
)
from sabor_da_terra.seguranca import norm_texto

_MESES_NOME_PARA_NUM = {
    "janeiro": "01",
    "fevereiro": "02",
    "marco": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}


def _ler_linhas_csv(caminho: Path) -> list[dict[str, str]]:
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo de dados não encontrado: {caminho}")
    with caminho.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _parse_data_opcional(valor: Optional[str]) -> Optional[date]:
    limpo = (valor or "").strip()
    if not limpo:
        return None
    return date.fromisoformat(limpo[:10])


def _parse_decimal_opcional(valor: Optional[str]) -> Optional[Decimal]:
    limpo = (valor or "").strip()
    if not limpo or norm_texto(limpo) == "n/d":
        return None
    return Decimal(limpo).quantize(Decimal("0.01"))


def _extrair_vigencia_nome_arquivo(caminho: Path) -> str:
    nome = norm_texto(caminho.stem)
    m_iso = re.search(r"(20\d{2})[_-](\d{2})", nome)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}"
    for mes_nome, mes_num in _MESES_NOME_PARA_NUM.items():
        m_ext = re.search(rf"{mes_nome}[_-](20\d{{2}})", nome)
        if m_ext:
            return f"{m_ext.group(1)}-{mes_num}"
    return TABELA_PRECOS_VIGENCIA_PADRAO


def _importar_produtores(session: Session, dados_dir: Path) -> int:
    linhas = _ler_linhas_csv(dados_dir / "produtores.csv")
    total = 0
    for row in linhas:
        pid = row["id"].strip().upper()
        cpf_bruto = (row.get("cpf") or "").strip()
        if not cpf_bruto:
            raise ValueError(f"Produtor {pid} sem CPF informado para criptografia.")

        modelo = ProdutorModel(
            id=pid,
            nome_completo=row["nome_completo"].strip(),
            municipio=row["municipio"].strip(),
            produtos=row["produtos"].strip(),
            certificacao_organica=norm_texto(row.get("certificacao_organica", "")) == "sim",
            validade_certificacao=_parse_data_opcional(row.get("validade_certificacao")),
            status=norm_texto(row.get("status", "ativo")) or "ativo",
            telefone=(row.get("telefone") or "").strip() or None,
            email=(row.get("email") or "").strip() or None,
            endereco=(row.get("endereco") or "").strip() or None,
            banco=(row.get("banco") or "").strip() or None,
            agencia=(row.get("agencia") or "").strip() or None,
            cpf_cifrado=cifrar_valor_sensivel(cpf_bruto) or "",
            data_nascimento_cifrada=cifrar_valor_sensivel(row.get("data_nascimento")),
            chave_pix_cifrada=cifrar_valor_sensivel(row.get("chave_pix")),
            conta_corrente_cifrada=cifrar_valor_sensivel(row.get("conta_corrente")),
        )
        session.merge(modelo)
        total += 1
    session.flush()
    return total


def _importar_sazonalidade(session: Session, dados_dir: Path) -> int:
    linhas = _ler_linhas_csv(dados_dir / "sazonalidade.csv")
    total = 0
    for row in linhas:
        modelo = SazonalidadeModel(
            produto=row["produto"].strip(),
            jan=norm_texto(row["jan"]),
            fev=norm_texto(row["fev"]),
            mar=norm_texto(row["mar"]),
            abr=norm_texto(row["abr"]),
            mai=norm_texto(row["mai"]),
            jun=norm_texto(row["jun"]),
            jul=norm_texto(row["jul"]),
            ago=norm_texto(row["ago"]),
            set=norm_texto(row["set"]),
            out=norm_texto(row["out"]),
            nov=norm_texto(row["nov"]),
            dez=norm_texto(row["dez"]),
            observacao=(row.get("observacao") or "").strip() or None,
        )
        session.merge(modelo)
        total += 1
    session.flush()
    return total


def _importar_precos(session: Session, dados_dir: Path) -> int:
    arquivos = sorted(dados_dir.glob("tabela_precos_*.csv"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhuma tabela_precos_*.csv encontrada em {dados_dir}")

    total = 0
    for arq in arquivos:
        vigencia = _extrair_vigencia_nome_arquivo(arq)
        linhas = _ler_linhas_csv(arq)
        existentes = {
            p.produto: p
            for p in session.scalars(
                select(PrecoModel).where(PrecoModel.vigencia == vigencia)
            ).all()
        }
        for row in linhas:
            nome_prod = row["produto"].strip()
            registro = existentes.get(nome_prod)
            if registro is None:
                registro = PrecoModel(vigencia=vigencia, produto=nome_prod)
                session.add(registro)

            registro.unidade = (row.get("unidade") or "kg").strip()
            registro.preco_convencional = _parse_decimal_opcional(row.get("preco_convencional"))
            registro.preco_organico = _parse_decimal_opcional(row.get("preco_organico"))
            registro.desconto_atacado_pct = Decimal(
                (row.get("desconto_atacado_pct") or "0").strip()
            ).quantize(Decimal("0.01"))
            registro.volume_minimo_atacado_kg = Decimal(
                (row.get("volume_minimo_atacado_kg") or "0").strip()
            ).quantize(Decimal("0.01"))
            registro.observacao = (row.get("observacao") or "").strip() or None
            total += 1
    session.flush()
    return total


def _importar_pedidos(session: Session, dados_dir: Path) -> int:
    caminho = dados_dir / "pedidos.json"
    if not caminho.is_file():
        raise FileNotFoundError(f"Arquivo pedidos.json não encontrado em {dados_dir}")
    itens = json.loads(caminho.read_text(encoding="utf-8"))
    total = 0
    for item in itens:
        dt_rec = datetime.fromisoformat(str(item["data_recebimento"]).strip())
        modelo = PedidoModel(
            id=str(item["id"]).strip().upper(),
            data_recebimento=dt_rec,
            canal=str(item["canal"]).strip(),
            remetente=str(item["remetente"]).strip(),
            comprador=str(item["comprador"]).strip(),
            mensagem_original=str(item["mensagem_original"]),
            status=norm_texto(item.get("status", "pendente")) or "pendente",
        )
        session.merge(modelo)
        total += 1
    session.flush()
    return total


def _importar_lotes(
    session: Session, dados_dir: Path, produtores_ids: set[str]
) -> int:
    linhas = _ler_linhas_csv(dados_dir / "lotes.csv")
    total = 0
    for row in linhas:
        lote_id = row["lote_id"].strip().upper()
        pid = row["produtor_id"].strip().upper()
        if pid not in produtores_ids:
            raise ValueError(
                f"Lote {lote_id} referencia produtor_id '{pid}' inexistente em produtores."
            )
        dt_colheita = _parse_data_opcional(row.get("data_colheita"))
        dt_entrega = _parse_data_opcional(row.get("data_entrega"))
        dt_validade = _parse_data_opcional(row.get("validade"))
        if not dt_colheita or not dt_entrega or not dt_validade:
            raise ValueError(f"Lote {lote_id} possui datas obrigatórias ausentes.")

        modelo = LoteModel(
            lote_id=lote_id,
            data_colheita=dt_colheita,
            data_entrega=dt_entrega,
            produtor_id=pid,
            produto=row["produto"].strip(),
            quantidade_kg=Decimal(row["quantidade_kg"].strip()).quantize(Decimal("0.01")),
            comprador=row["comprador"].strip(),
            pedido_id=row["pedido_id"].strip(),
            temperatura_transporte_c=row["temperatura_transporte_c"].strip(),
            validade=dt_validade,
            inspecao_visual=row["inspecao_visual"].strip(),
            observacao=(row.get("observacao") or "").strip() or None,
        )
        session.merge(modelo)
        total += 1
    session.flush()
    return total


def _importar_transacoes_financeiras(
    session: Session, dados_dir: Path, produtores_ids: set[str]
) -> tuple[int, Decimal, Decimal, Decimal]:
    linhas = _ler_linhas_csv(dados_dir / "financeiro.csv")
    total = 0
    soma_total = Decimal("0.00")
    soma_pago = Decimal("0.00")
    soma_pendente = Decimal("0.00")

    for row in linhas:
        id_tx = row["id_transacao"].strip().upper()
        pid = row["produtor_id"].strip().upper()
        if pid not in produtores_ids:
            raise ValueError(
                f"Transação {id_tx} referencia produtor_id '{pid}' inexistente em produtores."
            )
        dt_venda = _parse_data_opcional(row.get("data"))
        dt_venc = _parse_data_opcional(row.get("data_vencimento"))
        if not dt_venda or not dt_venc:
            raise ValueError(f"Transação {id_tx} sem data ou data_vencimento válida.")

        qtd = Decimal(row["quantidade_kg"].strip()).quantize(Decimal("0.01"))
        v_unit = Decimal(row["valor_unitario"].strip()).quantize(Decimal("0.01"))
        v_tot = Decimal(row["valor_total"].strip()).quantize(Decimal("0.01"))
        esperado = (qtd * v_unit).quantize(Decimal("0.01"))
        if v_tot != esperado:
            raise ValueError(
                f"Inconsistência contábil em {id_tx}: valor_total={v_tot} != {qtd} * {v_unit} ({esperado})."
            )

        status_pag = norm_texto(row.get("status_pagamento", ""))
        modelo = TransacaoFinanceiraModel(
            id_transacao=id_tx,
            data=dt_venda,
            produtor_id=pid,
            comprador=row["comprador"].strip(),
            tipo=norm_texto(row.get("tipo", "venda")) or "venda",
            produto=row["produto"].strip(),
            quantidade_kg=qtd,
            valor_unitario=v_unit,
            valor_total=v_tot,
            forma_pagamento=row["forma_pagamento"].strip(),
            status_pagamento=status_pag,
            data_vencimento=dt_venc,
            data_pagamento=_parse_data_opcional(row.get("data_pagamento")),
            observacao=(row.get("observacao") or "").strip() or None,
        )
        session.merge(modelo)
        total += 1
        soma_total += v_tot
        if status_pag == "pago":
            soma_pago += v_tot
        elif status_pag == "pendente":
            soma_pendente += v_tot

    session.flush()
    return total, soma_total, soma_pago, soma_pendente


def importar_todos_os_dados(
    *,
    dados_dir: Path = DADOS_DIR,
    engine: Optional[Engine] = None,
    criar_tabelas: bool = False,
) -> dict[str, Any]:
    """Importa todos os CSVs e pedidos.json de forma transacional, validada e idempotente."""
    eng = engine or get_engine()
    if criar_tabelas:
        Base.metadata.create_all(bind=eng)

    with session_scope(eng) as session:
        with session.begin():
            n_produtores = _importar_produtores(session, dados_dir)
            produtores_ids = set(session.scalars(select(ProdutorModel.id)).all())
            n_sazonalidade = _importar_sazonalidade(session, dados_dir)
            n_precos = _importar_precos(session, dados_dir)
            n_pedidos = _importar_pedidos(session, dados_dir)
            n_lotes = _importar_lotes(session, dados_dir, produtores_ids)
            n_fin, soma_total, soma_pago, soma_pendente = _importar_transacoes_financeiras(
                session, dados_dir, produtores_ids
            )

    return {
        "status": "ok",
        "dados_dir": str(dados_dir),
        "contagens": {
            "produtores": n_produtores,
            "sazonalidade": n_sazonalidade,
            "precos": n_precos,
            "pedidos": n_pedidos,
            "lotes": n_lotes,
            "transacoes_financeiras": n_fin,
        },
        "totais_financeiros": {
            "vendas_total": f"{soma_total:.2f}",
            "total_pago": f"{soma_pago:.2f}",
            "total_pendente": f"{soma_pendente:.2f}",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa os dados operacionais da Cooperativa Sabor da Terra para o banco SQL."
    )
    parser.add_argument(
        "--dados-dir",
        type=Path,
        default=DADOS_DIR,
        help="Diretório contendo os arquivos CSV e pedidos.json (padrão: dados/).",
    )
    parser.add_argument(
        "--criar-tabelas",
        action="store_true",
        help="Cria as tabelas via SQLAlchemy metadata caso ainda não tenha rodado alembic upgrade head.",
    )
    args = parser.parse_args()
    resumo = importar_todos_os_dados(
        dados_dir=args.dados_dir.resolve(),
        criar_tabelas=args.criar_tabelas,
    )
    print(json.dumps(resumo, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

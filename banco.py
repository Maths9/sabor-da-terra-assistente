"""Banco relacional (PostgreSQL / Cloud SQL): esquema e carga dos CSV limpos.

Gera dois arquivos SQL que funcionam em qualquer PostgreSQL (psql, Cloud SQL Studio):
    db/01_esquema.sql   tabelas, chaves e restrições
    db/02_dados.sql     INSERTs com os dados limpos (sem CPF, PIX, conta, telefone nem e-mail)

Uso (na raiz do projeto, depois de `py -m sabor.limpeza`):
    py -m sabor.banco --gerar-sql                    # só gera os arquivos em db/
    py -m sabor.banco --dsn "postgresql://usuario@host/banco"   # gera e carrega (precisa de psycopg)

A senha NUNCA vai no código: use a variável PGPASSWORD ou o Secret Manager.
"""
from __future__ import annotations

import argparse
import csv
import re
from datetime import date
from pathlib import Path

from . import config

TEXTO, DATA, NUM, BOOL = "text", "date", "num", "bool"

# nome da tabela -> (arquivo CSV limpo, [(coluna, tipo SQL, tipo lógico, restrição)], restrições da tabela)
TABELAS: dict[str, dict] = {
    "produtores": {
        "csv": "produtores_publico.csv",
        "mapa": {"id": "id"},
        "colunas": [
            ("id", "TEXT", TEXTO, "PRIMARY KEY"),
            ("nome_completo", "TEXT", TEXTO, "NOT NULL"),
            ("municipio", "TEXT", TEXTO, ""),
            ("status", "TEXT", TEXTO, ""),
            ("certificacao_organica_declarada", "TEXT", TEXTO, ""),
            ("validade_certificacao", "DATE", DATA, ""),
        ],
    },
    "produtores_produtos": {
        "csv": "produtores_produtos.csv",
        "colunas": [
            ("produtor_id", "TEXT", TEXTO, "NOT NULL REFERENCES produtores(id)"),
            ("produto", "TEXT", TEXTO, "NOT NULL"),
        ],
        "extra": ["PRIMARY KEY (produtor_id, produto)"],
    },
    "restricoes_produtor": {
        "csv": "restricoes_produtor.csv",
        "colunas": [
            ("produtor_id", "TEXT", TEXTO, "PRIMARY KEY REFERENCES produtores(id)"),
            ("sie_situacao", "TEXT", TEXTO, ""),
            ("sie_registro", "TEXT", TEXTO, ""),
            ("dap_caf", "TEXT", TEXTO, ""),
            ("venda_restrita", "TEXT", TEXTO, ""),
            ("fonte", "TEXT", TEXTO, ""),
        ],
    },
    "dim_produto": {
        "csv": "dim_produto.csv",
        "colunas": [
            ("produto_canonico", "TEXT", TEXTO, "PRIMARY KEY"),
            ("unidade_padrao", "TEXT", TEXTO, ""),
            ("sinonimos", "TEXT", TEXTO, ""),
            ("variantes", "TEXT", TEXTO, ""),
        ],
    },
    "tabela_precos": {
        "csv": "tabela_precos_limpa.csv",
        "colunas": [
            ("produto", "TEXT", TEXTO, "PRIMARY KEY"),
            ("unidade", "TEXT", TEXTO, ""),
            ("preco_convencional", "NUMERIC(10,2)", NUM, ""),
            ("preco_organico", "NUMERIC(10,2)", NUM, ""),
            ("desconto_atacado_pct", "NUMERIC(5,2)", NUM, ""),
            ("volume_minimo_atacado_kg", "NUMERIC(10,2)", NUM, ""),
            ("observacao", "TEXT", TEXTO, ""),
            ("produto_base", "TEXT", TEXTO, ""),
            ("grade", "TEXT", TEXTO, ""),
            ("produtor_ref", "TEXT", TEXTO, ""),
            ("venda_direta_apenas", "BOOLEAN", BOOL, ""),
        ],
    },
    "financeiro": {
        "csv": "financeiro_limpo.csv",
        "colunas": [
            ("id_transacao", "TEXT", TEXTO, "PRIMARY KEY"),
            ("data", "DATE", DATA, "NOT NULL"),
            ("produtor_id", "TEXT", TEXTO, "NOT NULL REFERENCES produtores(id)"),
            ("produtor_nome", "TEXT", TEXTO, ""),
            ("comprador", "TEXT", TEXTO, ""),
            ("tipo", "TEXT", TEXTO, ""),
            ("produto", "TEXT", TEXTO, ""),
            ("quantidade", "NUMERIC(12,3)", NUM, ""),
            ("valor_unitario", "NUMERIC(12,2)", NUM, ""),
            ("valor_total", "NUMERIC(12,2)", NUM, "NOT NULL"),
            ("forma_pagamento", "TEXT", TEXTO, ""),
            ("status_pagamento", "TEXT", TEXTO, "NOT NULL CHECK (status_pagamento IN ('pago','pendente'))"),
            ("data_vencimento", "DATE", DATA, ""),
            ("data_pagamento", "DATE", DATA, ""),
            ("observacao", "TEXT", TEXTO, ""),
            ("unidade", "TEXT", TEXTO, ""),
        ],
    },
    "lotes": {
        "csv": "lotes_limpo.csv",
        "colunas": [
            ("lote_id", "TEXT", TEXTO, "PRIMARY KEY"),
            ("data_colheita", "DATE", DATA, ""),
            ("data_entrega", "DATE", DATA, ""),
            ("produtor_id", "TEXT", TEXTO, "NOT NULL REFERENCES produtores(id)"),
            ("produtor_nome", "TEXT", TEXTO, ""),
            ("produto", "TEXT", TEXTO, ""),
            ("quantidade", "NUMERIC(12,3)", NUM, ""),
            ("comprador", "TEXT", TEXTO, ""),
            ("pedido_id_lote", "TEXT", TEXTO, ""),
            ("validade", "DATE", DATA, ""),
            ("inspecao_visual", "TEXT", TEXTO, ""),
            ("observacao", "TEXT", TEXTO, ""),
            ("unidade", "TEXT", TEXTO, ""),
            ("temperatura_c", "NUMERIC(4,1)", NUM, ""),
            ("transporte", "TEXT", TEXTO, ""),
        ],
    },
}

# Tabela vazia para a triagem registrar pedidos (proposta: ajustar com quem faz a triagem).
# Não carrega a mensagem original, que pode conter telefone, CPF ou RG do solicitante.
DDL_PEDIDOS = """CREATE TABLE IF NOT EXISTS pedidos (
    id TEXT PRIMARY KEY,
    recebido_em TIMESTAMP NOT NULL,
    canal TEXT,
    comprador TEXT,
    itens TEXT,
    prazo_entrega DATE,
    urgencia TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    observacoes TEXT
);"""


def ddl() -> str:
    partes = ["-- Esquema do banco da Sabor da Terra (PostgreSQL). Gerado por sabor/banco.py.\n"]
    for nome in reversed(list(TABELAS)):
        partes.append(f"DROP TABLE IF EXISTS {nome};")
    partes.append("DROP TABLE IF EXISTS pedidos;\n")
    for nome, t in TABELAS.items():
        linhas = [f"    {c} {tipo} {restr}".rstrip() for c, tipo, _l, restr in t["colunas"]] + [f"    {e}" for e in t.get("extra", [])]
        partes.append(f"CREATE TABLE {nome} (\n" + ",\n".join(linhas) + "\n);\n")
    partes.append(DDL_PEDIDOS.replace("IF NOT EXISTS ", "") + "\n")
    partes.append("CREATE INDEX idx_financeiro_produtor ON financeiro (produtor_id);")
    partes.append("CREATE INDEX idx_financeiro_status ON financeiro (status_pagamento);")
    partes.append("CREATE INDEX idx_lotes_produtor ON lotes (produtor_id);")
    return "\n".join(partes) + "\n"


def _aspas(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _valor(v: str, logico: str, tabela: str, coluna: str) -> str:
    v = (v or "").strip()
    if v == "":
        return "NULL"
    if logico == DATA:
        date.fromisoformat(v)  # falha cedo se a data for inválida
        return _aspas(v)
    if logico == NUM:
        float(v)
        return v
    if logico == BOOL:
        if v.lower() not in ("true", "false"):
            raise ValueError(f"{tabela}.{coluna}: booleano inválido {v!r}")
        return v.upper()
    return _aspas(v)


def dml(pasta_clean: Path = config.DATA_CLEAN) -> tuple[str, dict[str, int]]:
    partes, contagem = ["-- Dados limpos (sem CPF, PIX, conta, telefone nem e-mail). Gerado por sabor/banco.py.\n", "BEGIN;"], {}
    for nome, t in TABELAS.items():
        arq = Path(pasta_clean) / t["csv"]
        if not arq.exists():
            raise FileNotFoundError(f"{arq} não existe. Rode antes: py -m sabor.limpeza")
        with arq.open(encoding="utf-8", newline="") as f:
            linhas = list(csv.DictReader(f))
        cols = t["colunas"]
        nomes_sql = ", ".join(c for c, *_ in cols)
        for ln in linhas:
            vals = ", ".join(_valor(ln.get(c, ""), logico, nome, c) for c, _t, logico, _r in cols)
            partes.append(f"INSERT INTO {nome} ({nomes_sql}) VALUES ({vals});")
        contagem[nome] = len(linhas)
    partes.append("COMMIT;")
    return "\n".join(partes) + "\n", contagem


def gerar_sql(destino: Path = config.RAIZ / "db", pasta_clean: Path = config.DATA_CLEAN) -> dict[str, int]:
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    dados, contagem = dml(pasta_clean)
    (destino / "01_esquema.sql").write_text(ddl(), encoding="utf-8")
    (destino / "02_dados.sql").write_text(dados, encoding="utf-8")
    return contagem


def carregar(dsn: str, destino: Path = config.RAIZ / "db") -> None:
    """Executa os dois arquivos SQL no banco indicado (precisa de psycopg: py -m pip install psycopg[binary])."""
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError("psycopg não instalado. Rode: py -m pip install \"psycopg[binary]\" (ou use o psql com os arquivos de db/).") from e
    if re.search(r"://[^/@:]+:[^@]+@", dsn):
        print("Aviso: não deixe a senha na linha de comando; prefira a variável PGPASSWORD.")
    with psycopg.connect(dsn) as con:
        for arq in ("01_esquema.sql", "02_dados.sql"):
            con.execute((Path(destino) / arq).read_text(encoding="utf-8"))
        con.commit()


def main():
    ap = argparse.ArgumentParser(description="Gera o esquema e os dados SQL e, opcionalmente, carrega no PostgreSQL.")
    ap.add_argument("--clean", default=str(config.DATA_CLEAN))
    ap.add_argument("--saida", default=str(config.RAIZ / "db"))
    ap.add_argument("--gerar-sql", action="store_true", help="só gera os arquivos SQL")
    ap.add_argument("--dsn", help='ex.: "postgresql://usuario@host:5432/banco" (senha em PGPASSWORD)')
    a = ap.parse_args()
    contagem = gerar_sql(Path(a.saida), Path(a.clean))
    for t, n in contagem.items():
        print(f"  {t}: {n} linhas")
    print(f"Arquivos gerados em {a.saida}")
    if a.dsn and not a.gerar_sql:
        carregar(a.dsn, Path(a.saida))
        print("Carga concluída no PostgreSQL.")


if __name__ == "__main__":
    main()

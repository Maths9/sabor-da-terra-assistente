import csv
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sabor import banco, limpeza

RAIZ = Path(__file__).resolve().parents[1]
PII = [r"\d{3}\.\d{3}\.\d{3}-\d{2}", r"[\w.]+@[\w.]+\.\w+", r"\(\d{2}\)\s?\d{4,5}-?\d{4}", r"\bPIX\b\s*:"]


class TestBanco(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.clean = cls.tmp / "clean"
        limpeza.limpar(RAIZ / "data" / "raw", RAIZ / "data" / "documentos", cls.clean)
        cls.sql = cls.tmp / "db"
        cls.contagem = banco.gerar_sql(cls.sql, cls.clean)
        cls.con = sqlite3.connect(":memory:")
        cls.con.execute("PRAGMA foreign_keys = ON")
        cls.con.executescript((cls.sql / "01_esquema.sql").read_text(encoding="utf-8"))
        cls.con.executescript((cls.sql / "02_dados.sql").read_text(encoding="utf-8"))

    def test_contagem_igual_aos_csv(self):
        for nome, t in banco.TABELAS.items():
            with (self.clean / t["csv"]).open(encoding="utf-8", newline="") as f:
                esperado = len(list(csv.DictReader(f)))
            real = self.con.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()[0]
            self.assertEqual(real, esperado, nome)
            self.assertEqual(self.contagem[nome], esperado, nome)

    def test_totais_conhecidos(self):
        pend = self.con.execute("SELECT ROUND(SUM(valor_total),2) FROM financeiro WHERE status_pagamento='pendente'").fetchone()[0]
        self.assertEqual(pend, 13380.0)
        sb = self.con.execute(
            "SELECT SUM(valor_total) FROM financeiro WHERE status_pagamento='pendente' AND comprador LIKE '%SuperBom%'"
        ).fetchone()[0]
        self.assertEqual(sb, 6020.0)

    def test_chave_estrangeira(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO financeiro (id_transacao, data, produtor_id, valor_total, status_pagamento) "
                "VALUES ('X','2026-01-01','P999',1,'pago')"
            )

    def test_checagem_de_status(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO financeiro (id_transacao, data, produtor_id, valor_total, status_pagamento) "
                "VALUES ('Y','2026-01-01','P001',1,'talvez')"
            )

    def test_pedidos_vazia_e_sem_mensagem_original(self):
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0], 0)
        colunas = [c[1] for c in self.con.execute("PRAGMA table_info(pedidos)")]
        self.assertNotIn("mensagem_original", colunas)

    def test_sql_sem_dado_pessoal(self):
        for arq in ("01_esquema.sql", "02_dados.sql"):
            texto = (self.sql / arq).read_text(encoding="utf-8")
            for padrao in PII:
                self.assertIsNone(re.search(padrao, texto), (arq, padrao))

    def test_aspas_escapadas(self):
        self.assertEqual(banco._aspas("D'Ávila"), "'D''Ávila'")

    def test_data_invalida_falha(self):
        with self.assertRaises(ValueError):
            banco._valor("31/02/2026", banco.DATA, "t", "c")


if __name__ == "__main__":
    unittest.main()

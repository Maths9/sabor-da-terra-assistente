import re
import unittest
from pathlib import Path

from sabor import dados, limpeza, produtores
from sabor.produtores import extrato_produtor

RAIZ = Path(__file__).resolve().parents[1]
PII = [r"\d{3}\.\d{3}\.\d{3}-\d{2}", r"[\w.]+@[\w.]+\.\w+", r"\(\d{2}\)\s?\d{4,5}-?\d{4}", r"\bPIX\b.*:\s*\S+"]


class TestProdutores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile

        cls.tmp = Path(tempfile.mkdtemp())
        limpeza.limpar(RAIZ / "data" / "raw", RAIZ / "data" / "documentos", cls.tmp)
        dados.usar_pasta(cls.tmp)

    def test_proprio_produtor(self):
        r = extrato_produtor("P001", "P001", data_referencia="2026-11-09")
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["resumo"]["total_vendido"], 1090.0)
        self.assertEqual(r["resumo"]["saldo_a_receber"], 0.0)

    def test_filtro_periodo(self):
        r = extrato_produtor("P001", "P001", periodo="2026-10", data_referencia="2026-11-09")
        self.assertEqual(r["resumo"]["total_vendido"], 0.0)
        self.assertIn("não encontrei vendas", r["mensagem_simples"])

    def test_outro_produtor_negado(self):
        r = extrato_produtor("P003", "P001")
        self.assertEqual(r["status"], "negado")
        self.assertNotIn("vendas", r)

    def test_sem_identificacao_negado(self):
        self.assertEqual(extrato_produtor("P001", "")["status"], "negado")

    def test_diretoria_pode(self):
        self.assertEqual(extrato_produtor("P003", "diretoria", data_referencia="2026-11-09")["status"], "ok")

    def test_produtor_inexistente(self):
        self.assertEqual(extrato_produtor("P999", "diretoria")["status"], "nao_encontrado")

    def test_atraso_e_alertas(self):
        for pid in ("P003", "P008", "P017"):
            r = extrato_produtor(pid, pid, data_referencia="2026-11-14")
            self.assertEqual(r["status"], "ok")
            s = r["resumo"]
            self.assertAlmostEqual(s["saldo_a_receber"], s["em_atraso"] + s["a_receber_em_dia"], places=2)
        r = extrato_produtor("P008", "P008", data_referencia="2026-11-14")
        self.assertTrue(any("vencida" in a for a in r["alertas"]))

    def test_sem_dado_pessoal(self):
        for pid in ("P001", "P003", "P008", "P017"):
            texto = str(extrato_produtor(pid, pid, data_referencia="2026-11-14"))
            for padrao in PII:
                self.assertIsNone(re.search(padrao, texto), (pid, padrao))

    def test_reais(self):
        self.assertEqual(produtores._reais(1234.5), "R$ 1.234,50")


if __name__ == "__main__":
    unittest.main()

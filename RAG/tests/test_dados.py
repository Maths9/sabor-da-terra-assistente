import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from sabor import config, dados
from sabor.limpeza import limpar

PROIBIDAS = {"cpf", "produtor_cpf", "chave_pix", "chave_pix_deposito", "banco", "agencia", "conta_corrente",
             "telefone", "email", "endereco", "data_nascimento"}


class TestDados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.rel = limpar(config.DATA_RAW, config.DATA_DOCS, cls.tmp)
        dados.usar_pasta(cls.tmp)

    def test_sem_colunas_pessoais(self):
        for csv in sorted(self.tmp.glob("*.csv")):
            self.assertFalse(PROIBIDAS & set(pd.read_csv(csv, nrows=1).columns), csv.name)

    def test_unidades_reais(self):
        fin = pd.read_csv(self.tmp / "financeiro_limpo.csv")
        un = fin.drop_duplicates("produto").set_index("produto")["unidade"]
        self.assertEqual((un["alface"], un["coentro"], un["ovos caipira"], un["queijo coalho"]),
                         ("unidade", "maço", "dúzia", "kg"))

    def test_lote_inexistente_sugere_parecido(self):
        r = dados.consultar_lote("2024-089")
        self.assertEqual(r["status"], "nao_encontrado")
        self.assertEqual([s["lote_id"] for s in r["sugestoes"]], ["LOT-2026-0089"])
        self.assertEqual(dados.consultar_lote("LOT-2026-9999")["sugestoes"], [])

    def test_lote_com_alertas(self):
        r = dados.consultar_lote("lot-2026-0104")  # P008, mel entregue após o vencimento do selo
        self.assertEqual(r["status"], "ok")
        self.assertTrue(any("venceu" in a for a in r["lote"]["alertas"]))
        r = dados.consultar_lote("LOT-2026-0094")  # alface a 12 °C
        self.assertTrue(any("12" in a for a in r["lote"]["alertas"]))

    def test_situacao_produtor(self):
        ref = "2026-11-14"
        p008 = dados.situacao_produtor("P008", ref)["produtor"]
        self.assertEqual(p008["certificacao_organica"], "vencida")
        self.assertEqual(p008["registro"]["sie_situacao"], "pendente")
        self.assertEqual(dados.situacao_produtor("P004", ref)["produtor"]["certificacao_organica"], "vence_em_breve")
        self.assertEqual(dados.situacao_produtor("P001", ref)["produtor"]["certificacao_organica"], "vigente")
        p017 = dados.situacao_produtor("P017", ref)["produtor"]
        self.assertEqual(p017["registro"]["sie_situacao"], "nao_possui")
        self.assertTrue(p017["alertas"])
        self.assertEqual(dados.situacao_produtor("P999", ref)["status"], "nao_encontrado")

    def test_retorno_sem_dado_pessoal(self):
        texto = json.dumps(dados.situacao_produtor("P001", "2026-11-14"), ensure_ascii=False)
        for proibido in ("831.452.674-90", "28901-3", "99812-3456", "maria.graca@email.com"):
            self.assertNotIn(proibido, texto)


if __name__ == "__main__":
    unittest.main()

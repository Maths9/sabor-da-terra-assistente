import unittest

from sabor.mascara import mascarar, pii_residual

AMOSTRA = """DADOS DO PRODUTOR:
  Nome: Débora Cristina de Melo
  CPF: 890.123.456-78
  CEP: 55.295-000
  Telefone: (87) 99845-6623 e (87) 3761-5000
  E-mail: debora@email.com
  Banco do Nordeste - Ag. 0023 - C/C 63478-2
  Chave PIX: 890.123.456-78
Certificado Nº: ORG-PE-2025-002345 | Lote LOT-2026-0089 | DAP/CAF: SDR/PE-2020-0067890
CNPJ: 45.678.901/0001-23 | CRMV-PE 7.234
Chave PIX do Restaurante (para devoluções):
  restaurante.raizes@email.com
Chave PIX aleatória: 5f3a-9c21-aa77-0b12
"""


class TestMascara(unittest.TestCase):
    def setUp(self):
        self.saida, self.contagem = mascarar(AMOSTRA)

    def test_nao_sobra_dado_pessoal(self):
        self.assertEqual(pii_residual(self.saida), [])
        for proibido in ("890.123.456-78", "99845-6623", "debora@email.com", "63478-2", "55.295-000", "5f3a-9c21"):
            self.assertNotIn(proibido, self.saida)

    def test_preserva_informacao_util(self):
        for ok in ("Débora Cristina de Melo", "ORG-PE-2025-002345", "LOT-2026-0089", "SDR/PE-2020-0067890",
                   "45.678.901/0001-23", "CRMV-PE 7.234"):
            self.assertIn(ok, self.saida)

    def test_contagens(self):
        self.assertGreaterEqual(self.contagem["CPF"], 2)
        self.assertEqual(self.contagem["BANCO"], 1)
        self.assertGreaterEqual(self.contagem["PIX"], 1)

    def test_idempotente(self):
        de_novo, _ = mascarar(self.saida)
        self.assertEqual(de_novo, self.saida)


if __name__ == "__main__":
    unittest.main()

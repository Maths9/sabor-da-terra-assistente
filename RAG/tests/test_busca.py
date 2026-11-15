import json
import shutil
import tempfile
import unittest
from pathlib import Path

from sabor import busca, config
from sabor.embeddings import OfflineEmbedder
from sabor.ingestao import ingerir


class TestIngestaoEBusca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        # cópia dos documentos + um arquivo duplicado para testar a deduplicação
        cls.docs = cls.tmp / "docs"
        shutil.copytree(config.DATA_DOCS, cls.docs)
        original = cls.docs / "contratos" / "contrato_pnae_garanhuns.txt"
        shutil.copy(original, cls.docs / "contratos" / "contrato_pnae_garanhuns_1.txt")
        cls.index = cls.tmp / "index"
        cls.info = ingerir(cls.docs, cls.index, "memory", OfflineEmbedder(), verbose=False)
        busca.configurar(cls.index, limiar=0.12)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_duplicado_ignorado(self):
        self.assertEqual(len(self.info["duplicados_ignorados"]), 1)
        self.assertEqual(self.info["n_documentos"], 20)

    def test_indice_sem_dado_pessoal(self):
        dados = json.loads((self.index / "memory_index.json").read_text(encoding="utf-8"))
        texto = "\n".join(dados["textos"])
        for proibido in ("456.923.817-03", "890.123.456-78", "63478-2", "831.452.674-90"):
            self.assertNotIn(proibido, texto)
        self.assertGreater(sum(self.info["mascaramento"].values()), 20)

    def test_acha_certificado_vencido(self):
        r = busca.buscar_documentos("certificação orgânica da Josefa Alves de Souza vencida", k=3)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(any("josefa_souza_P008" in x["fonte"] for x in r["resultados"][:2]))
        p008 = next(x for x in r["resultados"] if "P008" in x["fonte"])
        self.assertEqual(p008["situacao_validade"], "vencido")

    def test_filtros(self):
        r = busca.buscar_documentos("registro SIE", tipo="inspecao", k=5)
        self.assertTrue(all(x["tipo"] == "inspecao" for x in r["resultados"]))
        r = busca.buscar_documentos("capacidade de produção por semana", produtor_id="P011", k=5)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(all("queijo_coalho" in x["fonte"] or "P011" in x["trecho"] for x in r["resultados"]))
        r = busca.buscar_documentos("certificado orgânico", tipo="certificacao_organica", valido_em="2026-11-14", k=10)
        self.assertFalse(any("P008" in x["fonte"] for x in r["resultados"]))  # P008 venceu em 30/09

    def test_nao_encontrado(self):
        r = busca.buscar_documentos("receita de bolo de chocolate com cobertura")
        self.assertEqual(r["status"], "nao_encontrado")
        self.assertEqual(busca.buscar_documentos("  ")["status"], "erro")

    def test_citacao_obrigatoria(self):
        r = busca.buscar_documentos("multa por atraso na entrega Mercado Bom Preço")
        for x in r["resultados"]:
            self.assertTrue(x["fonte"].endswith(".txt") and x["secao"] and x["trecho"])

    def test_embedder_incompativel(self):
        class Outro:
            nome, dim = "outro", 8

        with self.assertRaises(RuntimeError):
            busca.configurar(self.index, embedder=Outro())
        busca.configurar(self.index, limiar=0.12)  # restaura


if __name__ == "__main__":
    unittest.main()

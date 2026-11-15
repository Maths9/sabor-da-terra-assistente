import unittest

from sabor import config
from sabor.chunking import criar_chunks, metadados_documento

DOCS = config.DATA_DOCS


def _ler(rel):
    return (DOCS / rel).read_text(encoding="utf-8")


class TestChunking(unittest.TestCase):
    def test_metadados_certificado_vencido(self):
        rel = "certificacoes/cert_organica_josefa_souza_P008.txt"
        m = metadados_documento(rel, _ler(rel))
        self.assertEqual((m["tipo"], m["produtor_id"], m["validade_ate"]), ("certificacao_organica", "P008", 20260930))

    def test_validade_contratos(self):
        rel = "contratos/contrato_pnae_garanhuns.txt"
        self.assertEqual(metadados_documento(rel, _ler(rel))["validade_ate"], 20270228)
        rel = "contratos/contrato_restaurante_raizes.txt"
        self.assertEqual(metadados_documento(rel, _ler(rel))["validade_ate"], 0)  # vigência indeterminada

    def test_ficha_lista_produtores(self):
        rel = "fichas_tecnicas/queijo_coalho.txt"
        todos = "".join(c.metadata["produtores"] for c in criar_chunks(rel, _ler(rel)))
        for p in ("P003", "P007", "P011"):
            self.assertIn(p, todos)

    def test_todos_os_documentos(self):
        total = 0
        for arq in sorted(DOCS.rglob("*.txt")):
            rel = arq.relative_to(DOCS).as_posix()
            chunks = criar_chunks(rel, arq.read_text(encoding="utf-8"))
            self.assertTrue(chunks, rel)
            ids = [c.id for c in chunks]
            self.assertEqual(len(ids), len(set(ids)))
            for c in chunks:
                self.assertLessEqual(len(c.texto), 1400 * 1.3, rel)
                self.assertTrue(c.metadata["arquivo"] and c.metadata["secao"])
                self.assertIn(c.texto, c.texto_indexado)
            total += len(chunks)
        self.assertGreater(total, 20)


if __name__ == "__main__":
    unittest.main()

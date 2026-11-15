"""Teste de ambiente (1 minuto): confirma que ChromaDB e Gemini funcionam NESTA máquina.

Uso (na raiz do projeto):   py scripts\\testar_ambiente.py
Para testar o Gemini, defina antes a chave:   $env:GEMINI_API_KEY = "sua-chave"   (PowerShell)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
falhas = 0


def ok(msg):
    print("  [OK]     ", msg)


def falha(msg):
    global falhas
    falhas += 1
    print("  [FALHOU] ", msg)


def checar(cond, msg_ok, msg_falha):
    ok(msg_ok) if cond else falha(msg_falha)


print("Python", sys.version.split()[0])

print("\n1) Bibliotecas")
for mod in ("pandas", "numpy", "chromadb", "google.genai"):
    try:
        __import__(mod)
        ok(mod)
    except Exception as e:
        falha(f"{mod}: {e}")

print("\n2) ChromaDB (índice, filtro por metadados e similaridade)")
try:
    from sabor.armazenamento import ChromaStore

    pasta = Path(tempfile.mkdtemp()) / "chroma_teste"
    loja = ChromaStore(pasta, resetar=True)
    loja.adicionar(
        ["a", "b", "c"],
        ["texto a", "texto b", "texto c"],
        [[1, 0, 0], [0, 1, 0], [0.9, 0.1, 0]],
        [
            {"tipo": "contrato", "validade_ate": 20270101, "produtores": "|P001|"},
            {"tipo": "ficha_tecnica", "validade_ate": 0, "produtores": ""},
            {"tipo": "contrato", "validade_ate": 20260101, "produtores": ""},
        ],
    )
    r = loja.consultar([1, 0, 0], 3)
    ordem = [x.id for x in r]
    checar(ordem == ["a", "c", "b"], f"busca por similaridade: {ordem}", f"ordem inesperada: {ordem}")
    checar(r[0].relevancia > 0.99, f"relevância (cosseno) do melhor: {r[0].relevancia:.3f}", f"relevância {r[0].relevancia}")
    f1 = sorted(x.id for x in loja.consultar([1, 0, 0], 3, {"tipo": "contrato"}))
    checar(f1 == ["a", "c"], "filtro de igualdade (tipo)", f"filtro tipo: {f1}")
    f2 = [x.id for x in loja.consultar([1, 0, 0], 3, {"tipo": "contrato", "validade_ate": {"$gte": 20260601}})]
    checar(f2 == ["a"], "filtros combinados ($and + $gte)", f"filtro combinado: {f2}")
    checar(ChromaStore(pasta).contar() == 3, "índice gravado em disco e relido", "persistência")
except Exception as e:
    falha(f"ChromaDB: {type(e).__name__}: {e}")

print("\n3) Gemini (embeddings)")
if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
    print("  [PULADO] defina GEMINI_API_KEY para testar")
else:
    try:
        from sabor import config
        from sabor.embeddings import GeminiEmbedder

        emb = GeminiEmbedder()
        docs = emb.embed_documentos(["O certificado orgânico de P008 venceu em 30/09/2026.", "Receita de bolo de chocolate."])
        q = emb.embed_consulta("Qual a validade do selo orgânico da Josefa?")
        cos = lambda u, v: sum(a * b for a, b in zip(u, v))
        checar(len(q) == config.EMBED_DIM, f"dimensão {len(q)} (modelo {emb.nome})", f"dimensão {len(q)}")
        s_rel, s_irr = cos(q, docs[0]), cos(q, docs[1])
        checar(s_rel > s_irr, f"relacionado {s_rel:.3f} > irrelevante {s_irr:.3f}", f"similaridades {s_rel:.3f} / {s_irr:.3f}")
        print(f"           anote para calibrar SABOR_LIMIAR: {s_rel:.3f} (relevante) e {s_irr:.3f} (irrelevante)")
    except Exception as e:
        falha(f"Gemini: {type(e).__name__}: {e}")

print("\nResultado:", "TUDO OK" if not falhas else f"{falhas} problema(s): veja as linhas [FALHOU]")
sys.exit(1 if falhas else 0)

"""Ajuda a escolher o limiar de relevância (SABOR_LIMIAR) com perguntas reais.

Uso (na raiz do projeto, depois da ingestão com Gemini):
    $env:GEMINI_API_KEY = "sua-chave"
    py scripts\\calibrar_limiar.py

Mostra a melhor relevância de cada pergunta. O limiar ideal fica entre a MENOR nota das perguntas
"com resposta" e a MAIOR nota das perguntas "sem resposta". Edite as listas abaixo à vontade.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sabor import busca  # noqa: E402

COM_RESPOSTA = [
    "O selo orgânico da Josefa ainda está válido?",
    "Quando vence a certificação orgânica do produtor P004?",
    "O que a inspeção da ADAGRO encontrou no frango?",
    "Quais produtores têm laudo sanitário?",
    "Qual a faixa de quantidade de tomate no contrato do Mercado Bom Preço?",
    "Qual o prazo de validade do queijo coalho?",
    "Quais os dias de entrega do contrato do Restaurante Raízes?",
    "Qual o percentual mínimo de agricultura familiar no contrato do PNAE?",
    "Como armazenar o mel silvestre?",
    "Qual o prazo de pagamento do contrato do PNAE?",
]
SEM_RESPOSTA = [
    "Receita de bolo de chocolate",
    "Quem ganhou a Copa do Mundo de 2014?",
    "Qual a previsão do tempo para amanhã em Recife?",
    "Qual o CPF do produtor P001?",
    "Como configurar o Wi-Fi do roteador?",
    "Qual é a capital da Austrália?",
]


def melhor(consulta):
    r = busca.buscar_documentos(consulta, k=1)
    if r["status"] == "ok":
        x = r["resultados"][0]
        return x["relevancia"], f'{x["fonte"]} ({x["secao"]})'
    if r["status"] == "erro":
        raise SystemExit(f'Erro: {r["mensagem"]}')
    return 0.0, "-"


busca.configurar(limiar=0.0)  # sem corte, para ver todas as notas
print("\nPERGUNTAS COM RESPOSTA NOS DOCUMENTOS")
notas_ok = []
for q in COM_RESPOSTA:
    n, f = melhor(q)
    notas_ok.append(n)
    print(f"  {n:.3f}  {q}\n         -> {f}")
print("\nPERGUNTAS SEM RESPOSTA (fora do assunto)")
notas_no = []
for q in SEM_RESPOSTA:
    n, f = melhor(q)
    notas_no.append(n)
    print(f"  {n:.3f}  {q}")

menor_ok, maior_no = min(notas_ok), max(notas_no)
print(f"\nMenor nota com resposta: {menor_ok:.3f}  |  Maior nota sem resposta: {maior_no:.3f}")
if menor_ok > maior_no:
    print(f"Sugestão de SABOR_LIMIAR: {(menor_ok + maior_no) / 2:.2f}  (ponto médio, separa os dois grupos)")
else:
    print("Os grupos se sobrepõem: use o maior valor sem resposta como piso e confira as perguntas com nota baixa.")

# Comece aqui (Windows)

Este pacote já traz **todos os dados, documentos, scripts e relatórios**. Você não precisa de mais nenhum arquivo.

## 1. Extrair
Clique com o botão direito no `.zip` e escolha **Extrair tudo**. Abra a pasta `sabor-da-terra` que foi criada.

## 2. Rodar (jeito fácil)
Dê **duplo clique em `rodar.bat`**. Ele instala o pandas e executa a exploração dos dados. O resultado aparece na tela e é gravado em `docs\saida-exploracao.txt`.

## 3. Rodar (jeito manual, pelo terminal)
1. Dentro da pasta `sabor-da-terra`, clique na barra de endereço do Explorador de Arquivos, digite `powershell` e aperte Enter.
2. Confira se o Python está instalado: `python --version` (ou `py --version`). Se não estiver, instale em python.org e marque "Add Python to PATH".
3. Rode:
   ```
   pip install pandas
   python scripts\explorar_dados.py data\raw docs\saida-exploracao.txt
   ```
   Se `python` não funcionar, troque por `py`.

## 4. Pipeline do RAG (limpeza, índice e busca)
Na pasta do projeto, no PowerShell:
```
py -m pip install -r requirements.txt
py -m pip install -r requirements-rag.txt
py scripts\testar_ambiente.py
py -m unittest discover -s tests -t . -v
py -m sabor.limpeza
$env:GEMINI_API_KEY = "sua-chave"
py -m sabor.ingestao --embedder gemini --backend chroma
```
- `testar_ambiente.py` mostra se o ChromaDB e o Gemini funcionam na sua máquina.
- Sem chave ou sem Chroma: `py -m sabor.ingestao --embedder offline --backend memory` (só para teste).
- Detalhes em `docs\pipeline-rag.md`.

## 5. O que ler
1. `docs\pipeline-rag.md`: pipeline do RAG e o que não foi testado.
2. `docs\relatorio-varredura.md`: resumo, erros corrigidos e o que falta.
3. `docs\exploracao-dados.md`: as armadilhas encontradas nos dados e o plano.
4. `docs\decisoes.md`: decisão do banco vetorial (alternativas consideradas).
5. `docs\saida-exploracao.txt`: saída do script.

## Problemas comuns
- `python não é reconhecido`: use `py` ou reinstale o Python marcando "Add Python to PATH".
- `No module named pandas`: rode `pip install pandas` (ou `py -m pip install pandas`).
- Acentos estranhos na tela: abra o `.txt` gerado no VS Code ou no Bloco de Notas, que ficam corretos.

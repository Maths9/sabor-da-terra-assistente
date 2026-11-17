# Resumo para a apresentação: dados e RAG (Integrante 3)

## Em uma frase
O agente responde sobre certificações, laudos, contratos e fichas **citando o documento de onde tirou a informação** e diz "não encontrei" quando não há fonte, sem expor nenhum dado pessoal.

## O problema que resolvemos
Hoje a equipe gasta horas procurando informação espalhada em 20 documentos e 6 planilhas. Os dados também escondem armadilhas reais de uma cooperativa: certificado orgânico vencido, produtor sem registro sanitário, lote que não existe e pagamentos atrasados.

## Como funciona (4 passos)
1. **Limpeza:** tabelas sem CPF, PIX, conta, telefone nem e-mail; nomes de produtos padronizados.
2. **Ingestão:** os documentos são deduplicados, os dados pessoais são mascarados (a ingestão **falha** se sobrar algum) e o texto é dividido por seção.
3. **Índice:** cada trecho vira um vetor (Gemini, `gemini-embedding-001`, 768 dimensões) guardado no ChromaDB, com metadados de tipo, produtor e validade.
4. **Busca:** a pergunta vira vetor, o agente recebe os trechos mais próximos com **fonte e seção** e a situação de validade (vigente, vencida).

## Números
- 20 documentos únicos, 33 trechos, 36 dados pessoais mascarados na ingestão.
- 30 testes automáticos passando (mascaramento, chunking, busca, lotes, produtores).
- Teste de busca com perguntas reais: o documento certo apareceu nas 10 de 10; perguntas fora do assunto ficam abaixo do limiar de relevância (0,65).

## Por que ChromaDB (alternativas consideradas)
Comparamos ChromaDB, pgvector (Cloud SQL), AlloyDB e Vertex AI Vector Search em tempo de montagem, custo, deploy no Cloud Run e filtro por metadados. Como o corpus é pequeno (cerca de 20 documentos) e o protótipo tem 12 dias, o ChromaDB embutido na imagem tem custo zero e fica pronto em horas. A busca está atrás de uma função única, então migrar para pgvector depois muda só ela.

## Como evitamos erro e vazamento
- **Anti-alucinação:** o agente só responde com o que as ferramentas devolvem; sem fonte, diz que não encontrou.
- **LGPD:** dados pessoais nunca entram no índice nem nas respostas. O agente recusa pedidos de CPF, PIX e conta.
- **Privacidade entre produtores:** o extrato só é mostrado ao próprio produtor ou à diretoria; para qualquer outro, o acesso é negado.
- **Validade calculada na hora:** o selo orgânico não depende de uma coluna "sim/não", e sim da data de validade do documento.

## Exemplo para mostrar ao vivo
> "O selo orgânico da Josefa ainda está válido?" → o agente responde que **venceu em 30/09/2026**, cita o certificado do produtor P008 e não oferece o produto como orgânico.

## Limites que reconhecemos
- O índice só muda com novo build e novo deploy (corpus estático).
- A qualidade foi medida com 16 perguntas de teste, e não com uso real.
- Se o corpus crescer ou precisar de atualização contínua, o próximo passo é pgvector no Cloud SQL.

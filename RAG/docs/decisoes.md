# Decisões de arquitetura — Assistente Sabor da Terra

## D-001 — Onde ficam os vetores do RAG

**Status:** **DECIDIDA** em 14/11/2026 (ChromaDB). Comunicada ao grupo e ao Jorge (Integrante 4) pelo Integrante 3.
**Data da proposta:** 09/11/2026 · **Donos:** Integrante 3 (RAG) e Integrante 4 (orquestração ADK)

### Contexto
- O RAG indexa só os documentos de texto: certificações, laudos, inspeção ADAGRO, contratos e fichas técnicas. Os CSVs com CPF, PIX e conta **não entram no índice** (ver `exploracao-dados.md` §6); eles são consultados por ferramenta estruturada.
- O corpus real é **pequeno: 20 documentos únicos, cerca de 36 mil caracteres, estimados em 25 a 60 chunks**. Qualquer banco vetorial dá conta; não há necessidade de índice aproximado (ANN).
- O protótipo tem 12 dias e vai para o Cloud Run. O corpus é "congelado" no dia 12.
- Precisamos de **filtro por metadados**: `tipo_documento`, `produtor_id`, `validade_ate`, `produto`. Isso evita citar certificação vencida.

### Alternativas consideradas

| Critério | **ChromaDB** | **pgvector (Cloud SQL)** | **AlloyDB (pgvector/ScaNN)** | **Vertex AI Vector Search (hoje "Agent Retrieval")** |
|---|---|---|---|---|
| Tempo para montar (estimativa nossa) | ~1–2 h (`pip install` + script de ingestão) | ~0,5–1 dia (instância, conector, IAM, segredo, esquema) | ~1 dia + custo | ~1–2 dias (índice, endpoint, deploy do índice) |
| Custo | US$ 0 além do Cloud Run | instância sempre ligada: db-f1-micro ≈ US$ 8/mês e db-g1-small ≈ US$ 26/mês (us-central1, tabela de terceiros); esses tiers compartilhados **não têm SLA** do Cloud SQL (doc. oficial), ok só para protótipo | a menor máquina custa ~US$ 227/mês (2 vCPU / 16 GB, fonte de terceiros) | cobra por hora de VM do índice implantado (~US$ 0,094/h por nó e2-standard-2 ≈ US$ 70/mês, fonte de terceiros) mais US$ 3/GiB por build; sem desligar sozinho |
| Deploy no Cloud Run | roda **dentro** do contêiner; o disco do Cloud Run é temporário (some quando a instância para), então o índice vai **empacotado na imagem** (somente leitura) | serviço externo; Cloud Run conecta pelo conector do Cloud SQL | idem, serviço externo | serviço externo, via API |
| Filtro por metadados | sim (`where`); valores simples, sem lista nativa | **o melhor**: SQL (`WHERE`, JOIN, JSONB) | idem pgvector | sim (restrições/filtros), mais rígido |
| Persistência | do índice, na imagem; para atualizar, reconstruir e reimplantar | sim, banco gerenciado | sim | sim |
| Risco para o prazo | baixo | médio (rede e IAM dependem do Integrante 5) | médio/alto | alto (custo e tempo de implantação) |

**Observação técnica (pgvector):** o `gemini-embedding-001` gera 3072 dimensões por padrão, e pelo que sei o pgvector só indexa até 2000 dimensões no tipo `vector` (4000 em `halfvec`). Seria preciso reduzir a dimensão (768 ou 1536). Com ~50 chunks não precisa de índice, mas é um detalhe a lembrar.

### Decisão
**ChromaDB embutido** (modo persistente em disco), com o índice **gerado no build** pelo script de ingestão e **empacotado na imagem do Cloud Run** em modo somente leitura.

**Por quê**
1. Montagem em horas e custo zero; o Integrante 3 entrega o RAG sem depender do Cloud SQL do Integrante 5.
2. O corpus é minúsculo e estático: persistência gerenciada e índice aproximado não trazem ganho.
3. Menos superfície de dados sensíveis: nenhum banco externo com credencial; o índice só contém texto já mascarado.
4. Filtro por metadados é suficiente para o que a demo precisa (validade, tipo, produtor).

**Como contornar as limitações do Chroma**
- Datas: gravar `validade_ate` como inteiro `AAAAMMDD` e filtrar com `$gte`.
- Lista de produtos: gravar `produtos` como texto separado por `|` e filtrar de novo em Python depois da busca (buscar k=15 e reduzir a 5).
- Mudar o corpus = reconstruir o índice e reimplantar (aceitável: congelamento no dia 12).
- Sem escrita em produção, então não há problema de concorrência entre instâncias.

**Para o código do Jorge:** a busca é uma `FunctionTool` Python, `buscar_documentos(consulta, tipo="", produtor_id="", valido_em="", k=5)` (implementada em `sabor/busca.py`; strings vazias no lugar de `None`, mais simples para o ADK), que devolve trechos com fonte. O assistente não conhece o banco: trocar para pgvector depois muda só essa função.

### Quando mudaríamos
- Precisar **atualizar documentos sem reimplantar** (produção real) → **pgvector no Cloud SQL**, que também permitiria juntar os dados estruturados na mesma base (a arquitetura do PDF já cita Cloud SQL/AlloyDB).
- Corpus com milhares de documentos, alta concorrência ou necessidade de SLA → Vertex AI Vector Search / AlloyDB.

### Pontos a validar na implementação (não mudam a decisão)
1. `adk deploy cloud_run` inclui a pasta do índice no build da imagem? Se não incluir, plano B: Dockerfile próprio com a pasta copiada.
2. A ferramenta `buscar_documentos` com essa assinatura serve para o grafo (inclusive o estado `session.state`)?
3. Se o Isaque tiver Cloud SQL pronto e o grupo quiser atualizar documentos sem reimplantar, reavaliar pgvector (ver "Quando mudaríamos").

### Como apresentar ("alternativas consideradas")
> Comparamos ChromaDB, pgvector (Cloud SQL), AlloyDB e Vertex AI Vector Search em tempo de montagem, custo, deploy no Cloud Run e filtro por metadados. Como o corpus é de ~20 documentos e o protótipo tem 12 dias, escolhemos o ChromaDB empacotado na imagem: custo zero e montagem em horas. Mantivemos a busca atrás de uma função única para migrar para pgvector se o corpus crescer ou precisar de atualização contínua.

### Mensagem da daily (enviada)
> **Banco vetorial:** decidido: ChromaDB dentro da imagem do Cloud Run (índice gerado no build, só leitura). Motivo: corpus de ~20 docs, sem custo, pronto em horas. Jorge, confirma se o deploy inclui a pasta do índice e se a assinatura `buscar_documentos(consulta, tipo, produtor_id, valido_em)` serve pro grafo. Plano B: pgvector no Cloud SQL se o Isaque tiver a instância pronta até o dia 3.

### Fontes consultadas (custos a conferir na calculadora do Google Cloud antes da apresentação)
- Documentação do Cloud Run: o sistema de arquivos padrão é temporário e se perde quando a instância para.
- Blog do Google Cloud: pgvector com HNSW no Cloud SQL e no AlloyDB.
- Bytebase (tabelas de preço do Cloud SQL e do AlloyDB) e nOps (Vertex AI Vector Search): valores de **terceiros**, consultados em 10/11/2026 para us-central1. Conferir em cloud.google.com/sql/pricing e na calculadora do Google Cloud antes de citar em apresentação.
- Documentação do Cloud SQL: tipos de máquina compartilhados (db-f1-micro e db-g1-small) não são cobertos pelo SLA.
- Documentação do Google: o Vector Search 2.0 agora se chama "Agent Retrieval", com preço por uso ou por recurso.

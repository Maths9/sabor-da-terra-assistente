# Relatório da varredura geral

**Autor:** Integrante 3 · **Data:** 10/11/2026 · **Escopo:** conferir cada afirmação dos relatórios contra os arquivos e fontes oficiais, corrigir o que estava errado e listar o que falta.

> **Atenção à data.** Os números e prazos deste relatório foram calculados em **09/11/2026**. O script usa a **data do dia em que roda**: em 12/11/2026 o total vencido sobe de R$ 9.890 para **R$ 10.500** (as duas pendências de P010 passaram do prazo). A inspeção da ADAGRO (11–12/11) já está em andamento e a auditoria de P008 é em 15/11.

## 1. Resumo

- Reli os 29 `.txt`, os 5 CSV, o `pedidos.json` e reconferi os números dos relatórios.
- Encontrei e corrigi **5 erros meus** (§2). Os demais achados se confirmaram.
- Verifiquei em fonte oficial as normas que estavam como "confirmar" (§3).
- Ficam pendentes **decisões e confirmações que dependem de vocês** (§5).

## 2. Erros corrigidos nesta rodada

| # | Erro | Correção |
|---|---|---|
| 1 | O script usava `dayfirst=True` em datas ISO e **trocava dia e mês** (2026-10-01 virava 10/01), escondendo a venda de P008 | Parser ISO próprio; o script agora acusa as vendas de 01/10 |
| 2 | O script somava `valor_unitario` em vez de `valor_total` nas pendências | Corrigido; total pendente R$ 13.380, vencido R$ 9.890 |
| 3 | Escrevi que havia **11 arquivos duplicados**; são **8** a remover (6 grupos, 14 arquivos) | Corrigido em `exploracao-dados.md` |
| 4 | Escrevi que "os certificados 2025 citam a IN 46/2011"; só **P001 e P002** citam | Corrigido |
| 5 | Custos do banco vetorial vinham de fonte de 2023 | Trocados por tabelas de 2026 (terceiros) e marcados para conferir na calculadora oficial |

## 3. Afirmações que eram "confirmar" e agora têm fonte

| Tema | Resultado | Fonte |
|---|---|---|
| Hidroponia com selo orgânico (P009) | **Proibida**: Portaria MAPA 52/2021, art. 97 §4º. O §2º admite exceção para substrato que imite o solo, com autorização do OAC. O certificado diz "hidroponia" e não menciona a exceção | texto da Portaria (SISLEGIS/MAPA) |
| IN 46/2011 | **Revogada** pelo art. 144, III, da Portaria 52/2021; em vigor desde 01/04/2021 | idem |
| Ovos e mel no PNAE sem SIE | O contrato 045/2026 (condição 3) já exige SIE/SIM/SISBI; editais de outros entes tratam ovos e mel como origem animal sujeita a registro | contrato; editais (Bahia, Joinville) |
| Mínimo do PNAE | O contrato cita **30%**; a Lei 15.226/2025 passou para **45% desde 01/01/2026** | Lei 11.947/2009 art. 14 (redação de 2025) |
| Selo Arte | Concedido **ao produto**; exige registro em inspeção oficial e inscrição no CNPA. Nenhum documento de P003/P007 o comprova | Lei 13.680/2018, Decreto 11.099/2022, Portaria 531/2022 |
| ADK 2.0 | Existe; tem `Workflow` em grafo, `adk deploy cloud_run` e `adk eval` | PyPI e repositório do ADK |

## 4. Conferência dos fatos contra os arquivos

Tudo abaixo foi relido no arquivo de origem e **confere**.

- **Contrato PNAE:** 14 itens e preços, R$ 480 mil/ano (R$ 40 mil/mês), vigência 01/03/2026 a 28/02/2027, condições 1 a 5, pagamento em 45 dias, CRN-6 12345, ordenador como Secretário de Educação.
- **Contrato Mercado:** vigência até 31/12/2026, multa de 2% ao dia, aviso de 60 dias, entrega terça e sexta, preços "da tabela com IPCA".
- **Contrato Raízes:** sem preços, volumes ou assinaturas; PIX na entrega; vigência indeterminada.
- **ADAGRO:** NC-001 grave (P017, suspender frango), NC-002 (termômetro), nota sobre ovos, próxima inspeção em maio/2027.
- **P008:** vencido em 30/09; renovação REN-2026-0456; auditoria em 15/11; "não podem ser comercializados como orgânicos".
- **P004:** validade 01/12/2026; renovação devia ser pedida até 01/10/2026.
- **Fichas:** P011 sem SIE; P008 e P018 com SIE pendente; folhosas a 2–5 °C; descontos de atacado; jandaíra a R$ 140.
- **Laudos:** P003 de 12/08/2026 (NC com prazo até 12/09, validade de 6 meses); P002 de 05/05/2026 (próxima em novembro).
- **Certificados:** P007 (45 vacas, 300 L/dia, 200 kg de queijo), P014 (amora ~40 kg/sem), P002 (jandaíra 180 kg/ano, responsável técnico é o próprio produtor), P001 (próxima auditoria em dezembro/2026).
- **CSV:** totais de pendências, 10 vendas sem lote, ids de pedido que não casam, lote 2024-089 inexistente.
- **Datas:** 01/11/2026 é domingo e 04/11/2026 é quarta (conferido com `pandas`).

**Não consegui verificar:** a existência de "Gemini 3.5 Flash" e de `gemini-embedding-2` (citados no PDF); se a Res. FNDE 6/2020 foi revogada pela 4/2026; preços oficiais do Vertex AI Vector Search; os tempos de montagem (são estimativas minhas).

## 5. O que preciso de vocês

1. **Data de referência** (30/10 ou 09/11) para validade, atraso e prazos.
2. ~~Jorge: confirmar a D-001~~ **Decidida em 14/11/2026 (ChromaDB).** Falta só validar na implementação se o `adk deploy cloud_run` inclui a pasta do índice e se a assinatura de `buscar_documentos` serve ao grafo.
3. **Professor:** (a) se o PDF e os dados podem ir para um repositório **público**; (b) se as armadilhas são intencionais e qual resposta esperam do agente em cada uma.
4. **Isaque:** projeto no Google Cloud, créditos e chave da API do Gemini (necessários para gerar os embeddings).
5. **Grupo:** regras do agente para P008, P017, SuperBom, pedidos de CPF e dados bancários (§9 de `exploracao-dados.md`) e nomes que entram no README.

## 6. Próximos passos do Integrante 3 (por prioridade)

1. Pipeline de ingestão: remover as 8 cópias, mascarar CPF/PIX/conta/telefone/e-mail, dividir em chunks por seção, gerar metadados (`arquivo, tipo, produtor_id, validade_ate`) e criar o índice no Chroma.
2. Função `buscar_documentos(consulta, tipo, produtor_id, valido_em)` com fonte em toda resposta e resposta "não encontrei" para o lote inexistente.
3. Dados limpos: `restricoes_produtor.csv`, `dim_produto.csv` (sinônimos e unidades), agência/conta como texto, `cert_status` calculado.
4. Entregar a tabela de pedidos (§4 de `exploracao-dados.md`) ao Integrante 6 como gabarito do `evalset`.
5. Preencher os `TODO` do README com o que ficar pronto.

**Status em 14/11/2026:** os itens 1 a 3 acima foram implementados (`sabor/`, ver `pipeline-rag.md`) e passam em 21 testes offline. ChromaDB e Gemini foram validados na máquina do Integrante 3 em 15/11. Falta calibrar o limiar de relevância (`scripts/calibrar_limiar.py`).

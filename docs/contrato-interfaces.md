# Contrato de interfaces — proposta para v1

**Situação: rascunho para revisão; ainda não aprovado.** Base: seções 4 a 6 do [Projeto-especificacoes.pdf](../Projeto-especificacoes.pdf). Os nomes e formatos abaixo são propostas de integração, não interfaces já implementadas. O documento de especificações descreve necessidades e arquivos de dados, mas não define as assinaturas destas tools nem o JSON de Pedido.

## Fluxo e convenções

O coordenador recebe a mensagem e encaminha a solicitação para triagem, consulta documental ou comunicação. Conforme o caso, poderá chamar mais de uma capacidade. Uma tool é uma função disponibilizada ao agente; o formato aqui é o de suas entradas e saídas lógicas, independentemente de como será implementada.

- Todas as respostas das tools seguem `{ "status": ..., "dados": ..., "mensagem": ... }`. Os três campos estão sempre presentes; `mensagem` é texto ou `null`.
- `status` é `ok`, `nao_encontrado`, `dados_insuficientes`, `entrada_invalida` ou `erro`. Em `ok`, `dados` segue o formato da tool; nos demais, `dados` é `null` e `mensagem` explica a situação sem expor credenciais ou detalhes internos. Não confundir falha técnica com ausência de informação.
- `nao_encontrado` significa que a consulta foi concluída e não houve correspondência; `dados_insuficientes` significa que faltam dados para decidir. Listas vazias em um resultado `ok` só indicam ausência confirmada na fonte consultada, nunca uma consulta que falhou.
- Datas são strings `AAAA-MM-DD`; mês é inteiro de 1 a 12; períodos são inclusivos. Valores desconhecidos são `null`, não zero ou string vazia. A quantidade é um número decimal em JSON e a unidade é uma string; valores monetários são strings decimais em reais (por exemplo, `"123.45"`) para evitar erros de ponto flutuante.
- Todas as funções são propostas somente para leitura ou geração de texto. Nenhuma altera dados, aloca pedidos ou envia mensagens. O identificador de produtor é uma string estável do cadastro, a confirmar com a equipe.

## Tools propostas

Todas retornam o envelope definido acima. O conteúdo de `dados` em caso `ok` está descrito em cada linha.

| Tool | Parâmetros | `dados` em `ok` | Quando não encontra / não consegue determinar |
| --- | --- | --- | --- |
| `interpretar_pedido` | `texto: str` — pedido em linguagem natural; `data_referencia: str` — data para interpretar expressões relativas, como “sexta” | Objeto **Pedido** abaixo, inclusive incompleto; não inventar campos. | Texto sem pedido identificável: `nao_encontrado`. Texto vazio ou data inválida: `entrada_invalida`. Data relativa ambígua permanece `null` com pendência. |
| `esta_em_safra` | `produto: str`; `mes: int` | `{ "produto": str, "mes": int, "em_safra": bool }` | Produto ou mês sem registro: `nao_encontrado`, com `dados: null`; não usar `false` para ausência de dados. Mês inválido: `entrada_invalida`. |
| `consultar_documentos` | `pergunta: str` | Objeto **Resposta RAG** abaixo, com texto fundamentado e pelo menos uma fonte. | Nenhuma evidência suficiente: `nao_encontrado`, sem gerar resposta especulativa. Pergunta vazia: `entrada_invalida`. |
| `obter_resumo_produtor` | `produtor_id: str`; `inicio: str`; `fim: str` | Objeto **Resumo do produtor** abaixo. | Produtor não cadastrado: `nao_encontrado`; fonte necessária ausente ou incompleta: `dados_insuficientes`. Período inválido: `entrada_invalida`. |
| `redigir_notificacao` | `produtor_id: str`; `pedido: Pedido` | `{ "produtor_id": str, "texto": str }`, com notificação fundamentada nos dados recebidos. | Produtor não cadastrado: `nao_encontrado`; dados insuficientes para redigir: `dados_insuficientes`. Não envia a notificação. |

**Exemplo de ausência de registro de safra:**

```json
{"status": "nao_encontrado", "dados": null, "mensagem": "Não há informação de safra para o produto e mês informados."}
```

O PDF pede sinalização de quantidade acima da capacidade, mas os dados e a forma de consultar capacidade ainda não foram especificados. Até sua definição, não concluir que há capacidade nem inventar uma assinatura para essa consulta.

## Formato Pedido — provisório, sujeito ao JSON do José

O JSON do José ainda não está disponível. Este objeto é apenas uma proposta para discussão e **não representa um formato já aprovado**. Todos os campos mostrados estão presentes; campos singulares desconhecidos usam `null` e listas sem elementos conhecidos usam `[]`.

```json
{
  "pedido_id": null,
  "texto_original": "Preciso de 30 kg de queijo coalho e caixas de goiaba para sexta.",
  "comprador": {"id": null, "nome": null, "contato": null},
  "itens": [
    {"produto": "queijo coalho", "quantidade": 30, "unidade": "kg"},
    {"produto": "goiaba", "quantidade": null, "unidade": "caixa"}
  ],
  "prazo_entrega": null,
  "urgencia": "indeterminada",
  "tipo": null,
  "pendencias": ["Confirmar quantidade de caixas de goiaba.", "Confirmar data de entrega."],
  "alertas": []
}
```

`pedido_id`, dados do comprador, `prazo_entrega` e `tipo` são strings ou `null`; `itens` é uma lista de objetos com `produto` string e `quantidade` numérica ou `null`, e `unidade` string ou `null`. `urgencia` é `urgente`, `normal` ou `indeterminada`; os critérios de classificação precisam ser acordados. `pendencias` e `alertas` são listas de strings. A data de referência é entrada da tool e não deve ser confundida com uma data de entrega confirmada. Dados ausentes devem gerar perguntas ou pendências; não se deve atribuir uma data nem uma quantidade presumida.

## Formato Resposta RAG

```json
{
  "texto": "O documento consultado informa que a certificação está vigente até 31/12/2026.",
  "fontes": [
    {"documento_id": "certificacao-001", "nome": "certificacao-001.pdf", "localizacao": "página 2", "referencia": "certificacoes/certificacao-001.pdf"}
  ]
}
```

`texto` é string não vazia; `fontes` é lista não vazia. Cada fonte tem `documento_id` e `nome` strings, `localizacao` e `referencia` strings ou `null` quando indisponíveis. A equipe de RAG deve confirmar como os IDs e referências serão gerados e como distinguir informação não localizada de erro de acesso. Uma resposta `ok` precisa ter evidência para suas afirmações; uma fonte não deve ser criada por suposição.

## Formato Resumo do produtor

```json
{
  "produtor_id": "produtor-001",
  "periodo": {"inicio": "2026-10-01", "fim": "2026-10-31"},
  "moeda": "BRL",
  "vendas_total": "1250.00",
  "pedidos_alocados": [
    {"pedido_id": "pedido-001", "produto": "mel", "quantidade": 10, "unidade": "kg"}
  ],
  "pendencias_financeiras": [
    {"descricao": "Pagamento pendente", "valor": "150.00"}
  ]
}
```

`produtor_id`, datas e moeda são strings. `vendas_total` é string decimal, com duas casas. Cada pedido alocado contém `pedido_id`, `produto` e `unidade` strings, e `quantidade` numérica; cada pendência contém `descricao` e `valor` strings. `pedidos_alocados` e `pendencias_financeiras` podem ser listas vazias **somente quando a consulta confirmou ausência**. Se fontes necessárias estiverem ausentes ou incompletas, retornar `dados_insuficientes` em vez de inventar zero ou listas vazias. O PDF lista arquivos simulados, mas o esquema real e a fonte das alocações ainda precisam ser confirmados.

## Estado da sessão

Chaves sem prefixo pertencem à sessão. Proposta de valores JSON serializáveis:

| Chave | Tipo | Escrita e significado |
| --- | --- | --- |
| `ultimo_pedido` | `Pedido` ou `null` | Coordenador registra o último pedido interpretado ou atualizado; inclui pendências. Não implica pedido persistido ou alocado. |
| `produtor_em_foco` | `str` ou `null` | Coordenador registra o ID do produtor escolhido pelo usuário. Nome ambíguo não deve ser convertido em ID sem confirmação. |

Valores iniciam em `null` e podem ser limpos quando o usuário mudar de assunto ou de contexto. Ao trabalhar em paralelo, os módulos retornam resultados ao coordenador; este os valida e atualiza as chaves, evitando escritas concorrentes conflitantes. Atualizações em tools e callbacks devem usar o contexto do ADK (`tool_context.state` / `callback_context.state`), em vez de alterar diretamente uma sessão obtida do serviço. Com `InMemorySessionService`, o estado é perdido ao reiniciar; persistência exige um serviço persistente. Fontes e bases completas não são armazenadas no estado. [Documentação do ADK sobre estado](https://adk.dev/sessions/state/).

## Revisão e fixação da v1

- [ ] José: fornecer o JSON de Pedido e validar campos, tipos, pendências e regras de triagem.
- [ ] I3: validar a interface RAG, fonte, localização, identificação e ausência de evidência.
- [ ] Juliana: validar resumo, disponibilidade dos dados financeiros e de alocação, e conteúdo da notificação.
- [ ] Equipe: confirmar as ferramentas, contratos de erro, formatos dos dados simulados e critério de atualização do estado.
- [ ] Registrar neste arquivo a aprovação explícita de José, I3 e Juliana e a data; só então mudar o status para **v1 aprovada**.

As atribuições acima são uma proposta de revisão conforme as frentes citadas e devem ser confirmadas com a equipe. Nenhuma aprovação foi recebida ou presumida.

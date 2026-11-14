# Contrato de interfaces — proposta para v1

O coordenador recebe a mensagem, aciona os módulos necessários e apresenta a resposta. As interfaces abaixo não enviam notificações nem alteram pedidos.

## Tools de triagem existentes

As três retornam dicionários. Os parâmetros opcionais e seus valores padrão estão na [implementação](../sabor_da_terra/tools_triagem.py).

| Tool | Parâmetros | Retorno e ausência de dados |
| --- | --- | --- |
| `avaliar_item_catalogo` | `produto`, `quantidade`, `unidade`, `exige_organico`, `exige_sie`, `mes_entrega`, `data_referencia` | Dados do item, `status_item` e `alertas`. Produto não encontrado: `status_item = "nao_encontrado"`; produto ambíguo: `"ambiguo"`. A consulta de safra faz parte desta tool. |
| `consultar_produtores_ou_organicos` | `termo_busca_produtor`, `apenas_listar_organicos_vigentes`, `data_referencia` | Busca comum: `termo_busca` e `produtores_encontrados`; modo orgânicos: `data_referencia` e `produtores_organicos_vigentes`. Sem resultados, a lista correspondente fica vazia. Busca sem termo pode retornar todos os produtores. |
| `realizar_triagem_completa_pedido` | Obrigatórios: `remetente_identificado`, `tipo_cliente`, `tipo_demanda`, `itens`. Opcionais: `id_pedido`, `canal`, `data_referencia`, `mes_entrega`, `urgente_no_texto`, `exige_organico_global`, `solicita_dados_sensiveis`, `termo_identificacao_produtor`, `tool_context`. | Dicionário de triagem descrito no [schema de José](../sabor_da_terra/schemas_triagem.py). Sem itens, `status_viabilidade = "encaminhar_modulo_especialista"`; item não encontrado recebe `status_item = "nao_encontrado"`. Com contexto ADK, grava `resultado_triagem` no estado. Erros podem gerar exceções. |

O resultado `TriagemPedidoOutput` contém identificação, tipo de demanda, urgência, viabilidade, data e mês de referência, itens, valor estimado, alertas, módulos recomendados e resumo. Tipos e campos completos estão em [`schemas_triagem.py`](../sabor_da_terra/schemas_triagem.py). As mensagens brutas de [`dados/pedidos.json`](../dados/pedidos.json) têm formato diferente; a extração para a triagem depende do agente.

### Pontos para alinhar com José

| Ponto | Comportamento atual | Decisão pendente | Solução adotada (José) |
| --- | --- | --- | --- |
| Quantidade e unidade | Usa `1.0` e `kg` como valores padrão. | Como representar e solicitar informações ausentes. | `quantidade` e `unidade` passam a ser `Optional` com padrão `None` (inclusive em `ItemPedidoInput`). Sem `unidade`, a tool usa a unidade oficial da tabela de preços (kg, maço, dúzia, litro, unidade). Sem `quantidade`, a tool devolve o `preco_unitario`, deixa `subtotal_estimado = None`, marca o item como `"parcial"`, gera o alerta `QUANTIDADE_NAO_INFORMADA` e o pedido fica em `status_viabilidade = "requer_esclarecimento"`. Assim o agente pergunta a quantidade ("O queijo coalho custa R$ 32,00/kg. Qual quantidade você deseja?") em vez de assumir 1 kg. |
| Data e mês | Usa uma data fixa e outubro como valores padrão. | Quem fornece a data de referência e como tratar prazo desconhecido. | `data_referencia` é a data "de hoje" passada pelo coordenador; se não vier, assume `"2026-10-30"` (data-base do dataset simulado). Ela é usada para validar certificações (ex.: P008 vencida em 2026-09-30). `mes_entrega` passa a ser `Optional[int] = None` e continua `None` até o cliente informar o prazo. Em pedido ou cotação sem prazo, a safra do mês atual é só prévia, o status fica `"requer_esclarecimento"`, é gerado o alerta `PRAZO_NAO_INFORMADO` e o novo campo `campos_pendentes` lista o que falta (ex.: `["quantidade", "prazo_entrega"]`). Se o cliente informar só a quantidade, resta `["prazo_entrega"]` e o agente cobra a data antes de fechar o pedido. |
| Sazonalidade | Pode assumir safra `alta` quando não encontra registro. | Como indicar que não há informação de safra. | Todo produto vendido precisa ter sazonalidade cadastrada. A busca em `sazonalidade.csv` usa o nome exato e, se não achar, o nome-base (cobre "tomate santa cruz"/"tomate cereja" → "tomate", "goiaba paluma extra"/"especial" → "goiaba paluma" e "pimentão verde"/"colorido" → "pimentão"). Se ainda assim não houver registro, nunca assume `alta`: `disponibilidade_safra = "nenhuma"`, `status_item = "indisponivel"` e alerta crítico `FORA_DE_SAFRA` informando que o item não está disponível para venda. |
| Valores monetários | Usa `float` para preços e totais. | Qual representação e arredondamento adotar. | A triagem continua com `float` (`preco_unitario`, `subtotal_estimado`, `valor_total_estimado`), aplicando `round(valor, 2)` em cada etapa do cálculo (preço base, preço com desconto, subtotal e acumulação do total). Mantém o tipo numérico no JSON Schema, permitindo comparações e somas diretas, sem dízimas como `19.800000000000004`. |
| Campos extras | Pode retornar campos que não constam de `ItemTriado`. | Quais campos devem fazer parte da interface e sobreviver à validação. | `opcoes_catalogo: list[str]` entrou oficialmente em `ItemTriado`, para que as opções de produtos ambíguos (ex.: "goiaba") não se percam. `catalogo_disponivel` foi removido do item. A própria tool valida o retorno com `TriagemPedidoOutput(...).model_dump()`, e `tipo_demanda` passou a ser tipado como `TipoDemanda`, com normalizador (ex.: "Pedido de Compra" → `pedido_compra`). O conteúdo de `session.state["resultado_triagem"]` corresponde campo a campo ao schema. |
| Erros | Falhas podem gerar exceções. | Como distinguir falhas técnicas de dados não encontrados. | As 3 tools têm `try/except` e retornam o envelope padronizado `{"status", "dados", "mensagem"}`: em sucesso (`status = "ok"`), `dados` contém o resultado e `mensagem` é `null`; sem resultado ou em falha (`"nao_encontrado"`, `"dados_insuficientes"`, `"entrada_invalida"` ou `"erro"`), `dados` é `null` e `mensagem` explica o motivo. Parâmetro inválido (data fora de `AAAA-MM-DD`, mês fora de 1..12, quantidade ≤ 0 ou `tipo_demanda` desconhecido) → `"entrada_invalida"`. Produto ou produtor inexistente → `"nao_encontrado"`. Falha ao abrir CSV ou banco (`OSError`) → `"erro"`. O agente não cai por exceção não tratada. |

## Tools propostas para integração

Para as tools propostas abaixo, sugerimos que toda resposta tenha três campos: `status`, `dados` e `mensagem`.

- **Sucesso:** `status` é `"ok"`, `dados` contém o resultado e `mensagem` pode ser `null`.
- **Sem resultado ou falha:** `status` é `"nao_encontrado"`, `"dados_insuficientes"`, `"entrada_invalida"` ou `"erro"`; `dados` é `null` e `mensagem` explica o motivo.

Esse formato ainda é uma proposta para as tools abaixo. As tools de triagem já implementadas retornam dicionários próprios e **não seguem esse padrão**.

| Tool proposta | Parâmetros | Resultado em `ok` | Sem informação |
| --- | --- | --- | --- |
| `interpretar_pedido` | `texto: str`, `data_referencia: str` | Pedido estruturado; integração com a triagem existente a definir. | `nao_encontrado`; campos ambíguos permanecem pendentes. |
| `consultar_documentos` | `pergunta: str` | Resposta RAG com texto e fontes. | `nao_encontrado` quando não houver evidência suficiente. |
| `obter_resumo_produtor` | `produtor_id: str`, `inicio: str`, `fim: str` | Resumo do produtor no período inclusivo. | Produtor ausente: `nao_encontrado`; fonte incompleta: `dados_insuficientes`. |
| `redigir_notificacao` | `produtor_id: str`, `pedido: Pedido` | `{produtor_id: str, texto: str}`; somente redação. | Produtor ausente: `nao_encontrado`; pedido incompleto: `dados_insuficientes`. |

Entradas inválidas retornariam `entrada_invalida`; falhas técnicas, `erro`. Datas propostas usam `AAAA-MM-DD`. Não confundir fonte sem resultados com fonte indisponível.

## Formatos propostos

**Pedido:** o resultado atualmente implementado é `TriagemPedidoOutput`. O formato de entrada comum e seu mapeamento para a triagem ainda precisam ser acordados com José. Valores desconhecidos devem ser identificados como pendentes, sem pressupor que a implementação atual já faça isso.

**Resposta RAG:**

```json
{"texto": "Certificação vigente até 31/12/2026.", "fontes": [{"documento_id": "cert-001", "nome": "cert-001.txt", "localizacao": null, "referencia": "certificacoes/cert-001.txt"}]}
```

Em caso de sucesso, `texto` é uma string e `fontes` é uma lista não vazia; localização e referência podem ser `null`. A fonte deve sustentar a resposta.

**Resumo do produtor:**

```json
{"produtor_id": "P001", "periodo": {"inicio": "2026-10-01", "fim": "2026-10-31"}, "moeda": "BRL", "vendas_total": "1250.00", "pedidos_alocados": [{"pedido_id": "PED-001", "produto": "mel", "quantidade": 10, "unidade": "kg"}], "pendencias_financeiras": [{"descricao": "Pagamento pendente", "valor": "150.00"}]}
```

Valores monetários são strings decimais; listas vazias indicam ausência confirmada. A fonte dos pedidos alocados e a disponibilidade dos dados financeiros precisam ser confirmadas.

## Estado da sessão

| Chave | Situação | Conteúdo |
| --- | --- | --- |
| `resultado_triagem` | Já escrita pela tool de triagem quando há contexto ADK. | Resultado bruto da triagem, possivelmente com campos extras. |
| `ultimo_pedido` | Proposta. | Último pedido estruturado ou `null`. |
| `produtor_em_foco` | Proposta. | ID do produtor ou `null`. |

A equipe deve decidir se `ultimo_pedido` duplica `resultado_triagem` e como evitar escritas concorrentes. Tools e callbacks atualizam estado pelo contexto do ADK. `InMemorySessionService` perde o estado ao reiniciar; um serviço persistente deve ser escolhido se necessário.

## Revisão para fixar a v1

- [ ] **José:** validar triagem, formato de Pedido, informações ausentes e erros.
- [ ] **Matheus Audiere:** validar resposta RAG, fontes e ausência de evidência.
- [ ] **Juliana:** validar resumo, dados disponíveis e notificação.
- [ ] **Equipe:** acordar envelope, estado, concorrência e necessidade das tools propostas.

As atribuições de revisão são propostas e devem ser confirmadas com a equipe.

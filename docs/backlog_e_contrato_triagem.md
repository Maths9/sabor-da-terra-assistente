# Backlog do Produto & Contrato de Integração — Módulo de Triagem

**Projeto:** Assistente Inteligente para Gestão da Cooperativa Agrícola *Sabor da Terra*  
**Responsável:** Integrante 2 — José Portela (*Product Owner & Engenheiro do Módulo de Triagem*)  
**Arquivos de Código Entregues:**
- [`sabor_da_terra/schemas_triagem.py`](file:///c:/sabor-da-terra-assistente/sabor_da_terra/schemas_triagem.py) *(74 linhas — Contratos Pydantic)*
- [`sabor_da_terra/tools_triagem.py`](file:///c:/sabor-da-terra-assistente/sabor_da_terra/tools_triagem.py) *(216 linhas — FunctionTools Dinâmicas)*
- [`validacao/teste_triagem.py`](file:///c:/sabor-da-terra-assistente/validacao/teste_triagem.py) *(Validação Offline sem gasto de tokens)*

---

## 1. Product Backlog Priorizado (12 Dias / 2 Sprints)

| ID | Sprint | User Story | Critérios de Aceite (DoD) |
| :--- | :---: | :--- | :--- |
| **US-01** | Sprint 1 | Como equipe comercial (Dona Lúcia), quero que os pedidos em linguagem coloquial (WhatsApp, e-mail, formulário web, inclusive em inglês) sejam estruturados e classificados por tipo e urgência. | Extrai itens, quantidades, prazo e classifica nos 5 tipos de demanda (`pedido_compra`, `cotacao_evento`, `consulta_comercial`, `comunicacao_produtor`, `notificacao_fiscalizacao`) validando em [`TriagemPedidoOutput`](file:///c:/sabor-da-terra-assistente/sabor_da_terra/schemas_triagem.py#L46-L64). |
| **US-02** | Sprint 1 | Como analista de triagem, quero validar preços, descontos de atacado, sazonalidade do mês de entrega e limites semanais nos CSVs. | [`avaliar_item_catalogo`](file:///c:/sabor-da-terra-assistente/sabor_da_terra/tools_triagem.py#L64-L147) descobre `tabela_precos_*.csv` vigente, detecta ambiguidades dinamicamente (`goiaba`, `tomate`, `pimentão`, `manteiga`), lê limites semanais (`~80kg/sem`, `~120 dz/sem`) e checa safra do `mes_entrega`. |
| **US-03** | Sprint 1 | Como gestor de compliance, quero filtrar produtores ativos, bloquear certificações orgânicas vencidas e sinalizar restrições sanitárias `sem SIE`. | Bloqueia `P015` (`inativo`), bloqueia `P008` (Josefa — certificação orgânica vencida em `2026-09-30`) e gera `RESTRICAO_SIE` para `P017` (frango caipira) e `P011` (iogurte natural) em vendas institucionais/revenda. |
| **US-04** | Sprint 1 | Como cooperado (ex.: Maria das Graças `P001` ou Cícero `P003`) ou comprador orgânico (`PED-2026-010`), quero ser identificado por pistas do cadastro ou listar todos os orgânicos vigentes. | [`consultar_produtores_ou_organicos`](file:///c:/sabor-da-terra-assistente/sabor_da_terra/tools_triagem.py#L150-L169) identifica produtores por telefone, nome, município ou produto sem expor dados sensíveis e lista produtores com certificação orgânica vigente. |
| **US-05** | Sprint 2 | Como DPO/Compliance (LGPD), quero garantir que nenhum CPF ou dado bancário de produtor vaze nas saídas das tools. | `_ler_csv(..., filtrar_lgpd=True)` remove `cpf`, `chave_pix`, `banco`, `agencia`, `conta_corrente` e `data_nascimento` na fonte antes de retornar ao LLM. |
| **US-06** | Sprint 2 | Como Orquestrador ADK (Integrante 4), quero receber `modulos_recomendados` no `session.state["resultado_triagem"]` para rotear entre Estoque, RAG e Comunicação com Produtores. | [`realizar_triagem_completa_pedido`](file:///c:/sabor-da-terra-assistente/sabor_da_terra/tools_triagem.py#L172-L246) preenche `modulos_recomendados` e grava automaticamente em `tool_context.state["resultado_triagem"]`. |

---

## 2. Gabarito Oficial dos 15 Casos de `pedidos.json`

| ID Pedido | Remetente / Comprador (`pedidos.json`) | Tipo de Demanda | Urgência | Alertas e Regras de Negócio Esperadas na Triagem | Módulos Recomendados |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **PED-2026-001** | Restaurante Raízes (Carlos) | `pedido_compra` | `media` | Entrega `01/nov` (mês 11): queijo coalho (30kg), manteiga de garrafa (10kg), mel silvestre (5kg), coentro (20mç), cebolinha (10mç), ricota (5kg - `P003`). Todos viáveis. | `estoque_safra`, `comunicacao_produtores` |
| **PED-2026-002** | Mercado Bom Preço (Seu Ernesto) | `pedido_compra` | `alta` | Entrega `04/nov`: `goiaba paluma` (ambíguo: `extra` vs `especial`), `tomate` (ambíguo: `santa cruz` vs `cereja`), banana prata (40kg), maracujá (25kg), macaxeira (60kg), inhame (30kg), alface (50un), rúcula (30mç). | `estoque_safra`, `rastreabilidade_compliance`, `comunicacao_produtores` |
| **PED-2026-003** | Chef Amanda — Bistrô Sertão Gourmet | `pedido_compra` | `critica` | Urgente para amanhã: *"queijo mais artesanal"* (`PRODUTO_AMBIGUO`) + `mel de jandaíra` 3kg (exclusivo `P002`, R\$ 140/kg). | `estoque_safra`, `comunicacao_produtores` |
| **PED-2026-004** | Prefeitura de Garanhuns — PNAE | `pedido_compra` | `alta` | Contrato 045/2026-PNAE (possui CPF do coordenador no rodapé): `goiaba` e `tomate` (`PRODUTO_AMBIGUO`), `ovos caipira` 100 dz (`CAPACIDADE_PROXIMA_DO_LIMITE` — 100/120 dz), `mel silvestre` orgânico 20kg (`CERTIFICACAO_VENCIDA` para `P008`, aptos `P002` e `P018`). | `estoque_safra`, `rastreabilidade_compliance`, `comunicacao_produtores` |
| **PED-2026-005** | Dona Cremilda — Lanchonete da Feira | `pedido_compra` | `media` | Queijo coalho 10kg + `"5kg de manteiga"` (`PRODUTO_AMBIGUO`: `manteiga de garrafa` vs `queijo manteiga`). | `estoque_safra`, `comunicacao_produtores` |
| **PED-2026-006** | Rede SuperBom Atacado | `pedido_compra` | `critica` | Pedido urgente para HOJE (`29/10`): queijo coalho 200kg, queijo manteiga 50kg, mel silvestre orgânico 40kg (`P008` bloqueada), `goiaba` 300kg (`PRODUTO_AMBIGUO`). *(Nota: SuperBom possui boletos vencidos em `financeiro.csv`)*. | `estoque_safra`, `rastreabilidade_compliance`, `comunicacao_produtores` |
| **PED-2026-007** | Hotel Fazenda Serra Negra | `cotacao_evento` | `alta` | Evento em `08/nov` (mês 11): `goiaba` 20kg (`PRODUTO_AMBIGUO`), `cajá` 10kg (`SAFRA_BAIXA` em nov, `nenhuma` em out), `frango caipira` 40kg (`RESTRICAO_SIE` — `P017` sem SIE / NC-001 ADAGRO). | `estoque_safra`, `rastreabilidade_compliance` |
| **PED-2026-008** | Marcos — Sorveteria Tropical | `consulta_comercial` | `media` | Pede 50kg/sem de `morango` e `amora` orgânicos (`P014` Mariana): ambos em safra `media` em outubro, desconto de atacado aplicável, produção limitada. | `estoque_safra`, `rastreabilidade_compliance` |
| **PED-2026-009** | Hospital São Francisco | `cotacao_evento` | `alta` | Pede `"Frutas variadas"` e `"Hortaliças"` (`PRODUTO_AMBIGUO`), `ovos caipira` 50 dz (`SEM_PRODUTOR_ORGANICO`), exige certificações/fichas técnicas e **pede CPF dos produtores** (`SOLICITACAO_DADOS_SENSIVEIS`). | `estoque_safra`, `rastreabilidade_compliance` |
| **PED-2026-010** | João Pedro — Feira Orgânica do Recife | `consulta_comercial` | `media` | Solicita lista completa de produtos orgânicos vigentes, produtores, validades e preços. Atendido por [`consultar_produtores_ou_organicos`](file:///c:/sabor-da-terra-assistente/sabor_da_terra/tools_triagem.py#L150-L169) (exclui `P008` vencida). | `rastreabilidade_compliance` |
| **PED-2026-011** | Tropical Fruits Exportadora (Inglês) | `consulta_comercial` | `alta` | E-mail em inglês: `Mango` 500kg (`manga tommy`), `Guava` 300kg (`goiaba` ambígua), `Passion fruit` 200kg (`maracujá` — `SEM_PRODUTOR_ORGANICO`). | `estoque_safra`, `rastreabilidade_compliance` |
| **PED-2026-012** | Maria das Graças (`P001`) | `comunicacao_produtor` | `media` | Produtora `P001` pergunta quanto vendeu no mês e se o pagamento do Mercado Bom Preço de setembro caiu. Identificada como `P001` e encaminhada para `comunicacao_produtores`. | `comunicacao_produtores` |
| **PED-2026-013** | SESC — Unidade Garanhuns | `cotacao_evento` | `alta` | Colônia de férias em `jan/2027` (mês 1): `"Frutas variadas"` e `"Hortaliças variadas"` (`PRODUTO_AMBIGUO`), `ovos caipira` 200 dz (`ACIMA_DA_CAPACIDADE` > 120 dz), `frango caipira` 100kg (`ACIMA_DA_CAPACIDADE` > 80kg e `RESTRICAO_SIE`). | `estoque_safra`, `rastreabilidade_compliance` |
| **PED-2026-014** | ADAGRO — Fiscalização Agropecuária | `notificacao_fiscalizacao` | `critica` | Notificação de inspeção sanitária (11 e 12/nov): solicita laudos, certificações, contratos, últimos 3 lotes e cadastro com CPF (`SOLICITACAO_DADOS_SENSIVEIS` no chat aberto). Roteado para `rastreabilidade_compliance`. | `rastreabilidade_compliance` |
| **PED-2026-015** | Cícero (`P003`) | `comunicacao_produtor` | `alta` | Produtor `P003` (Caetés) avisa que tem 200kg de queijo coalho e 30kg de manteiga prontos e envia CPF do vizinho Sebastião para cadastro. Identificado como `P003`. | `estoque_safra`, `comunicacao_produtores` |

---

## 3. Como Integrar no `agent.py` (Para o Integrante 4 — Jorge)

```python
from google.adk.agents import LlmAgent
from sabor_da_terra.tools_triagem import LISTA_TOOLS_TRIAGEM

agente_triagem = LlmAgent(
    name="agente_triagem",
    model="gemini-2.5-flash",
    description="Realiza a triagem de pedidos, cotações, consultas de catálogo e identificação de produtores.",
    instruction="""
    Você é o Especialista de Triagem da Cooperativa Sabor da Terra.
    1. Ao receber qualquer mensagem, extraia o remetente, tipo de cliente, tipo de demanda, mês de entrega e itens.
    2. Chame `realizar_triagem_completa_pedido` passando os itens solicitados.
    3. Se o cliente pedir a lista de orgânicos vigentes (ex: PED-2026-010) ou se precisar identificar um produtor por pistas (ex: Caetés, telefone), use `consultar_produtores_ou_organicos`.
    4. Nunca invente preços, safras ou produtores e jamais exponha CPFs ou dados bancários.
    """,
    tools=LISTA_TOOLS_TRIAGEM,
)
```

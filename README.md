# 🌱 Sabor da Terra — Assistente Inteligente

Assistente operacional inteligente baseado em agentes de IA desenvolvido para a **Cooperativa Sabor da Terra** (Garanhuns / Agreste Meridional – PE).

## Sobre o Projeto e Escopo

O **Assistente Sabor da Terra** automatiza e dá suporte às rotinas comerciais, documentais, sanitárias e de atendimento da cooperativa, combinando um agente coordenador construído com **Google ADK (`2.14.0`)** e **Gemini**, uma API **FastAPI** com autenticação stateless, interface web em **React 18 + TypeScript**, banco operacional **PostgreSQL (Cloud SQL)**, busca semântica documental (**RAG** com **ChromaDB**) e persistência de sessões no **Cloud Firestore**.

### Escopo Funcional

A aplicação atende **exclusivamente** demandas da Cooperativa Sabor da Terra por meio de dois portais com perfis e permissões isolados:

- **Portal do Operador (Gestão Cooperativa)**
  - Visualização da caixa de pedidos pendentes (`PED-2026-XXX`) e atendimento assistido por chat.
  - **Triagem completa de pedidos**: análise de múltiplos itens, viabilidade, tabela de preços, descontos de atacado, calendário de sazonalidade e indicação de produtores aptos.
  - **Compliance sanitário e crédito**: verificação de inadimplência/títulos vencidos de compradores, validade de certificações orgânicas, restrições SIE e não conformidades ADAGRO.
  - **Rastreabilidade de lotes** (`LOT-YYYY-NNNN`), temperatura de transporte, validade e inspeção visual.
  - **Consulta documental (RAG)** sobre certificações, laudos sanitários, inspeção ADAGRO 2026, contratos (`PNAE Garanhuns`, `Mercado Bom Preço`, `Restaurante Raízes`) e fichas técnicas, com **citação obrigatória de fontes**.
  - **Geração de notificações em modo rascunho** (`somente_rascunho: true`, sem envio automático externo).
- **Portal do Produtor (Cooperado)**
  - Painel individual com vendas, pagamentos recebidos/pendentes/vencidos, entregas e status de certificação.
  - Chat em primeira pessoa com isolamento estrito por `produtor_id`, bloqueando acesso a dados de outros produtores, contratos comerciais e relatórios internos da ADAGRO.

### Segurança, RBAC e LGPD

- **4 Guardrails Determinísticos (Callbacks ADK):**
  1. `before_model_callback` (`injetar_contexto_temporal`): mascara/bloqueia PII na entrada (CPF, RG, data de nascimento, chave PIX e conta bancária), injeta a data atual e reforça a restrição estrita de escopo.
  2. `before_tool_callback` (`validar_acesso_tool`): aplica **RBAC *fail-closed*** (Operador vs. Produtor), isolamento por `produtor_id` e bloqueio de dados financeiros individuais de produtores para operadores.
  3. `after_tool_callback` (`processar_retorno_tool`): sanitiza retornos recursivamente, filtra/anonimiza dados conforme o perfil e sincroniza `session.state`.
  4. `after_model_callback` (`sanitizar_resposta_modelo`): camada final de proteção LGPD sobre o texto gerado pelo modelo.
- **Proteção em Repouso e em Trânsito:** colunas sensíveis (`cpf_cifrado`, `chave_pix_cifrada`, `conta_corrente_cifrada`, `data_nascimento_cifrada`) criptografadas com `Fernet/AES` no PostgreSQL, tokens assinados com `HMAC-SHA256` e rotas nativas abertas do ADK (`/run`, `/apps/`) desabilitadas em produção.

---

## Link em Produção

> **Aplicação publicada (Google Cloud Run):**
> [https://sabor-da-terra-agente-187012578538.southamerica-east1.run.app/](https://sabor-da-terra-agente-187012578538.southamerica-east1.run.app/)

---

## Arquitetura da Solução

> **IMAGEM DA ARQUITETURA:**
>
> [Arquitetura do Assistente Sabor da Terra](docs/arquitetura.png)

### Visão Geral das Camadas

| Camada | Tecnologias e Componentes | Responsabilidade |
| --- | --- | --- |
| **1. Frontend** | React 18, TypeScript, Vite (`frontend/`) | Portais do Operador e do Produtor, painéis operacionais e cliente REST autenticado (`agentService.ts`). |
| **2. Backend API** | FastAPI, Uvicorn (`sabor_da_terra/api/`) | Autenticação HMAC (`/api/auth/*`), rotas determinísticas sem LLM (`/api/pedidos-pendentes`, `/api/produtores/*`) e chat/sessões (`/api/chat`, `/api/sessoes`). |
| **3. Orquestração & Guardrails** | Google ADK 2.14.0, Gemini (`agent.py`, `callbacks.py`, `seguranca.py`) | Agente coordenador `root_agent` (`LlmAgent`), 4 callbacks determinísticos de LGPD/RBAC e gestão de estado. |
| **4. Ferramentas (9 Tools)** | `sabor_da_terra/tools/` e `sabor_da_terra/rag.py` | **Triagem (3):** `realizar_triagem_completa_pedido`, `avaliar_item_catalogo`, `consultar_produtores_ou_organicos` · **Operacional/Compliance (5):** `verificar_compliance_e_credito`, `consultar_pedidos_pendentes`, `consultar_lotes`, `obter_resumo_produtor`, `redigir_notificacao` · **RAG (1):** `consultar_documentos`. |
| **5. Dados, RAG & GCP** | Cloud SQL (PostgreSQL 16), ChromaDB, Cloud Firestore, Secret Manager, Vertex AI, Cloud Run | 6 tabelas operacionais (SQLAlchemy 2.0 + Alembic + Fernet), índice vetorial (`index/`, 20 docs / 33 chunks, `gemini-embedding-001` 768d) e sessões persistentes (`adk_sessions`). |

### Estrutura do Projeto

```text
sabor-da-terra-assistente/
├── .env.example                  # Modelo oficial das variáveis de ambiente (na raiz)
├── alembic.ini                   # Configuração do Alembic para migrações PostgreSQL
├── Dockerfile                    # Build multi-stage (React + FastAPI + ADK + índice RAG)
├── requirements.txt              # Dependências Python do projeto
├── dados/                        # CSVs/JSON de carga e documentos textuais (certificações, contratos, fichas)
├── docs/                         # Documentação técnica, contratos e diagramas
├── frontend/                     # Interface web React 18 + TypeScript + Vite
├── index/                        # Índice vetorial ChromaDB pré-gerado (sabor_da_terra_docs)
├── migrations/                   # Migrações versionadas das 6 tabelas operacionais
├── scripts/
│   ├── importar_dados.py         # Carga idempotente (UPSERT) dos CSVs/JSON com criptografia LGPD
│   └── indexar_rag.py            # Geração/atualização do índice vetorial ChromaDB
├── validacao/                    # Provas técnicas e conjunto de avaliação ADK
└── sabor_da_terra/
    ├── __init__.py               # Exporta o agente para o Google ADK
    ├── agent.py                  # Instância e configuração do agente coordenador
    ├── callbacks.py              # 4 callbacks determinísticos (LGPD, RBAC e estado)
    ├── config.py                 # Configurações centralizadas e leitura do .env da raiz
    ├── prompts.py                # Instruções e política operacional do coordenador
    ├── rag.py                    # Pipeline vetorial ChromaDB + FunctionTool consultar_documentos
    ├── seguranca.py              # Detecção e sanitização de PII/LGPD
    ├── database/                 # SQLAlchemy 2.0 (connection, models, crypto, repositories)
    ├── tools/                    # Ferramentas de triagem, compliance, rastreabilidade e notificações
    └── api/                      # Backend FastAPI, autenticação HMAC e sessões Firestore
```

---

## Como Rodar o Projeto Completo

### Pré-requisitos

- **Python 3.11+**
- **Node.js 20+** (para rodar ou compilar o frontend React)
- **Docker** (recomendado para subir o PostgreSQL 16 local ou rodar a imagem completa)
- Credencial do **Google AI Studio** (`GOOGLE_API_KEY`) **ou** projeto GCP com **Vertex AI** habilitado (`gcloud auth application-default login`)

---

### Passo 1 — Preparar o Ambiente Python

Clone o repositório e crie o ambiente virtual a partir da raiz do projeto.

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Confira a instalação do Google ADK:

```bash
adk --version
```

---

### Passo 2 — Configurar o arquivo `.env` na raiz

Copie o modelo `.env.example` para `.env` na **raiz do projeto** (o arquivo `.env` é ignorado pelo Git e pelo Docker):

```bash
cp .env.example .env
```

Escolha uma das duas opções de autenticação para o modelo Gemini (além das variáveis `DB_*` do PostgreSQL e `SABOR_AUTH_SECRET`):

#### Opção A — Google AI Studio (`GOOGLE_API_KEY`, mais rápida para testes locais)

```env
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=cole_sua_chave_aqui
```

#### Opção B — Vertex AI (sem API key, usando ADC local)

1. Autentique suas Application Default Credentials:

```bash
gcloud auth application-default login
```

2. Preencha no `.env` da raiz:

```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=projeto-sabor-da-terra
GOOGLE_CLOUD_LOCATION=global
```

> **Modelo usado pelo agente:** configurado via `SABOR_MODEL` em `sabor_da_terra/config.py` (padrão `gemini-3.5-flash-lite`; também validado com `gemini-3.5-flash` na Vertex AI conforme `validacao/README.md`).

---

### Passo 3 — Subir o PostgreSQL Local, Migrar e Popular os Dados

1. Suba uma instância **PostgreSQL 16** local com Docker (exemplo na porta `5434` para evitar conflito com eventual PostgreSQL nativo na `5432`; ajuste `DB_PORT` no `.env` conforme a porta escolhida):

```powershell
docker run --name sabor-postgres-local `
  -e POSTGRES_DB=sabor_terra `
  -e POSTGRES_USER=sabor_app `
  -e POSTGRES_PASSWORD=senha_local_de_exemplo `
  -p 5434:5432 `
  -d postgres:16-alpine
```

2. Execute as migrações **Alembic** para criar as 6 tabelas (`produtores`, `transacoes_financeiras`, `lotes`, `precos`, `sazonalidade`, `pedidos`) e importe os dados operacionais (com criptografia `Fernet` em `cpf_cifrado`, `chave_pix_cifrada`, `conta_corrente_cifrada` e `data_nascimento_cifrada`):

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m scripts.importar_dados
```

**Linux / macOS:**

```bash
alembic upgrade head
python -m scripts.importar_dados
```

> **Sobre o índice RAG (`index/`):** o índice vetorial ChromaDB já vem empacotado no repositório com os 20 documentos / 33 chunks sanitizados. Caso altere algum documento em `dados/`, reindexe executando `python -m scripts.indexar_rag`.

---

### Passo 4 — Executar API (FastAPI + ADK) e Frontend (React)

1. Suba o backend **FastAPI + Google ADK** na porta `8080`:

```powershell
.\.venv\Scripts\uvicorn.exe sabor_da_terra.api:app --host 127.0.0.1 --port 8080 --reload
```

*(No Linux/macOS com a `.venv` ativa: `uvicorn sabor_da_terra.api:app --host 127.0.0.1 --port 8080 --reload`.)*

2. Em outro terminal, suba o frontend em `frontend/` (o `vite.config.ts` já redireciona `/api/*` para `http://127.0.0.1:8080`):

```bash
cd frontend
npm install
npm run dev
```

3. Acesse `http://localhost:5173` para escolher entre **Área do Operador** e **Área do Produtor**.
   - Se preferir servir tudo diretamente pela porta `8080` via FastAPI sem `npm run dev`, gere o build estático antes com `cd frontend && npm run build`.

---

### Passo 5 — Executar o Agente Diretamente via Google ADK (Opcional)

Com o ambiente virtual ativado, você também pode executar o agente pelo CLI ou interface web de desenvolvimento do ADK a partir da raiz do projeto:

```bash
adk run sabor_da_terra
```

Ou via interface web local do ADK (selecionando `sabor_da_terra`):

```bash
adk web
```

> **Nota sobre RBAC no ADK direto (`adk run` / `adk web`):** o guardrail `validar_acesso_tool` é *fail-closed* e exige `perfil_usuario` no `session.state` (`"operador"` ou `"produtor"` + `"produtor_em_foco"`). Pela API + Interface React isso é preenchido automaticamente a partir do token de sessão; ao testar diretamente via `adk run` ou `adk web`, informe `perfil_usuario` no estado inicial da sessão (como em `validacao/evalset_cooperativa.evalset.json`). Consulte o [guia oficial do ADK](https://adk.dev/get-started/python/) para mais detalhes.

---

## Executar com Docker

A imagem multi-stage compila o frontend React (`frontend/dist`) e empacota o agente (`sabor_da_terra/`), as migrações (`migrations/` + `alembic.ini`), os scripts (`scripts/`), os documentos (`dados/`), o índice RAG (`index/`) e o servidor FastAPI.

### 1. Construir a imagem

Na raiz do repositório (`--platform linux/amd64` garante compatibilidade com o Cloud Run):

```bash
docker build --platform linux/amd64 -t sabor-da-terra-assistente:v2 .
```

### 2. Rodar localmente

> **Nota:** Quando o container roda localmente apontando para um PostgreSQL também na máquina local, passe `-e DB_HOST=host.docker.internal` para o container alcançar o host.

**Com Google AI Studio (`.env` da raiz):**

```bash
docker run --rm -p 8080:8080 --env-file .env -e DB_HOST=host.docker.internal sabor-da-terra-assistente:v2
```

**Com Vertex AI (montando o ADC local em modo somente leitura):**

```bash
docker run --rm -p 8080:8080 \
  --env-file .env \
  -e DB_HOST=host.docker.internal \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/tmp/adc.json:ro" \
  sabor-da-terra-assistente:v2
```

### 3. Parar e remover o container

```bash
docker ps                              # lista containers em execução
docker stop <NOME_OU_ID_DO_CONTAINER>  # para o container
```

---

## Testar os Endpoints da API

Com o servidor em execução na porta `8080`, rode em outro terminal:

```bash
# Saúde do serviço e agentes carregados
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/list-apps

# Emitir token de sessão para o perfil Operador (ou perfil="produtor", produtor_id="P001")
TOKEN=$(curl -s -X POST http://127.0.0.1:8080/api/auth/sessao \
  -H "Content-Type: application/json" \
  -d '{"perfil": "operador"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Enviar mensagem autenticada ao chat (retorna session_id, resposta, fontes RAG e estado)
curl -s -X POST http://127.0.0.1:8080/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quais pedidos pendentes temos hoje?"
  }'

# Consultar pedidos pendentes (somente Operador) e lista pública de produtores (vindos do PostgreSQL)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/pedidos-pendentes
curl -s http://127.0.0.1:8080/api/produtores
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/produtores/P001
```

---

## Variáveis de Ambiente Suportadas

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `PORT` | `8080` | Porta HTTP em que o servidor escuta (`0.0.0.0:$PORT`; definida automaticamente no Cloud Run). |
| `SABOR_MODEL` | `gemini-3.5-flash-lite` | Modelo Gemini usado pelo agente coordenador (`sabor_da_terra/config.py`). |
| `SABOR_DATA_BACKEND` | `postgres` | Backend de dados operacionais: `postgres` (PostgreSQL / Cloud SQL) ou `csv` (fallback local). |
| `DB_HOST` | `127.0.0.1` | Host do PostgreSQL (`127.0.0.1` localmente / Auth Proxy, ou `/cloudsql/PROJETO:REGIAO:INSTANCIA` no Cloud Run). |
| `DB_PORT` | `5432` | Porta TCP do PostgreSQL (ex.: `5432`, `5433` no Auth Proxy ou `5434` no Docker local). |
| `DB_NAME` | `sabor_terra` | Nome do banco de dados PostgreSQL. |
| `DB_USER` | `sabor_app` | Usuário da aplicação no PostgreSQL. |
| `DB_PASSWORD` | — | Senha do usuário do PostgreSQL (injetada via Secret Manager no Cloud Run). |
| `DATABASE_URL` | — | URI SQLAlchemy opcional (se informada, sobrepõe `DB_HOST`..`DB_PASSWORD`). |
| `SABOR_DB_ENCRYPTION_KEY` | — | Chave opcional para criptografia Fernet de CPF/PIX/conta (se vazia, deriva de `SABOR_AUTH_SECRET`). |
| `GOOGLE_API_KEY` | — | Chave do Google AI Studio (ou `GEMINI_API_KEY`, quando `GOOGLE_GENAI_USE_VERTEXAI=FALSE`). |
| `GOOGLE_GENAI_USE_VERTEXAI` | — | `TRUE` para usar Vertex AI em vez da API do AI Studio. |
| `GOOGLE_CLOUD_PROJECT` | — | ID do projeto GCP (necessário no modo Vertex AI e Firestore). |
| `GOOGLE_CLOUD_LOCATION` | — | Região/endpoint da Vertex AI (ex.: `global`, `us-central1`). |
| `SABOR_INDEX_DIR` | `/app/index` | Diretório do índice ChromaDB empacotado (`index/` com 33 trechos, `gemini-embedding-001` em 768 dimensões). |
| `SABOR_EMBED_DIM` | `768` | Dimensão do embedding usada na busca vetorial (deve coincidir com `index/index_info.json`). |
| `SABOR_LIMIAR` | `0.65` | Limiar mínimo de similaridade de cosseno para retornar trechos do RAG. |
| `SESSION_SERVICE_URI` | `memory://` | URI do serviço de sessões do ADK (`firestore://` no Cloud Run para persistir após deploys; `sqlite:///...` localmente). |
| `FIRESTORE_SESSIONS_COLLECTION` | `adk_sessions` | Nome da coleção no Firestore quando `SESSION_SERVICE_URI=firestore://...`. |
| `SABOR_AUTH_SECRET` | — | Chave HMAC para assinar tokens de sessão e derivar criptografia LGPD (definir no Secret Manager). |
| `SABOR_EXIGIR_CODIGO_ACESSO` | `false` | Se `true` (ou se códigos abaixo forem definidos), exige PIN de acesso ao entrar como Operador ou Produtor. |
| `SABOR_CODIGO_OPERADOR` | — | Código de acesso opcional para o perfil **Operador**. |
| `SABOR_CODIGO_PRODUTOR` | — | Código de acesso padrão opcional para **Produtor** (ou use `SABOR_CODIGOS_PRODUTORES_JSON`). |
| `ARTIFACT_SERVICE_URI` | `memory://` | URI do serviço de artefatos do ADK (ex.: `gs://...` em produção). |
| `MEMORY_SERVICE_URI` | — | URI opcional do serviço de memória do ADK. |
| `ALLOW_ORIGINS` | — | Origens permitidas para CORS, separadas por vírgula (ex.: URL do frontend). |
| `ADK_WITH_UI` | `false` | Se `true`, habilita a interface web de desenvolvimento em `/dev-ui/`. Em produção (`false`), rotas nativas abertas como `/run` ficam desabilitadas. |

---

## Deploy no Google Cloud (Cloud SQL + Cloud Run)

> **Importante:** **não use `adk deploy`** para subir este projeto — utilize o `Dockerfile` da raiz conforme os passos abaixo.

### 1. Pré-requisitos no Google Cloud (Cloud SQL + Firestore + Secret Manager)

- Habilitar as APIs necessárias:

```bash
gcloud services enable sqladmin.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com firestore.googleapis.com aiplatform.googleapis.com --project=SEU_PROJETO_GCP
```

- Criar a instância **Cloud SQL for PostgreSQL** (na mesma região do Cloud Run), o banco `sabor_terra` e o usuário `sabor_app`:

```bash
gcloud sql instances create sabor-postgres-demo \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-f1-micro \
  --region=us-central1 \
  --project=SEU_PROJETO_GCP

gcloud sql databases create sabor_terra \
  --instance=sabor-postgres-demo \
  --project=SEU_PROJETO_GCP

gcloud sql users create sabor_app \
  --instance=sabor-postgres-demo \
  --password="SUA_SENHA_FORTE_CLOUD_SQL" \
  --project=SEU_PROJETO_GCP
```

- Criar os segredos `SABOR_AUTH_SECRET` e `DB_PASSWORD` no **Secret Manager**:

```bash
openssl rand -hex 32 | gcloud secrets create SABOR_AUTH_SECRET --data-file=- --project=SEU_PROJETO_GCP
printf "SUA_SENHA_FORTE_CLOUD_SQL" | gcloud secrets create DB_PASSWORD --data-file=- --project=SEU_PROJETO_GCP
```

- Garantir na conta de serviço do Cloud Run as permissões:
  - `roles/cloudsql.client` (conexão com o Cloud SQL via Unix Socket)
  - `roles/datastore.user` (sessões no Firestore)
  - `roles/secretmanager.secretAccessor` (leitura de `SABOR_AUTH_SECRET` e `DB_PASSWORD`)
  - `roles/aiplatform.user` (se usar Vertex AI)

### 2. Executar as migrações Alembic e popular o Cloud SQL via Auth Proxy

- Em um terminal dedicado, inicie o proxy apontando para a instância na porta local `5433`:

```powershell
gcloud auth application-default login
.\cloud-sql-proxy.exe --port 5433 SEU_PROJETO_GCP:us-central1:sabor-postgres-demo
```

- No `.env` da raiz, aponte temporariamente `DB_HOST=127.0.0.1`, `DB_PORT=5433`, `DB_USER=sabor_app`, `DB_PASSWORD=SUA_SENHA_FORTE_CLOUD_SQL` e execute:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m scripts.importar_dados
```

### 3. Fazer o deploy no Cloud Run conectado ao Cloud SQL

**Opção A — Com Vertex AI (usa a conta de serviço do Cloud Run, sem API key):**

```bash
gcloud run deploy sabor-da-terra-assistente \
  --source . \
  --project SEU_PROJETO_GCP \
  --region us-central1 \
  --port 8080 \
  --no-allow-unauthenticated \
  --max-instances 3 \
  --add-cloudsql-instances "SEU_PROJETO_GCP:us-central1:sabor-postgres-demo" \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=SEU_PROJETO_GCP,GOOGLE_CLOUD_LOCATION=global,SESSION_SERVICE_URI=firestore://,SABOR_DATA_BACKEND=postgres,DB_HOST=/cloudsql/SEU_PROJETO_GCP:us-central1:sabor-postgres-demo,DB_PORT=5432,DB_NAME=sabor_terra,DB_USER=sabor_app" \
  --set-secrets "SABOR_AUTH_SECRET=SABOR_AUTH_SECRET:latest,DB_PASSWORD=DB_PASSWORD:latest"
```

**Opção B — Com Google AI Studio (`GOOGLE_API_KEY` via Secret Manager):**

```bash
gcloud run deploy sabor-da-terra-assistente \
  --source . \
  --project SEU_PROJETO_GCP \
  --region us-central1 \
  --port 8080 \
  --no-allow-unauthenticated \
  --max-instances 3 \
  --add-cloudsql-instances "SEU_PROJETO_GCP:us-central1:sabor-postgres-demo" \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=FALSE,GOOGLE_CLOUD_PROJECT=SEU_PROJETO_GCP,SESSION_SERVICE_URI=firestore://,SABOR_DATA_BACKEND=postgres,DB_HOST=/cloudsql/SEU_PROJETO_GCP:us-central1:sabor-postgres-demo,DB_PORT=5432,DB_NAME=sabor_terra,DB_USER=sabor_app" \
  --set-secrets "GOOGLE_API_KEY=NOME_DO_SEGREDO:latest,SABOR_AUTH_SECRET=SABOR_AUTH_SECRET:latest,DB_PASSWORD=DB_PASSWORD:latest"
```

### 4. Acessar serviço privado via túnel autenticado pelo IAM (quando `--no-allow-unauthenticated`)

```bash
gcloud run services proxy sabor-da-terra-assistente \
  --project SEU_PROJETO_GCP \
  --region us-central1 \
  --port 8080
```

Depois acesse `http://127.0.0.1:8080` diretamente no navegador.

---

## Validação Técnica

Consulte o [README de validação](validacao/README.md) para ver os testes, resultados e o plano alternativo.

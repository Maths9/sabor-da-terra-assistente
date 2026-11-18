# Sabor da Terra — Assistente

## Preparar o ambiente

É necessário ter Python 3.11 ou superior. No Linux ou macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No Windows, crie o ambiente com `py -m venv .venv` e ative-o no PowerShell com `.\.venv\Scripts\Activate.ps1`. Depois, instale as dependências com `python -m pip install -r requirements.txt`.

Confira a instalação com `adk --version`.

## Estrutura do projeto

```text
sabor-da-terra-assistente/
├── .env.example                  # Modelo oficial das variáveis de ambiente (na raiz)
├── alembic.ini                   # Configuração do Alembic para migrações PostgreSQL
├── migrations/                   # Migrações versionadas das 6 tabelas operacionais
├── scripts/
│   ├── importar_dados.py         # Carga idempotente (UPSERT) dos CSVs/JSON com criptografia LGPD
│   └── indexar_rag.py            # Geração do índice vetorial ChromaDB
└── sabor_da_terra/
    ├── __init__.py               # Torna o agente disponível para o ADK
    ├── agent.py                  # Instância e configuração do agente coordenador
    ├── config.py                 # Configurações centralizadas e leitura do .env da raiz
    ├── database/                 # SQLAlchemy 2.0 (connection, models, crypto, repositories)
    ├── tools/                    # Ferramentas operacionais integradas ao banco
    └── api/                      # Backend FastAPI + sessões Firestore
```

## Configurar `.env` e Banco de Dados Local (PostgreSQL)

1. Copie `.env.example` para `.env` na **raiz do projeto** e preencha sua chave da API do [Google AI Studio](https://aistudio.google.com/apikey) (ou configure Vertex AI):

```bash
cp .env.example .env
```

2. Suba uma instância PostgreSQL 16 local (exemplo com Docker na porta `5434` para não conflitar com eventual PostgreSQL nativo do Windows na `5432`; ajuste `DB_PORT` no `.env` conforme a porta escolhida):

```powershell
docker run --name sabor-postgres-local `
  -e POSTGRES_DB=sabor_terra `
  -e POSTGRES_USER=sabor_app `
  -e POSTGRES_PASSWORD=senha_local_de_exemplo `
  -p 5434:5432 `
  -d postgres:16-alpine
```

3. Crie as 6 tabelas no banco (`produtores`, `transacoes_financeiras`, `lotes`, `precos`, `sazonalidade`, `pedidos`) e popule os dados operacionais (com criptografia `Fernet` em `cpf_cifrado`, `chave_pix_cifrada`, `conta_corrente_cifrada` e `data_nascimento_cifrada`):

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m scripts.importar_dados
```

4. Com o ambiente virtual ativado, você pode executar o agente no terminal a partir da raiz do projeto:

```bash
adk run sabor_da_terra
```

Para usar a interface web local de desenvolvimento do ADK, execute `adk web` na raiz do projeto e selecione `sabor_da_terra`. O arquivo `.env` contém credenciais e é ignorado pelo Git.
Configure suas credenciais no `.env` da raiz (veja a seção de Docker abaixo) ou em `sabor_da_terra/.env` (a partir de `sabor_da_terra/.env.example`):

```bash
cp sabor_da_terra/.env.example .env
```

> **Nota sobre RBAC e ADK direto (`adk run` / `adk web`):** o guardrail `validar_acesso_tool` é *fail-closed* e exige `perfil_usuario` no `session.state` (`"operador"` ou `"produtor"` + `"produtor_em_foco"`). Pela API + Interface React abaixo isso é preenchido automaticamente a partir do token de sessão; ao testar diretamente com `adk run sabor_da_terra` ou `adk web` na raiz do projeto, informe `perfil_usuario` no estado inicial da sessão (como em `validacao/evalset_cooperativa.evalset.json`). Consulte o [guia oficial do ADK](https://adk.dev/get-started/python/) para mais detalhes. O arquivo `.env` contém credenciais e é ignorado pelo Git.

## Executar API + Interface Frontend (React)

1. Suba o backend FastAPI + Google ADK na porta `8080`:

```powershell
.\.venv\Scripts\uvicorn.exe sabor_da_terra.api:app --host 127.0.0.1 --port 8080 --reload
```

2. Em outro terminal, suba o frontend em `frontend/` (o `vite.config.ts` já encaminha `/api/*` para `http://127.0.0.1:8080`):

```bash
cd frontend
npm install
npm run dev
```

3. Acesse `http://localhost:5173` para escolher entre **Área do Operador** e **Área do Produtor**. Se quiser servir tudo pela porta `8080` diretamente pelo FastAPI sem `npm run dev`, gere o build estático antes com `cd frontend && npm run build`.

## Executar com Docker

A imagem multi-stage compila o frontend React (`frontend/dist`) e empacota o agente (`sabor_da_terra/`), as migrações (`migrations/` + `alembic.ini`), os scripts (`scripts/`), os documentos (`dados/`), o índice RAG (`index/`) e o servidor FastAPI.

### 1. Configurar o `.env` na raiz

Tanto o `.gitignore` quanto o `.dockerignore` ignoram o `.env` e arquivos de credenciais, garantindo que nenhuma chave entre no Git nem na imagem Docker.

```bash
cp .env.example .env
```

Escolha uma das duas opções de modelo para preencher o `.env` da raiz (além das variáveis `DB_*` do PostgreSQL):

#### Opção A — Google AI Studio (`GOOGLE_API_KEY`, mais rápida para testar localmente)

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

> **Modelo usado pelo agente:** `sabor_da_terra/agent.py` utiliza `gemini-3.5-flash` (validado na Vertex AI do projeto `projeto-sabor-da-terra`, conforme `validacao/README.md`).

### 2. Construir a imagem

Na raiz do repositório (`--platform linux/amd64` garante compatibilidade com o Cloud Run):

```bash
docker build --platform linux/amd64 -t sabor-da-terra-assistente:v2 .
```

### 3. Rodar localmente

> **Nota:** Quando o container da aplicação roda no Docker apontando para um banco PostgreSQL também na máquina local, passe `-e DB_HOST=host.docker.internal` para o container enxergar a porta do host.

**Usando o `.env` da raiz com Google AI Studio:**

```bash
docker run --rm -p 8080:8080 --env-file .env -e DB_HOST=host.docker.internal sabor-da-terra-assistente:v2
```

**Ou usando o `.env` da raiz com Vertex AI (montando o ADC local em modo somente leitura):**

```bash
docker run --rm -p 8080:8080 \
  --env-file .env \
  -e DB_HOST=host.docker.internal \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/tmp/adc.json:ro" \
  sabor-da-terra-assistente:v2
```

### 4. Variáveis de ambiente suportadas pelo container

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `PORT` | `8080` | Porta HTTP em que o servidor escuta (`0.0.0.0:$PORT`; definida automaticamente no Cloud Run). |
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

### 5. Testar os endpoints no container

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

### 6. Parar e remover o container

```bash
docker ps                              # lista containers em execução
docker stop <NOME_OU_ID_DO_CONTAINER>  # para o container
```

### 7. Subir no Cloud SQL + Cloud Run usando o `Dockerfile`

> **Importante:** **não use `adk deploy`** para subir este projeto — use o `Dockerfile` da raiz conforme os passos abaixo.

1. **Pré-requisitos no Google Cloud (Cloud SQL + Firestore + Secret Manager):**
   - Habilitar as APIs necessárias:
     ```bash
     gcloud services enable sqladmin.googleapis.com run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com firestore.googleapis.com aiplatform.googleapis.com --project=SEU_PROJETO_GCP
     ```
   - Criar a instância **Cloud SQL for PostgreSQL** (na mesma região `us-central1` do Cloud Run), o banco `sabor_terra` e o usuário `sabor_app`:
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

2. **Executar as migrações Alembic e popular o Cloud SQL via Cloud SQL Auth Proxy:**
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

3. **Fazer o deploy no Cloud Run conectado ao Cloud SQL (`--add-cloudsql-instances`):**

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

4. **Acessar o serviço privado na demonstração (túnel autenticado pelo IAM):**

```bash
gcloud run services proxy sabor-da-terra-assistente \
  --project SEU_PROJETO_GCP \
  --region us-central1 \
  --port 8080
```

Depois acesse `http://127.0.0.1:8080` diretamente no navegador.

## Validação técnica

Consulte o [README de validação](validacao/README.md) para ver os testes, resultados e o plano alternativo.

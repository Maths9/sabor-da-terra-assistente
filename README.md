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

## Estrutura do agente

```text
sabor_da_terra/
├── __init__.py      # Torna o agente disponível para o ADK
├── agent.py         # Instância e configuração do agente
└── .env.example     # Exemplo das variáveis de ambiente
```

## Configurar e executar

Crie uma chave de API no [Google AI Studio](https://aistudio.google.com/apikey). Copie `sabor_da_terra/.env.example` para `sabor_da_terra/.env` e substitua `sua_chave_aqui` pela sua chave. No Linux ou macOS:

```bash
cp sabor_da_terra/.env.example sabor_da_terra/.env
```

Com o ambiente virtual ativado, execute o agente no terminal a partir da raiz do projeto:

```bash
adk run sabor_da_terra
```

Para usar a interface web local do ADK, execute `adk web` na raiz do projeto e selecione `sabor_da_terra`. Consulte o [guia oficial do ADK](https://adk.dev/get-started/python/) para mais detalhes. O arquivo `.env` contém credenciais e é ignorado pelo Git.

## Executar API + Interface Frontend (React)

1. Suba o backend FastAPI + Google ADK na porta `8080`:

```bash
.venv/bin/uvicorn sabor_da_terra.api:app --host 127.0.0.1 --port 8080
```

2. Em outro terminal, suba o frontend em `frontend/` (o `vite.config.ts` já encaminha `/api/*` para `http://127.0.0.1:8080`):

```bash
cd frontend
npm install
npm run dev
```

3. Acesse `http://localhost:5173` (ou `http://127.0.0.1:8080` se `frontend/dist` já estiver compilado) para escolher entre **Área do Operador** e **Área do Produtor**.

## Executar com Docker

A imagem multi-stage compila o frontend React (`frontend/dist`) e empacota o agente (`sabor_da_terra/`), os dados operacionais (`dados/`) e o servidor FastAPI com proteção de rotas e sessões persistentes.

### 1. Obter credenciais e configurar o `.env` na raiz (recomendado)

Para uso no dia a dia no computador, é mais prático manter o arquivo `.env` já criado e preenchido **na raiz do projeto** (em vez de passar várias flags `-e` a cada execução). O ADK local encontra o `.env` na raiz automaticamente ao subir a partir de `sabor_da_terra/`, e o Docker lê o mesmo arquivo em tempo de execução com `--env-file .env`.

Tanto o `.gitignore` quanto o `.dockerignore` ignoram o `.env` e arquivos de credenciais, garantindo que nenhuma chave entre no Git nem na imagem Docker.

```bash
cp sabor_da_terra/.env.example .env
```

Escolha uma das duas opções abaixo para preencher o `.env` da raiz (sem aspas extras e sem espaços ao redor do `=`):

#### Opção A — Google AI Studio (`GOOGLE_API_KEY`, mais rápida para testar localmente)

1. Acesse o [Google AI Studio](https://aistudio.google.com/apikey) com sua conta Google.
2. Clique em **Create API key** (crie ou vincule a um projeto se solicitado) e copie a chave.
3. Preencha o `.env` da raiz assim:

```env
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=cole_sua_chave_aqui
```

#### Opção B — Vertex AI (sem API key, usando ADC local)

1. Autentique suas Application Default Credentials (caso ainda não tenha `~/.config/gcloud/application_default_credentials.json`):

```bash
gcloud auth application-default login
```

2. Preencha o `.env` da raiz:

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

**Usando o `.env` da raiz com Google AI Studio (mais prático):**

```bash
docker run --rm -p 8080:8080 --env-file .env sabor-da-terra-assistente:v2
```

Para abrir também a interface web do ADK em `http://127.0.0.1:8080` e testar no navegador:

```bash
docker run --rm -p 8080:8080 --env-file .env -e ADK_WITH_UI=true sabor-da-terra-assistente:v2
```

**Ou usando o `.env` da raiz com Vertex AI (montando o ADC local em modo somente leitura):**

```bash
docker run --rm -p 8080:8080 \
  --env-file .env \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/tmp/adc.json:ro" \
  sabor-da-terra-assistente:v2
```

### 4. Variáveis de ambiente suportadas pelo container

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `PORT` | `8080` | Porta HTTP em que o servidor escuta (`0.0.0.0:$PORT`; definida automaticamente no Cloud Run). |
| `GOOGLE_API_KEY` | — | Chave do Google AI Studio (quando `GOOGLE_GENAI_USE_VERTEXAI=FALSE`). |
| `GOOGLE_GENAI_USE_VERTEXAI` | — | `TRUE` para usar Vertex AI em vez da API do AI Studio. |
| `GOOGLE_CLOUD_PROJECT` | — | ID do projeto GCP (necessário no modo Vertex AI). |
| `GOOGLE_CLOUD_LOCATION` | — | Região/endpoint da Vertex AI (ex.: `global`, `us-central1`). |
| `SESSION_SERVICE_URI` | `memory://` | URI do serviço de sessões do ADK (`firestore://` no Cloud Run para persistir após deploys; `sqlite:///...` localmente; ou PostgreSQL). |
| `FIRESTORE_SESSIONS_COLLECTION` | `adk_sessions` | Nome da coleção no Firestore quando `SESSION_SERVICE_URI=firestore://...`. |
| `SABOR_AUTH_SECRET` | — | Chave HMAC para assinar tokens de sessão (recomendado definir no Cloud Run para manter tokens válidos entre revisões). |
| `SABOR_EXIGIR_CODIGO_ACESSO` | `false` | Se `true` (ou se códigos abaixo forem definidos), exige PIN de acesso ao entrar como Operador ou Produtor. |
| `SABOR_CODIGO_OPERADOR` | — | Código de acesso opcional para o perfil **Operador**. |
| `SABOR_CODIGO_PRODUTOR` | — | Código de acesso padrão opcional para **Produtor** (ou use `SABOR_CODIGOS_PRODUTORES_JSON`). |
| `ARTIFACT_SERVICE_URI` | `memory://` | URI do serviço de artefatos do ADK (ex.: `gs://...` em produção). |
| `MEMORY_SERVICE_URI` | — | URI opcional do serviço de memória do ADK. |
| `ALLOW_ORIGINS` | — | Origens permitidas para CORS, separadas por vírgula (ex.: URL do frontend). |
| `ADK_WITH_UI` | `false` | Se `true`, habilita a interface web de desenvolvimento em `/dev-ui/`. Em produção (`false`), rotas nativas abertas como `/run` ficam desabilitadas. |

### 5. Testar os endpoints no container

Com o container em execução na porta `8080`, rode em outro terminal:

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

# Consultar pedidos pendentes (somente Operador) e lista pública de produtores
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/pedidos-pendentes
curl -s http://127.0.0.1:8080/api/produtores
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/produtores/P001
```

### 6. Parar e remover o container

- Se o container estiver rodando em primeiro plano no terminal atual (com `--rm`), pressione `Ctrl+C` para encerrar e removê-lo automaticamente.
- Se estiver rodando em segundo plano (`-d`) ou em outro terminal, descubra o nome/ID e pare o container:

```bash
docker ps                              # lista containers em execução
docker stop <NOME_OU_ID_DO_CONTAINER>  # para o container (com --rm, já remove sozinho)
docker rm <NOME_OU_ID_DO_CONTAINER>    # remove manualmente caso tenha subido sem --rm
```

### 7. Subir no Cloud Run usando o `Dockerfile` (T39c)

> **Importante:** **não use `adk deploy`** para subir este projeto — ele gera um `Dockerfile` próprio que copia apenas a pasta do agente (deixando dados/índices externos fora da imagem, além de ignorar o `requirements.txt` da raiz e a API `/api/*` do frontend). Use o `Dockerfile` da raiz conforme os passos abaixo, e garanta que a pasta do índice (`sabor_da_terra/rag_store/`) não esteja no `.gitignore` nem no `.dockerignore`.

1. **Pré-requisitos no Google Cloud (100% na nuvem):**
   - Estar autenticado no Google Cloud CLI (`gcloud auth login`), com faturamento ativo e APIs do Cloud Run, Cloud Build, Secret Manager e Firestore habilitadas no projeto.
   - Criar o banco **Firestore (modo Nativo)** no projeto (ex.: `gcloud firestore databases create --location=us-central1 --project=SEU_PROJETO_GCP`).
   - Criar o segredo do `SABOR_AUTH_SECRET` no **Secret Manager** (ex.: `openssl rand -hex 32 | gcloud secrets create SABOR_AUTH_SECRET --data-file=- --project=SEU_PROJETO_GCP`).
   - Garantir na conta de serviço do Cloud Run as permissões `roles/datastore.user` (sessões no Firestore), `roles/secretmanager.secretAccessor` (leitura dos segredos) e `roles/aiplatform.user` (se usar Vertex AI), além de `roles/run.invoker` nas contas Google autorizadas a invocar o serviço privado.
2. **Subir privado com IAM (`--no-allow-unauthenticated`) e sessões persistentes no Firestore (executa na nuvem via Cloud Build + Cloud Run):**

**Opção A — Com Vertex AI (usa a conta de serviço do Cloud Run, sem API key):**

```bash
gcloud run deploy sabor-da-terra-assistente \
  --source . \
  --project SEU_PROJETO_GCP \
  --region us-central1 \
  --port 8080 \
  --no-allow-unauthenticated \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=SEU_PROJETO_GCP,GOOGLE_CLOUD_LOCATION=global,SESSION_SERVICE_URI=firestore://" \
  --set-secrets "SABOR_AUTH_SECRET=SABOR_AUTH_SECRET:latest"
```

**Opção B — Com Google AI Studio (`GOOGLE_API_KEY` via Secret Manager):**

```bash
gcloud run deploy sabor-da-terra-assistente \
  --source . \
  --project SEU_PROJETO_GCP \
  --region us-central1 \
  --port 8080 \
  --no-allow-unauthenticated \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=FALSE,GOOGLE_CLOUD_PROJECT=SEU_PROJETO_GCP,SESSION_SERVICE_URI=firestore://" \
  --set-secrets "GOOGLE_API_KEY=NOME_DO_SEGREDO:latest,SABOR_AUTH_SECRET=SABOR_AUTH_SECRET:latest"
```

3. **Acessar o serviço privado na demonstração (túnel autenticado pelo IAM):**

Todo o processamento (API, agente, frontend empacotado, Vertex AI e Firestore) roda **na nuvem**. Como o serviço é privado (`--no-allow-unauthenticated`), escolha uma das duas formas de acesso autenticado:

- **Forma 1 — Túnel local com `gcloud` (sem infra extra na nuvem):** na máquina de quem vai apresentar (com permissão `roles/run.invoker`), abra o proxy autenticado pelo IAM:

```bash
gcloud run services proxy sabor-da-terra-assistente \
  --project SEU_PROJETO_GCP \
  --region us-central1 \
  --port 8080
```

Depois acesse `http://127.0.0.1:8080` diretamente no navegador (ou suba `npm run dev` em `frontend/` apontando para `http://127.0.0.1:8080`).

- **Forma 2 — URL direta no navegador (100% na nuvem):** caso não queiram usar `gcloud` na máquina da apresentação, configure um **Load Balancer + Identity-Aware Proxy (IAP)** no Google Cloud na frente do Cloud Run para exigir login Google das contas autorizadas no IAM diretamente pelo navegador.

*(Opcional: se já tiver gerado a imagem localmente e enviado ao Artifact Registry, substitua `--source .` por `--image <URL_DA_IMAGEM_NO_ARTIFACT_REGISTRY>`.)*

**Notas de produção e conferência pré-commit:**

- O `Dockerfile` já empacota `frontend/dist`, `sabor_da_terra/` (incluindo `rag_store/`), `dados/` e inicia `uvicorn sabor_da_terra.api:app` como usuário não-root (`appuser`).
- Com `SESSION_SERVICE_URI=firestore://` e `SABOR_AUTH_SECRET` configurada, o histórico das conversas e o `session.state` sobrevivem a reinícios, múltiplas instâncias e novos deploys no Cloud Run.
- Informe credenciais, chaves de API e segredos apenas em runtime (`--set-env-vars` / `--set-secrets`), nunca dentro da imagem nem do Git.
- Antes de fazer `git commit`, rode `git status` e confirme que o arquivo `.env` continua ignorado e não aparece na lista de alterações.

## Validação técnica

Consulte o [README de validação](validacao/README.md) para ver os testes, resultados e o plano alternativo.

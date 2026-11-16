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

3. Acesse `http://localhost:5173` para escolher entre **Área do Cooperado** e **Área do Produtor** (carrega `/api/produtores`, `/api/produtores/{id}` e `/api/chat`).

## Executar com Docker

A imagem empacota o agente (`sabor_da_terra/`), os dados operacionais (`dados/`) e o servidor FastAPI do ADK (`adk api_server`) para rodar da mesma forma localmente e no Cloud Run.

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
docker build --platform linux/amd64 -t sabor-da-terra-assistente:v1 .
```

### 3. Rodar localmente

**Usando o `.env` da raiz com Google AI Studio (mais prático):**

```bash
docker run --rm -p 8080:8080 --env-file .env sabor-da-terra-assistente:v1
```

Para abrir também a interface web do ADK em `http://127.0.0.1:8080` e testar no navegador:

```bash
docker run --rm -p 8080:8080 --env-file .env -e ADK_WITH_UI=true sabor-da-terra-assistente:v1
```

**Ou usando o `.env` da raiz com Vertex AI (montando o ADC local em modo somente leitura):**

```bash
docker run --rm -p 8080:8080 \
  --env-file .env \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/tmp/adc.json:ro" \
  sabor-da-terra-assistente:v1
```

### 4. Variáveis de ambiente suportadas pelo container

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `PORT` | `8080` | Porta HTTP em que o servidor escuta (`0.0.0.0:$PORT`; definida automaticamente no Cloud Run). |
| `GOOGLE_API_KEY` | — | Chave do Google AI Studio (quando `GOOGLE_GENAI_USE_VERTEXAI=FALSE`). |
| `GOOGLE_GENAI_USE_VERTEXAI` | — | `TRUE` para usar Vertex AI em vez da API do AI Studio. |
| `GOOGLE_CLOUD_PROJECT` | — | ID do projeto GCP (necessário no modo Vertex AI). |
| `GOOGLE_CLOUD_LOCATION` | — | Região/endpoint da Vertex AI (ex.: `global`, `us-central1`). |
| `SESSION_SERVICE_URI` | `memory://` | URI do serviço de sessões do ADK (ex.: Cloud SQL em produção). |
| `ARTIFACT_SERVICE_URI` | `memory://` | URI do serviço de artefatos do ADK (ex.: `gs://...` em produção). |
| `MEMORY_SERVICE_URI` | — | URI opcional do serviço de memória do ADK. |
| `ALLOW_ORIGINS` | — | Origens permitidas para CORS, separadas por vírgula (ex.: URL do frontend). |
| `ADK_WITH_UI` | `false` | Se `true`, habilita a interface web de desenvolvimento em `/dev-ui/`. |

### 5. Testar os endpoints no container

Com o container em execução na porta `8080`, rode em outro terminal:

```bash
# Saúde do serviço e agentes carregados
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/list-apps

# Enviar mensagem ao endpoint simplificado da interface (retorna resposta, fontes RAG e estado)
curl -s -X POST http://127.0.0.1:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quais pedidos pendentes temos hoje?",
    "user_id": "operador"
  }'

# Consultar pedidos pendentes e produtores da cooperativa
curl -s http://127.0.0.1:8080/api/pedidos-pendentes
curl -s http://127.0.0.1:8080/api/produtores
curl -s http://127.0.0.1:8080/api/produtores/P001

# Enviar mensagem pela rota nativa do ADK (criação de sessão automática habilitada)
curl -s -X POST http://127.0.0.1:8080/run \
  -H "Content-Type: application/json" \
  -d '{
    "appName": "sabor_da_terra",
    "userId": "teste",
    "sessionId": "sessao-1",
    "newMessage": {"role": "user", "parts": [{"text": "Olá! Responda em uma frase curta quem você é."}]}
  }'
```

### 6. Parar e remover o container

- Se o container estiver rodando em primeiro plano no terminal atual (com `--rm`), pressione `Ctrl+C` para encerrar e removê-lo automaticamente.
- Se estiver rodando em segundo plano (`-d`) ou em outro terminal, descubra o nome/ID e pare o container:

```bash
docker ps                              # lista containers em execução
docker stop <NOME_OU_ID_DO_CONTAINER>  # para o container (com --rm, já remove sozinho)
docker rm <NOME_OU_ID_DO_CONTAINER>    # remove manualmente caso tenha subido sem --rm
```

### 7. Notas para deploy no Cloud Run (T39c) e conferência pré-commit

- O container executa como usuário não-root (`appuser`), com `--no-reload` e `ADK_DISABLE_LOCAL_STORAGE=1`, comportando-se igual localmente e no Cloud Run.
- Como o padrão de sessão é `memory://`, o histórico da conversa não persiste entre reinicializações ou múltiplas instâncias no Cloud Run; para persistência em produção, configure `SESSION_SERVICE_URI`.
- No deploy (via Artifact Registry com a imagem `sabor-da-terra-assistente:v1` ou `gcloud run deploy --source .` usando o `Dockerfile`), informe as credenciais e variáveis em runtime (variáveis de ambiente / Secret Manager), nunca dentro da imagem.
- Antes de fazer `git commit`, rode `git status` e confirme que o arquivo `.env` continua ignorado e não aparece na lista de alterações.

## Validação técnica

Consulte o [README de validação](validacao/README.md) para ver os testes, resultados e o plano alternativo.

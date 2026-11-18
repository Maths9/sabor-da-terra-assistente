# Planejamento e Guia de Implantação — PostgreSQL + Cloud SQL

A migração das ferramentas Python e rotas da API para o banco relacional PostgreSQL (com criptografia LGPD em nível de coluna) **já foi implementada no código** (Passos 1 a 6 concluídos). O frontend React continua consumindo exatamente as mesmas rotas da API.

Os Passos 7 a 12 abaixo constituem o **roteiro pronto de implantação no GCP (Cloud SQL + Cloud Run)** para o integrante de Cloud/DevOps (Isaque).

---

## Avisos sobre Custos e Créditos do Cloud SQL

* **Cloud SQL normalmente é pago**, com cobrança de processamento, armazenamento e outros recursos conforme a configuração. Poucos acessos não tornam uma instância comum gratuita. [Preços do Cloud SQL](https://cloud.google.com/sql/pricing).
* Atualmente existe um **teste específico de Cloud SQL por até 30 dias**, disponível para clientes novos e existentes, exigindo um projeto GCP elegível e faturamento habilitado. A instância de teste não é convertida automaticamente em paga: ao terminar o período, ela para de atender. [Condições do teste](https://docs.cloud.google.com/sql/docs/postgres/free-trial-instance).
* Também existem créditos gerais de US$ 300 por 90 dias para novos clientes elegíveis. [Programa gratuito do GCP](https://docs.cloud.google.com/free/docs/free-cloud-features).

---

## Parte I — O que já está implementado no código (Passos 1 a 6 — Concluídos)

1. **Tabelas modeladas e normalizadas (`sabor_da_terra/database/models.py`):**

   | Fonte original | Tabela no PostgreSQL | Destaques de Modelagem e LGPD |
   |---|---|---|
   | `produtores.csv` | `produtores` | PK `id` (`P001`..`P018`); colunas `cpf_cifrado`, `data_nascimento_cifrada`, `chave_pix_cifrada` e `conta_corrente_cifrada` gravadas com criptografia simétrica `Fernet` (`enc:v1:...`). |
   | `financeiro.csv` | `transacoes_financeiras` | PK `id_transacao`; FK `produtor_id -> produtores.id`; valores em `NUMERIC(10, 2)`; eliminadas as colunas redundantes `produtor_cpf` e `chave_pix_deposito`. |
   | `lotes.csv` | `lotes` | PK `lote_id`; FK `produtor_id -> produtores.id`; `temperatura_transporte_c` em `VARCHAR(20)` (suporta números e `'ambiente'`); eliminada `produtor_cpf`; sem FK rígida com `pedidos`. |
   | `tabela_precos_outubro_2026.csv` | `precos` | PK `id`; `UNIQUE (vigencia, produto)`; valores `'n/d'` armazenados como `NULL` em `NUMERIC(10, 2)`. |
   | `sazonalidade.csv` | `sazonalidade` | PK `produto`; 12 colunas mensais (`jan`..`dez`) e `observacao` (com limites semanais). |
   | `pedidos.json` | `pedidos` | PK `id` (`PED-2026-001`..`015`); `data_recebimento` em `TIMESTAMP`. |

   O índice documental RAG (`index/` com ChromaDB) e o histórico das conversas (`SESSION_SERVICE_URI=firestore://`) permanecem nas suas estruturas dedicadas.

2. **Configuração via `.env` na raiz do projeto (`.env.example` e `sabor_da_terra/config.py`):**

   ```env
   SABOR_DATA_BACKEND=postgres
   DB_HOST=127.0.0.1
   DB_PORT=5432
   DB_NAME=sabor_terra
   DB_USER=sabor_app
   DB_PASSWORD=senha_local_de_exemplo
   SABOR_AUTH_SECRET=troque_por_um_segredo_forte_de_32_bytes
   SABOR_DB_ENCRYPTION_KEY=
   ```

3. **Arquitetura de Acesso ao Banco implementada:**

   ```text
   .env.example
   alembic.ini
   migrations/
     env.py
     versions/20261118_0001_schema_inicial.py
   scripts/
     importar_dados.py
   sabor_da_terra/
     database/
       __init__.py
       connection.py
       crypto.py
       models.py
       repositories.py
   ```

   * `connection.py` detecta automaticamente se `DB_HOST` é TCP (`127.0.0.1`) ou Unix Domain Socket do Cloud Run (`/cloudsql/...`).
   * `crypto.py` cifra os dados sensíveis com `Fernet` (usando `SABOR_DB_ENCRYPTION_KEY` ou derivando de `SABOR_AUTH_SECRET`).
   * `repositories.py` executa as queries SQLAlchemy (`SELECT`, `WHERE`, `JOIN` com `produtores`) mantendo 100% do contrato `{status, dados, mensagem}` das 8 tools operacionais e das rotas `/api/produtores` e `/api/pedidos-pendentes`.

4. **Comandos locais de migração e carga idempotente (`UPSERT`):**

   ```powershell
   .\.venv\Scripts\alembic.exe upgrade head
   .\.venv\Scripts\python.exe -m scripts.importar_dados
   ```

---

## Parte II — Roteiro de Execução no GCP para o Integrante de Cloud (Passos 7 a 12)

### 7. Preparar o projeto GCP e habilitar APIs

Autentique no Google Cloud CLI, selecione o projeto e habilite as APIs necessárias:

```bash
gcloud auth login
gcloud config set project SEU_PROJETO_GCP

gcloud services enable \
  sqladmin.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  --project=SEU_PROJETO_GCP
```

Configure também um orçamento com alertas de consumo no console de Faturamento. [Orçamentos e alertas](https://docs.cloud.google.com/billing/docs/how-to/budgets).

---

### 8. Criar e configurar a instância Cloud SQL (PostgreSQL 16)

Use a mesma região do Cloud Run (`us-central1`) para reduzir latência e custos de tráfego:

```bash
# 1. Criar a instância PostgreSQL 16 (ou criar pelo Console na opção Free Trial de 30 dias, se elegível)
gcloud sql instances create sabor-postgres-demo \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-f1-micro \
  --region=us-central1 \
  --storage-type=SSD \
  --storage-size=10GB \
  --project=SEU_PROJETO_GCP

# 2. Criar o banco de dados sabor_terra
gcloud sql databases create sabor_terra \
  --instance=sabor-postgres-demo \
  --project=SEU_PROJETO_GCP

# 3. Criar o usuário da aplicação sabor_app
gcloud sql users create sabor_app \
  --instance=sabor-postgres-demo \
  --password="SUA_SENHA_FORTE_CLOUD_SQL" \
  --project=SEU_PROJETO_GCP
```

---

### 9. Conectar o computador ao Cloud SQL (Auth Proxy) e carregar a base

1. Autentique as credenciais ADC na máquina local:
   ```powershell
   gcloud auth application-default login
   ```
2. Em um terminal dedicado, inicie o [Cloud SQL Auth Proxy](https://docs.cloud.google.com/sql/docs/postgres/connect-auth-proxy) escutando na porta local `5433`:
   ```powershell
   .\cloud-sql-proxy.exe --port 5433 SEU_PROJETO_GCP:us-central1:sabor-postgres-demo
   ```
3. No arquivo `.env` na **raiz do projeto**, aponte para a porta `5433` do proxy e informe a senha do Cloud SQL e o `SABOR_AUTH_SECRET`:
   ```env
   SABOR_DATA_BACKEND=postgres
   DB_HOST=127.0.0.1
   DB_PORT=5433
   DB_NAME=sabor_terra
   DB_USER=sabor_app
   DB_PASSWORD=SUA_SENHA_FORTE_CLOUD_SQL
   SABOR_AUTH_SECRET=MESMO_SEGREDO_QUE_IRA_PARA_O_SECRET_MANAGER
   ```
4. Rode as migrações Alembic e o script de importação contra o Cloud SQL:
   ```powershell
   .\.venv\Scripts\alembic.exe upgrade head
   .\.venv\Scripts\python.exe -m scripts.importar_dados
   ```
   O script imprimirá o JSON confirmando `18` produtores, `50` sazonalidades, `53` preços, `15` pedidos, `20` lotes e `30` transações financeiras (`vendas_total: 24634.00`, `total_pendente: 13380.00`) carregados na nuvem.

---

### 10. Configurar Secret Manager e permissões IAM do Cloud Run

1. Crie os segredos `SABOR_AUTH_SECRET` e `DB_PASSWORD` no Secret Manager (caso `SABOR_AUTH_SECRET` ainda não exista):
   ```bash
   printf "MESMO_SEGREDO_QUE_IRA_PARA_O_SECRET_MANAGER" | gcloud secrets create SABOR_AUTH_SECRET --data-file=- --project=SEU_PROJETO_GCP
   printf "SUA_SENHA_FORTE_CLOUD_SQL" | gcloud secrets create DB_PASSWORD --data-file=- --project=SEU_PROJETO_GCP
   ```
2. Garanta que a Service Account usada pelo serviço do Cloud Run possua as roles:
   * `roles/cloudsql.client` *(obrigatória para conectar ao socket `/cloudsql/...`)*
   * `roles/secretmanager.secretAccessor` *(para ler `DB_PASSWORD` e `SABOR_AUTH_SECRET`)*
   * `roles/datastore.user` *(para persistir sessões de chat no Firestore)*
   * `roles/aiplatform.user` *(para invocar o Gemini via Vertex AI)*

---

### 11. Publicar a aplicação no Cloud Run conectada ao Cloud SQL

O `Dockerfile` da raiz já instala `sqlalchemy`, `psycopg[binary]`, `alembic` e `cryptography`, empacota o build do frontend, o índice RAG e define `SABOR_DATA_BACKEND=postgres`.

Execute o deploy vinculando a instância do Cloud SQL com `--add-cloudsql-instances` e passando o caminho do Unix Socket em `DB_HOST`:

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

*(Caso utilizem chave do Google AI Studio em vez de Vertex AI, troque `GOOGLE_GENAI_USE_VERTEXAI=TRUE` por `FALSE` e adicione `GOOGLE_API_KEY=NOME_DO_SEGREDO:latest` em `--set-secrets`).*

O fluxo final em produção fica:

```text
Navegador
    ↓
Cloud Run: Frontend React + FastAPI (/api/*) + Agente Coordenador ADK
    ├── Dados operacionais (6 tabelas) ──► Cloud SQL for PostgreSQL (via Unix Socket /cloudsql/...)
    ├── Sessões multi-turno            ──► Cloud Firestore (SESSION_SERVICE_URI=firestore://)
    └── Documentos normativos (RAG)    ──► ChromaDB embarcado (/app/index)
```

---

### 12. Roteiro para a Demonstração ao Vivo e Encerramento

1. **Demonstração de atualização em tempo real no Cloud SQL (sem rebuild):**
   * No chat (perfil Operador), pergunte: *"Qual o preço do queijo coalho?"* $\to$ O assistente responderá **R\$ 32,00/kg** (convencional) e **R\$ 38,00/kg** (orgânico).
   * Atualize o preço diretamente no Cloud SQL (pelo Cloud SQL Studio no Console GCP ou via Auth Proxy):
     ```sql
     UPDATE precos SET preco_convencional = 35.00 WHERE produto = 'queijo coalho' AND vigencia = '2026-10';
     ```
   * Pergunte novamente no chat $\to$ O assistente responderá **R\$ 35,00/kg** imediatamente, comprovando que as tools consultam o Cloud SQL em tempo real.
2. **Demonstração de Segurança LGPD no Banco:**
   * Mostre no Cloud SQL Studio o resultado de:
     ```sql
     SELECT id, nome_completo, left(cpf_cifrado, 28) AS cpf_cifrado, left(chave_pix_cifrada, 28) AS pix_cifrado FROM produtores LIMIT 5;
     ```
   * Destaque que os CPFs, chaves PIX, contas correntes e datas de nascimento estão criptografados com `Fernet` (`enc:v1:...`) no banco e foram removidos das tabelas `lotes` e `transacoes_financeiras`.
3. **Encerramento após a apresentação:**
   * Se utilizarem uma instância paga, excluam ou parem os recursos após a banca para evitar cobranças contínuas. [Comportamento de instâncias paradas](https://docs.cloud.google.com/sql/docs/postgres/start-stop-restart-instance).

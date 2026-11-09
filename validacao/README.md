# Validação técnica do ADK e Vertex AI

Execute os comandos abaixo a partir da raiz do repositório, com o ambiente virtual ativado.

As provas em `validacao/` são independentes do agente da aplicação. Ambiente observado em 09/11/2026: Python 3.11.14, `google-adk` 2.14.0, `google-genai` 2.34.0 e Google Cloud CLI 592.0.0. A dependência direta `google-adk` está fixada em `requirements.txt`; a versão transitiva de `google-genai` é a observada, não um lock de dependências.

- **Grafo:** `Workflow` com duas ramificações e `JoinNode` executou localmente com sucesso. É uma prova funcional pequena, não uma garantia de estabilidade em produção.
- **Modelo e ferramenta:** em 09/11/2026, `gemini-3.5-flash` respondeu no Vertex AI do projeto `projeto-sabor-da-terra` e chamou a ferramenta `saudacao`, que retornou `Olá, Ana! Ferramenta executada.`. O ID também consta na [documentação do Google](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash).
- **Plano B:** se o grafo apresentar impedimentos para o protótipo, usar um `LlmAgent` coordenador com subagentes de triagem, consulta documental e comunicação; testar a delegação e compartilhar o estado da sessão. A decisão não implica regressão de versão do ADK.

Para repetir o teste do grafo, sem credenciais ou chamadas ao modelo:

```bash
python validacao/grafo.py
```

Para testar o modelo e uma ferramenta no Vertex AI, instale o [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) e autentique as Application Default Credentials (ADC). No ambiente onde a validação foi preparada, o executável está em `~/.local/google-cloud-sdk/bin/gcloud`:

```bash
export PATH="$HOME/.local/google-cloud-sdk/bin:$PATH"  # se instalado nesse local
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="projeto-sabor-da-terra"
export GOOGLE_CLOUD_LOCATION="global"
export GOOGLE_GENAI_USE_VERTEXAI="TRUE"
python validacao/hello_world.py
```

O comando verifica se o modelo chama a ferramenta e se ela retorna o resultado esperado. É necessário que o projeto exista, tenha faturamento, API Vertex AI habilitada e permissões apropriadas; a chamada pode gerar custos. As variáveis acima configuram essa prova independente; o agente inicial continua configurado pelo arquivo `sabor_da_terra/.env`.

Na execução validada, o Google Auth avisou que as ADC de usuário não tinham um projeto de cota configurado, embora a chamada tenha funcionado. Se houver erro de cota ou API não habilitada, confira a [orientação sobre credenciais ADC](https://cloud.google.com/docs/authentication/adc-troubleshooting/user-creds) e as permissões do projeto antes de alterar essa configuração.

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

Para usar a interface web local, execute `adk web` na raiz do projeto e selecione `sabor_da_terra`. Consulte o [guia oficial do ADK](https://adk.dev/get-started/python/) para mais detalhes. O arquivo `.env` contém credenciais e é ignorado pelo Git.

## Validação técnica

Consulte o [README de validação](validacao/README.md) para ver os testes, resultados e o plano alternativo.

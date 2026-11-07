# Sabor da Terra — Assistente

## Preparar o ambiente

É necessário ter Python 3.11 ou superior. No Linux ou macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

No Windows, crie o ambiente com `py -m venv .venv` e ative-o no PowerShell com `.\.venv\Scripts\Activate.ps1`. Depois, instale as dependências com `python -m pip install -r requirements.txt`.

Confira a instalação com `adk --version`. Para executar um agente com Gemini, será necessário configurar uma chave de API; consulte o [guia oficial do ADK](https://adk.dev/get-started/python/). Não envie arquivos `.env` com credenciais para o repositório.

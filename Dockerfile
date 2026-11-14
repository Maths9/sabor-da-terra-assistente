# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    ADK_DISABLE_LOCAL_STORAGE=1

WORKDIR /app

# Usuário sem privilégios para execução segura local e no Cloud Run
RUN adduser --disabled-password --gecos "" appuser

# Instala dependências antes de copiar o código para aproveitar o cache de camadas
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia apenas o código do agente e a base de dados operacional
COPY --chown=appuser:appuser sabor_da_terra/ ./sabor_da_terra/
COPY --chown=appuser:appuser dados/ ./dados/

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/health', timeout=3)" || exit 1

CMD ["sh", "-c", "set -- adk api_server --host=0.0.0.0 --port=\"${PORT:-8080}\" --no-reload --auto_create_session --session_service_uri=\"${SESSION_SERVICE_URI:-memory://}\" --artifact_service_uri=\"${ARTIFACT_SERVICE_URI:-memory://}\"; if [ -n \"${MEMORY_SERVICE_URI:-}\" ]; then set -- \"$@\" --memory_service_uri=\"${MEMORY_SERVICE_URI}\"; fi; if [ -n \"${ALLOW_ORIGINS:-}\" ]; then OLD_IFS=\"$IFS\"; IFS=,; for origin in $ALLOW_ORIGINS; do origin=$(printf '%s' \"$origin\" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'); [ -n \"$origin\" ] && set -- \"$@\" --allow_origins=\"$origin\"; done; IFS=\"$OLD_IFS\"; fi; if [ \"${ADK_WITH_UI:-false}\" = \"true\" ]; then set -- \"$@\" --with_ui; fi; exec \"$@\" /app/sabor_da_terra"]

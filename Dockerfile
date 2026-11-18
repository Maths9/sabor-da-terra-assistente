# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    ADK_DISABLE_LOCAL_STORAGE=1 \
    SABOR_INDEX_DIR=/app/index \
    SABOR_DATA_BACKEND=postgres

WORKDIR /app

# Usuário sem privilégios para execução segura local e no Cloud Run
RUN adduser --disabled-password --gecos "" appuser

# Instala dependências antes de copiar o código para aproveitar o cache de camadas
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia migrações Alembic, scripts de carga, código do agente, base documental, índice RAG e build do frontend
COPY --chown=appuser:appuser alembic.ini ./alembic.ini
COPY --chown=appuser:appuser migrations/ ./migrations/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser sabor_da_terra/ ./sabor_da_terra/
COPY --chown=appuser:appuser dados/ ./dados/
COPY --chown=appuser:appuser index/ ./index/
COPY --from=frontend-builder --chown=appuser:appuser /frontend/dist ./frontend/dist

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/health', timeout=3)" || exit 1

CMD ["sh", "-c", "exec uvicorn sabor_da_terra.api:app --host 0.0.0.0 --port \"${PORT:-8080}\""]

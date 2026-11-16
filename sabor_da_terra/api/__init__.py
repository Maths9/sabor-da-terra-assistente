"""Pacote modular da API HTTP FastAPI integrada ao Google ADK."""

from sabor_da_terra.api.adk_runtime import APP_NAME
from sabor_da_terra.api.app_factory import app, criar_app

__all__ = ["APP_NAME", "app", "criar_app"]

"""Inicialização do runtime ADK (ApiServer/DevServer e serviços de sessão)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.cli import fast_api as adk_fast_api
from google.adk.cli.api_server import ApiServer
from google.adk.cli.utils._eval_storage import create_eval_managers
from google.adk.cli.utils.agent_loader import AgentLoader
from google.adk.cli.utils.service_factory import (
    create_artifact_service_from_options,
    create_memory_service_from_options,
    create_session_service_from_options,
)
from google.adk.evaluation.local_eval_set_results_manager import (
    LocalEvalSetResultsManager,
)
from google.adk.evaluation.local_eval_sets_manager import LocalEvalSetsManager

from sabor_da_terra.api.session_firestore import registrar_firestore_no_adk
from sabor_da_terra.config import PACKAGE_DIR, PROJECT_ROOT

logger = logging.getLogger("sabor_da_terra.runtime")

APP_NAME = "sabor_da_terra"

_CORS_LOCAL_PADRAO = [
    "regex:https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?"
]


def parse_allow_origins(raw: Optional[str]) -> list[str]:
    """Converte variável ALLOW_ORIGINS em lista de origens CORS."""
    if not raw:
        return list(_CORS_LOCAL_PADRAO)
    origens = [item.strip() for item in raw.split(",") if item.strip()]
    return origens or list(_CORS_LOCAL_PADRAO)


def criar_servidor_adk(
    *,
    session_service_uri: Optional[str] = None,
    artifact_service_uri: Optional[str] = None,
    memory_service_uri: Optional[str] = None,
    allow_origins: Optional[list[str]] = None,
    use_web_ui: Optional[bool] = None,
) -> tuple[ApiServer, list[str], Optional[str], bool]:
    """Instancia ApiServer/DevServer e os serviços compartilhados do Google ADK."""
    agents_parent_dir = str(PROJECT_ROOT)
    single_agent_dir = str(PACKAGE_DIR)

    session_uri = session_service_uri or os.environ.get("SESSION_SERVICE_URI") or "memory://"
    artifact_uri = artifact_service_uri or os.environ.get("ARTIFACT_SERVICE_URI") or "memory://"
    memory_uri = memory_service_uri or os.environ.get("MEMORY_SERVICE_URI") or None
    origins = (
        allow_origins
        if allow_origins is not None
        else parse_allow_origins(os.environ.get("ALLOW_ORIGINS"))
    )
    web = (
        use_web_ui
        if use_web_ui is not None
        else os.environ.get("ADK_WITH_UI", "false").strip().lower() == "true"
    )
    use_local_storage = os.environ.get("ADK_DISABLE_LOCAL_STORAGE", "1") != "1"

    eval_sets_manager, eval_set_results_manager = create_eval_managers(
        None,
        agents_parent_dir,
        local_eval_sets_manager_cls=LocalEvalSetsManager,
        local_eval_set_results_manager_cls=LocalEvalSetResultsManager,
    )

    if web:
        from google.adk.cli.dev_server import DevServer
        from google.adk.cli.utils._nested_agent_loader import NestedAgentLoader

        agent_loader = NestedAgentLoader(single_agent_dir)
        server_cls: type[ApiServer] = DevServer
        web_assets_dir: Optional[str] = str(
            Path(adk_fast_api.__file__).parent.resolve() / "browser"
        )
    else:
        agent_loader = AgentLoader(single_agent_dir)
        server_cls = ApiServer
        web_assets_dir = None

    registrar_firestore_no_adk()

    memory_service = create_memory_service_from_options(
        base_dir=agents_parent_dir,
        memory_service_uri=memory_uri,
    )
    session_service = create_session_service_from_options(
        base_dir=agents_parent_dir,
        session_service_uri=session_uri,
        use_local_storage=use_local_storage,
    )
    if session_uri == "memory://":
        logger.warning(
            "SESSION_SERVICE_URI='memory://' ativo: sessões serão perdidas ao reiniciar/reimplantar. "
            "Para persistência no Cloud Run, configure SESSION_SERVICE_URI=firestore:// (ou PostgreSQL)."
        )
    artifact_service = create_artifact_service_from_options(
        base_dir=agents_parent_dir,
        artifact_service_uri=artifact_uri,
        strict_uri=True,
        use_local_storage=use_local_storage,
    )
    credential_service = InMemoryCredentialService()

    adk_server = server_cls(
        agent_loader=agent_loader,
        session_service=session_service,
        memory_service=memory_service,
        artifact_service=artifact_service,
        credential_service=credential_service,
        eval_sets_manager=eval_sets_manager,
        eval_set_results_manager=eval_set_results_manager,
        agents_dir=agents_parent_dir,
        auto_create_session=True,
    )
    adk_server.default_app_name = APP_NAME

    return adk_server, origins, web_assets_dir, web

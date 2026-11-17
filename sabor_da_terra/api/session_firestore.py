"""Serviço de sessões persistente do Google ADK apoiado no Cloud Firestore (REST v1)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import google.auth
import google.auth.transport.requests
import httpx
from google.adk.events.event import Event
from google.adk.sessions import _session_util
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.sessions.session import Session
from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.errors.session_not_found_error import SessionNotFoundError
from typing_extensions import override

logger = logging.getLogger("sabor_da_terra.session_firestore")

_FIRESTORE_SCOPE = "https://www.googleapis.com/auth/datastore"
_DEFAULT_COLLECTION = "adk_sessions"


def _safe_id(raw: str) -> str:
    limpo = re.sub(r"[^A-Za-z0-9_-]", "", raw or "")
    return limpo[:36] or uuid4().hex[:12]


def _str_val(val: str) -> dict[str, Any]:
    return {"stringValue": val}


def _double_val(val: float) -> dict[str, Any]:
    return {"doubleValue": float(val)}


def _int_val(val: int) -> dict[str, Any]:
    return {"integerValue": str(int(val))}


def _read_str(fields: dict[str, Any], key: str, default: str = "") -> str:
    raw = fields.get(key) or {}
    return str(raw.get("stringValue", default))


def _read_float(fields: dict[str, Any], key: str, default: float = 0.0) -> float:
    raw = fields.get(key) or {}
    if "doubleValue" in raw:
        return float(raw["doubleValue"])
    if "integerValue" in raw:
        return float(raw["integerValue"])
    return default


def _read_int(fields: dict[str, Any], key: str, default: int = 0) -> int:
    raw = fields.get(key) or {}
    if "integerValue" in raw:
        return int(raw["integerValue"])
    if "doubleValue" in raw:
        return int(raw["doubleValue"])
    return default


class FirestoreSessionService(BaseSessionService):
    """Persiste sessões e eventos ADK no Cloud Firestore via REST v1 com ADC ou Emulador."""

    def __init__(
        self,
        *,
        project_id: Optional[str] = None,
        database_id: str = "(default)",
        collection: str = _DEFAULT_COLLECTION,
        emulator_host: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._emulator_host = (
            emulator_host
            if emulator_host is not None
            else os.environ.get("FIRESTORE_EMULATOR_HOST", "").strip()
        ) or None
        self._database_id = (database_id or "(default)").strip() or "(default)"
        self._collection = (collection or _DEFAULT_COLLECTION).strip() or _DEFAULT_COLLECTION
        self._credentials: Any = None
        self._cred_lock = asyncio.Lock()

        resolved_project = (
            project_id
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("GCLOUD_PROJECT")
            or ""
        ).strip()

        if not self._emulator_host and not resolved_project:
            creds, adc_project = google.auth.default(scopes=[_FIRESTORE_SCOPE])
            self._credentials = creds
            resolved_project = (adc_project or "").strip()
        elif self._emulator_host and not resolved_project:
            resolved_project = "demo-sabor-da-terra"

        if not resolved_project:
            raise ValueError(
                "Projeto GCP não definido para FirestoreSessionService. "
                "Informe na URI (firestore://PROJETO/(default)) ou em GOOGLE_CLOUD_PROJECT."
            )

        self._project_id = resolved_project
        if self._emulator_host:
            host = self._emulator_host.removeprefix("http://").removeprefix("https://").rstrip("/")
            self._base_origin = f"http://{host}"
        else:
            self._base_origin = "https://firestore.googleapis.com"

        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=15.0)

    @classmethod
    def from_uri(cls, uri: str, **kwargs: Any) -> FirestoreSessionService:
        """Cria FirestoreSessionService a partir de URI `firestore://[projeto]/[database]?collection=...`."""
        del kwargs
        parsed = urlparse(uri)
        if parsed.scheme != "firestore":
            raise ValueError(f"URI inválida para FirestoreSessionService: {uri}")

        host = unquote_safe(parsed.netloc).strip()
        path_part = unquote_safe(parsed.path).strip("/")
        qs = parse_qs(parsed.query)
        collection = (
            (qs.get("collection") or [None])[0]
            or os.environ.get("FIRESTORE_SESSIONS_COLLECTION")
            or _DEFAULT_COLLECTION
        )

        project_id: Optional[str] = None
        database_id = "(default)"

        if host and path_part:
            project_id = host
            database_id = path_part
        elif host:
            if host == "(default)":
                database_id = "(default)"
            else:
                project_id = host
        elif path_part:
            database_id = path_part

        return cls(
            project_id=project_id,
            database_id=database_id,
            collection=collection,
        )

    @property
    def _documents_rel(self) -> str:
        return f"projects/{self._project_id}/databases/{self._database_id}/documents"

    @property
    def _documents_url(self) -> str:
        return f"{self._base_origin}/v1/{self._documents_rel}"

    @staticmethod
    def _session_doc_id(app_name: str, user_id: str, session_id: str) -> str:
        chave = f"{app_name}\0{user_id}\0{session_id}".encode("utf-8")
        return hashlib.sha256(chave).hexdigest()

    @staticmethod
    def _app_user_key(app_name: str, user_id: str) -> str:
        return f"{app_name}\0{user_id}"

    def _session_doc_rel(self, app_name: str, user_id: str, session_id: str) -> str:
        doc_id = self._session_doc_id(app_name, user_id, session_id)
        return f"{self._documents_rel}/{self._collection}/{doc_id}"

    def _session_doc_url(self, app_name: str, user_id: str, session_id: str) -> str:
        doc_id = self._session_doc_id(app_name, user_id, session_id)
        return f"{self._documents_url}/{self._collection}/{doc_id}"

    async def _auth_headers(self) -> dict[str, str]:
        if self._emulator_host:
            return {"Content-Type": "application/json"}

        async with self._cred_lock:
            if self._credentials is None:
                creds, _ = await asyncio.to_thread(
                    google.auth.default, scopes=[_FIRESTORE_SCOPE]
                )
                self._credentials = creds
            if not self._credentials.valid or not self._credentials.token:
                await asyncio.to_thread(
                    self._credentials.refresh,
                    google.auth.transport.requests.Request(),
                )
            token = self._credentials.token

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @override
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        sid = (session_id or "").strip() or str(uuid4())
        doc_id = self._session_doc_id(app_name, user_id, sid)
        deltas = _session_util.extract_state_delta(state or {})
        session_state = _session_util.make_json_safe_state(deltas["session"])
        now = time.time()

        payload = {
            "fields": {
                "app_name": _str_val(app_name),
                "user_id": _str_val(user_id),
                "session_id": _str_val(sid),
                "app_user_key": _str_val(self._app_user_key(app_name, user_id)),
                "state_json": _str_val(json.dumps(session_state, ensure_ascii=False)),
                "last_update_time": _double_val(now),
            }
        }

        headers = await self._auth_headers()
        res = await self._client.post(
            f"{self._documents_url}/{self._collection}",
            params={"documentId": doc_id},
            json=payload,
            headers=headers,
        )
        if res.status_code == 409:
            raise AlreadyExistsError(f"Session with id {sid} already exists.")
        res.raise_for_status()

        return Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=session_state,
            events=[],
            last_update_time=now,
        )

    async def _listar_eventos_docs(
        self, app_name: str, user_id: str, session_id: str, headers: dict[str, str]
    ) -> list[dict[str, Any]]:
        url = f"{self._session_doc_url(app_name, user_id, session_id)}/events"
        docs: list[dict[str, Any]] = []
        page_token: Optional[str] = None

        while True:
            params: dict[str, Any] = {"pageSize": 300}
            if page_token:
                params["pageToken"] = page_token
            res = await self._client.get(url, params=params, headers=headers)
            if res.status_code == 404:
                break
            res.raise_for_status()
            body = res.json()
            docs.extend(body.get("documents") or [])
            page_token = body.get("nextPageToken")
            if not page_token:
                break
        return docs

    @override
    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        sid = (session_id or "").strip()
        if not sid:
            return None

        headers = await self._auth_headers()
        res = await self._client.get(
            self._session_doc_url(app_name, user_id, sid),
            headers=headers,
        )
        if res.status_code == 404:
            return None
        res.raise_for_status()

        fields = res.json().get("fields") or {}
        raw_state = _read_str(fields, "state_json", "{}")
        try:
            state = json.loads(raw_state) if raw_state else {}
        except json.JSONDecodeError:
            state = {}
        last_update = _read_float(fields, "last_update_time", 0.0)

        event_docs = await self._listar_eventos_docs(app_name, user_id, sid, headers)
        eventos_ordenados: list[tuple[int, float, Event]] = []
        for doc in event_docs:
            ef = doc.get("fields") or {}
            ev_raw = _read_str(ef, "event_json", "")
            if not ev_raw:
                continue
            ev = Event.model_validate_json(ev_raw)
            seq = _read_int(ef, "seq", 0)
            eventos_ordenados.append((seq, ev.timestamp, ev))

        eventos_ordenados.sort(key=lambda item: (item[0], item[1]))
        events = [item[2] for item in eventos_ordenados]

        if config is not None:
            if config.after_timestamp is not None:
                events = [e for e in events if e.timestamp >= config.after_timestamp]
            if config.num_recent_events is not None:
                n = config.num_recent_events
                events = events[-n:] if n > 0 else []

        return Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=state if isinstance(state, dict) else {},
            events=events,
            last_update_time=last_update,
        )

    @override
    async def list_sessions(
        self, *, app_name: str, user_id: str | None = None
    ) -> ListSessionsResponse:
        headers = await self._auth_headers()
        if user_id is not None:
            campo = "app_user_key"
            valor = self._app_user_key(app_name, user_id)
        else:
            campo = "app_name"
            valor = app_name

        query_body = {
            "structuredQuery": {
                "from": [{"collectionId": self._collection}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": campo},
                        "op": "EQUAL",
                        "value": _str_val(valor),
                    }
                },
            }
        }
        res = await self._client.post(
            f"{self._documents_url}:runQuery",
            json=query_body,
            headers=headers,
        )
        res.raise_for_status()

        sessions: list[Session] = []
        for item in res.json() or []:
            doc = item.get("document")
            if not doc:
                continue
            fields = doc.get("fields") or {}
            raw_state = _read_str(fields, "state_json", "{}")
            try:
                state = json.loads(raw_state) if raw_state else {}
            except json.JSONDecodeError:
                state = {}
            sessions.append(
                Session(
                    id=_read_str(fields, "session_id"),
                    app_name=_read_str(fields, "app_name", app_name),
                    user_id=_read_str(fields, "user_id"),
                    state=state if isinstance(state, dict) else {},
                    events=[],
                    last_update_time=_read_float(fields, "last_update_time", 0.0),
                )
            )

        sessions.sort(key=lambda s: (s.last_update_time, s.user_id, s.id))
        return ListSessionsResponse(sessions=sessions)

    @override
    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        sid = (session_id or "").strip()
        if not sid:
            return
        headers = await self._auth_headers()
        event_docs = await self._listar_eventos_docs(app_name, user_id, sid, headers)
        nomes_para_deletar = [doc["name"] for doc in event_docs if doc.get("name")]
        nomes_para_deletar.append(self._session_doc_rel(app_name, user_id, sid))

        # Limite de 500 operações por commit no Firestore.
        for i in range(0, len(nomes_para_deletar), 450):
            lote = nomes_para_deletar[i : i + 450]
            res = await self._client.post(
                f"{self._documents_url}:commit",
                json={"writes": [{"delete": nome} for nome in lote]},
                headers=headers,
            )
            if res.status_code != 404:
                res.raise_for_status()

    @override
    async def get_user_state(
        self, *, app_name: str, user_id: str
    ) -> dict[str, Any]:
        del app_name, user_id
        return {}

    @override
    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event

        if any(e == event for e in session.events if e.id == event.id):
            return event

        seq = len(session.events)
        event = await super().append_event(session=session, event=event)
        session.last_update_time = event.timestamp

        estado_persistivel = {
            k: v for k, v in session.state.items() if not str(k).startswith("temp:")
        }
        state_seguro = _session_util.make_json_safe_state(estado_persistivel)
        ts_micro = int(max(0.0, float(event.timestamp)) * 1_000_000)
        event_doc_id = f"{seq:08d}_{ts_micro:019d}_{_safe_id(event.id)}"
        sess_rel = self._session_doc_rel(session.app_name, session.user_id, session.id)
        event_rel = f"{sess_rel}/events/{event_doc_id}"

        commit_body = {
            "writes": [
                {
                    "update": {
                        "name": event_rel,
                        "fields": {
                            "seq": _int_val(seq),
                            "timestamp": _double_val(event.timestamp),
                            "event_json": _str_val(
                                event.model_dump_json(by_alias=True, exclude_none=True)
                            ),
                        },
                    }
                },
                {
                    "update": {
                        "name": sess_rel,
                        "fields": {
                            "state_json": _str_val(
                                json.dumps(state_seguro, ensure_ascii=False)
                            ),
                            "last_update_time": _double_val(session.last_update_time),
                        },
                    },
                    "updateMask": {"fieldPaths": ["state_json", "last_update_time"]},
                    "currentDocument": {"exists": True},
                },
            ]
        }

        headers = await self._auth_headers()
        res = await self._client.post(
            f"{self._documents_url}:commit",
            json=commit_body,
            headers=headers,
        )
        if res.status_code in {400, 404, 409}:
            detalhe = res.text
            if "NOT_FOUND" in detalhe or "does not exist" in detalhe.lower() or res.status_code == 404:
                raise SessionNotFoundError(f"Session {session.id} not found.")
        res.raise_for_status()
        return event


def unquote_safe(val: str) -> str:
    from urllib.parse import unquote

    return unquote(val or "")


def registrar_firestore_no_adk() -> None:
    """Registra o esquema `firestore://` no ServiceRegistry do Google ADK."""
    from google.adk.cli.service_registry import get_service_registry

    def _factory(uri: str, **kwargs: Any) -> FirestoreSessionService:
        return FirestoreSessionService.from_uri(uri, **kwargs)

    get_service_registry().register_session_service("firestore", _factory)

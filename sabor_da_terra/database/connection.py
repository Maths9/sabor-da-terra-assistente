"""Gerenciamento de conexão SQLAlchemy e sessões para PostgreSQL, Cloud SQL (Unix Socket) e SQLite."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from sabor_da_terra.config import (
    DADOS_DIR,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
)

_engines_cache: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker[Session]] = {}
_fallback_sqlite_engine: Optional[Engine] = None
_fallback_sqlite_dados_dir: Optional[str] = None


def possui_config_banco_explicita() -> bool:
    """Indica se há configuração explícita de PostgreSQL/SQL definida nas variáveis de ambiente."""
    return any(
        os.environ.get(var, "").strip()
        for var in ("DATABASE_URL", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
    )


def construir_database_url(
    *,
    database_url: Optional[str] = None,
    db_host: Optional[str] = None,
    db_port: Optional[int | str] = None,
    db_name: Optional[str] = None,
    db_user: Optional[str] = None,
    db_password: Optional[str] = None,
) -> URL:
    """Constrói a URL do SQLAlchemy suportando TCP local, Cloud SQL Auth Proxy e Unix Socket do Cloud Run."""
    raw_url = (
        database_url
        if database_url is not None
        else os.environ.get("DATABASE_URL", "")
    ).strip()

    if raw_url:
        if raw_url.startswith("postgres://"):
            raw_url = "postgresql+psycopg://" + raw_url[len("postgres://") :]
        elif raw_url.startswith("postgresql://"):
            raw_url = "postgresql+psycopg://" + raw_url[len("postgresql://") :]
        return make_url(raw_url)

    host = (
        db_host
        if db_host is not None
        else os.environ.get("DB_HOST", DB_HOST)
    ).strip()
    port_raw = (
        db_port
        if db_port is not None
        else os.environ.get("DB_PORT", str(DB_PORT))
    )
    name = (
        db_name
        if db_name is not None
        else os.environ.get("DB_NAME", DB_NAME)
    ).strip()
    user = (
        db_user
        if db_user is not None
        else os.environ.get("DB_USER", DB_USER)
    ).strip()
    password = (
        db_password
        if db_password is not None
        else os.environ.get("DB_PASSWORD", DB_PASSWORD)
    )

    # No Cloud Run, o Cloud SQL é montado como Unix Domain Socket em /cloudsql/PROJETO:REGIAO:INSTANCIA
    if host.startswith("/"):
        return URL.create(
            drivername="postgresql+psycopg",
            username=user or None,
            password=password or None,
            database=name,
            query={"host": host},
        )

    return URL.create(
        drivername="postgresql+psycopg",
        username=user or None,
        password=password or None,
        host=host or "127.0.0.1",
        port=int(port_raw) if str(port_raw).strip() else 5432,
        database=name,
    )


def _chave_cache_url(url: URL) -> str:
    return url.render_as_string(hide_password=False)


def get_engine(url: Optional[URL | str] = None) -> Engine:
    """Retorna ou cria o Engine SQLAlchemy com pool de conexões configurado."""
    resolved_url = make_url(url) if isinstance(url, str) else (url or construir_database_url())
    key = _chave_cache_url(resolved_url)

    if key not in _engines_cache:
        kwargs: dict[str, Any] = {"future": True}
        if resolved_url.get_backend_name() == "sqlite":
            kwargs["connect_args"] = {"check_same_thread": False}
            if resolved_url.database in (None, "", ":memory:"):
                kwargs["poolclass"] = StaticPool
        else:
            pool_size = int(os.environ.get("DB_POOL_SIZE", "5"))
            max_overflow = int(os.environ.get("DB_MAX_OVERFLOW", "5"))
            pool_timeout = int(os.environ.get("DB_POOL_TIMEOUT", "30"))
            kwargs.update(
                {
                    "pool_size": pool_size,
                    "max_overflow": max_overflow,
                    "pool_timeout": pool_timeout,
                    "pool_pre_ping": True,
                }
            )
        _engines_cache[key] = create_engine(resolved_url, **kwargs)

    return _engines_cache[key]


def _obter_engine_sqlite_autoseed() -> Engine:
    """Cria e popula sob demanda um banco SQLite em memória quando variáveis DB_* não estão definidas."""
    global _fallback_sqlite_engine, _fallback_sqlite_dados_dir
    dados_atual = str(
        os.environ.get("SABOR_DADOS_DIR") or DADOS_DIR
    )
    if _fallback_sqlite_engine is None or _fallback_sqlite_dados_dir != dados_atual:
        if _fallback_sqlite_engine is not None:
            _fallback_sqlite_engine.dispose()
        eng = create_engine(
            "sqlite://",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        from pathlib import Path
        from scripts.importar_dados import importar_todos_os_dados

        importar_todos_os_dados(
            dados_dir=Path(dados_atual).resolve(),
            engine=eng,
            criar_tabelas=True,
        )
        _fallback_sqlite_engine = eng
        _fallback_sqlite_dados_dir = dados_atual
    return _fallback_sqlite_engine


def get_operational_engine(engine: Optional[Engine] = None) -> Engine:
    """Retorna o Engine PostgreSQL configurado ou o Engine SQLite auto-populado em ambiente de teste local."""
    if engine is not None:
        return engine
    if possui_config_banco_explicita():
        return get_engine()
    return _obter_engine_sqlite_autoseed()


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker[Session]:
    """Retorna a fábrica de sessões vinculada ao Engine ativo."""
    eng = get_operational_engine(engine)
    key = f"{id(eng)}:{eng.url.render_as_string(hide_password=False)}"
    if key not in _session_factories:
        _session_factories[key] = sessionmaker(
            bind=eng,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factories[key]


@contextmanager
def session_scope(engine: Optional[Engine] = None) -> Iterator[Session]:
    """Context manager transacional seguro que fecha a sessão ao sair."""
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def limpar_cache_conexoes() -> None:
    """Descarta engines em cache (útil ao alternar variáveis de ambiente em testes)."""
    global _fallback_sqlite_engine, _fallback_sqlite_dados_dir
    for eng in _engines_cache.values():
        eng.dispose()
    _engines_cache.clear()
    _session_factories.clear()
    if _fallback_sqlite_engine is not None:
        _fallback_sqlite_engine.dispose()
        _fallback_sqlite_engine = None
        _fallback_sqlite_dados_dir = None

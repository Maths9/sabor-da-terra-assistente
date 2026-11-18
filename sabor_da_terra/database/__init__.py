"""Pacote de banco de dados relacional (SQLAlchemy 2.0 + PostgreSQL/Cloud SQL) e criptografia LGPD."""

from sabor_da_terra.database.connection import (
    construir_database_url,
    get_engine,
    get_operational_engine,
    get_session_factory,
    limpar_cache_conexoes,
    possui_config_banco_explicita,
    session_scope,
)
from sabor_da_terra.database.crypto import (
    PREFIXO_CIFRADO,
    cifrar_valor_sensivel,
    decifrar_valor_sensivel,
    esta_cifrado,
    gerar_hash_deterministico,
)
from sabor_da_terra.database.models import (
    Base,
    LoteModel,
    PedidoModel,
    PrecoModel,
    ProdutorModel,
    SazonalidadeModel,
    TransacaoFinanceiraModel,
)
from sabor_da_terra.database.repositories import RepositorioOperacional, repositorio

__all__ = [
    "Base",
    "LoteModel",
    "PREFIXO_CIFRADO",
    "PedidoModel",
    "PrecoModel",
    "ProdutorModel",
    "RepositorioOperacional",
    "SazonalidadeModel",
    "TransacaoFinanceiraModel",
    "cifrar_valor_sensivel",
    "construir_database_url",
    "decifrar_valor_sensivel",
    "esta_cifrado",
    "gerar_hash_deterministico",
    "get_engine",
    "get_operational_engine",
    "get_session_factory",
    "limpar_cache_conexoes",
    "possui_config_banco_explicita",
    "repositorio",
    "session_scope",
]

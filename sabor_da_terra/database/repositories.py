"""Camada de repositório operacional (PostgreSQL/SQLAlchemy com fallback CSV controlado por SABOR_DATA_BACKEND)."""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Engine, desc, func, select
from sqlalchemy.exc import SQLAlchemyError

from sabor_da_terra.config import DADOS_DIR, obter_backend_dados
from sabor_da_terra.database.connection import session_scope
from sabor_da_terra.database.models import (
    LoteModel,
    PedidoModel,
    PrecoModel,
    ProdutorModel,
    SazonalidadeModel,
    TransacaoFinanceiraModel,
)
from sabor_da_terra.seguranca import CAMPOS_CONTATO_PESSOAL, CAMPOS_SENSIVEIS_LGPD, norm_texto


def _obter_dados_dir() -> Path:
    env_dir = os.environ.get("SABOR_DADOS_DIR", "").strip()
    return Path(env_dir).resolve() if env_dir else DADOS_DIR


def _fmt_moeda(valor: Optional[Decimal]) -> str:
    if valor is None:
        return "0.00"
    return f"{Decimal(valor).quantize(Decimal('0.01'))}"


def _fmt_num_compacto(valor: Optional[Decimal]) -> str:
    if valor is None:
        return "0"
    dec = Decimal(valor)
    if dec == dec.to_integral_value():
        return str(int(dec))
    return f"{dec.normalize():f}"


def _ler_csv_arquivo(
    caminho: Path,
    *,
    filtrar_lgpd: bool = True,
    remover_contato: bool = True,
) -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    if not filtrar_lgpd and not remover_contato:
        return linhas
    proibidos = set(CAMPOS_SENSIVEIS_LGPD) if filtrar_lgpd else set()
    if remover_contato:
        proibidos |= CAMPOS_CONTATO_PESSOAL
    return [
        {k: v for k, v in row.items() if k.lower() not in proibidos}
        for row in linhas
    ]


class RepositorioOperacional:
    """Repositório unificado para consulta às 6 entidades operacionais da cooperativa."""

    def __init__(self, engine: Optional[Engine] = None) -> None:
        self._engine = engine

    def _usar_csv(self) -> bool:
        return self._engine is None and obter_backend_dados() == "csv"

    # ------------------------------------------------------------------
    # 1. PRODUTORES
    # ------------------------------------------------------------------

    @staticmethod
    def _serializar_produtor(
        p: ProdutorModel,
        *,
        filtrar_lgpd: bool = True,
        remover_contato: bool = True,
        incluir_agencia_interna: bool = False,
    ) -> dict[str, str]:
        dados: dict[str, str] = {
            "id": p.id,
            "nome_completo": p.nome_completo,
            "municipio": p.municipio,
            "produtos": p.produtos,
            "certificacao_organica": "sim" if p.certificacao_organica else "nao",
            "validade_certificacao": (
                p.validade_certificacao.isoformat() if p.validade_certificacao else ""
            ),
            "status": p.status,
        }
        if not remover_contato:
            dados["telefone"] = p.telefone or ""
            dados["email"] = p.email or ""
            dados["endereco"] = p.endereco or ""

        if incluir_agencia_interna or not filtrar_lgpd:
            dados["agencia"] = p.agencia or ""
            dados["banco"] = p.banco or ""

        return dados

    def listar_produtores(
        self,
        *,
        filtrar_lgpd: bool = True,
        remover_contato: bool = True,
        incluir_agencia_interna: bool = False,
    ) -> list[dict[str, str]]:
        """Lista os produtores cadastrados aplicando filtros LGPD e de contato na origem."""
        if self._usar_csv():
            return _ler_csv_arquivo(
                _obter_dados_dir() / "produtores.csv",
                filtrar_lgpd=filtrar_lgpd and not incluir_agencia_interna,
                remover_contato=remover_contato,
            )

        try:
            with session_scope(self._engine) as session:
                stmt = select(ProdutorModel).order_by(ProdutorModel.id.asc())
                registros = session.scalars(stmt).all()
                return [
                    self._serializar_produtor(
                        p,
                        filtrar_lgpd=filtrar_lgpd,
                        remover_contato=remover_contato,
                        incluir_agencia_interna=incluir_agencia_interna,
                    )
                    for p in registros
                ]
        except SQLAlchemyError as exc:
            raise OSError(f"Erro ao consultar tabela 'produtores': {exc}") from exc

    def obter_produtor_por_id(
        self,
        produtor_id: str,
        *,
        remover_contato: bool = True,
        incluir_agencia_interna: bool = False,
    ) -> Optional[dict[str, str]]:
        """Busca um produtor pelo ID (ex.: P001) sem jamais expor CPF, PIX ou conta corrente."""
        pid = (produtor_id or "").strip().upper()
        if not pid:
            return None

        if self._usar_csv():
            linhas = _ler_csv_arquivo(
                _obter_dados_dir() / "produtores.csv",
                filtrar_lgpd=not incluir_agencia_interna,
                remover_contato=remover_contato,
            )
            return next((r for r in linhas if r["id"].strip().upper() == pid), None)

        try:
            with session_scope(self._engine) as session:
                stmt = select(ProdutorModel).where(func.upper(ProdutorModel.id) == pid)
                reg = session.scalar(stmt)
                if reg is None:
                    return None
                return self._serializar_produtor(
                    reg,
                    filtrar_lgpd=True,
                    remover_contato=remover_contato,
                    incluir_agencia_interna=incluir_agencia_interna,
                )
        except SQLAlchemyError as exc:
            raise OSError(f"Erro ao consultar produtor '{pid}' no banco: {exc}") from exc

    def verificar_agencia_produtor(
        self, produtor_id: str, agencia_informada: Optional[str]
    ) -> Optional[bool]:
        """Compara apenas os dígitos da agência bancária sem expor dados bancários ao agente."""
        if not agencia_informada:
            return None
        prod = self.obter_produtor_por_id(produtor_id, incluir_agencia_interna=True)
        if not prod:
            return None
        inf_digits = re.sub(r"\D", "", agencia_informada)
        real_digits = re.sub(r"\D", "", prod.get("agencia", ""))
        return bool(real_digits and inf_digits) and inf_digits.zfill(4) == real_digits.zfill(4)

    # ------------------------------------------------------------------
    # 2. TRANSAÇÕES FINANCEIRAS
    # ------------------------------------------------------------------

    @staticmethod
    def _serializar_transacao(
        tx: TransacaoFinanceiraModel, produtor_nome: Optional[str] = None
    ) -> dict[str, str]:
        dados: dict[str, str] = {
            "id_transacao": tx.id_transacao,
            "data": tx.data.isoformat(),
            "produtor_id": tx.produtor_id,
            "produtor_nome": produtor_nome or (tx.produtor.nome_completo if tx.produtor else ""),
            "comprador": tx.comprador,
            "tipo": tx.tipo,
            "produto": tx.produto,
            "quantidade_kg": _fmt_num_compacto(tx.quantidade_kg),
            "valor_unitario": _fmt_moeda(tx.valor_unitario),
            "valor_total": _fmt_moeda(tx.valor_total),
            "forma_pagamento": tx.forma_pagamento,
            "status_pagamento": tx.status_pagamento,
            "data_vencimento": tx.data_vencimento.isoformat() if tx.data_vencimento else "",
            "data_pagamento": tx.data_pagamento.isoformat() if tx.data_pagamento else "",
            "observacao": tx.observacao or "",
        }
        return dados

    def listar_transacoes_financeiras(
        self,
        *,
        produtor_id: Optional[str] = None,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
        status_pagamento: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """Consulta transações financeiras com filtros opcionais de produtor, período e status."""
        pid = produtor_id.strip().upper() if produtor_id else None
        status_norm = norm_texto(status_pagamento) if status_pagamento else None

        if self._usar_csv():
            linhas = _ler_csv_arquivo(
                _obter_dados_dir() / "financeiro.csv",
                filtrar_lgpd=True,
                remover_contato=True,
            )
            resultado: list[dict[str, str]] = []
            for r in linhas:
                if pid and r.get("produtor_id", "").strip().upper() != pid:
                    continue
                if status_norm and norm_texto(r.get("status_pagamento", "")) != status_norm:
                    continue
                if data_inicio or data_fim:
                    dt_str = (r.get("data") or "").strip()[:10]
                    if not dt_str:
                        continue
                    dt_venda = date.fromisoformat(dt_str)
                    if data_inicio and dt_venda < data_inicio:
                        continue
                    if data_fim and dt_venda > data_fim:
                        continue
                resultado.append(r)
            return resultado

        try:
            with session_scope(self._engine) as session:
                stmt = (
                    select(TransacaoFinanceiraModel, ProdutorModel.nome_completo)
                    .join(
                        ProdutorModel,
                        TransacaoFinanceiraModel.produtor_id == ProdutorModel.id,
                    )
                    .order_by(TransacaoFinanceiraModel.id_transacao.asc())
                )
                if pid:
                    stmt = stmt.where(
                        func.upper(TransacaoFinanceiraModel.produtor_id) == pid
                    )
                if status_norm:
                    stmt = stmt.where(
                        func.lower(TransacaoFinanceiraModel.status_pagamento) == status_norm
                    )
                if data_inicio is not None:
                    stmt = stmt.where(TransacaoFinanceiraModel.data >= data_inicio)
                if data_fim is not None:
                    stmt = stmt.where(TransacaoFinanceiraModel.data <= data_fim)

                rows = session.execute(stmt).all()
                return [
                    self._serializar_transacao(tx, nome_prod)
                    for tx, nome_prod in rows
                ]
        except SQLAlchemyError as exc:
            raise OSError(
                f"Erro ao consultar tabela 'transacoes_financeiras': {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # 3. LOTES (RASTREABILIDADE)
    # ------------------------------------------------------------------

    @staticmethod
    def _serializar_lote(
        lote: LoteModel, produtor_nome: Optional[str] = None
    ) -> dict[str, str]:
        return {
            "lote_id": lote.lote_id,
            "data_colheita": lote.data_colheita.isoformat(),
            "data_entrega": lote.data_entrega.isoformat(),
            "produtor_id": lote.produtor_id,
            "produtor_nome": produtor_nome or (lote.produtor.nome_completo if lote.produtor else ""),
            "produto": lote.produto,
            "quantidade_kg": _fmt_num_compacto(lote.quantidade_kg),
            "comprador": lote.comprador,
            "pedido_id": lote.pedido_id,
            "temperatura_transporte_c": lote.temperatura_transporte_c,
            "validade": lote.validade.isoformat(),
            "inspecao_visual": lote.inspecao_visual,
            "observacao": lote.observacao or "",
        }

    def listar_lotes(
        self,
        *,
        lote_id: Optional[str] = None,
        produtor_id: Optional[str] = None,
        data_entrega_inicio: Optional[date] = None,
        data_entrega_fim: Optional[date] = None,
    ) -> list[dict[str, str]]:
        """Consulta lotes entregues com JOIN em produtores para recuperar o nome sem expor CPF."""
        lid = lote_id.strip().upper() if lote_id else None
        pid = produtor_id.strip().upper() if produtor_id else None

        if self._usar_csv():
            linhas = _ler_csv_arquivo(
                _obter_dados_dir() / "lotes.csv",
                filtrar_lgpd=True,
                remover_contato=True,
            )
            resultado: list[dict[str, str]] = []
            for r in linhas:
                if lid and r.get("lote_id", "").strip().upper() != lid:
                    continue
                if pid and r.get("produtor_id", "").strip().upper() != pid:
                    continue
                if data_entrega_inicio or data_entrega_fim:
                    dt_str = (r.get("data_entrega") or "").strip()[:10]
                    if not dt_str:
                        continue
                    dt_ent = date.fromisoformat(dt_str)
                    if data_entrega_inicio and dt_ent < data_entrega_inicio:
                        continue
                    if data_entrega_fim and dt_ent > data_entrega_fim:
                        continue
                resultado.append(r)
            return resultado

        try:
            with session_scope(self._engine) as session:
                stmt = (
                    select(LoteModel, ProdutorModel.nome_completo)
                    .join(ProdutorModel, LoteModel.produtor_id == ProdutorModel.id)
                    .order_by(LoteModel.lote_id.asc())
                )
                if lid:
                    stmt = stmt.where(func.upper(LoteModel.lote_id) == lid)
                if pid:
                    stmt = stmt.where(func.upper(LoteModel.produtor_id) == pid)
                if data_entrega_inicio is not None:
                    stmt = stmt.where(LoteModel.data_entrega >= data_entrega_inicio)
                if data_entrega_fim is not None:
                    stmt = stmt.where(LoteModel.data_entrega <= data_entrega_fim)

                rows = session.execute(stmt).all()
                return [
                    self._serializar_lote(lote, nome_prod)
                    for lote, nome_prod in rows
                ]
        except SQLAlchemyError as exc:
            raise OSError(f"Erro ao consultar tabela 'lotes': {exc}") from exc

    # ------------------------------------------------------------------
    # 4. TABELA DE PREÇOS
    # ------------------------------------------------------------------

    @staticmethod
    def _serializar_preco(p: PrecoModel) -> dict[str, str]:
        return {
            "produto": p.produto,
            "unidade": p.unidade,
            "preco_convencional": (
                _fmt_moeda(p.preco_convencional)
                if p.preco_convencional is not None
                else "n/d"
            ),
            "preco_organico": (
                _fmt_moeda(p.preco_organico)
                if p.preco_organico is not None
                else "n/d"
            ),
            "desconto_atacado_pct": _fmt_num_compacto(p.desconto_atacado_pct),
            "volume_minimo_atacado_kg": _fmt_num_compacto(p.volume_minimo_atacado_kg),
            "observacao": p.observacao or "",
        }

    def obter_tabela_precos_vigente(
        self, vigencia: Optional[str] = None
    ) -> list[dict[str, str]]:
        """Carrega os itens da tabela de preços da vigência mais recente."""
        if self._usar_csv():
            dados_dir = _obter_dados_dir()
            arquivos = sorted(dados_dir.glob("tabela_precos_*.csv"))
            if not arquivos:
                raise FileNotFoundError(
                    f"Nenhuma tabela de preços (tabela_precos_*.csv) encontrada em {dados_dir}."
                )
            return _ler_csv_arquivo(
                arquivos[-1], filtrar_lgpd=False, remover_contato=False
            )

        try:
            with session_scope(self._engine) as session:
                vig_alvo = (vigencia or "").strip()
                if not vig_alvo:
                    vig_alvo = (
                        session.scalar(
                            select(PrecoModel.vigencia)
                            .order_by(desc(PrecoModel.vigencia))
                            .limit(1)
                        )
                        or ""
                    )
                if not vig_alvo:
                    raise FileNotFoundError(
                        "Nenhum registro de preços encontrado na tabela 'precos'."
                    )
                stmt = (
                    select(PrecoModel)
                    .where(PrecoModel.vigencia == vig_alvo)
                    .order_by(PrecoModel.id.asc())
                )
                itens = session.scalars(stmt).all()
                return [self._serializar_preco(p) for p in itens]
        except SQLAlchemyError as exc:
            raise OSError(f"Erro ao consultar tabela 'precos': {exc}") from exc

    # ------------------------------------------------------------------
    # 5. SAZONALIDADE
    # ------------------------------------------------------------------

    @staticmethod
    def _serializar_sazonalidade(s: SazonalidadeModel) -> dict[str, str]:
        return {
            "produto": s.produto,
            "jan": s.jan,
            "fev": s.fev,
            "mar": s.mar,
            "abr": s.abr,
            "mai": s.mai,
            "jun": s.jun,
            "jul": s.jul,
            "ago": s.ago,
            "set": s.set,
            "out": s.out,
            "nov": s.nov,
            "dez": s.dez,
            "observacao": s.observacao or "",
        }

    def listar_sazonalidade(self) -> list[dict[str, str]]:
        """Retorna todas as linhas do calendário de sazonalidade."""
        if self._usar_csv():
            return _ler_csv_arquivo(
                _obter_dados_dir() / "sazonalidade.csv",
                filtrar_lgpd=False,
                remover_contato=False,
            )

        try:
            with session_scope(self._engine) as session:
                stmt = select(SazonalidadeModel).order_by(SazonalidadeModel.produto.asc())
                itens = session.scalars(stmt).all()
                return [self._serializar_sazonalidade(s) for s in itens]
        except SQLAlchemyError as exc:
            raise OSError(f"Erro ao consultar tabela 'sazonalidade': {exc}") from exc

    def obter_mapa_sazonalidade(self) -> dict[str, dict[str, str]]:
        """Retorna dicionário produto_normalizado -> registro de sazonalidade."""
        return {norm_texto(r["produto"]): r for r in self.listar_sazonalidade()}

    # ------------------------------------------------------------------
    # 6. PEDIDOS (CAIXA DE ENTRADA)
    # ------------------------------------------------------------------

    @staticmethod
    def _serializar_pedido(p: PedidoModel) -> dict[str, Any]:
        return {
            "id": p.id,
            "data_recebimento": p.data_recebimento.isoformat(timespec="seconds"),
            "canal": p.canal,
            "remetente": p.remetente,
            "comprador": p.comprador,
            "mensagem_original": p.mensagem_original,
            "status": p.status,
        }

    def listar_pedidos(self) -> list[dict[str, Any]]:
        """Lista todos os pedidos da caixa de entrada ordenados por ID."""
        if self._usar_csv():
            caminho = _obter_dados_dir() / "pedidos.json"
            with caminho.open("r", encoding="utf-8") as f:
                return list(json.load(f))

        try:
            with session_scope(self._engine) as session:
                stmt = select(PedidoModel).order_by(PedidoModel.id.asc())
                itens = session.scalars(stmt).all()
                return [self._serializar_pedido(p) for p in itens]
        except SQLAlchemyError as exc:
            raise OSError(f"Erro ao consultar tabela 'pedidos': {exc}") from exc

    def obter_pedido_por_id(self, id_pedido: str) -> Optional[dict[str, Any]]:
        """Busca um pedido específico pelo ID (ex.: PED-2026-004)."""
        alvo = (id_pedido or "").strip().upper()
        if not alvo:
            return None

        if self._usar_csv():
            pedidos = self.listar_pedidos()
            return next((p for p in pedidos if str(p.get("id", "")).upper() == alvo), None)

        try:
            with session_scope(self._engine) as session:
                stmt = select(PedidoModel).where(func.upper(PedidoModel.id) == alvo)
                reg = session.scalar(stmt)
                return self._serializar_pedido(reg) if reg is not None else None
        except SQLAlchemyError as exc:
            raise OSError(f"Erro ao consultar pedido '{alvo}' no banco: {exc}") from exc

    # ------------------------------------------------------------------
    # ROTEADOR GENÉRICO DE COMPATIBILIDADE (para ler_csv / ler_csv_bruto)
    # ------------------------------------------------------------------

    def ler_tabela_por_caminho(
        self,
        caminho: Path,
        *,
        filtrar_lgpd: bool = True,
        remover_contato: bool = True,
    ) -> list[dict[str, str]]:
        """Mapeia chamadas legadas baseadas em nome de arquivo CSV para as consultas do repositório."""
        if self._usar_csv():
            return _ler_csv_arquivo(
                caminho,
                filtrar_lgpd=filtrar_lgpd,
                remover_contato=remover_contato,
            )

        nome = caminho.name.lower()
        if nome == "produtores.csv":
            return self.listar_produtores(
                filtrar_lgpd=filtrar_lgpd,
                remover_contato=remover_contato,
                incluir_agencia_interna=not filtrar_lgpd,
            )
        if nome == "financeiro.csv":
            return self.listar_transacoes_financeiras()
        if nome == "lotes.csv":
            return self.listar_lotes()
        if nome == "sazonalidade.csv":
            return self.listar_sazonalidade()
        if nome.startswith("tabela_precos_"):
            return self.obter_tabela_precos_vigente()

        return _ler_csv_arquivo(
            caminho,
            filtrar_lgpd=filtrar_lgpd,
            remover_contato=remover_contato,
        )


repositorio = RepositorioOperacional()

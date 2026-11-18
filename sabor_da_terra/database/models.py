"""Modelos declarativos SQLAlchemy 2.0 para as 6 tabelas operacionais da Cooperativa Sabor da Terra."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Classe-base declarativa para os modelos ORM e migrações Alembic."""


class ProdutorModel(Base):
    """Cadastro dos produtores cooperados com colunas sensíveis LGPD criptografadas."""

    __tablename__ = "produtores"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    nome_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    municipio: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    produtos: Mapped[str] = mapped_column(Text, nullable=False)
    certificacao_organica: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    validade_certificacao: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ativo", index=True
    )

    # Contato (usado internamente apenas para identificação por pista, nunca exposto quando remover_contato=True)
    telefone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    endereco: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Dados bancários e pessoais sensíveis (LGPD)
    banco: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    agencia: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    cpf_cifrado: Mapped[str] = mapped_column(Text, nullable=False)
    data_nascimento_cifrada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chave_pix_cifrada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conta_corrente_cifrada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    transacoes: Mapped[list["TransacaoFinanceiraModel"]] = relationship(
        back_populates="produtor",
        cascade="save-update, merge",
    )
    lotes: Mapped[list["LoteModel"]] = relationship(
        back_populates="produtor",
        cascade="save-update, merge",
    )


class TransacaoFinanceiraModel(Base):
    """Histórico de transações financeiras normalizado (sem duplicar CPF ou PIX do produtor)."""

    __tablename__ = "transacoes_financeiras"
    __table_args__ = (
        Index("ix_transacoes_produtor_data", "produtor_id", "data"),
        Index("ix_transacoes_status_vencimento", "status_pagamento", "data_vencimento"),
    )

    id_transacao: Mapped[str] = mapped_column(String(20), primary_key=True)
    data: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    produtor_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("produtores.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    comprador: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False, default="venda")
    produto: Mapped[str] = mapped_column(String(80), nullable=False)
    quantidade_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    forma_pagamento: Mapped[str] = mapped_column(String(40), nullable=False)
    status_pagamento: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data_pagamento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    observacao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    produtor: Mapped["ProdutorModel"] = relationship(back_populates="transacoes")


class LoteModel(Base):
    """Rastreabilidade dos lotes entregues (sem duplicar CPF e sem FK rígida com pedidos.json)."""

    __tablename__ = "lotes"
    __table_args__ = (
        Index("ix_lotes_produtor_entrega", "produtor_id", "data_entrega"),
    )

    lote_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    data_colheita: Mapped[date] = mapped_column(Date, nullable=False)
    data_entrega: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    produtor_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("produtores.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    produto: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    quantidade_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    comprador: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    pedido_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    temperatura_transporte_c: Mapped[str] = mapped_column(String(20), nullable=False)
    validade: Mapped[date] = mapped_column(Date, nullable=False)
    inspecao_visual: Mapped[str] = mapped_column(String(30), nullable=False)
    observacao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    produtor: Mapped["ProdutorModel"] = relationship(back_populates="lotes")


class PrecoModel(Base):
    """Tabela de preços da cooperativa com suporte a vigência e descontos de atacado."""

    __tablename__ = "precos"
    __table_args__ = (
        UniqueConstraint("vigencia", "produto", name="uq_precos_vigencia_produto"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vigencia: Mapped[str] = mapped_column(
        String(20), nullable=False, default="2026-10", index=True
    )
    produto: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    unidade: Mapped[str] = mapped_column(String(20), nullable=False)
    preco_convencional: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    preco_organico: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    desconto_atacado_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    volume_minimo_atacado_kg: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    observacao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SazonalidadeModel(Base):
    """Calendário de disponibilidade mensal e observações de limite produtivo por produto."""

    __tablename__ = "sazonalidade"

    produto: Mapped[str] = mapped_column(String(80), primary_key=True)
    jan: Mapped[str] = mapped_column(String(15), nullable=False)
    fev: Mapped[str] = mapped_column(String(15), nullable=False)
    mar: Mapped[str] = mapped_column(String(15), nullable=False)
    abr: Mapped[str] = mapped_column(String(15), nullable=False)
    mai: Mapped[str] = mapped_column(String(15), nullable=False)
    jun: Mapped[str] = mapped_column(String(15), nullable=False)
    jul: Mapped[str] = mapped_column(String(15), nullable=False)
    ago: Mapped[str] = mapped_column(String(15), nullable=False)
    set: Mapped[str] = mapped_column(String(15), nullable=False)
    out: Mapped[str] = mapped_column(String(15), nullable=False)
    nov: Mapped[str] = mapped_column(String(15), nullable=False)
    dez: Mapped[str] = mapped_column(String(15), nullable=False)
    observacao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PedidoModel(Base):
    """Caixa de entrada de pedidos e demandas recebidos pelos canais da cooperativa."""

    __tablename__ = "pedidos"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    data_recebimento: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    canal: Mapped[str] = mapped_column(String(30), nullable=False)
    remetente: Mapped[str] = mapped_column(String(150), nullable=False)
    comprador: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    mensagem_original: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendente", index=True
    )

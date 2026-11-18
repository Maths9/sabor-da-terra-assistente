"""Schema inicial das 6 tabelas operacionais da Cooperativa Sabor da Terra.

Revision ID: 20261118_0001
Revises: None
Create Date: 2026-11-18 11:45:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261118_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "produtores",
        sa.Column("id", sa.String(length=10), nullable=False),
        sa.Column("nome_completo", sa.String(length=150), nullable=False),
        sa.Column("municipio", sa.String(length=80), nullable=False),
        sa.Column("produtos", sa.Text(), nullable=False),
        sa.Column("certificacao_organica", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("validade_certificacao", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'ativo'")),
        sa.Column("telefone", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("endereco", sa.Text(), nullable=True),
        sa.Column("banco", sa.String(length=60), nullable=True),
        sa.Column("agencia", sa.String(length=10), nullable=True),
        sa.Column("cpf_cifrado", sa.Text(), nullable=False),
        sa.Column("data_nascimento_cifrada", sa.Text(), nullable=True),
        sa.Column("chave_pix_cifrada", sa.Text(), nullable=True),
        sa.Column("conta_corrente_cifrada", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_produtores_municipio", "produtores", ["municipio"], unique=False)
    op.create_index("ix_produtores_status", "produtores", ["status"], unique=False)

    op.create_table(
        "precos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vigencia", sa.String(length=20), nullable=False, server_default=sa.text("'2026-10'")),
        sa.Column("produto", sa.String(length=80), nullable=False),
        sa.Column("unidade", sa.String(length=20), nullable=False),
        sa.Column("preco_convencional", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("preco_organico", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("desconto_atacado_pct", sa.Numeric(precision=5, scale=2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("volume_minimo_atacado_kg", sa.Numeric(precision=10, scale=2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vigencia", "produto", name="uq_precos_vigencia_produto"),
    )
    op.create_index("ix_precos_vigencia", "precos", ["vigencia"], unique=False)
    op.create_index("ix_precos_produto", "precos", ["produto"], unique=False)

    op.create_table(
        "sazonalidade",
        sa.Column("produto", sa.String(length=80), nullable=False),
        sa.Column("jan", sa.String(length=15), nullable=False),
        sa.Column("fev", sa.String(length=15), nullable=False),
        sa.Column("mar", sa.String(length=15), nullable=False),
        sa.Column("abr", sa.String(length=15), nullable=False),
        sa.Column("mai", sa.String(length=15), nullable=False),
        sa.Column("jun", sa.String(length=15), nullable=False),
        sa.Column("jul", sa.String(length=15), nullable=False),
        sa.Column("ago", sa.String(length=15), nullable=False),
        sa.Column("set", sa.String(length=15), nullable=False),
        sa.Column("out", sa.String(length=15), nullable=False),
        sa.Column("nov", sa.String(length=15), nullable=False),
        sa.Column("dez", sa.String(length=15), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("produto"),
    )

    op.create_table(
        "pedidos",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("data_recebimento", sa.DateTime(), nullable=False),
        sa.Column("canal", sa.String(length=30), nullable=False),
        sa.Column("remetente", sa.String(length=150), nullable=False),
        sa.Column("comprador", sa.String(length=150), nullable=False),
        sa.Column("mensagem_original", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'pendente'")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pedidos_data_recebimento", "pedidos", ["data_recebimento"], unique=False)
    op.create_index("ix_pedidos_comprador", "pedidos", ["comprador"], unique=False)
    op.create_index("ix_pedidos_status", "pedidos", ["status"], unique=False)

    op.create_table(
        "transacoes_financeiras",
        sa.Column("id_transacao", sa.String(length=20), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("produtor_id", sa.String(length=10), nullable=False),
        sa.Column("comprador", sa.String(length=120), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False, server_default=sa.text("'venda'")),
        sa.Column("produto", sa.String(length=80), nullable=False),
        sa.Column("quantidade_kg", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("valor_unitario", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("valor_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("forma_pagamento", sa.String(length=40), nullable=False),
        sa.Column("status_pagamento", sa.String(length=20), nullable=False),
        sa.Column("data_vencimento", sa.Date(), nullable=False),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["produtor_id"], ["produtores.id"], onupdate="CASCADE", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id_transacao"),
    )
    op.create_index("ix_transacoes_financeiras_data", "transacoes_financeiras", ["data"], unique=False)
    op.create_index("ix_transacoes_financeiras_produtor_id", "transacoes_financeiras", ["produtor_id"], unique=False)
    op.create_index("ix_transacoes_financeiras_comprador", "transacoes_financeiras", ["comprador"], unique=False)
    op.create_index("ix_transacoes_financeiras_status_pagamento", "transacoes_financeiras", ["status_pagamento"], unique=False)
    op.create_index("ix_transacoes_financeiras_data_vencimento", "transacoes_financeiras", ["data_vencimento"], unique=False)
    op.create_index("ix_transacoes_produtor_data", "transacoes_financeiras", ["produtor_id", "data"], unique=False)
    op.create_index("ix_transacoes_status_vencimento", "transacoes_financeiras", ["status_pagamento", "data_vencimento"], unique=False)

    op.create_table(
        "lotes",
        sa.Column("lote_id", sa.String(length=20), nullable=False),
        sa.Column("data_colheita", sa.Date(), nullable=False),
        sa.Column("data_entrega", sa.Date(), nullable=False),
        sa.Column("produtor_id", sa.String(length=10), nullable=False),
        sa.Column("produto", sa.String(length=80), nullable=False),
        sa.Column("quantidade_kg", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("comprador", sa.String(length=120), nullable=False),
        sa.Column("pedido_id", sa.String(length=30), nullable=False),
        sa.Column("temperatura_transporte_c", sa.String(length=20), nullable=False),
        sa.Column("validade", sa.Date(), nullable=False),
        sa.Column("inspecao_visual", sa.String(length=30), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["produtor_id"], ["produtores.id"], onupdate="CASCADE", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("lote_id"),
    )
    op.create_index("ix_lotes_data_entrega", "lotes", ["data_entrega"], unique=False)
    op.create_index("ix_lotes_produtor_id", "lotes", ["produtor_id"], unique=False)
    op.create_index("ix_lotes_produto", "lotes", ["produto"], unique=False)
    op.create_index("ix_lotes_comprador", "lotes", ["comprador"], unique=False)
    op.create_index("ix_lotes_pedido_id", "lotes", ["pedido_id"], unique=False)
    op.create_index("ix_lotes_produtor_entrega", "lotes", ["produtor_id", "data_entrega"], unique=False)


def downgrade() -> None:
    op.drop_table("lotes")
    op.drop_table("transacoes_financeiras")
    op.drop_table("pedidos")
    op.drop_table("sazonalidade")
    op.drop_table("precos")
    op.drop_table("produtores")

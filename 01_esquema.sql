-- Esquema do banco da Sabor da Terra (PostgreSQL). Gerado por sabor/banco.py.

DROP TABLE IF EXISTS lotes;
DROP TABLE IF EXISTS financeiro;
DROP TABLE IF EXISTS tabela_precos;
DROP TABLE IF EXISTS dim_produto;
DROP TABLE IF EXISTS restricoes_produtor;
DROP TABLE IF EXISTS produtores_produtos;
DROP TABLE IF EXISTS produtores;
DROP TABLE IF EXISTS pedidos;

CREATE TABLE produtores (
    id TEXT PRIMARY KEY,
    nome_completo TEXT NOT NULL,
    municipio TEXT,
    status TEXT,
    certificacao_organica_declarada TEXT,
    validade_certificacao DATE
);

CREATE TABLE produtores_produtos (
    produtor_id TEXT NOT NULL REFERENCES produtores(id),
    produto TEXT NOT NULL,
    PRIMARY KEY (produtor_id, produto)
);

CREATE TABLE restricoes_produtor (
    produtor_id TEXT PRIMARY KEY REFERENCES produtores(id),
    sie_situacao TEXT,
    sie_registro TEXT,
    dap_caf TEXT,
    venda_restrita TEXT,
    fonte TEXT
);

CREATE TABLE dim_produto (
    produto_canonico TEXT PRIMARY KEY,
    unidade_padrao TEXT,
    sinonimos TEXT,
    variantes TEXT
);

CREATE TABLE tabela_precos (
    produto TEXT PRIMARY KEY,
    unidade TEXT,
    preco_convencional NUMERIC(10,2),
    preco_organico NUMERIC(10,2),
    desconto_atacado_pct NUMERIC(5,2),
    volume_minimo_atacado_kg NUMERIC(10,2),
    observacao TEXT,
    produto_base TEXT,
    grade TEXT,
    produtor_ref TEXT,
    venda_direta_apenas BOOLEAN
);

CREATE TABLE financeiro (
    id_transacao TEXT PRIMARY KEY,
    data DATE NOT NULL,
    produtor_id TEXT NOT NULL REFERENCES produtores(id),
    produtor_nome TEXT,
    comprador TEXT,
    tipo TEXT,
    produto TEXT,
    quantidade NUMERIC(12,3),
    valor_unitario NUMERIC(12,2),
    valor_total NUMERIC(12,2) NOT NULL,
    forma_pagamento TEXT,
    status_pagamento TEXT NOT NULL CHECK (status_pagamento IN ('pago','pendente')),
    data_vencimento DATE,
    data_pagamento DATE,
    observacao TEXT,
    unidade TEXT
);

CREATE TABLE lotes (
    lote_id TEXT PRIMARY KEY,
    data_colheita DATE,
    data_entrega DATE,
    produtor_id TEXT NOT NULL REFERENCES produtores(id),
    produtor_nome TEXT,
    produto TEXT,
    quantidade NUMERIC(12,3),
    comprador TEXT,
    pedido_id_lote TEXT,
    validade DATE,
    inspecao_visual TEXT,
    observacao TEXT,
    unidade TEXT,
    temperatura_c NUMERIC(4,1),
    transporte TEXT
);

CREATE TABLE pedidos (
    id TEXT PRIMARY KEY,
    recebido_em TIMESTAMP NOT NULL,
    canal TEXT,
    comprador TEXT,
    itens TEXT,
    prazo_entrega DATE,
    urgencia TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    observacoes TEXT
);

CREATE INDEX idx_financeiro_produtor ON financeiro (produtor_id);
CREATE INDEX idx_financeiro_status ON financeiro (status_pagamento);
CREATE INDEX idx_lotes_produtor ON lotes (produtor_id);

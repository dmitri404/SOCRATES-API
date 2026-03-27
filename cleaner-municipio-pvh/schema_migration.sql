-- ================================================================
-- Migração: cleaner-municipio-pvh
-- Adiciona colunas de controle em pagamentos e cria pagamentos_treated
-- ================================================================

-- Colunas de controle do cleaner na tabela de origem
ALTER TABLE portal_municipio_pvh.pagamentos
    ADD COLUMN IF NOT EXISTS treatment      TEXT,
    ADD COLUMN IF NOT EXISTS treatment_time TIMESTAMPTZ;

-- Tabela de destino com campos extraídos do historico
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.pagamentos_treated (
    id                   INTEGER PRIMARY KEY,
    despesa_numero       TEXT,
    data_pagamento       DATE,
    liquidacao_numero    TEXT,
    pagamento_numero     TEXT,
    unidade_orcamentaria TEXT,
    valor                NUMERIC,
    favorecido_nome      TEXT,
    favorecido_cnpj      TEXT,
    historico            TEXT,
    -- campos extraídos
    nl_numero            TEXT,
    nf_numero            TEXT,
    nf_data              TEXT,
    mes_ref              TEXT,
    processo             TEXT,
    contrato             TEXT
);

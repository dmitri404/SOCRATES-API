-- ================================================================
-- Schema: portal_municipio_pvh
-- Portal da Transparencia de Porto Velho
-- API: https://api.portovelho.ro.gov.br/api/v1
-- ================================================================

CREATE SCHEMA IF NOT EXISTS portal_municipio_pvh;

-- ----------------------------------------------------------------
-- Configuracao do scraper
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.conf (
    id            SERIAL PRIMARY KEY,
    url_base      TEXT NOT NULL DEFAULT 'https://api.portovelho.ro.gov.br/api/v1',
    modo_limpar   BOOLEAN NOT NULL DEFAULT false,
    criado_em     TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- CPFs/CNPJs monitorados
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.conf_cpfs (
    id         SERIAL PRIMARY KEY,
    cpf        TEXT NOT NULL UNIQUE,
    nome       TEXT,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- E-mails para notificacao
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.conf_emails (
    id         SERIAL PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    nome       TEXT,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Exercicios monitorados
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.conf_exercicios (
    id         SERIAL PRIMARY KEY,
    exercicio  TEXT NOT NULL UNIQUE,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO portal_municipio_pvh.conf_exercicios (exercicio) VALUES ('2025')
ON CONFLICT (exercicio) DO NOTHING;
INSERT INTO portal_municipio_pvh.conf_exercicios (exercicio) VALUES ('2026')
ON CONFLICT (exercicio) DO NOTHING;

-- ----------------------------------------------------------------
-- Empenhos
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.empenhos (
    id               SERIAL PRIMARY KEY,
    api_id           TEXT NOT NULL UNIQUE,
    num_ne           TEXT,
    ano              INTEGER,
    data_empenho     DATE,
    tipo             TEXT,
    valor            NUMERIC,
    historico        TEXT,
    favorecido_nome  TEXT,
    favorecido_cnpj  TEXT,
    unidade_gestora  TEXT,
    orgao            TEXT,
    natureza         TEXT,
    processo_numero  TEXT,
    url              TEXT,
    criado_em        TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Pagamentos
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.pagamentos (
    id               SERIAL PRIMARY KEY,
    api_id           TEXT NOT NULL UNIQUE,
    num_pagamento    TEXT,
    ano              INTEGER,
    data_pagamento   DATE,
    tipo             TEXT,
    valor            NUMERIC,
    favorecido_nome  TEXT,
    favorecido_cnpj  TEXT,
    unidade_gestora  TEXT,
    orgao            TEXT,
    processo_numero  TEXT,
    criado_em        TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Log de execucoes
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.execucao_logs (
    id               SERIAL PRIMARY KEY,
    iniciado_em      TIMESTAMPTZ DEFAULT NOW(),
    finalizado_em    TIMESTAMPTZ,
    status           TEXT,
    exercicio        TEXT,
    empenhos_novos   INTEGER DEFAULT 0,
    pagamentos_novos INTEGER DEFAULT 0,
    mensagem         TEXT
);

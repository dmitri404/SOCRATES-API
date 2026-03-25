-- ================================================================
-- Schema: portal_municipio_pvh
-- Portal da Transparencia de Porto Velho
-- Portal: https://transparencia.portovelho.ro.gov.br/despesas/
-- ================================================================

CREATE SCHEMA IF NOT EXISTS portal_municipio_pvh;

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
-- Despesas (empenhos, liquidacoes, pagamentos unificados)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.despesas (
    id                   SERIAL PRIMARY KEY,
    exercicio            TEXT NOT NULL,
    data_despesa         DATE,
    numero               TEXT NOT NULL,
    fase                 TEXT NOT NULL,
    tipo                 TEXT,
    valor                NUMERIC,
    valor_liquidado      NUMERIC,
    valor_pago           NUMERIC,
    unidade_gestora      TEXT,
    orgao                TEXT,
    unidade_orcamentaria TEXT,
    processo_numero      TEXT,
    historico            TEXT,
    empenho_numero       TEXT,
    liquidacao_tipo      TEXT,
    liquidacao_numero    TEXT,
    classificacao_funcao TEXT,
    favorecido_nome      TEXT,
    favorecido_cnpj      TEXT,
    portal_uuid          TEXT UNIQUE,
    criado_em            TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (numero, fase)
);

-- ----------------------------------------------------------------
-- Pagamentos (vindos da pagina de detalhe de cada despesa)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_municipio_pvh.pagamentos (
    id                   SERIAL PRIMARY KEY,
    despesa_numero       TEXT,
    despesa_uuid         TEXT,
    data_pagamento       DATE,
    liquidacao_numero    TEXT,
    liquidacao_uuid      TEXT,
    pagamento_numero     TEXT,
    pagamento_uuid       TEXT UNIQUE,
    especie              TEXT,
    tipo                 TEXT,
    unidade_orcamentaria TEXT,
    valor                NUMERIC,
    favorecido_nome      TEXT,
    favorecido_cnpj      TEXT,
    historico            TEXT,
    criado_em            TIMESTAMPTZ DEFAULT NOW()
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
    cpf              TEXT,
    despesas_novas   INTEGER DEFAULT 0,
    pagamentos_novos INTEGER DEFAULT 0,
    mensagem         TEXT
);

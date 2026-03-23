-- ================================================================
-- Schema: portal_estado_ms
-- Portal da Transparencia de Mato Grosso do Sul
-- API REST: https://gw.sgi.ms.gov.br/d0146/transpdespesas/v1/
-- ================================================================

CREATE SCHEMA IF NOT EXISTS portal_estado_ms;

-- ----------------------------------------------------------------
-- Configuracao do scraper
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ms.conf (
    id            SERIAL PRIMARY KEY,
    chave         TEXT NOT NULL UNIQUE,
    valor         TEXT,
    descricao     TEXT,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO portal_estado_ms.conf (chave, valor, descricao) VALUES
    ('mes_inicio',   '1',    'Mes inicial (inteiro)'),
    ('mes_fim',      '12',   'Mes final (inteiro)'),
    ('pagesize',     '100',  'Tamanho de pagina nas requisicoes'),
    ('t_sleep',      '1.0',  'Pausa entre requisicoes em segundos')
ON CONFLICT (chave) DO NOTHING;

-- ----------------------------------------------------------------
-- Empenhos (NE)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ms.empenhos (
    id                   SERIAL PRIMARY KEY,
    exercicio            TEXT,
    mes                  TEXT,
    num_ne               TEXT,
    data_empenho         TEXT,
    num_processo         TEXT,
    ug_nome              TEXT,
    ug_codigo            TEXT,
    credor_nome          TEXT,
    projeto_atividade    TEXT,
    programa             TEXT,
    funcao               TEXT,
    fonte_recursos       TEXT,
    natureza_despesa     TEXT,
    elemento_despesa_id  TEXT,
    empenhado            NUMERIC,
    liquidado            NUMERIC,
    pago                 NUMERIC,
    criado_em            TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS empenhos_ne_ug_idx
    ON portal_estado_ms.empenhos (num_ne, ug_codigo)
    WHERE num_ne IS NOT NULL AND ug_codigo IS NOT NULL;

-- ----------------------------------------------------------------
-- Documentos do empenho (EMPENHO, VLR. LIQ., VLR. PAGO)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ms.ne_documentos (
    id      SERIAL PRIMARY KEY,
    num_ne  TEXT,
    documento   TEXT,
    descricao   TEXT,
    tipo        TEXT,
    data        TEXT,
    valor       NUMERIC,
    criado_em   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ne_documentos_num_ne_idx
    ON portal_estado_ms.ne_documentos (num_ne);

-- ----------------------------------------------------------------
-- CPFs/CNPJs monitorados
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ms.conf_cpfs (
    id         SERIAL PRIMARY KEY,
    cpf        TEXT NOT NULL UNIQUE,
    nome       TEXT,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- E-mails para notificacao
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ms.conf_emails (
    id         SERIAL PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    nome       TEXT,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Exercicios monitorados
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ms.conf_exercicios (
    id         SERIAL PRIMARY KEY,
    exercicio  TEXT NOT NULL UNIQUE,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO portal_estado_ms.conf_exercicios (exercicio) VALUES ('2026')
ON CONFLICT (exercicio) DO NOTHING;

-- ----------------------------------------------------------------
-- Log de execucoes
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ms.execucao_logs (
    id             SERIAL PRIMARY KEY,
    iniciado_em    TIMESTAMPTZ DEFAULT NOW(),
    finalizado_em  TIMESTAMPTZ,
    status         TEXT,           -- 'executando', 'sucesso', 'erro'
    exercicio      TEXT,
    mes            TEXT,
    empenhos_novos INTEGER DEFAULT 0,
    mensagem       TEXT
);

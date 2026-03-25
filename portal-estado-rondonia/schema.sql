-- ================================================================
-- Schema: portal_estado_ro
-- Portal da Transparencia de Rondonia
-- API: https://transparencia.ro.gov.br/Despesa/FiltrarEmpenhos
-- ================================================================

CREATE SCHEMA IF NOT EXISTS portal_estado_ro;

-- ----------------------------------------------------------------
-- Configuracao do scraper
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ro.conf (
    id            SERIAL PRIMARY KEY,
    url_base      TEXT,
    modo_limpar   BOOLEAN NOT NULL DEFAULT false,
    criado_em     TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- CPFs/CNPJs monitorados
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ro.conf_cpfs (
    id         SERIAL PRIMARY KEY,
    cpf        TEXT NOT NULL UNIQUE,
    nome       TEXT,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- E-mails para notificacao
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ro.conf_emails (
    id         SERIAL PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    nome       TEXT,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Exercicios monitorados
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ro.conf_exercicios (
    id         SERIAL PRIMARY KEY,
    exercicio  TEXT NOT NULL UNIQUE,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO portal_estado_ro.conf_exercicios (exercicio) VALUES ('2026')
ON CONFLICT (exercicio) DO NOTHING;

-- ----------------------------------------------------------------
-- Empenhos
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ro.empenhos (
    id               SERIAL PRIMARY KEY,
    exercicio        TEXT,
    num_ne           TEXT,
    data_empenho     TEXT,
    unidade_gestora  TEXT,
    credor           TEXT,
    valor_empenhado  NUMERIC,
    valor_pago       NUMERIC,
    portal_id        INTEGER,
    criado_em        TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS empenhos_ne_exercicio_idx
    ON portal_estado_ro.empenhos (num_ne, exercicio)
    WHERE num_ne IS NOT NULL AND exercicio IS NOT NULL;

-- ----------------------------------------------------------------
-- Detalhes dos empenhos (pagina de detalhe do portal)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ro.empenhos_detalhes (
    id                               SERIAL PRIMARY KEY,
    num_ne                           TEXT NOT NULL,
    exercicio                        TEXT NOT NULL,
    portal_id                        INTEGER,
    historico                        TEXT,
    modalidade_licitacao             TEXT,
    secretaria                       TEXT,
    tipo_empenho                     TEXT,
    funcao                           TEXT,
    subfuncao                        TEXT,
    programa_governo                 TEXT,
    acao_governo                     TEXT,
    fonte_recurso                    TEXT,
    valor_empenhado_final            NUMERIC,
    valor_pago_exercicio             NUMERIC,
    valor_pago_anos_posteriores      NUMERIC,
    valor_liquidado_exercicio        NUMERIC,
    valor_liquidado_anos_posteriores NUMERIC,
    criado_em                        TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS empenhos_detalhes_ne_exercicio_idx
    ON portal_estado_ro.empenhos_detalhes (num_ne, exercicio);

-- ----------------------------------------------------------------
-- Log de execucoes
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_ro.execucao_logs (
    id               SERIAL PRIMARY KEY,
    iniciado_em      TIMESTAMPTZ DEFAULT NOW(),
    finalizado_em    TIMESTAMPTZ,
    status           TEXT,           -- 'executando', 'sucesso', 'erro'
    exercicio        TEXT,
    mes              TEXT,
    empenhos_novos   INTEGER DEFAULT 0,
    documentos_novos INTEGER DEFAULT 0,
    mensagem         TEXT
);

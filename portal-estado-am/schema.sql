-- ================================================================
-- Schema: portal_estado_am
-- Portal da Transparência Fiscal do Amazonas (SEFAZ AM)
-- ================================================================

CREATE SCHEMA IF NOT EXISTS portal_estado_am;

-- ----------------------------------------------------------------
-- Configuração do scraper
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_am.conf (
    id              SERIAL PRIMARY KEY,
    chave           TEXT NOT NULL UNIQUE,
    valor           TEXT,
    descricao       TEXT,
    atualizado_em   TIMESTAMPTZ DEFAULT NOW()
);

-- Valores padrão
INSERT INTO portal_estado_am.conf (chave, valor, descricao) VALUES
    ('cnpj',         '03211236000165',       'CNPJ do credor a pesquisar'),
    ('credor_texto', 'IIN TECNOLOGIAS',      'Texto do credor para seleção'),
    ('exercicios',   '2025,2026',            'Lista de exercícios separados por vírgula'),
    ('mes_inicio',   '01',                   'Mês de início para o exercício atual'),
    ('mes_fim',      '12',                   'Mês de fim para o exercício atual'),
    ('headless',     'true',                 'Rodar browser em modo headless'),
    ('t_render',     '4.0',                  'Tempo de espera React renderizar (segundos)'),
    ('t_pesq',       '7.0',                  'Tempo de espera resultado pesquisa (segundos)'),
    ('t_modal',      '5.0',                  'Tempo de espera modal abrir (segundos)'),
    ('t_fechar',     '2.0',                  'Tempo de espera após fechar modal (segundos)')
ON CONFLICT (chave) DO NOTHING;

-- ----------------------------------------------------------------
-- Pagamentos (Planilha 1)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_am.pagamentos (
    id                      SERIAL PRIMARY KEY,
    exercicio               TEXT,
    mes                     TEXT,
    orgao                   TEXT,
    credor                  TEXT,
    data                    TEXT,
    num_ob                  TEXT,
    num_nl                  TEXT,
    num_ne                  TEXT,
    fr                      TEXT,
    classificacao           TEXT,
    pago_exercicio          TEXT,
    pago_exercicio_anterior TEXT,
    ug_ob                   TEXT,
    valor_ob                TEXT,
    credor_ob               TEXT,
    descricao_ob            TEXT,
    criado_em               TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS pagamentos_num_ob_idx
    ON portal_estado_am.pagamentos (num_ob)
    WHERE num_ob IS NOT NULL AND num_ob <> '';

-- ----------------------------------------------------------------
-- NL / Itens de Empenho (Planilha 2)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_am.nl_itens (
    id                  SERIAL PRIMARY KEY,
    exercicio           TEXT,
    mes                 TEXT,
    orgao               TEXT,
    num_nl              TEXT,
    -- NL
    data_nl             TEXT,
    valor_nl            TEXT,
    credor_nl           TEXT,
    natureza_nl         TEXT,
    fonte_nl            TEXT,
    descricao_nl        TEXT,
    -- NE
    ug_ne               TEXT,
    num_empenho         TEXT,
    data_ne             TEXT,
    valor_ne            TEXT,
    credor_ne           TEXT,
    unid_orcamentaria   TEXT,
    natureza_ne         TEXT,
    fonte_ne            TEXT,
    descricao_ne        TEXT,
    -- Cronograma mensal NE
    cron_jan            TEXT,
    cron_fev            TEXT,
    cron_mar            TEXT,
    cron_abr            TEXT,
    cron_mai            TEXT,
    cron_jun            TEXT,
    cron_jul            TEXT,
    cron_ago            TEXT,
    cron_set            TEXT,
    cron_out            TEXT,
    cron_nov            TEXT,
    cron_dez            TEXT,
    -- Item
    un_item             TEXT,
    descricao_item      TEXT,
    qtde                TEXT,
    valor_un            TEXT,
    valor_total         TEXT,
    criado_em           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS nl_itens_num_nl_idx
    ON portal_estado_am.nl_itens (num_nl);

-- ----------------------------------------------------------------
-- CPFs/CNPJs monitorados
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_am.conf_cpfs (
    id         SERIAL PRIMARY KEY,
    cpf        TEXT NOT NULL UNIQUE,
    nome       TEXT,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- E-mails para notificacao
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_am.conf_emails (
    id         SERIAL PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    nome       TEXT,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------
-- Exercicios monitorados
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_am.conf_exercicios (
    id         SERIAL PRIMARY KEY,
    exercicio  TEXT NOT NULL UNIQUE,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    criado_em  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO portal_estado_am.conf_exercicios (exercicio) VALUES ('2025'), ('2026')
ON CONFLICT (exercicio) DO NOTHING;

-- ----------------------------------------------------------------
-- Log de execuções
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portal_estado_am.execucao_logs (
    id                  SERIAL PRIMARY KEY,
    iniciado_em         TIMESTAMPTZ DEFAULT NOW(),
    finalizado_em       TIMESTAMPTZ,
    status              TEXT,           -- 'executando', 'sucesso', 'erro'
    exercicio           TEXT,
    mes                 TEXT,
    pagamentos_novos    INTEGER DEFAULT 0,
    nl_itens_novos      INTEGER DEFAULT 0,
    mensagem            TEXT
);

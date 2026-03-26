-- ============================================================
-- SCHEMA RBAC — Sistema Socrates
-- ============================================================

CREATE SCHEMA IF NOT EXISTS rbac;

-- 1. ROLES
CREATE TABLE IF NOT EXISTS rbac.roles (
    id        SMALLINT PRIMARY KEY,
    nome      TEXT NOT NULL UNIQUE,
    descricao TEXT
);

INSERT INTO rbac.roles (id, nome, descricao) VALUES
    (1, 'admin',      'Gestão total: usuários, portais, configurações globais'),
    (2, 'supervisor', 'Gestão de usuários e portais atribuídos'),
    (3, 'usuario',    'Acesso operacional nos portais atribuídos')
ON CONFLICT (id) DO NOTHING;


-- 2. PORTAIS
CREATE TABLE IF NOT EXISTS rbac.portais (
    id        SERIAL PRIMARY KEY,
    slug      TEXT NOT NULL UNIQUE,
    nome      TEXT NOT NULL,
    schema_bd TEXT NOT NULL,
    ativo     BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO rbac.portais (slug, nome, schema_bd) VALUES
    ('municipal',     'Portal Municipal Manaus',      'public'),
    ('estado-am',     'Portal Estado AM',             'portal_estado_am'),
    ('municipio-pvh', 'Portal Município Porto Velho', 'portal_municipio_pvh'),
    ('estado-ms',     'Portal Estado MS',             'portal_estado_ms'),
    ('estado-ro',     'Portal Estado RO',             'portal_estado_ro')
ON CONFLICT (slug) DO NOTHING;


-- 3. USUÁRIOS
CREATE TABLE IF NOT EXISTS rbac.usuarios (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario       TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    nome          TEXT NOT NULL,
    senha_hash    TEXT NOT NULL,
    role_id       SMALLINT NOT NULL REFERENCES rbac.roles(id),
    ativo         BOOLEAN NOT NULL DEFAULT TRUE,
    senha_temp    BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultimo_login  TIMESTAMPTZ,
    criado_por    UUID REFERENCES rbac.usuarios(id)
);

CREATE INDEX IF NOT EXISTS idx_usuarios_email
    ON rbac.usuarios(email) WHERE ativo = TRUE;


-- 4. ATRIBUIÇÃO USUÁRIO → PORTAL
CREATE TABLE IF NOT EXISTS rbac.usuario_portais (
    id            SERIAL PRIMARY KEY,
    usuario_id    UUID NOT NULL REFERENCES rbac.usuarios(id) ON DELETE CASCADE,
    portal_id     INT  NOT NULL REFERENCES rbac.portais(id)  ON DELETE CASCADE,
    pode_editar   BOOLEAN NOT NULL DEFAULT TRUE,
    atribuido_em  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atribuido_por UUID REFERENCES rbac.usuarios(id),
    UNIQUE (usuario_id, portal_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_portais_usuario
    ON rbac.usuario_portais(usuario_id);


-- 5. SESSÕES
CREATE TABLE IF NOT EXISTS rbac.sessoes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id  UUID NOT NULL REFERENCES rbac.usuarios(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    ip_origem   INET,
    user_agent  TEXT,
    criada_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_em   TIMESTAMPTZ NOT NULL,
    revogada_em TIMESTAMPTZ,
    ultimo_uso  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessoes_token_hash
    ON rbac.sessoes(token_hash) WHERE revogada_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_sessoes_expira
    ON rbac.sessoes(expira_em) WHERE revogada_em IS NULL;


-- 6. AUDIT LOG
CREATE TABLE IF NOT EXISTS rbac.audit_log (
    id          BIGSERIAL PRIMARY KEY,
    usuario_id  UUID REFERENCES rbac.usuarios(id),
    acao        TEXT NOT NULL,
    portal_slug TEXT,
    payload     JSONB,
    ip_origem   INET,
    resultado   TEXT NOT NULL,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_usuario
    ON rbac.audit_log(usuario_id, criado_em DESC);

CREATE INDEX IF NOT EXISTS idx_audit_portal
    ON rbac.audit_log(portal_slug, criado_em DESC);


-- 7. FUNÇÃO: verifica acesso de usuário a portal
CREATE OR REPLACE FUNCTION rbac.tem_acesso(
    p_usuario_id    UUID,
    p_portal_slug   TEXT,
    p_requer_edicao BOOLEAN DEFAULT FALSE
)
RETURNS BOOLEAN
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM rbac.usuarios u
        WHERE u.id = p_usuario_id AND u.role_id = 1 AND u.ativo = TRUE

        UNION ALL

        SELECT 1
        FROM rbac.usuario_portais up
        JOIN rbac.usuarios u ON u.id = up.usuario_id
        JOIN rbac.portais  p ON p.id = up.portal_id
        WHERE up.usuario_id = p_usuario_id
          AND p.slug        = p_portal_slug
          AND u.ativo       = TRUE
          AND (NOT p_requer_edicao OR up.pode_editar = TRUE)
    )
$$;


-- 8. TRIGGER: atualiza atualizado_em
CREATE OR REPLACE FUNCTION rbac._set_atualizado_em()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_usuarios_atualizado_em ON rbac.usuarios;
CREATE TRIGGER trg_usuarios_atualizado_em
    BEFORE UPDATE ON rbac.usuarios
    FOR EACH ROW EXECUTE FUNCTION rbac._set_atualizado_em();

# SOCRATES

Sistema integrado de monitoramento, captura e gestão de dados de transparência governamental.

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Portais Monitorados](#3-portais-monitorados)
4. [Interface Web](#4-interface-web)
5. [Autenticação e Controle de Acesso (RBAC)](#5-autenticação-e-controle-de-acesso-rbac)
6. [Agendamento e Disparo](#6-agendamento-e-disparo)
7. [Guia de Deploy](#7-guia-de-deploy)
8. [Estrutura do Repositório](#8-estrutura-do-repositório)

---

## 1. Visão Geral

O SOCRATES automatiza a coleta de dados de pagamentos e empenhos em portais de transparência governamental, armazena as informações em banco de dados estruturado e disponibiliza uma interface web administrativa para gestão completa do sistema.

| Problema | Solução |
|---|---|
| Dados de pagamentos dispersos em portais públicos | Scrapers automatizados coletam e estruturam os dados |
| Múltiplos portais com schemas distintos | Cada portal tem seu próprio schema, router e configuração independente |
| Ausência de controle de acesso | RBAC com JWT, roles e atribuição de portais por usuário |
| Configuração manual via banco de dados | Interface web para gerenciar credores, e-mails, exercícios e agendamentos |
| Sem visibilidade operacional | Dashboard com saúde da VPS e status das últimas execuções |

---

## 2. Arquitetura

### Stack

| Camada | Tecnologia |
|---|---|
| Banco de Dados | PostgreSQL 15 via Supabase self-hosted |
| API | FastAPI + Uvicorn (porta 9000, exposta via Nginx) |
| Frontend | React + Vite + TypeScript + Tailwind CSS v4 |
| Proxy Reverso | Nginx (porta 80) |
| Scraping | Playwright (Chromium headless) |
| Infraestrutura | Docker + Docker Compose (VPS 187.77.240.80) |

### Diagrama

```
  Navegador
      │  HTTP :80
      ▼
  ┌─────────────────────────────┐
  │  Nginx                      │
  │  /          → /var/www/socrates (React SPA)
  │  /api/      → localhost:9000 (portal-api)
  └─────────────────────────────┘
                │
                ▼
  ┌─────────────────────────────────────────────────┐
  │  portal-api (FastAPI)                           │
  │                                                 │
  │  /auth/*        JWT login, logout, me           │
  │  /admin/*       Usuários, portais, saúde VPS    │
  │  /conf/{portal} Geral, credores, emails,        │
  │                 exercícios, cron                │
  │  /{portal}/trigger  Disparo manual scraper      │
  └──────────────────────┬──────────────────────────┘
                         │ psycopg2
                         ▼
  ┌─────────────────────────────────────────────────┐
  │  PostgreSQL 15 (supabase-db)                    │
  │                                                 │
  │  rbac.*              Usuários, roles, sessões   │
  │  public.*            Portal Municipal Manaus    │
  │  portal_estado_am.*  Portal Estado AM           │
  │  portal_municipio_pvh.*  Portal PVH             │
  │  portal_estado_ms.*  Portal Estado MS           │
  │  portal_estado_ro.*  Portal Estado RO           │
  └─────────────────────────────────────────────────┘
```

### Containers Docker

| Container | Função | Restart |
|---|---|---|
| `portal-api` | API HTTP + proxy para scrapers | `unless-stopped` |
| `portal-municipal-mao` | Scraper SEFAZ Municipal Manaus | `no` (cron/trigger) |
| `portal-estado-am` | Scraper SEFAZ Estadual AM | `no` (cron/trigger) |
| `portal-municipio-pvh` | Scraper Portal Porto Velho | `no` (cron/trigger) |
| `portal-estado-ms` | Scraper Portal Estado MS | `no` (cron/trigger) |
| `portal-estado-ro` | Scraper Portal Estado RO | `no` (cron/trigger) |
| `portal-cleaner` | ETL `public.pagamentos` | `no` (cron) |
| `portal-cleaner-estado-am` | ETL `portal_estado_am.pagamentos` | `no` (cron) |

---

## 3. Portais Monitorados

| Slug | Nome | Schema BD | Cron Padrão |
|---|---|---|---|
| `municipal` | Portal Municipal Manaus | `public` | 20:15 dias úteis |
| `estado-am` | Portal Estado AM | `portal_estado_am` | 20:30 dias úteis |
| `municipio-pvh` | Portal Município Porto Velho | `portal_municipio_pvh` | 19:00 dias úteis |
| `estado-ms` | Portal Estado MS | `portal_estado_ms` | 19:00 dias úteis |
| `estado-ro` | Portal Estado RO | `portal_estado_ro` | 20:20 dias úteis |

Cada portal possui as tabelas: `conf`, `conf_cpfs`, `conf_emails`, `conf_exercicios`.

---

## 4. Interface Web

Acesso: **http://187.77.240.80**

### Funcionalidades por área

**Dashboard**
- Cards de saúde da VPS: RAM, disco, CPU load, uptime, PostgreSQL
- Tabela de última execução de cada scraper (data, duração, status)
- Atualização automática a cada 5 minutos

**Portais** (`/portais/{slug}`)

| Aba | Descrição |
|---|---|
| Geral | URL base e modo limpeza |
| Credores | CPFs/CNPJs monitorados com toggle ativo/inativo |
| E-mails | Destinatários do relatório de conclusão |
| Exercícios | Anos fiscais monitorados |
| Cron | Agendamento visual (dias da semana + horário) |
| Power BI | Dashboard embarcado (Portal Municipal) |
| Executar | Disparo manual do scraper |

**Admin → Usuários**
- Listagem com role, portais, último acesso, status
- Criar, editar, ativar/desativar usuários
- Atribuir portais com controle de permissão de edição
- Resetar senha (gera senha temporária exibida ao admin)

**Perfil**
- Troca de senha obrigatória quando `senha_temp = true`

---

## 5. Autenticação e Controle de Acesso (RBAC)

### Roles

| Role | Permissões |
|---|---|
| `admin` | Acesso total: todos os portais, gestão de usuários |
| `supervisor` | Gestão de usuários com role `usuario`, portais atribuídos |
| `usuario` | Acesso operacional nos portais atribuídos |

### Fluxo de autenticação

```
1. POST /auth/login → valida usuário/senha bcrypt → gera JWT
2. JWT é armazenado no localStorage (Zustand persist)
3. Todas as requisições enviam Authorization: Bearer <token>
4. Sessão registrada em rbac.sessoes com hash SHA-256
5. /auth/me retorna dados frescos (portais, role) a cada abertura do app
6. POST /auth/logout revoga a sessão no banco
```

### Schema RBAC (PostgreSQL)

```
rbac.roles           — admin (1), supervisor (2), usuario (3)
rbac.portais         — slugs dos portais ativos
rbac.usuarios        — credenciais, role, senha_temp
rbac.usuario_portais — atribuição usuário × portal × pode_editar
rbac.sessoes         — tokens ativos com expiração
rbac.audit_log       — log de login/logout
```

---

## 6. Agendamento e Disparo

### Crontab atual (`/var/spool/cron/crontabs/root`)

```
15 20 * * 1-5  portal-municipal-mao  &&  cleaner
30 20 * * 1-5  portal-estado-am      &&  cleaner-estado-am
00 19 * * 1-5  portal-municipio-pvh
00 19 * * 1-5  portal-estado-ms
20 20 * * 1-5  portal-estado-ro
```

O agendamento pode ser editado pela interface web (aba **Cron** de cada portal) sem acesso direto ao servidor.

### Disparo manual

Via interface web (aba **Executar** do portal ou botão no Dashboard):
- Verifica se o container já está rodando antes de disparar
- Redireciona a saída para o arquivo de log correspondente
- Resposta imediata; resultado chega por e-mail ao concluir

---

## 7. Guia de Deploy

### Variáveis de Ambiente — `portal-api`

| Variável | Descrição |
|---|---|
| `DB_HOST` | Host PostgreSQL interno (`supabase-db`) |
| `DB_PORT` | Porta PostgreSQL (`5432`) |
| `DB_NAME` | Nome do banco (`postgres`) |
| `DB_USER` | Usuário do banco |
| `DB_PASSWORD` | Senha do banco |
| `JWT_SECRET` | Chave secreta para assinatura JWT |
| `JWT_EXPIRY_HOURS` | Validade do token em horas (padrão: `8`) |
| `API_KEY_PORTAL_MUNICIPAL_MANAUS` | Chave legada — portal municipal |
| `API_KEY_PORTAL_ESTADO_AM` | Chave legada — portal estado AM |
| `API_KEY_PORTAL_ESTADO_MS` | Chave legada — portal estado MS |
| `API_KEY_PORTAL_ESTADO_RO` | Chave legada — portal estado RO |

### Volumes montados na `portal-api`

| Volume | Finalidade |
|---|---|
| `/var/spool/cron/crontabs` | Leitura e escrita do crontab via interface web |
| `/var/run/docker.sock` | Comunicação com o daemon Docker |
| `/usr/bin/docker` | CLI Docker do host |
| `/usr/libexec/docker/cli-plugins` | Plugin `docker compose` |
| `/opt/portal` | Acesso ao `docker-compose.yml` para `docker compose run` |

### Comandos de deploy

```bash
# Atualizar código
cd /opt/portal
git pull

# Reconstruir e reiniciar a API
docker compose up -d --build api

# Reconstruir o frontend
cd web
npm install
npm run build
cp -r dist/* /var/www/socrates/

# Ver logs da API
docker compose logs -f portal-api

# Executar scraper manualmente
docker compose run --rm portal-municipal-mao
```

### Nginx (`/etc/nginx/sites-available/socrates`)

```nginx
server {
    listen 80 default_server;
    root /var/www/socrates;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        proxy_pass http://127.0.0.1:9000/;
        proxy_read_timeout 300;
    }

    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

---

## 8. Estrutura do Repositório

```
SOCRATES/
├── main.py                        # Entry point FastAPI
├── auth.py                        # Validação de API keys (legado)
├── Dockerfile                     # Build da portal-api
├── docker-compose.yml             # Orquestração completa
│
├── routers/
│   ├── auth_rbac.py               # JWT: login, logout, me, alterar-senha
│   ├── admin.py                   # Usuários, portais, saúde VPS
│   ├── conf.py                    # Configurações por portal (geral, credores, emails, exercícios, cron)
│   ├── trigger.py                 # Disparo manual de scrapers
│   ├── portal_municipal_manaus.py # Router faturamento municipal
│   ├── portal_estado_am.py        # Router faturamento estado AM
│   ├── portal_estado_ms.py        # Router faturamento estado MS
│   └── portal_estado_ro.py        # Router faturamento estado RO
│
├── rbac/
│   └── schema.sql                 # DDL completo do schema RBAC
│
├── web/                           # Frontend React
│   ├── src/
│   │   ├── api/                   # Clientes HTTP (auth, conf, admin)
│   │   ├── layouts/AppLayout.tsx  # Sidebar + navegação
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx      # Saúde VPS + últimas execuções
│   │   │   ├── Perfil.tsx
│   │   │   ├── admin/Usuarios.tsx # CRUD de usuários
│   │   │   └── portais/           # Abas por portal
│   │   ├── store/auth.ts          # Zustand: token + user
│   │   └── router.tsx             # React Router + guards
│   └── public/logo.png
│
├── portal-municipio-mao/          # Scraper Municipal Manaus
├── portal-estado-am/              # Scraper Estadual AM
├── portal-municipio-pvh/          # Scraper Municipal Porto Velho
├── portal-estado-ms/              # Scraper Estadual MS
├── portal-estado-ro/              # Scraper Estadual RO
├── cleaner/                       # ETL public.pagamentos
└── cleaner-estado-am/             # ETL portal_estado_am.pagamentos
```

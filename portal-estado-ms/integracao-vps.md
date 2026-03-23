# Integracao com PROJETO-SOCRATES-VPS

## Diferenca em relacao ao portal-estado-am

Este scraper **nao usa Playwright**. O Portal MS expoe uma API REST autenticada
via OAuth2 (`client_credentials`). As credenciais estao no JavaScript publico do
portal e sao as mesmas que o proprio site usa no browser.

- Auth:    `https://id.ms.gov.br/auth/realms/ms/protocol/openid-connect/token`
- Gateway: `https://gw.sgi.ms.gov.br/d0146/transpdespesas/v1/`
- Token expira em 5 min; o scraper renova automaticamente a cada 4 min.

---

## Estrutura criada

```
portal-estado-ms/
├── Dockerfile                  # python:3.12-slim (sem Playwright)
├── requirements.txt            # requests + psycopg2-binary
├── main.py                     # Scraper via API REST
├── schema.sql                  # Schema PostgreSQL portal_estado_ms
├── docker-compose.snippet.yml  # Trecho a adicionar no docker-compose.yml do VPS
└── integracao-vps.md           # Este arquivo

routers/portal_estado_ms.py     # Router FastAPI (ja criado em routers/)
auth.py                         # Ja atualizado com portal_estado_ms
main.py (raiz)                  # Ja atualizado com include_router
routers/trigger.py              # Ja atualizado com /portal-estado-ms/trigger
docker-compose.yml              # Ja atualizado com servico portal-estado-ms
```

---

## Passo 1 — Aplicar schema no Supabase

No psql ou na interface do Supabase:
```sql
\i portal-estado-ms/schema.sql
```

---

## Passo 2 — Build e teste

```bash
# Na pasta PROJETO-SOCRATES-VPS:
docker compose build portal-estado-ms
docker compose run --rm portal-estado-ms

# Verificar logs:
docker compose logs portal-estado-ms
```

---

## Passo 3 — Teste da API

```bash
# Resumo
curl -H "x-api-key: estms-7f3c91a2b84d5e6f019c237ab8d4e15f" \
  http://localhost:9000/portal-estado-ms/resumo

# Empenhos
curl -H "x-api-key: estms-7f3c91a2b84d5e6f019c237ab8d4e15f" \
  "http://localhost:9000/portal-estado-ms/empenhos?exercicio=2026"
```

---

## Agendamento (cron no host)

```bash
# /etc/cron.d/portal-estado-ms
# Rodar todo dia as 07:00 (horario Campo Grande = UTC-4)
0 7 * * * root cd /opt/portal && docker compose run --rm portal-estado-ms
```

---

## Endpoints da API

| Metodo | Endpoint                               | Descricao                   |
|--------|----------------------------------------|-----------------------------|
| GET    | `/portal-estado-ms/resumo`             | Totais e estatisticas       |
| GET    | `/portal-estado-ms/empenhos`           | Lista empenhos (NE)         |
| GET    | `/portal-estado-ms/ne-documentos`      | Documentos por NE           |
| GET    | `/portal-estado-ms/logs`               | Logs de execucao            |
| GET    | `/portal-estado-ms/conf`               | Configuracao atual          |
| PUT    | `/portal-estado-ms/conf/{chave}`       | Atualizar configuracao      |
| POST   | `/portal-estado-ms/trigger`            | Disparar scraper manualmente|

### Query params disponiveis

`/empenhos`: `exercicio`, `mes`, `num_ne`, `ug_nome`, `num_processo`, `limit`, `offset`
`/ne-documentos`: `num_ne`, `tipo`, `limit`, `offset`

---

## Chaves de configuracao (tabela portal_estado_ms.conf)

| Chave        | Padrao           | Descricao                                  |
|--------------|------------------|--------------------------------------------|
| credor_nome  | IIN TECNOLOGIAS  | Texto parcial do credor para busca na API  |
| exercicios   | 2026             | Exercicios separados por virgula           |
| mes_inicio   | 1                | Mes inicial                                |
| mes_fim      | 12               | Mes final                                  |
| pagesize     | 100              | Tamanho de pagina nas requisicoes          |
| t_sleep      | 1.0              | Pausa entre requisicoes (segundos)         |

Alterar sem rebuild:
```bash
curl -X PUT -H "x-api-key: estms-7f3c91a2b84d5e6f019c237ab8d4e15f" \
  "http://localhost:9000/portal-estado-ms/conf/mes_fim?valor=06"
```

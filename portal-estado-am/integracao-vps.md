# Integração com PROJETO-SOCRATES-VPS

## Estrutura criada

```
portal-estado-am/
├── Dockerfile                  # Container do scraper (Playwright)
├── requirements.txt            # playwright + psycopg2-binary
├── main.py                     # Scraper refatorado (DB em vez de Excel)
├── schema.sql                  # Schema PostgreSQL portal_estado_am
├── api_router.py               # Router FastAPI (copiar para api/routers/)
└── docker-compose.snippet.yml  # Trecho a adicionar no docker-compose.yml do VPS
```

---

## Passo 1 — Copiar pasta para o VPS

```bash
cp -r portal-estado-am/ /caminho/PROJETO-SOCRATES-VPS/portal-estado-am
cp portal-estado-am/api_router.py /caminho/PROJETO-SOCRATES-VPS/api/routers/portal_estado_am.py
```

---

## Passo 2 — Aplicar schema no Supabase

No psql ou na interface do Supabase:
```sql
\i portal-estado-am/schema.sql
```

---

## Passo 3 — Atualizar api/main.py

Adicionar o import e include_router:

```python
from routers import portal_estado_am

app.include_router(portal_estado_am.router)
```

---

## Passo 4 — Atualizar api/auth.py

Adicionar a chave no dicionário `API_KEYS`:

```python
API_KEYS = {
    "aristoteles": os.environ.get("API_KEY_ARISTOTELES", ""),
    "portal-estado-am": os.environ.get("API_KEY_PORTAL_ESTADO_AM", ""),
}
```

---

## Passo 5 — Atualizar docker-compose.yml

Ver `docker-compose.snippet.yml` — adicionar:
- Serviço `portal-estado-am`
- Variável `API_KEY_PORTAL_ESTADO_AM` no serviço `api`

---

## Passo 6 — Build e teste

```bash
# Na pasta PROJETO-SOCRATES-VPS:
docker compose build portal-estado-am
docker compose run --rm portal-estado-am

# Verificar logs:
docker compose logs portal-estado-am

# Teste da API:
curl -H "x-api-key: pea-xxx" http://localhost:9000/portal-estado-am/resumo
```

---

## Agendamento (cron)

Como `restart: no`, o container é iniciado via cron no host:

```bash
# /etc/cron.d/portal-estado-am
# Rodar todo dia às 06:00 (horário Manaus)
0 6 * * * root cd /caminho/PROJETO-SOCRATES-VPS && docker compose run --rm portal-estado-am
```

---

## Endpoints da API

| Método | Endpoint                              | Descrição               |
|--------|---------------------------------------|-------------------------|
| GET    | `/portal-estado-am/resumo`            | Totais e estatísticas   |
| GET    | `/portal-estado-am/pagamentos`        | Lista pagamentos (OBs)  |
| GET    | `/portal-estado-am/nl-itens`          | Lista NLs e itens NE    |
| GET    | `/portal-estado-am/logs`              | Logs de execução        |
| GET    | `/portal-estado-am/conf`              | Configuração atual      |
| PUT    | `/portal-estado-am/conf/{chave}`      | Atualizar configuração  |

### Query params disponíveis

`/pagamentos`: `exercicio`, `mes`, `orgao`, `num_ob`, `limit`, `offset`
`/nl-itens`: `exercicio`, `mes`, `num_nl`, `num_ne`, `limit`, `offset`

---

## Alterar configuração sem rebuild

As configurações (CNPJ, credor, exercícios, meses) ficam na tabela `portal_estado_am.conf`.
Para alterar:

```bash
curl -X PUT -H "x-api-key: pea-xxx" \
  "http://localhost:9000/portal-estado-am/conf/mes_fim?valor=06"
```

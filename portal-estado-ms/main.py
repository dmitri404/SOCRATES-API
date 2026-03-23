"""
Scraper – Portal da Transparencia de Mato Grosso do Sul
API: https://gw.sgi.ms.gov.br/d0146/transpdespesas/v1/
Auth: OAuth2 client_credentials (credenciais publicas do JS do portal)

Fluxo por exercicio/mes:
  1. Obter token OAuth2
  2. Buscar hash do credor pelo nome na lista de credores
  3. despesaporcredores  -> elementos de despesa do credor
  4. detalhedespesaorgaoscredores -> NEs individuais por elemento
  5. EmpenhoDespesaOrgaosCredores -> detalhe completo do NE
  6. Salvar empenhos + documentos no PostgreSQL (schema portal_estado_ms)
"""
import sys
import io
import os
import time
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import requests
import psycopg2
import psycopg2.extras

# ═══════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════
TOKEN_URL     = "https://id.ms.gov.br/auth/realms/ms/protocol/openid-connect/token"
CLIENT_ID     = "ptransparencia.app"
CLIENT_SECRET = "95064d80-afd5-4e6b-8cb5-4385db664f5a"
BASE_URL      = "https://gw.sgi.ms.gov.br/d0146/transpdespesas/v1"
TOKEN_TTL     = 240  # renovar a cada 4 min (token expira em 5)

# ═══════════════════════════════════════════════════════════════════
# TOKEN OAUTH2
# ═══════════════════════════════════════════════════════════════════
_token_cache = {"value": None, "ts": 0.0}


def obter_token() -> str:
    if _token_cache["value"] and time.time() - _token_cache["ts"] < TOKEN_TTL:
        return _token_cache["value"]
    resp = requests.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "grant_type":    "client_credentials",
        "client_secret": CLIENT_SECRET,
    }, timeout=30)
    resp.raise_for_status()
    _token_cache["value"] = resp.json()["access_token"]
    _token_cache["ts"] = time.time()
    print("[AUTH] Token renovado")
    return _token_cache["value"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {obter_token()}"}


def get_api(endpoint: str, params: dict) -> dict | None:
    url = f"{BASE_URL}/{endpoint}"
    resp = requests.get(url, params=params, headers=_headers(), timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


# ═══════════════════════════════════════════════════════════════════
# BANCO DE DADOS
# ═══════════════════════════════════════════════════════════════════
def _conectar():
    return psycopg2.connect(
        host=os.environ["SUPABASE_DB_HOST"],
        port=int(os.environ.get("SUPABASE_DB_PORT", 5432)),
        dbname=os.environ["SUPABASE_DB_NAME"],
        user=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
    )


def carregar_conf(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT chave, valor FROM portal_estado_ms.conf")
        return {r[0]: r[1] for r in cur.fetchall()}


def carregar_conf_cpfs(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT cpf, nome FROM portal_estado_ms.conf_cpfs WHERE ativo = true")
        return [{"cpf": r[0], "nome": r[1]} for r in cur.fetchall()]


def carregar_nes_existentes(conn) -> set:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT num_ne, ug_codigo FROM portal_estado_ms.empenhos
            WHERE num_ne IS NOT NULL AND ug_codigo IS NOT NULL
        """)
        return {(r[0], r[1]) for r in cur.fetchall()}


def inserir_empenho(conn, exercicio: str, mes: str, ne: dict,
                    ug_codigo: str, docs: list,
                    elem_id: str) -> int:
    num_ne = ne.get("numeroEmpenho")
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_ms.empenhos
                (exercicio, mes, num_ne, data_empenho, num_processo,
                 ug_nome, ug_codigo, credor_nome,
                 projeto_atividade, programa, funcao,
                 fonte_recursos, natureza_despesa,
                 elemento_despesa_id,
                 empenhado, liquidado, pago)
            VALUES
                (%(exercicio)s, %(mes)s, %(num_ne)s, %(data_empenho)s, %(num_processo)s,
                 %(ug_nome)s, %(ug_codigo)s, %(credor_nome)s,
                 %(projeto_atividade)s, %(programa)s, %(funcao)s,
                 %(fonte_recursos)s, %(natureza_despesa)s,
                 %(elemento_despesa_id)s,
                 %(empenhado)s, %(liquidado)s, %(pago)s)
            ON CONFLICT (num_ne, ug_codigo) WHERE num_ne IS NOT NULL AND ug_codigo IS NOT NULL
            DO UPDATE SET empenhado = EXCLUDED.empenhado,
                          liquidado = EXCLUDED.liquidado,
                          pago      = EXCLUDED.pago
        """, {
            "exercicio":          exercicio,
            "mes":                mes,
            "num_ne":             num_ne,
            "data_empenho":       ne.get("dataEmpenho"),
            "num_processo":       ne.get("numeroProcesso"),
            "ug_nome":            ne.get("unidadeGestoraNome"),
            "ug_codigo":          ug_codigo,
            "credor_nome":        ne.get("credorNome"),
            "projeto_atividade":  (ne.get("projetoAtividadeDescricao") or "").strip(),
            "programa":           ne.get("programaDescricao"),
            "funcao":             (ne.get("funcaoNome") or "").strip(),
            "fonte_recursos":     (ne.get("fonteRecursos") or "").strip(),
            "natureza_despesa":   ne.get("naturezaDespesa"),
            "elemento_despesa_id": elem_id,
            "empenhado":          ne.get("totalEmpenhado"),
            "liquidado":          ne.get("totalLiquidado"),
            "pago":               ne.get("totalPago"),
        })
        conn.commit()
        # xmax=0 significa insert; xmax>0 significa update
        cur.execute("SELECT xmax FROM portal_estado_ms.empenhos WHERE num_ne = %s AND ug_codigo = %s",
                    (num_ne, ug_codigo))
        row = cur.fetchone()
        is_new = row and int(row[0]) == 0

        if row and docs:
            for doc in docs:
                cur.execute("""
                    INSERT INTO portal_estado_ms.ne_documentos
                        (num_ne, documento, descricao, tipo, data, valor)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (num_ne, tipo, documento)
                    WHERE documento IS NOT NULL DO NOTHING
                """, (
                    num_ne,
                    doc.get("documento"),
                    doc.get("descricaoDocumento"),
                    doc.get("tipo"),
                    doc.get("data"),
                    doc.get("valor"),
                ))
            conn.commit()

    return 1 if is_new else 0


def log_inicio(conn, exercicio: str, mes: str) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_ms.execucao_logs (status, exercicio, mes)
            VALUES ('executando', %s, %s) RETURNING id
        """, (exercicio, mes))
        conn.commit()
        return cur.fetchone()[0]


def log_fim(conn, log_id: int, status: str, empenhos_novos: int, mensagem: str = ""):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE portal_estado_ms.execucao_logs
            SET finalizado_em = NOW(), status = %s, empenhos_novos = %s, mensagem = %s
            WHERE id = %s
        """, (status, empenhos_novos, mensagem, log_id))
        conn.commit()


# ═══════════════════════════════════════════════════════════════════
# HELPERS DA API
# ═══════════════════════════════════════════════════════════════════
def buscar_credor_hash(exercicio: str, credor_nome: str) -> str | None:
    """Percorre a lista de credores do exercicio e retorna o hash do primeiro match."""
    data = get_api("credores", {"exercicio": exercicio})
    if not data:
        print(f"[CREDOR] Sem resposta para exercicio {exercicio}")
        return None
    needle = credor_nome.upper().strip()
    for item in data.get("data", []):
        if needle in (item.get("nome") or "").upper():
            print(f"[CREDOR] {item['nome'].strip()} -> {item['identificacao']}")
            return item["identificacao"]
    print(f"[CREDOR] '{credor_nome}' nao encontrado no exercicio {exercicio}")
    return None


def paginar(endpoint: str, params: dict) -> list:
    """Itera todas as paginas de um endpoint e retorna lista de 'data[0].despesas'."""
    resultados = []
    pageno = params.get("pageno", 1)
    while True:
        params["pageno"] = pageno
        resp = get_api(endpoint, params)
        if not resp or not resp.get("data"):
            break
        despesas = resp["data"][0].get("despesas", [])
        resultados.extend(despesas)
        has_next = (resp.get("pagination") or {}).get("has_next", "")
        if not has_next:
            break
        pageno += 1
    return resultados


# ═══════════════════════════════════════════════════════════════════
# SCRAPE DE UM EXERCICIO (range do ano inteiro em todas as chamadas)
# ═══════════════════════════════════════════════════════════════════
def scrape_exercicio(conn, exercicio: str, credor_hash: str, conf: dict):
    data_inicio = f"{exercicio}-01-01"
    data_fim    = f"{exercicio}-12-31"
    pagesize    = int(conf.get("pagesize", "100"))
    t_sleep     = float(conf.get("t_sleep", "1.0"))

    print(f"\n[EXERCICIO] {exercicio} | {data_inicio} -> {data_fim}")
    log_id = log_inicio(conn, exercicio, None)
    novos = 0

    try:
        # ── Passo 1: elementos de despesa do credor ─────────────────
        elementos = paginar("despesaporcredores", {
            "anoconsulta": exercicio,
            "dataInicio":  data_inicio,
            "dataFim":     data_fim,
            "credor":      credor_hash,
            "pagesize":    pagesize,
        })

        if not elementos:
            print("  [INFO] Sem despesas no exercicio")
            log_fim(conn, log_id, "sucesso", 0, "Sem dados no exercicio")
            return

        print(f"  [INFO] {len(elementos)} elemento(s) de despesa")

        # ── Passo 2: NEs por elemento ────────────────────────────────
        for elem in elementos:
            elem_id   = str(elem.get("elementoDespesaId", ""))

            nes = paginar("detalhedespesaorgaoscredores", {
                "anoconsulta":       exercicio,
                "dataInicio":        data_inicio,
                "dataFim":           data_fim,
                "credor":            credor_hash,
                "elementoDespesaId": elem_id,
                "pagesize":          pagesize,
            })

            for ne_item in nes:
                num_ne    = ne_item.get("documento")
                ug_codigo = str(ne_item.get("unidadeGestoraCodigo") or "")

                if not num_ne:
                    continue

                # ── Passo 3: detalhe completo do NE ─────────────────
                time.sleep(t_sleep)
                detalhe = get_api("EmpenhoDespesaOrgaosCredores", {
                    "empenho":              num_ne,
                    "credorId":             credor_hash,
                    "unidadeGestoraCodigo": ug_codigo,
                    "dataInicio":           data_inicio,
                    "dataFim":              data_fim,
                    "pageno":               1,
                    "pagesize":             1,
                })

                if not detalhe or not detalhe.get("data"):
                    print(f"  [AVISO] Sem detalhe para NE {num_ne}")
                    continue

                ne_full = detalhe["data"][0]
                docs    = ne_full.get("lista", [])

                # Extrai mes do dataEmpenho (formato DD/MM/YYYY)
                data_empenho = ne_full.get("dataEmpenho") or ""
                mes = data_empenho[3:5] if len(data_empenho) >= 5 else None

                cnt = inserir_empenho(
                    conn, exercicio, mes, ne_full,
                    ug_codigo, docs,
                    elem_id,
                )
                if cnt:
                    novos += 1
                print(f"  {'[+]' if cnt else '[~]'} {num_ne} | {(ne_full.get('unidadeGestoraNome') or '').strip()}")

        log_fim(conn, log_id, "sucesso", novos)
        print(f"  [OK] {novos} novo(s), demais atualizados")

    except Exception as exc:
        msg = str(exc)
        log_fim(conn, log_id, "erro", novos, msg)
        print(f"  [ERRO] {msg}")
        raise


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("Scraper – Portal da Transparencia de MS")
    print("=" * 60)

    conn = _conectar()
    conf = carregar_conf(conn)

    exercicios = [e.strip() for e in conf.get("exercicios", "2026").split(",")]
    credores   = carregar_conf_cpfs(conn)

    if not credores:
        print("[AVISO] Nenhum credor ativo em conf_cpfs, encerrando")
        conn.close()
        return

    for credor in credores:
        credor_nome = credor["nome"]
        print(f"\n[CREDOR] {credor_nome}")
        for exercicio in exercicios:
            credor_hash = buscar_credor_hash(exercicio, credor_nome)
            if not credor_hash:
                print(f"[AVISO] Credor nao encontrado para {exercicio}, pulando")
                continue
            scrape_exercicio(conn, exercicio, credor_hash, conf)

    conn.close()
    print("\n[FIM] Scraper concluido")


if __name__ == "__main__":
    main()

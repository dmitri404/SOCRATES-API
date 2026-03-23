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
from calendar import monthrange
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


def carregar_nes_existentes(conn) -> set:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT num_ne, ug_codigo FROM portal_estado_ms.empenhos
            WHERE num_ne IS NOT NULL AND ug_codigo IS NOT NULL
        """)
        return {(r[0], r[1]) for r in cur.fetchall()}


def inserir_empenho(conn, exercicio: str, mes: str, ne: dict,
                    ug_codigo: str, docs: list,
                    elem_nome: str, elem_id: str,
                    tipo_licitacao: str, credor_hash: str) -> int:
    num_ne = ne.get("numeroEmpenho")
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_ms.empenhos
                (exercicio, mes, num_ne, data_empenho, num_processo,
                 ug_nome, ug_codigo, credor_nome, credor_hash,
                 projeto_atividade, programa, sub_funcao, funcao,
                 fonte_recursos, natureza_despesa,
                 elemento_despesa, elemento_despesa_id, tipo_licitacao,
                 empenhado, liquidado, pago)
            VALUES
                (%(exercicio)s, %(mes)s, %(num_ne)s, %(data_empenho)s, %(num_processo)s,
                 %(ug_nome)s, %(ug_codigo)s, %(credor_nome)s, %(credor_hash)s,
                 %(projeto_atividade)s, %(programa)s, %(sub_funcao)s, %(funcao)s,
                 %(fonte_recursos)s, %(natureza_despesa)s,
                 %(elemento_despesa)s, %(elemento_despesa_id)s, %(tipo_licitacao)s,
                 %(empenhado)s, %(liquidado)s, %(pago)s)
            ON CONFLICT (num_ne, ug_codigo) WHERE num_ne IS NOT NULL AND ug_codigo IS NOT NULL DO NOTHING
        """, {
            "exercicio":          exercicio,
            "mes":                mes,
            "num_ne":             num_ne,
            "data_empenho":       ne.get("dataEmpenho"),
            "num_processo":       ne.get("numeroProcesso"),
            "ug_nome":            ne.get("unidadeGestoraNome"),
            "ug_codigo":          ug_codigo,
            "credor_nome":        ne.get("credorNome"),
            "credor_hash":        credor_hash,
            "projeto_atividade":  (ne.get("projetoAtividadeDescricao") or "").strip(),
            "programa":           ne.get("programaDescricao"),
            "sub_funcao":         (ne.get("subFuncaoNome") or "").strip(),
            "funcao":             (ne.get("funcaoNome") or "").strip(),
            "fonte_recursos":     (ne.get("fonteRecursos") or "").strip(),
            "natureza_despesa":   ne.get("naturezaDespesa"),
            "elemento_despesa":   elem_nome,
            "elemento_despesa_id": elem_id,
            "tipo_licitacao":     tipo_licitacao,
            "empenhado":          ne.get("totalEmpenhado"),
            "liquidado":          ne.get("totalLiquidado"),
            "pago":               ne.get("totalPago"),
        })
        conn.commit()
        inserted = cur.rowcount

        if inserted and docs:
            cur.execute(
                "SELECT id FROM portal_estado_ms.empenhos WHERE num_ne = %s AND ug_codigo = %s",
                (num_ne, ug_codigo),
            )
            row = cur.fetchone()
            if row:
                empenho_id = row[0]
                for doc in docs:
                    cur.execute("""
                        INSERT INTO portal_estado_ms.ne_documentos
                            (empenho_id, num_ne, documento, descricao, tipo, data, valor)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        empenho_id,
                        num_ne,
                        doc.get("documento"),
                        doc.get("descricaoDocumento"),
                        doc.get("tipo"),
                        doc.get("data"),
                        doc.get("valor"),
                    ))
                conn.commit()

    return inserted


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
# SCRAPE DE UM PERIODO
# ═══════════════════════════════════════════════════════════════════
def scrape_periodo(conn, exercicio: str, mes: str,
                   credor_hash: str, conf: dict):
    ano = int(exercicio)
    mes_n = int(mes)
    _, ultimo_dia = monthrange(ano, mes_n)
    data_inicio = f"{exercicio}-{mes_n:02d}-01"
    data_fim    = f"{exercicio}-{mes_n:02d}-{ultimo_dia:02d}"
    pagesize    = int(conf.get("pagesize", "100"))
    t_sleep     = float(conf.get("t_sleep", "1.0"))

    print(f"\n[PERIODO] {exercicio}/{mes} | {data_inicio} -> {data_fim}")
    log_id = log_inicio(conn, exercicio, mes)
    nes_existentes = carregar_nes_existentes(conn)
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
            print("  [INFO] Sem despesas no periodo")
            log_fim(conn, log_id, "sucesso", 0, "Sem dados no periodo")
            return

        print(f"  [INFO] {len(elementos)} elemento(s) de despesa")

        # ── Passo 2: NEs por elemento ────────────────────────────────
        for elem in elementos:
            elem_id   = str(elem.get("elementoDespesaId", ""))
            elem_nome = (elem.get("elementoDespesa") or "").strip()
            tipo_lic  = elem.get("tipoLicitacao") or ""

            nes = paginar("detalhedespesaorgaoscredores", {
                "anoconsulta":     exercicio,
                "dataInicio":      data_inicio,
                "dataFim":         data_fim,
                "credor":          credor_hash,
                "elementoDespesaId": elem_id,
                "pagesize":        pagesize,
            })

            for ne_item in nes:
                num_ne    = ne_item.get("documento")
                ug_codigo = str(ne_item.get("unidadeGestoraCodigo") or "")

                if not num_ne:
                    continue
                if (num_ne, ug_codigo) in nes_existentes:
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

                cnt = inserir_empenho(
                    conn, exercicio, mes, ne_full,
                    ug_codigo, docs,
                    elem_nome, elem_id, tipo_lic, credor_hash,
                )
                if cnt:
                    novos += 1
                    nes_existentes.add((num_ne, ug_codigo))
                    print(f"  [+] {num_ne} | {(ne_full.get('unidadeGestoraNome') or '').strip()}")

        log_fim(conn, log_id, "sucesso", novos)
        print(f"  [OK] {novos} empenho(s) novo(s)")

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

    exercicios  = [e.strip() for e in conf.get("exercicios", "2026").split(",")]
    mes_inicio  = int(conf.get("mes_inicio", "1"))
    mes_fim     = int(conf.get("mes_fim", "12"))
    credor_nome = conf.get("credor_nome", "IIN TECNOLOGIAS")

    for exercicio in exercicios:
        credor_hash = buscar_credor_hash(exercicio, credor_nome)
        if not credor_hash:
            print(f"[AVISO] Credor nao encontrado para {exercicio}, pulando")
            continue

        for mes_n in range(mes_inicio, mes_fim + 1):
            # Nao scrape meses futuros
            if date(int(exercicio), mes_n, 1) > date.today():
                break
            scrape_periodo(conn, exercicio, f"{mes_n:02d}", credor_hash, conf)

    conn.close()
    print("\n[FIM] Scraper concluido")


if __name__ == "__main__":
    main()

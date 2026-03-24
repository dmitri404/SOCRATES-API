"""
Scraper – Portal da Transparencia de Rondonia
API: https://transparencia.ro.gov.br/Despesa/FiltrarEmpenhos
Auth: Nenhuma (sessao via cookie anonimo)

Fluxo por exercicio:
  1. GET /Despesa/notas-de-empenho  -> inicializa sessao
  2. POST /Despesa/FiltrarEmpenhos  -> lista empenhos paginada (DataTables)
  3. Salvar empenhos no PostgreSQL (schema portal_estado_ro)
"""
import sys
import io
import os
import json
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import requests
import psycopg2
import psycopg2.extras

# ═══════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════
BASE_URL   = None  # carregado de portal_estado_ro.conf.url_base
PAGESIZE   = 100
T_SLEEP    = 0.5

SESSION_URL   = "https://transparencia.ro.gov.br/Despesa/notas-de-empenho"
FILTRAR_PATH  = "/Despesa/FiltrarEmpenhos"

_session = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"X-Requested-With": "XMLHttpRequest"})
        _session.get(SESSION_URL, timeout=30)
        print("[SESSION] Sessao inicializada")
    return _session


def _parse_valor(valor_str: str) -> float | None:
    """Converte 'R$ 18.288,50' -> 18288.50"""
    if not valor_str:
        return None
    try:
        return float(valor_str.replace("R$", "").replace(".", "").replace(",", ".").strip())
    except Exception:
        return None


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
        cur.execute("SELECT url_base, modo_limpar FROM portal_estado_ro.conf LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Tabela conf vazia — insira uma linha com url_base")
        return {"url_base": row[0], "modo_limpar": row[1]}


def carregar_conf_cpfs(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT cpf, nome FROM portal_estado_ro.conf_cpfs WHERE ativo = true")
        return [{"cpf": r[0], "nome": r[1]} for r in cur.fetchall()]


def carregar_conf_emails(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM portal_estado_ro.conf_emails WHERE ativo = true ORDER BY id")
        return [r[0] for r in cur.fetchall()]


def carregar_exercicios(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT exercicio FROM portal_estado_ro.conf_exercicios WHERE ativo = true ORDER BY exercicio")
        return [r[0] for r in cur.fetchall()]


def inserir_empenho(conn, exercicio: str, row: dict) -> int:
    num_ne = row.get("numeroEmpenho")
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_ro.empenhos
                (exercicio, num_ne, data_empenho, unidade_gestora, credor,
                 valor_empenhado, valor_pago)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (num_ne, exercicio)
            WHERE num_ne IS NOT NULL AND exercicio IS NOT NULL
            DO UPDATE SET valor_empenhado = EXCLUDED.valor_empenhado,
                          valor_pago      = EXCLUDED.valor_pago
        """, (
            exercicio,
            num_ne,
            row.get("dataDocumentoFormatada"),
            row.get("unidadeGestora"),
            row.get("credor"),
            _parse_valor(row.get("valorEmpenhado")),
            _parse_valor(row.get("valorPago")),
        ))
        conn.commit()
        cur.execute("""
            SELECT xmax FROM portal_estado_ro.empenhos
            WHERE num_ne = %s AND exercicio = %s
        """, (num_ne, exercicio))
        row_db = cur.fetchone()
        return 1 if (row_db and int(row_db[0]) == 0) else 0


def log_inicio(conn, exercicio: str) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_ro.execucao_logs (status, exercicio)
            VALUES ('executando', %s) RETURNING id
        """, (exercicio,))
        conn.commit()
        return cur.fetchone()[0]


def log_fim(conn, log_id: int, status: str, empenhos_novos: int, mensagem: str = ""):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE portal_estado_ro.execucao_logs
            SET finalizado_em = NOW(), status = %s,
                empenhos_novos = %s, mensagem = %s
            WHERE id = %s
        """, (status, empenhos_novos, mensagem, log_id))
        conn.commit()


# ═══════════════════════════════════════════════════════════════════
# SCRAPER
# ═══════════════════════════════════════════════════════════════════
def _dt_params(start: int) -> dict:
    return {
        "draw":                 str(start // PAGESIZE + 1),
        "start":                str(start),
        "length":               str(PAGESIZE),
        "columns[0][data]":     "numeroEmpenho",
        "columns[0][name]":     "NotaEmpenho",
        "columns[1][data]":     "dataDocumentoFormatada",
        "columns[1][name]":     "DataEmpenho",
        "columns[2][data]":     "unidadeGestora",
        "columns[2][name]":     "Unidade",
        "columns[3][data]":     "credor",
        "columns[3][name]":     "Credor",
        "columns[4][data]":     "valorEmpenhado",
        "columns[5][data]":     "valorPago",
        "columns[6][data]":     "linkDetalhes",
        "order[0][column]":     "0",
        "order[0][dir]":        "asc",
    }


def scrape_exercicio(conn, exercicio: str, credor_nome: str) -> int:
    print(f"\n[EXERCICIO] {exercicio} | credor={credor_nome}")
    log_id = log_inicio(conn, exercicio)
    novos  = 0
    sess   = _get_session()
    url    = f"{BASE_URL}{FILTRAR_PATH}"

    try:
        start  = 0
        total  = None

        while True:
            params = _dt_params(start)
            params["AnoAvancado"]  = exercicio
            params["NomeCredor"]   = credor_nome

            resp = sess.post(url, data=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("recordsFiltered", 0)
                print(f"  [INFO] {total} empenho(s) encontrado(s)")
                if total == 0:
                    break

            for row in data.get("data", []):
                cnt = inserir_empenho(conn, exercicio, row)
                if cnt:
                    novos += 1
                print(f"  {'[+]' if cnt else '[~]'} {row.get('numeroEmpenho')} | {row.get('unidadeGestora')}")

            start += PAGESIZE
            if start >= total:
                break

            time.sleep(T_SLEEP)

        log_fim(conn, log_id, "sucesso", novos)
        print(f"  [OK] {novos} novo(s), demais atualizados")
        return novos

    except Exception as exc:
        msg = str(exc)
        log_fim(conn, log_id, "erro", novos, msg)
        print(f"  [ERRO] {msg}")
        raise


# ═══════════════════════════════════════════════════════════════════
# EMAIL
# ═══════════════════════════════════════════════════════════════════
def enviar_email(destinatarios: list, inicio: datetime, fim: datetime,
                 empenhos_novos: int, credores: list):
    if not destinatarios:
        print("[EMAIL] Nenhum destinatario em conf_emails, e-mail nao enviado")
        return

    remetente = "eliotsafadao@gmail.com"
    try:
        with open("credentials.json", "r") as f:
            creds = json.load(f)
        senha = creds.get("gmail_app_password", "")
    except Exception as e:
        print(f"[EMAIL] Nao foi possivel ler credentials.json: {e}")
        return

    if not senha:
        print("[EMAIL] gmail_app_password ausente em credentials.json")
        return

    assunto = f"[Portal Estado RO] Execucao concluida - {fim.strftime('%d/%m/%Y %H:%M')}"
    duracao = fim - inicio
    nomes_credores = ", ".join(c["nome"] for c in credores)

    corpo = (
        "Resumo da Execucao - Scraper Portal da Transparencia RO\n"
        "======================================================\n\n"
        f"Inicio  : {inicio.strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Fim     : {fim.strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Duracao : {duracao}\n\n"
        f"Empenhos novos : {empenhos_novos}\n\n"
        f"Credores: {nomes_credores}\n\n"
        "Mensagem automatica gerada pelo scraper."
    )

    try:
        msg = MIMEMultipart()
        msg["From"]    = remetente
        msg["To"]      = ", ".join(destinatarios)
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo, "plain", "utf-8"))

        print(f"[EMAIL] Enviando para {destinatarios}")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(remetente, senha)
            smtp.sendmail(remetente, destinatarios, msg.as_string())
        print("[EMAIL] E-mail enviado com sucesso!")
    except Exception as e:
        print(f"[EMAIL] Erro ao enviar: {e}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("Scraper – Portal da Transparencia de RO")
    print("=" * 60)

    conn   = _conectar()
    conf   = carregar_conf(conn)

    global BASE_URL
    BASE_URL = conf["url_base"]
    print(f"[CONF] url_base={BASE_URL}")

    exercicios = carregar_exercicios(conn)
    credores   = carregar_conf_cpfs(conn)
    emails     = carregar_conf_emails(conn)
    inicio     = datetime.now()
    total_novos = 0

    if not credores:
        print("[AVISO] Nenhum credor ativo em conf_cpfs, encerrando")
        conn.close()
        return

    for credor in credores:
        print(f"\n[CREDOR] {credor['nome']}")
        for exercicio in exercicios:
            novos = scrape_exercicio(conn, exercicio, credor["nome"])
            total_novos += novos

    conn.close()
    fim = datetime.now()
    enviar_email(emails, inicio, fim, total_novos, credores)
    print("\n[FIM] Scraper concluido")


if __name__ == "__main__":
    main()

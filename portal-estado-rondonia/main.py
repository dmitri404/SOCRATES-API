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
import re
import json
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import unescape

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
DETALHES_PATH = "/Despesa/notas-de-empenho/detalhes"

_session = None

_LABEL_MAP = {
    "Histórico":                                                        "historico",
    "Modalidade licitatória":                                           "modalidade_licitacao",
    "Secretaria":                                                       "secretaria",
    "Tipo de empenho":                                                  "tipo_empenho",
    "Função":                                                           "funcao",
    "Subfunção":                                                        "subfuncao",
    "Programa de governo":                                              "programa_governo",
    "Ação de governo":                                                  "acao_governo",
    "Fonte do recurso":                                                 "fonte_recurso",
    "Valor empenhado final":                                            "valor_empenhado_final",
    "Valor pago no exercício do empenho":                               "valor_pago_exercicio",
    "Valor pago em anos posteriores ao da emissão do empenho":          "valor_pago_anos_posteriores",
    "Valor liquidado no exercício da emissão do empenho":               "valor_liquidado_exercicio",
    "Valor liquidado em anos posteriores ao da emissão do empenho":     "valor_liquidado_anos_posteriores",
}


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


def inserir_empenho(conn, exercicio: str, row: dict, portal_id: int = None) -> tuple:
    """Retorna (is_new, db_id)."""
    num_ne = row.get("numeroEmpenho")
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_ro.empenhos
                (exercicio, num_ne, data_empenho, unidade_gestora, credor,
                 valor_empenhado, valor_pago, portal_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (num_ne, exercicio)
            WHERE num_ne IS NOT NULL AND exercicio IS NOT NULL
            DO UPDATE SET valor_empenhado = EXCLUDED.valor_empenhado,
                          valor_pago      = EXCLUDED.valor_pago,
                          portal_id       = EXCLUDED.portal_id
        """, (
            exercicio,
            num_ne,
            row.get("dataDocumentoFormatada"),
            row.get("unidadeGestora"),
            row.get("credor"),
            _parse_valor(row.get("valorEmpenhado")),
            _parse_valor(row.get("valorPago")),
            portal_id,
        ))
        conn.commit()
        cur.execute("""
            SELECT xmax, id FROM portal_estado_ro.empenhos
            WHERE num_ne = %s AND exercicio = %s
        """, (num_ne, exercicio))
        row_db = cur.fetchone()
        is_new = 1 if (row_db and int(row_db[0]) == 0) else 0
        db_id  = row_db[1] if row_db else None
        return is_new, db_id


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
# DETALHES
# ═══════════════════════════════════════════════════════════════════
def _extract_portal_id(link: str) -> int | None:
    m = re.search(r"\?id=(\d+)", link or "")
    val = int(m.group(1)) if m else None
    return val if val and val > 0 else None


def _buscar_detalhes(portal_id: int) -> dict | None:
    url = f"{BASE_URL}{DETALHES_PATH}?id={portal_id}"
    try:
        resp = _get_session().get(url, timeout=30)
        resp.raise_for_status()
        pairs = re.findall(
            r'<p\s+class="content-label">(.*?)</p>\s*<p\s+class="content-value">\s*(?:<em>)?(.*?)(?:</em>)?\s*</p>',
            resp.text, re.DOTALL,
        )
        result = {}
        for label, value in pairs:
            col = _LABEL_MAP.get(unescape(label.strip()))
            if col:
                result[col] = unescape(re.sub(r"\s+", " ", value.strip())) or None
        return result if result else None
    except Exception as exc:
        print(f"  [DETALHE] Erro id={portal_id}: {exc}")
        return None


def inserir_detalhe(conn, num_ne: str, exercicio: str, portal_id: int, det: dict) -> None:
    val_cols = [
        "valor_empenhado_final", "valor_pago_exercicio",
        "valor_pago_anos_posteriores", "valor_liquidado_exercicio",
        "valor_liquidado_anos_posteriores",
    ]
    for col in val_cols:
        if det.get(col) is not None:
            det[col] = _parse_valor(det[col])
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_ro.empenhos_detalhes
                (num_ne, exercicio, portal_id, historico, modalidade_licitacao, secretaria,
                 tipo_empenho, funcao, subfuncao, programa_governo, acao_governo,
                 fonte_recurso,
                 valor_empenhado_final, valor_pago_exercicio, valor_pago_anos_posteriores,
                 valor_liquidado_exercicio, valor_liquidado_anos_posteriores)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (num_ne, exercicio) DO UPDATE SET
                portal_id             = EXCLUDED.portal_id,
                historico             = EXCLUDED.historico,
                modalidade_licitacao  = EXCLUDED.modalidade_licitacao,
                secretaria            = EXCLUDED.secretaria,
                tipo_empenho          = EXCLUDED.tipo_empenho,
                funcao                = EXCLUDED.funcao,
                subfuncao             = EXCLUDED.subfuncao,
                programa_governo      = EXCLUDED.programa_governo,
                acao_governo          = EXCLUDED.acao_governo,
                fonte_recurso         = EXCLUDED.fonte_recurso,
                valor_empenhado_final            = EXCLUDED.valor_empenhado_final,
                valor_pago_exercicio             = EXCLUDED.valor_pago_exercicio,
                valor_pago_anos_posteriores      = EXCLUDED.valor_pago_anos_posteriores,
                valor_liquidado_exercicio        = EXCLUDED.valor_liquidado_exercicio,
                valor_liquidado_anos_posteriores = EXCLUDED.valor_liquidado_anos_posteriores
        """, (
            num_ne, exercicio, portal_id,
            det.get("historico"), det.get("modalidade_licitacao"), det.get("secretaria"),
            det.get("tipo_empenho"), det.get("funcao"),
            det.get("subfuncao"), det.get("programa_governo"), det.get("acao_governo"),
            det.get("fonte_recurso"),
            det.get("valor_empenhado_final"), det.get("valor_pago_exercicio"),
            det.get("valor_pago_anos_posteriores"), det.get("valor_liquidado_exercicio"),
            det.get("valor_liquidado_anos_posteriores"),
        ))
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


def _buscar_portal_ids(exercicio: str, ne_meses: dict) -> dict:
    """
    Busca portal_ids sem filtro de credor, pesquisando mes a mes.
    ne_meses: {num_ne: "YYYY-MM-DDT00:00:00"}
    Retorna: {num_ne: portal_id}
    """
    if not ne_meses:
        return {}

    from collections import defaultdict
    mes_grupos = defaultdict(set)
    for ne, doc_date in ne_meses.items():
        try:
            mes = str(int(doc_date[5:7]))
        except Exception:
            mes = "1"
        mes_grupos[mes].add(ne)

    result = {}
    sess = _get_session()
    url  = f"{BASE_URL}{FILTRAR_PATH}"

    for mes, pendentes in mes_grupos.items():
        pendentes = set(pendentes)
        start = 0
        total = None
        print(f"  [IDS] mes={mes}/{exercicio} | {len(pendentes)} NE(s) a localizar")

        while pendentes:
            params = _dt_params(start)
            params["AnoAvancado"]        = exercicio
            params["MesInicialAvancado"] = mes
            params["MesFinalAvancado"]   = mes

            resp = sess.post(url, data=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("recordsFiltered", 0)
                if total == 0:
                    break

            for row in data.get("data", []):
                ne = row.get("numeroEmpenho")
                if ne in pendentes:
                    pid = _extract_portal_id(row.get("linkDetalhes"))
                    if pid:
                        result[ne] = pid
                    pendentes.discard(ne)

            start += PAGESIZE
            if start >= total:
                break
            time.sleep(T_SLEEP)

    return result


def scrape_exercicio(conn, exercicio: str, credor: dict) -> int:
    nome = credor["nome"]
    print(f"\n[EXERCICIO] {exercicio} | credor={nome}")
    log_id = log_inicio(conn, exercicio)
    novos  = 0
    sess   = _get_session()
    url    = f"{BASE_URL}{FILTRAR_PATH}"

    try:
        # Passo 1: coletar empenhos via NomeCredor (filtragem correta)
        empenhos_raw = []
        start = 0
        total = None

        while True:
            params = _dt_params(start)
            params["AnoAvancado"] = exercicio
            params["NomeCredor"]  = nome

            resp = sess.post(url, data=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if total is None:
                total = data.get("recordsFiltered", 0)
                print(f"  [INFO] {total} empenho(s) encontrado(s)")
                if total == 0:
                    break

            rows = data.get("data", [])
            if not rows:
                break
            empenhos_raw.extend(rows)
            start += PAGESIZE
            if start >= total:
                break
            time.sleep(T_SLEEP)

        # Filtro client-side: o portal ignora NomeCredor e retorna tudo
        nome_lower = nome.lower()
        empenhos_raw = [r for r in empenhos_raw
                        if nome_lower in r.get("credor", "").lower()]
        print(f"  [FILTRO] {len(empenhos_raw)} empenho(s) apos filtro client-side")

        # Passo 2: buscar portal_ids via pesquisa por mes sem NomeCredor
        ne_meses   = {r["numeroEmpenho"]: r.get("dataDocumento", "") for r in empenhos_raw}
        portal_ids = _buscar_portal_ids(exercicio, ne_meses)

        # Passo 3: inserir empenhos e buscar detalhes
        for row in empenhos_raw:
            num_ne        = row.get("numeroEmpenho")
            pid           = portal_ids.get(num_ne)
            is_new, db_id = inserir_empenho(conn, exercicio, row, pid)
            if is_new:
                novos += 1
            label = "[+]" if is_new else "[~]"
            print(f"  {label} {num_ne} | {row.get('unidadeGestora')}"
                  + (f" | id={pid}" if pid else ""))

            if pid:
                det = _buscar_detalhes(pid)
                if det:
                    inserir_detalhe(conn, num_ne, exercicio, pid, det)
                    print(f"    [DET] salvo")
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
            novos = scrape_exercicio(conn, exercicio, credor)
            total_novos += novos

    conn.close()
    fim = datetime.now()
    enviar_email(emails, inicio, fim, total_novos, credores)
    print("\n[FIM] Scraper concluido")


if __name__ == "__main__":
    main()

"""
Scraper – Portal da Transparencia de Porto Velho
API: https://api.portovelho.ro.gov.br/api/v1
Auth: Nenhuma (API publica)

Fluxo por exercicio/mes/credor:
  1. GET /despesas/empenhos?ano=X&mes=M&por-pagina=100&pagina=N  -> filtra por CNPJ
  2. GET /despesas/pagamentos?ano=X&mes=M&por-pagina=100&pagina=N -> filtra por CNPJ
  3. Salva no PostgreSQL (schema portal_municipio_pvh)

Otimizacao:
  - Meses ja processados com sucesso sao pulados
  - Apenas o mes atual e sempre re-varrido (novos registros aparecem no mes corrente)
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

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import requests
import psycopg2

# ═══════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════
API_BASE = "https://api.portovelho.ro.gov.br/api/v1"
PAGESIZE = 25
T_SLEEP  = 5

_session = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"Accept": "application/json"})
    return _session


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _match_cnpj(doc_api: str, cnpj_conf: str) -> bool:
    return _digits(doc_api) == _digits(cnpj_conf)


def _parse_valor(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, dict):
        return v.get("value")
    try:
        return float(v)
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


def carregar_conf_cpfs(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT cpf, nome FROM portal_municipio_pvh.conf_cpfs WHERE ativo = true")
        return [{"cpf": r[0], "nome": r[1]} for r in cur.fetchall()]


def carregar_conf_emails(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM portal_municipio_pvh.conf_emails WHERE ativo = true ORDER BY id")
        return [r[0] for r in cur.fetchall()]


def carregar_exercicios(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT exercicio FROM portal_municipio_pvh.conf_exercicios WHERE ativo = true ORDER BY exercicio")
        return [r[0] for r in cur.fetchall()]


def mes_ja_processado(conn, exercicio: str, mes: int) -> bool:
    """Retorna True se o mes ja foi processado com sucesso anteriormente."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM portal_municipio_pvh.execucao_logs
            WHERE exercicio = %s AND mes = %s AND status = 'sucesso'
            LIMIT 1
        """, (exercicio, str(mes)))
        return cur.fetchone() is not None


def log_inicio(conn, exercicio: str, mes: int) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_municipio_pvh.execucao_logs (status, exercicio, mes)
            VALUES ('executando', %s, %s) RETURNING id
        """, (exercicio, str(mes)))
        conn.commit()
        return cur.fetchone()[0]


def log_fim(conn, log_id: int, status: str, empenhos_novos: int,
            pagamentos_novos: int, mensagem: str = ""):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE portal_municipio_pvh.execucao_logs
            SET finalizado_em = NOW(), status = %s,
                empenhos_novos = %s, pagamentos_novos = %s, mensagem = %s
            WHERE id = %s
        """, (status, empenhos_novos, pagamentos_novos, mensagem, log_id))
        conn.commit()


def inserir_empenho(conn, row: dict) -> bool:
    fav  = row.get("favorecido") or {}
    nat  = row.get("natureza_orcamentaria") or {}
    ug   = row.get("unidade_gestora") or {}
    proc = row.get("processo") or {}
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_municipio_pvh.empenhos
                (api_id, num_ne, ano, data_empenho, tipo, valor, historico,
                 favorecido_nome, favorecido_cnpj, unidade_gestora, orgao,
                 natureza, processo_numero, url)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (api_id) DO UPDATE SET
                valor           = EXCLUDED.valor,
                favorecido_nome = EXCLUDED.favorecido_nome
        """, (
            row.get("id"),
            row.get("numero"),
            row.get("ano"),
            row.get("data_documento"),
            row.get("documento"),
            _parse_valor(row.get("valor")),
            row.get("historico"),
            fav.get("nome"),
            _digits(fav.get("documento", "")),
            ug.get("nome"),
            nat.get("orgao"),
            nat.get("plano_conta"),
            f"{proc.get('numero', '')}",
            row.get("url"),
        ))
        conn.commit()
        cur.execute("SELECT xmax FROM portal_municipio_pvh.empenhos WHERE api_id = %s", (row.get("id"),))
        r = cur.fetchone()
        return bool(r and int(r[0]) == 0)


def inserir_pagamento(conn, row: dict) -> bool:
    fav  = row.get("favorecido") or {}
    nat  = row.get("natureza_orcamentaria") or {}
    ug   = row.get("unidade_gestora") or {}
    proc = row.get("processo") or {}
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_municipio_pvh.pagamentos
                (api_id, num_pagamento, ano, data_pagamento, tipo, valor,
                 favorecido_nome, favorecido_cnpj, unidade_gestora, orgao,
                 processo_numero)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (api_id) DO UPDATE SET
                valor           = EXCLUDED.valor,
                favorecido_nome = EXCLUDED.favorecido_nome
        """, (
            row.get("id"),
            row.get("numero"),
            row.get("ano"),
            row.get("data_documento"),
            row.get("tipo"),
            _parse_valor(row.get("valor")),
            fav.get("nome"),
            _digits(fav.get("documento", "")),
            ug.get("nome"),
            nat.get("orgao"),
            f"{proc.get('numero', '')}",
        ))
        conn.commit()
        cur.execute("SELECT xmax FROM portal_municipio_pvh.pagamentos WHERE api_id = %s", (row.get("id"),))
        r = cur.fetchone()
        return bool(r and int(r[0]) == 0)


# ═══════════════════════════════════════════════════════════════════
# SCRAPER
# ═══════════════════════════════════════════════════════════════════
def _get_com_retry(url: str, params: dict, tentativas: int = 3) -> dict:
    """GET com retry para erros 5xx e timeout."""
    for tentativa in range(1, tentativas + 1):
        try:
            resp = _get_session().get(url, params=params, timeout=120)
            if resp.status_code in (502, 503, 504) and tentativa < tentativas:
                print(f"    [RETRY] {resp.status_code} na tentativa {tentativa}, aguardando 90s...")
                time.sleep(30)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            if tentativa < tentativas:
                print(f"    [RETRY] timeout na tentativa {tentativa}, aguardando 90s...")
                time.sleep(30)
            else:
                raise
    raise RuntimeError("Todas as tentativas falharam")


def _varrer(endpoint: str, ano: str, mes: int, cnpjs: set) -> list:
    """Varre todas as paginas do endpoint/mes e retorna registros cujo
    favorecido.documento (digits) esteja em cnpjs."""
    url    = f"{API_BASE}{endpoint}"
    pagina = 1
    ultimo = None
    result = []

    while True:
        data = _get_com_retry(url, {
            "ano": ano, "mes": mes,
            "por-pagina": PAGESIZE, "pagina": pagina,
        })

        if ultimo is None:
            ultimo = data.get("meta", {}).get("last_page", 1)
            total  = data.get("meta", {}).get("total", 0)
            print(f"    [API] {endpoint} {ano}/{mes:02d} | {total} registros / {ultimo} paginas")
            if total == 0:
                break

        for row in data.get("data", []):
            fav = row.get("favorecido") or {}
            if _digits(fav.get("documento", "")) in cnpjs:
                result.append(row)

        if pagina >= ultimo:
            break
        pagina += 1
        time.sleep(T_SLEEP)

    return result


def scrape_mes(conn, exercicio: str, mes: int, cnpjs: set) -> tuple:
    """Processa um mes. Retorna (empenhos_novos, pagamentos_novos)."""
    log_id = log_inicio(conn, exercicio, mes)
    empenhos_novos = pagamentos_novos = 0

    try:
        empenhos = _varrer("/despesas/empenhos", exercicio, mes, cnpjs)
        print(f"    [FILTRO] {len(empenhos)} empenho(s) para os credores monitorados")
        for row in empenhos:
            is_new = inserir_empenho(conn, row)
            if is_new:
                empenhos_novos += 1
            label = "[+]" if is_new else "[~]"
            print(f"    {label} NE {row.get('numero')} | {(row.get('favorecido') or {}).get('nome')}")

        pagamentos = _varrer("/despesas/pagamentos", exercicio, mes, cnpjs)
        print(f"    [FILTRO] {len(pagamentos)} pagamento(s) para os credores monitorados")
        for row in pagamentos:
            is_new = inserir_pagamento(conn, row)
            if is_new:
                pagamentos_novos += 1
            label = "[+]" if is_new else "[~]"
            print(f"    {label} PAG {row.get('numero')} | {(row.get('favorecido') or {}).get('nome')}")

        log_fim(conn, log_id, "sucesso", empenhos_novos, pagamentos_novos)
        return empenhos_novos, pagamentos_novos

    except Exception as exc:
        msg = str(exc)
        log_fim(conn, log_id, "erro", empenhos_novos, pagamentos_novos, msg)
        print(f"    [ERRO] {msg}")
        raise


def scrape_exercicio(conn, exercicio: str, cnpjs: set) -> tuple:
    agora      = datetime.now()
    ano_atual  = agora.year
    mes_atual  = agora.month
    exercicio_int = int(exercicio)

    # Determina ate qual mes varrer
    if exercicio_int < ano_atual:
        meses = range(1, 13)
    else:
        meses = range(1, mes_atual + 1)

    total_emp = total_pag = 0

    for mes in meses:
        eh_mes_atual = (exercicio_int == ano_atual and mes == mes_atual)

        if not eh_mes_atual and mes_ja_processado(conn, exercicio, mes):
            print(f"  [SKIP] {exercicio}/{mes:02d} ja processado")
            continue

        print(f"  [MES] {exercicio}/{mes:02d}{' (atual)' if eh_mes_atual else ''}")
        e, p = scrape_mes(conn, exercicio, mes, cnpjs)
        total_emp += e
        total_pag += p

    return total_emp, total_pag


# ═══════════════════════════════════════════════════════════════════
# EMAIL
# ═══════════════════════════════════════════════════════════════════
def enviar_email(destinatarios: list, inicio: datetime, fim: datetime,
                 total_empenhos: int, total_pagamentos: int, credores: list):
    if not destinatarios:
        print("[EMAIL] Nenhum destinatario em conf_emails, e-mail nao enviado")
        return

    remetente = "eliotsafadao@gmail.com"
    try:
        with open("credentials.json") as f:
            creds = json.load(f)
        senha = creds.get("gmail_app_password", "")
    except Exception as e:
        print(f"[EMAIL] Nao foi possivel ler credentials.json: {e}")
        return

    if not senha:
        print("[EMAIL] gmail_app_password ausente em credentials.json")
        return

    duracao = fim - inicio
    nomes   = ", ".join(c["nome"] for c in credores)
    assunto = f"[Portal PVH] Execucao concluida - {fim.strftime('%d/%m/%Y %H:%M')}"
    corpo = (
        "Resumo da Execucao - Scraper Portal da Transparencia PVH\n"
        "=========================================================\n\n"
        f"Inicio  : {inicio.strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Fim     : {fim.strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"Duracao : {duracao}\n\n"
        f"Empenhos novos  : {total_empenhos}\n"
        f"Pagamentos novos: {total_pagamentos}\n\n"
        f"Credores: {nomes}\n\n"
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
    print("Scraper – Portal da Transparencia de Porto Velho")
    print("=" * 60)

    conn       = _conectar()
    credores   = carregar_conf_cpfs(conn)
    exercicios = carregar_exercicios(conn)
    emails     = carregar_conf_emails(conn)
    inicio     = datetime.now()
    total_emp  = 0
    total_pag  = 0

    if not credores:
        print("[AVISO] Nenhum credor ativo em conf_cpfs, encerrando")
        conn.close()
        return

    cnpjs = {_digits(c["cpf"]) for c in credores}
    print(f"[CONF] {len(credores)} credor(es) | exercicios: {exercicios}")

    for exercicio in exercicios:
        print(f"\n[EXERCICIO] {exercicio}")
        e, p = scrape_exercicio(conn, exercicio, cnpjs)
        total_emp += e
        total_pag += p

    conn.close()
    fim = datetime.now()
    enviar_email(emails, inicio, fim, total_emp, total_pag, credores)
    print("\n[FIM] Scraper concluido")


if __name__ == "__main__":
    main()

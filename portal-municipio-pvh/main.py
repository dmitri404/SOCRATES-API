"""
Scraper – Portal da Transparencia de Porto Velho
Portal: https://transparencia.portovelho.ro.gov.br/despesas/
Tecnologia: Laravel Livewire v3 + PowerGrid

Fluxo por exercicio/credor:
  1. GET /despesas/ -> extrai CSRF token + wire:snapshot do componente
  2. POST /livewire/update com search=CNPJ + filtro_ano -> HTML filtrado
  3. Parseia linhas da tabela (BeautifulSoup)
  4. Pagina via gotoPage() ate fim
  5. Salva no PostgreSQL (schema portal_municipio_pvh)

Otimizacao:
  - Exercicios passados ja processados sao pulados
  - O exercicio atual e sempre re-varrido
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
from bs4 import BeautifulSoup

PORTAL_URL   = "https://transparencia.portovelho.ro.gov.br"
DESPESAS_URL = PORTAL_URL + "/despesas/"
LIVEWIRE_URL = PORTAL_URL + "/livewire/update"
T_SLEEP      = 3

# Ordem das colunas da tabela PowerGrid (data-column nos <th>)
COL_ORDER = [
    "actions",
    "unidade_gestora_id",
    "orgao",
    "unidade_orcamentaria",
    "ano",
    "data",
    "numero",
    "fase_nome",
    "tipo",
    "valor",
    "valor_liquidado_brl",
    "valor_pago_brl",
    "processo_numero",
    "historico",
    "empenho_numero",
    "liquidacao_tipo",
    "liquidacao_numero",
    "classificacao_funcao",
    "classificacao_subfuncao",
    "programa",
    "projeto",
    "plano_conta",
    "plano_conta_categoria",
    "plano_conta_grupo",
    "plano_conta_modalidade",
    "plano_conta_elemento",
    "fonte_recurso",
    "favorecido_nome",
    "favorecido_documento",
    "documento_fiscal",
]

_session = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9",
        })
    return _session


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _parse_valor(v) -> float | None:
    if not v:
        return None
    cleaned = re.sub(r"[^\d,]", "", str(v)).replace(",", ".")
    try:
        return float(cleaned) if cleaned else None
    except Exception:
        return None


def _parse_data(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").date()
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


def exercicio_ja_processado(conn, exercicio: str, cpf: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM portal_municipio_pvh.execucao_logs
            WHERE exercicio = %s AND cpf = %s AND status = 'sucesso'
            LIMIT 1
        """, (exercicio, cpf))
        return cur.fetchone() is not None


def log_inicio(conn, exercicio: str, cpf: str) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_municipio_pvh.execucao_logs (status, exercicio, cpf)
            VALUES ('executando', %s, %s) RETURNING id
        """, (exercicio, cpf))
        conn.commit()
        return cur.fetchone()[0]


def log_fim(conn, log_id: int, status: str, despesas_novas: int, mensagem: str = ""):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE portal_municipio_pvh.execucao_logs
            SET finalizado_em = NOW(), status = %s, despesas_novas = %s, mensagem = %s
            WHERE id = %s
        """, (status, despesas_novas, mensagem, log_id))
        conn.commit()


def inserir_despesa(conn, row: dict) -> bool:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_municipio_pvh.despesas
                (exercicio, data_despesa, numero, fase, tipo,
                 valor, valor_liquidado, valor_pago,
                 unidade_gestora, orgao, unidade_orcamentaria,
                 processo_numero, historico, empenho_numero,
                 liquidacao_tipo, liquidacao_numero, classificacao_funcao,
                 favorecido_nome, favorecido_cnpj)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (numero, fase) DO UPDATE SET
                valor           = EXCLUDED.valor,
                valor_liquidado = EXCLUDED.valor_liquidado,
                valor_pago      = EXCLUDED.valor_pago
        """, (
            row.get("exercicio"),
            _parse_data(row.get("data")),
            row.get("numero"),
            row.get("fase_nome"),
            row.get("tipo"),
            _parse_valor(row.get("valor")),
            _parse_valor(row.get("valor_liquidado_brl")),
            _parse_valor(row.get("valor_pago_brl")),
            row.get("unidade_gestora_id"),
            row.get("orgao"),
            row.get("unidade_orcamentaria"),
            row.get("processo_numero"),
            row.get("historico"),
            row.get("empenho_numero"),
            row.get("liquidacao_tipo"),
            row.get("liquidacao_numero"),
            row.get("classificacao_funcao"),
            row.get("favorecido_nome"),
            row.get("favorecido_cnpj"),
        ))
        conn.commit()
        cur.execute(
            "SELECT xmax FROM portal_municipio_pvh.despesas WHERE numero = %s AND fase = %s",
            (row.get("numero"), row.get("fase_nome")),
        )
        r = cur.fetchone()
        return bool(r and int(r[0]) == 0)


# ═══════════════════════════════════════════════════════════════════
# LIVEWIRE
# ═══════════════════════════════════════════════════════════════════
def _iniciar_sessao() -> tuple[str, str]:
    """GET /despesas/ e retorna (csrf_token, snapshot_str)."""
    print("  [HTTP] GET /despesas/")
    resp = _get_session().get(DESPESAS_URL, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    meta = soup.find("meta", {"name": "csrf-token"})
    if not meta:
        raise RuntimeError("CSRF token nao encontrado na pagina")
    csrf = meta["content"]

    # Componente principal: o que tem filtro_ano ou search nos dados
    snapshot_str = None
    for el in soup.find_all(attrs={"wire:snapshot": True}):
        snap_raw = el.get("wire:snapshot", "")
        try:
            snap = json.loads(snap_raw)
            data = snap.get("data", {})
            if "filtro_ano" in data or "search" in data:
                snapshot_str = snap_raw
                break
        except Exception:
            continue

    if not snapshot_str:
        raise RuntimeError("Snapshot Livewire nao encontrado na pagina")

    print(f"  [LW] Sessao iniciada | CSRF={csrf[:10]}...")
    return csrf, snapshot_str


def _lw_post(csrf: str, snapshot_str: str,
             updates: dict | None = None,
             calls: list | None = None) -> tuple[str, str]:
    """POST /livewire/update. Retorna (novo_snapshot, html_effects)."""
    payload = {
        "components": [{
            "snapshot": snapshot_str,
            "updates":  updates or {},
            "calls":    calls   or [],
        }]
    }
    headers = {
        "X-CSRF-TOKEN":  csrf,
        "X-Livewire":    "true",
        "Content-Type":  "application/json",
        "Accept":        "text/html, application/xhtml+xml",
        "Referer":       DESPESAS_URL,
    }
    resp = _get_session().post(LIVEWIRE_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()

    data     = resp.json()
    comp     = data["components"][0]
    new_snap = comp["snapshot"]
    html     = comp.get("effects", {}).get("html") or ""
    return new_snap, html


def _extrair_linhas(html: str) -> tuple[list, int]:
    """Extrai linhas da tabela e total de paginas do HTML retornado pelo Livewire."""
    soup  = BeautifulSoup(html, "lxml")
    tbody = soup.find("tbody")
    if not tbody:
        return [], 1

    # Detecta colunas pelo thead (disponivel no HTML completo, nao no parcial)
    thead = soup.find("thead")
    col_order = COL_ORDER
    if thead:
        cols = [th.get("data-column", "") for th in thead.find_all("th")]
        if cols:
            col_order = cols

    rows = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) <= 1:
            continue  # linha vazia ou "sem registros"
        # Pula linha de sumario (ex: "Soma: R$ X")
        row_text = tr.get_text(" ", strip=True)
        if "Soma:" in row_text or "soma:" in row_text:
            continue
        row = {}
        for i, col in enumerate(col_order):
            if col != "actions" and i < len(cells):
                row[col] = cells[i].get_text(" ", strip=True)
        rows.append(row)

    # Total de paginas: botoes numerados na paginacao
    total_pages = 1
    nav = soup.find("nav", attrs={"aria-label": re.compile(r"pagination", re.I)})
    if nav:
        btns = [b.get_text(strip=True) for b in nav.find_all(["button", "span"])
                if b.get_text(strip=True).isdigit()]
        if btns:
            total_pages = max(int(x) for x in btns)

    return rows, total_pages


# ═══════════════════════════════════════════════════════════════════
# SCRAPER
# ═══════════════════════════════════════════════════════════════════
def scrape_credor(conn, exercicio: str, credor: dict) -> int:
    """Raspa todos os registros de um credor num exercicio. Retorna despesas_novas."""
    cpf    = _digits(credor["cpf"])
    nome   = credor["nome"]
    log_id = log_inicio(conn, exercicio, cpf)
    despesas_novas = 0

    try:
        csrf, snapshot = _iniciar_sessao()
        time.sleep(T_SLEEP)

        # Aplica filtros: ano + busca por nome do credor
        print(f"  [LW] filtro_ano={exercicio}  search={nome!r}")
        snapshot, html = _lw_post(csrf, snapshot, updates={
            "filtro_ano": int(exercicio),
            "search":     nome,
        })
        time.sleep(T_SLEEP)

        rows, total_pages = _extrair_linhas(html)
        print(f"  [LW] pagina 1/{total_pages} | {len(rows)} linha(s)")

        def _processar_rows(rows):
            nonlocal despesas_novas
            for row in rows:
                row["exercicio"] = exercicio
                # favorecido_nome e favorecido_documento vem do HTML
                # mas usamos conf como fallback
                if not row.get("favorecido_nome"):
                    row["favorecido_nome"] = nome
                # normaliza cnpj: favorecido_documento -> favorecido_cnpj
                row["favorecido_cnpj"] = _digits(
                    row.get("favorecido_documento") or cpf
                )
                if not row.get("numero"):
                    continue
                is_new = inserir_despesa(conn, row)
                if is_new:
                    despesas_novas += 1
                label = "[+]" if is_new else "[~]"
                print(f"    {label} {row.get('numero')} | {row.get('fase_nome')} | {row.get('valor')}")

        _processar_rows(rows)

        for pagina in range(2, total_pages + 1):
            print(f"  [LW] pagina {pagina}/{total_pages}")
            snapshot, html = _lw_post(csrf, snapshot, calls=[
                {"path": "", "method": "gotoPage", "params": [pagina, "page"]}
            ])
            rows, _ = _extrair_linhas(html)
            print(f"       {len(rows)} linha(s)")
            _processar_rows(rows)
            time.sleep(T_SLEEP)

        log_fim(conn, log_id, "sucesso", despesas_novas)
        return despesas_novas

    except Exception as exc:
        msg = str(exc)
        log_fim(conn, log_id, "erro", despesas_novas, msg)
        print(f"  [ERRO] {msg}")
        raise


# ═══════════════════════════════════════════════════════════════════
# EMAIL
# ═══════════════════════════════════════════════════════════════════
def enviar_email(destinatarios: list, inicio: datetime, fim: datetime,
                 total: int, credores: list):
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
        f"Despesas novas: {total}\n\n"
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
    total      = 0

    if not credores:
        print("[AVISO] Nenhum credor ativo em conf_cpfs, encerrando")
        conn.close()
        return

    print(f"[CONF] {len(credores)} credor(es) | exercicios: {exercicios}")

    ano_atual = datetime.now().year

    for exercicio in exercicios:
        for credor in credores:
            cpf = _digits(credor["cpf"])
            print(f"\n[EXERCICIO] {exercicio} | {credor['nome']}")

            eh_atual = int(exercicio) >= ano_atual
            if not eh_atual and exercicio_ja_processado(conn, exercicio, cpf):
                print("  [SKIP] ja processado com sucesso")
                continue

            n = scrape_credor(conn, exercicio, credor)
            total += n

    conn.close()
    fim = datetime.now()
    enviar_email(emails, inicio, fim, total, credores)
    print("\n[FIM] Scraper concluido")


if __name__ == "__main__":
    main()

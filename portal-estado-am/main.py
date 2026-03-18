"""
Scraper – Portal da Transparência Fiscal do Amazonas (SEFAZ AM)
URL: https://sistemas.sefaz.am.gov.br/transparencia/pagamentos/credor

Salva dados no PostgreSQL (schema portal_estado_am).
Configuração lida da tabela portal_estado_am.conf.
"""
import sys, io, json, time, os
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import psycopg2
import psycopg2.extras
from playwright.sync_api import sync_playwright, Page

URL = "https://sistemas.sefaz.am.gov.br/transparencia/pagamentos/credor"

# ════════════════════════════════════════════════════════════════
# BANCO DE DADOS
# ════════════════════════════════════════════════════════════════
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
        cur.execute("SELECT chave, valor FROM portal_estado_am.conf")
        return {row[0]: row[1] for row in cur.fetchall()}

def carregar_obs_existentes(conn) -> set:
    with conn.cursor() as cur:
        cur.execute("SELECT num_ob FROM portal_estado_am.pagamentos WHERE num_ob IS NOT NULL AND num_ob <> ''")
        return {row[0] for row in cur.fetchall()}

def carregar_nls_existentes(conn) -> set:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT num_nl FROM portal_estado_am.nl_itens WHERE num_nl IS NOT NULL AND num_nl <> ''")
        return {row[0] for row in cur.fetchall()}

def inserir_pagamento(conn, exercicio, mes, row: dict):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_am.pagamentos
                (exercicio, mes, orgao, credor, data, num_ob, num_nl, num_ne,
                 fr, classificacao, pago_exercicio, pago_exercicio_anterior,
                 ug_ob, valor_ob, credor_ob, descricao_ob)
            VALUES
                (%(exercicio)s, %(mes)s, %(orgao)s, %(credor)s, %(data)s,
                 %(num_ob)s, %(num_nl)s, %(num_ne)s,
                 %(fr)s, %(classificacao)s, %(pago_exercicio)s, %(pago_exercicio_anterior)s,
                 %(ug_ob)s, %(valor_ob)s, %(credor_ob)s, %(descricao_ob)s)
            ON CONFLICT (num_ob) DO NOTHING
        """, {**row, "exercicio": exercicio, "mes": mes})
        conn.commit()
        return cur.rowcount

def inserir_nl_item(conn, exercicio, mes, row: dict):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_am.nl_itens
                (exercicio, mes, orgao, num_nl,
                 data_nl, valor_nl, credor_nl, natureza_nl, fonte_nl, descricao_nl,
                 ug_ne, num_empenho, data_ne, valor_ne, credor_ne,
                 unid_orcamentaria, natureza_ne, fonte_ne, descricao_ne,
                 cron_jan, cron_fev, cron_mar, cron_abr, cron_mai, cron_jun,
                 cron_jul, cron_ago, cron_set, cron_out, cron_nov, cron_dez,
                 un_item, descricao_item, qtde, valor_un, valor_total)
            VALUES
                (%(exercicio)s, %(mes)s, %(orgao)s, %(num_nl)s,
                 %(data_nl)s, %(valor_nl)s, %(credor_nl)s, %(natureza_nl)s, %(fonte_nl)s, %(descricao_nl)s,
                 %(ug_ne)s, %(num_empenho)s, %(data_ne)s, %(valor_ne)s, %(credor_ne)s,
                 %(unid_orcamentaria)s, %(natureza_ne)s, %(fonte_ne)s, %(descricao_ne)s,
                 %(cron_jan)s, %(cron_fev)s, %(cron_mar)s, %(cron_abr)s, %(cron_mai)s, %(cron_jun)s,
                 %(cron_jul)s, %(cron_ago)s, %(cron_set)s, %(cron_out)s, %(cron_nov)s, %(cron_dez)s,
                 %(un_item)s, %(descricao_item)s, %(qtde)s, %(valor_un)s, %(valor_total)s)
        """, {**row, "exercicio": exercicio, "mes": mes})
        conn.commit()

def log_inicio(conn, exercicio, mes) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO portal_estado_am.execucao_logs (status, exercicio, mes)
            VALUES ('executando', %s, %s) RETURNING id
        """, (exercicio, mes))
        conn.commit()
        return cur.fetchone()[0]

def log_fim(conn, log_id, status, pagamentos_novos, nl_itens_novos, mensagem=""):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE portal_estado_am.execucao_logs
            SET finalizado_em = NOW(), status = %s,
                pagamentos_novos = %s, nl_itens_novos = %s, mensagem = %s
            WHERE id = %s
        """, (status, pagamentos_novos, nl_itens_novos, mensagem, log_id))
        conn.commit()

# ════════════════════════════════════════════════════════════════
# HELPERS PLAYWRIGHT
# ════════════════════════════════════════════════════════════════
def w(page: Page, sel: str, t=15000, state="visible") -> bool:
    try:
        page.wait_for_selector(sel, timeout=t, state=state)
        return True
    except:
        print(f"[WAIT] ⚠ timeout '{sel}'")
        return False

def val_input(page: Page, label_text: str) -> str:
    return page.evaluate(f"""
        () => {{
            for (const lbl of document.querySelectorAll('label')) {{
                if (lbl.innerText.trim().includes({json.dumps(label_text)})) {{
                    const p = lbl.closest('div') || lbl.parentElement;
                    const el = p?.querySelector('input, textarea');
                    if (el) return el.value?.trim() || el.innerText?.trim() || '';
                }}
            }}
            return '';
        }}
    """)

def _val_textarea(page: Page, label_text: str) -> str:
    return page.evaluate(f"""
        () => {{
            for (const lbl of document.querySelectorAll('label')) {{
                if (lbl.innerText.trim().includes({json.dumps(label_text)})) {{
                    const p = lbl.closest('div') || lbl.parentElement;
                    const ta = p?.querySelector('textarea');
                    if (ta) return ta.value?.trim() || ta.innerText?.trim() || '';
                    const inp = p?.querySelector('input');
                    if (inp) return inp.value?.trim() || '';
                }}
            }}
            return '';
        }}
    """)

def _react_select(page: Page, selector: str, value: str, label: str):
    try:
        page.wait_for_selector(selector, timeout=10000)
        page.select_option(selector, value=value)
        time.sleep(0.3)
        atual = page.eval_on_selector(selector, "el => el.value")
        if atual != value:
            page.evaluate(f"""
                () => {{
                    const sel = document.querySelector('{selector}');
                    if (!sel) return;
                    const setter = Object.getOwnPropertyDescriptor(
                        HTMLSelectElement.prototype, 'value').set;
                    setter.call(sel, {json.dumps(value)});
                    sel.dispatchEvent(new Event('input',  {{bubbles:true}}));
                    sel.dispatchEvent(new Event('change', {{bubbles:true}}));
                }}
            """)
            time.sleep(0.3)
        print(f"[FILTRO] ✓ {label}={value}")
    except Exception as e:
        print(f"[FILTRO] ⚠ {label}: {e}")

def _fechar_detalhe(page: Page, t_fechar: float):
    sels = [
        ".modal-transparencia-close",
        "button:has-text('Voltar')",
        "a:has-text('Voltar')",
        "button:has-text('Fechar')",
        "[aria-label='Fechar']",
        "[aria-label='Close']",
        ".modal .close",
        "button.btn-secondary",
    ]
    for sel in sels:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                el.click()
                time.sleep(t_fechar)
                return
        except:
            continue
    try:
        page.keyboard.press("Escape")
        time.sleep(1.0)
    except:
        pass

def _reexpandir_orgao(page: Page, i_org: int):
    try:
        n2 = page.evaluate(f"""
            () => {{
                const n1s = [...document.querySelectorAll('tr.nivel1')];
                const alvo = n1s[{i_org}];
                if (!alvo) return 0;
                let sib = alvo.nextElementSibling; let cnt = 0;
                while (sib && !sib.classList.contains('nivel1')) {{
                    if (sib.classList.contains('nivel2') || sib.querySelector('td.nivel2'))
                        cnt++;
                    sib = sib.nextElementSibling;
                }}
                return cnt;
            }}
        """)
        if n2 == 0:
            orgaos = page.locator("tr.nivel1")
            if i_org < orgaos.count():
                try:
                    orgaos.nth(i_org).locator('td[role="button"]').first.click()
                except:
                    orgaos.nth(i_org).click()
                time.sleep(2.0)
    except:
        pass

def _extrair_cronograma(page: Page) -> dict:
    try:
        return page.evaluate("""
            () => {
                const MESES = ["Jan","Fev","Mar","Abr","Mai","Jun",
                               "Jul","Ago","Set","Out","Nov","Dez"];
                const FULL  = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
                               "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];
                const result = {};
                for (const tbl of document.querySelectorAll('table')) {
                    const txt = tbl.innerText.toLowerCase();
                    if (!txt.includes('janeiro') && !txt.includes('fevereiro')) continue;
                    const rows = [...tbl.querySelectorAll('tr')];
                    for (let i = 0; i < rows.length - 1; i++) {
                        const ths = [...rows[i].querySelectorAll('th')];
                        const tds = [...rows[i+1].querySelectorAll('td')];
                        if (ths.length > 0 && tds.length > 0) {
                            ths.forEach((th, j) => {
                                const nome = th.innerText.trim();
                                const idx  = FULL.findIndex(m => nome.toLowerCase().includes(m.toLowerCase()));
                                if (idx >= 0) result[MESES[idx]] = tds[j]?.innerText.trim() || '';
                            });
                        }
                    }
                    if (Object.keys(result).length > 0) break;
                }
                return result;
            }
        """)
    except:
        return {}

def _extrair_itens_nl(page: Page) -> list:
    try:
        return page.evaluate("""
            () => {
                for (const tbl of document.querySelectorAll('table')) {
                    const head = tbl.querySelector('thead')?.innerText?.toLowerCase() || '';
                    if (!head.includes('un') && !head.includes('qtd') &&
                        !head.includes('descri')) continue;
                    return [...tbl.querySelectorAll('tbody tr')].map(tr => {
                        const tds = [...tr.querySelectorAll('td')];
                        return tds.map(td => td.innerText.trim());
                    }).filter(r => r.length >= 3);
                }
                return [];
            }
        """)
    except:
        return []

# ════════════════════════════════════════════════════════════════
# ETAPAS DO SCRAPER
# ════════════════════════════════════════════════════════════════
def etapa1_pesquisar_credor(page: Page, cnpj: str, t_render: float, t_pesq: float):
    print(f"\n[NAV] {URL}")
    page.goto(URL, timeout=60000, wait_until="domcontentloaded")
    time.sleep(t_render)

    page.select_option("#filtroTipoPessoa", "PJ")
    print("[FORM] ✓ Pessoa Jurídica selecionada")
    time.sleep(0.3)

    input_sels = [
        'label:has-text("CPF/CNPJ") ~ input',
        'label:has-text("CPF") ~ input',
        '.col-md-4.mb-2 input[type="text"]',
        'input[type="text"]',
    ]
    preencheu = False
    for sel in input_sels:
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                el.wait_for(state="visible", timeout=5000)
                el.fill(cnpj)
                print(f"[FORM] ✓ CNPJ '{cnpj}'")
                preencheu = True
                break
        except:
            continue

    if not preencheu:
        raise RuntimeError("Campo CPF/CNPJ não encontrado")

    time.sleep(0.3)
    page.locator("button.btn-pesquisa").first.click()
    print("[FORM] ✓ Pesquisar clicado")
    time.sleep(t_pesq)

def etapa2_selecionar_credor(page: Page, credor_texto: str, t_pesq: float):
    print(f"\n[CREDOR] Selecionando: '{credor_texto}'")
    w(page, 'tr[role="button"]', t=15000)

    termos = list(dict.fromkeys([credor_texto] + credor_texto.split()))
    for txt in termos:
        sel = f'tr[role="button"]:has-text("{txt}")'
        try:
            el = page.locator(sel).first
            if el.count() > 0:
                el.click()
                print(f"[CREDOR] ✓ '{txt}'")
                time.sleep(t_pesq)
                return
        except:
            continue

    raise RuntimeError(f"Credor '{credor_texto}' não encontrado")

def etapa3_filtros_periodo(page: Page, exercicio: str, mes: str):
    print(f"\n[FILTRO] Exercício={exercicio}  Mês={mes}")
    page.wait_for_selector("#filtroExercicio", timeout=15000)
    _react_select(page, "#filtroExercicio", exercicio, "Exercício")
    _react_select(page, "#filtroMesInicio", mes, "MesInicio")
    _react_select(page, "#filtroMesFim",    mes, "MesFim")
    time.sleep(0.3)

    page.locator("button.btn-pesquisa").first.click()
    print("[FILTRO] ✓ Pesquisar clicado — aguardando resultados...")

    try:
        page.wait_for_selector('text="Aguarde, pesquisando dados..."', state="hidden", timeout=180000)
        print("[FILTRO] ✓ Carregamento concluído")
    except:
        pass

    time.sleep(3.0)

def coletar_detalhe_ob(page: Page, ob_val: str, t_modal: float, t_fechar: float) -> dict:
    print(f"      [OB] {ob_val}")
    detalhe = {}
    try:
        sel_span = f'span[role="button"]:has-text("{ob_val}")'
        el = page.locator(sel_span).first
        if el.count() > 0:
            el.click()
        else:
            page.locator(f'span[role="button"]:has-text("{ob_val[:10]}")').first.click()

        time.sleep(t_modal)
        detalhe = {
            "ug":        val_input(page, "Unidade Gestora"),
            "num_ob":    val_input(page, "Número da Ordem Bancária"),
            "data":      val_input(page, "Data"),
            "valor":     val_input(page, "Valor"),
            "credor":    val_input(page, "Credor"),
            "descricao": _val_textarea(page, "Descrição"),
        }
        print(f"      [OB] data={detalhe['data']} | valor={detalhe['valor']}")
    except Exception as e:
        print(f"      [OB] ⚠ {e}")

    _fechar_detalhe(page, t_fechar)
    return detalhe

def coletar_detalhe_nl(page: Page, nl_val: str, t_modal: float, t_fechar: float) -> dict:
    print(f"      [NL] {nl_val}")
    detalhe = {}
    try:
        sel_span = f'span[role="button"]:has-text("{nl_val}")'
        el = page.locator(sel_span).first
        if el.count() > 0:
            el.click()
        else:
            page.locator(f'span[role="button"]:has-text("{nl_val[:10]}")').first.click()

        time.sleep(t_modal)
        detalhe = {
            "ug":             val_input(page, "Unidade Gestora"),
            "num_lancamento": val_input(page, "Número do Lançamento"),
            "data":           val_input(page, "Data"),
            "valor":          val_input(page, "Valor"),
            "credor":         val_input(page, "Credor"),
            "natureza":       val_input(page, "Natureza de Despesa"),
            "fonte":          val_input(page, "Fonte de Recurso"),
            "descricao":      _val_textarea(page, "Descrição"),
        }
        print(f"      [NL] ug={detalhe['ug']} | valor={detalhe['valor']}")
    except Exception as e:
        print(f"      [NL] ⚠ {e}")

    _fechar_detalhe(page, t_fechar)
    return detalhe

def coletar_detalhe_ne(page: Page, ne_val: str, t_modal: float, t_fechar: float):
    print(f"      [NE] {ne_val}")
    detalhe, cronograma, itens = {}, {}, []
    try:
        sel_span = f'span[role="button"]:has-text("{ne_val}")'
        el = page.locator(sel_span).first
        if el.count() > 0:
            el.click()
        else:
            page.locator(f'span[role="button"]:has-text("{ne_val[:10]}")').first.click()

        time.sleep(t_modal)
        detalhe = {
            "ug":                val_input(page, "Unidade Gestora"),
            "num_empenho":       val_input(page, "Número do Empenho"),
            "data":              val_input(page, "Data"),
            "valor":             val_input(page, "Valor"),
            "credor":            val_input(page, "Credor"),
            "unid_orcamentaria": val_input(page, "Unidade Orçamentária"),
            "natureza":          val_input(page, "Natureza de Despesa"),
            "fonte":             val_input(page, "Fonte de Recurso"),
            "descricao":         _val_textarea(page, "Descrição"),
        }
        print(f"      [NE] valor={detalhe['valor']}")
        cronograma = _extrair_cronograma(page)
        itens      = _extrair_itens_nl(page)
        print(f"      [NE] cronograma={len(cronograma)} meses | {len(itens)} item(ns)")
    except Exception as e:
        print(f"      [NE] ⚠ {e}")

    _fechar_detalhe(page, t_fechar)
    return detalhe, cronograma, itens

def processar_linha_nivel2(page: Page, row_tds, orgao_txt: str, i_org: int, i_row: int,
                           exercicio: str, mes: str, conn,
                           obs_existentes: set, nls_existentes: set,
                           t_modal: float, t_fechar: float) -> tuple:
    """Retorna (pagamentos_inseridos, nl_itens_inseridos)."""
    credor_v = data_v = ob_v = nl_v = ne_v = fr_v = class_v = pago_v = pago_ant_v = ""
    ob_col_idx = nenl_col_idx = -1

    span_cols = []
    for ci, td in enumerate(row_tds):
        spans = td.get("spans", [])
        if spans:
            span_cols.append(ci)
            if any("OB" in s for s in spans):
                ob_col_idx = ci
                ob_v = next((s for s in spans if "OB" in s), "")
            elif any("NE" in s or "NL" in s for s in spans):
                nenl_col_idx = ci
                ne_v = next((s for s in spans if "NE" in s), "")
                nl_v = next((s for s in spans if "NL" in s), "")

    last_span = max(span_cols) if span_cols else 1
    text_cols  = [ci for ci in range(len(row_tds)) if ci not in span_cols]
    after_span = [ci for ci in text_cols if ci > last_span]

    for ci, td in enumerate(row_tds):
        if ci in span_cols:
            continue
        txt = td.get("text", "")
        if ci == 0:                                              credor_v   = txt
        elif ci == 1:                                            data_v     = txt
        elif len(after_span) >= 1 and ci == after_span[0]:      fr_v       = txt
        elif len(after_span) >= 2 and ci == after_span[1]:      class_v    = txt
        elif len(after_span) >= 3 and ci == after_span[2]:      pago_v     = txt
        elif len(after_span) >= 4 and ci == after_span[3]:      pago_ant_v = txt

    print(f"    [R{i_row+1}] OB={ob_v} | NE={ne_v} | NL={nl_v} | FR={fr_v} | CLASS={class_v}")

    pag_ins = nl_ins = 0

    # ── Pagamentos ──────────────────────────────────────────────
    if ob_v and ob_v in obs_existentes:
        print(f"    [SKIP] OB {ob_v} já existe")
    else:
        ob_detalhe = {}
        if ob_v and ob_col_idx >= 0:
            ob_detalhe = coletar_detalhe_ob(page, ob_v, t_modal, t_fechar)
            _reexpandir_orgao(page, i_org)

        n = inserir_pagamento(conn, exercicio, mes, {
            "orgao":                   orgao_txt,
            "credor":                  credor_v,
            "data":                    data_v,
            "num_ob":                  ob_v or None,
            "num_nl":                  nl_v,
            "num_ne":                  ne_v,
            "fr":                      fr_v,
            "classificacao":           class_v,
            "pago_exercicio":          pago_v,
            "pago_exercicio_anterior": pago_ant_v,
            "ug_ob":                   ob_detalhe.get("ug", ""),
            "valor_ob":                ob_detalhe.get("valor", ""),
            "credor_ob":               ob_detalhe.get("credor", ""),
            "descricao_ob":            ob_detalhe.get("descricao", ""),
        })
        if ob_v:
            obs_existentes.add(ob_v)
        pag_ins += n

    # ── NL / NE Itens ────────────────────────────────────────────
    if nl_v and nl_v in nls_existentes:
        print(f"    [SKIP] NL {nl_v} já existe")
    else:
        ne_detalhe, ne_cronograma, ne_itens = {}, {}, []
        nl_detalhe = {}

        if ne_v and nenl_col_idx >= 0:
            ne_detalhe, ne_cronograma, ne_itens = coletar_detalhe_ne(page, ne_v, t_modal, t_fechar)
            _reexpandir_orgao(page, i_org)

        if nl_v and nenl_col_idx >= 0:
            nl_detalhe = coletar_detalhe_nl(page, nl_v, t_modal, t_fechar)
            _reexpandir_orgao(page, i_org)

        if nl_v or ne_v:
            itens = ne_itens if ne_itens else [["", "", "", "", ""]]
            for item in itens:
                while len(item) < 5:
                    item.append("")
                inserir_nl_item(conn, exercicio, mes, {
                    "orgao":            orgao_txt,
                    "num_nl":           nl_v or None,
                    "data_nl":          nl_detalhe.get("data", ""),
                    "valor_nl":         nl_detalhe.get("valor", ""),
                    "credor_nl":        nl_detalhe.get("credor", ""),
                    "natureza_nl":      nl_detalhe.get("natureza", ""),
                    "fonte_nl":         nl_detalhe.get("fonte", ""),
                    "descricao_nl":     nl_detalhe.get("descricao", ""),
                    "ug_ne":            ne_detalhe.get("ug", ""),
                    "num_empenho":      ne_detalhe.get("num_empenho", ""),
                    "data_ne":          ne_detalhe.get("data", ""),
                    "valor_ne":         ne_detalhe.get("valor", ""),
                    "credor_ne":        ne_detalhe.get("credor", ""),
                    "unid_orcamentaria": ne_detalhe.get("unid_orcamentaria", ""),
                    "natureza_ne":      ne_detalhe.get("natureza", ""),
                    "fonte_ne":         ne_detalhe.get("fonte", ""),
                    "descricao_ne":     ne_detalhe.get("descricao", ""),
                    "cron_jan": ne_cronograma.get("Jan", ""), "cron_fev": ne_cronograma.get("Fev", ""),
                    "cron_mar": ne_cronograma.get("Mar", ""), "cron_abr": ne_cronograma.get("Abr", ""),
                    "cron_mai": ne_cronograma.get("Mai", ""), "cron_jun": ne_cronograma.get("Jun", ""),
                    "cron_jul": ne_cronograma.get("Jul", ""), "cron_ago": ne_cronograma.get("Ago", ""),
                    "cron_set": ne_cronograma.get("Set", ""), "cron_out": ne_cronograma.get("Out", ""),
                    "cron_nov": ne_cronograma.get("Nov", ""), "cron_dez": ne_cronograma.get("Dez", ""),
                    "un_item":       item[0] if len(item) > 0 else "",
                    "descricao_item": item[1] if len(item) > 1 else "",
                    "qtde":          item[2] if len(item) > 2 else "",
                    "valor_un":      item[3] if len(item) > 3 else "",
                    "valor_total":   item[4] if len(item) > 4 else "",
                })
                nl_ins += 1

            if nl_v:
                nls_existentes.add(nl_v)

    return pag_ins, nl_ins

def etapa4_coletar_pagamentos(page: Page, exercicio: str, mes: str, conn,
                               obs_existentes: set, nls_existentes: set,
                               t_modal: float, t_fechar: float) -> tuple:
    print("\n[COLETA] Iniciando coleta de pagamentos por órgão...")
    pag_total = nl_total = 0

    if not w(page, "tr.nivel1", t=30000):
        sem_dados = page.locator('text="Sem dados para exibir"').count()
        if sem_dados > 0:
            print("[COLETA] ⚠ 'Sem dados para exibir' — nenhum registro no período")
            return 0, 0
        print("[COLETA] ⚠ tr.nivel1 não encontrado")
        return 0, 0

    orgaos_els = page.locator("tr.nivel1")
    n_orgaos   = orgaos_els.count()
    print(f"[COLETA] {n_orgaos} órgão(s) encontrado(s)")

    for i_org in range(n_orgaos):
        orgao_el  = orgaos_els.nth(i_org)
        orgao_txt = orgao_el.locator("td").first.inner_text().strip()
        print(f"\n[ORGAO {i_org+1}/{n_orgaos}] {orgao_txt}")

        try:
            orgao_el.locator('td[role="button"]').first.click()
        except:
            orgao_el.click()
        time.sleep(2.0)

        linhas_n2 = page.evaluate(f"""
            () => {{
                const nivel1s = [...document.querySelectorAll('tr.nivel1')];
                const alvo = nivel1s[{i_org}];
                if (!alvo) return [];
                const result = [];
                let sib = alvo.nextElementSibling;
                while (sib && !sib.classList.contains('nivel1')) {{
                    if (sib.classList.contains('nivel2') || sib.querySelector('td.nivel2')) {{
                        const tds = [...sib.querySelectorAll('td')];
                        result.push(tds.map(td => ({{
                            text:    td.innerText.trim(),
                            hasSpan: td.querySelectorAll('span[role="button"]').length > 0,
                            spans:   [...td.querySelectorAll('span[role="button"]')].map(s => s.innerText.trim()),
                        }})));
                    }}
                    sib = sib.nextElementSibling;
                }}
                return result;
            }}
        """)

        print(f"  [NIVEL2] {len(linhas_n2)} linha(s)")

        for i_row, row_tds in enumerate(linhas_n2):
            p, n = processar_linha_nivel2(
                page, row_tds, orgao_txt, i_org, i_row,
                exercicio, mes, conn,
                obs_existentes, nls_existentes,
                t_modal, t_fechar,
            )
            pag_total += p
            nl_total  += n

        orgaos_els = page.locator("tr.nivel1")

    return pag_total, nl_total

# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════
def executar():
    inicio = datetime.now()
    print(f"\n{'#'*60}")
    print(f"# SCRAPER TRANSPARÊNCIA AM")
    print(f"# {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}")

    conn = _conectar()
    print("[DB] ✓ Conectado ao PostgreSQL")

    conf = carregar_conf(conn)
    cnpj         = conf.get("cnpj", "03211236000165")
    credor_texto = conf.get("credor_texto", "IIN TECNOLOGIAS")
    exercicios   = [e.strip() for e in conf.get("exercicios", "2025,2026").split(",")]
    mes_inicio   = conf.get("mes_inicio", "01")
    mes_fim      = conf.get("mes_fim", "12")
    headless     = conf.get("headless", "true").lower() == "true"
    t_render     = float(conf.get("t_render", "4.0"))
    t_pesq       = float(conf.get("t_pesq",   "7.0"))
    t_modal      = float(conf.get("t_modal",  "5.0"))
    t_fechar     = float(conf.get("t_fechar", "2.0"))

    print(f"[CONF] CNPJ={cnpj} | Credor={credor_texto}")
    print(f"[CONF] Exercícios={exercicios} | Meses {mes_inicio}→{mes_fim}")

    ano_atual = inicio.year
    mes_atual = inicio.month

    combinacoes = []
    for ex in exercicios:
        ano_ex = int(ex)
        if ano_ex < ano_atual:
            meses = [str(m).zfill(2) for m in range(1, 13)]
        else:
            fim_mes = min(int(mes_fim), mes_atual)
            meses = [str(m).zfill(2) for m in range(int(mes_inicio), fim_mes + 1)]
        for mes in meses:
            combinacoes.append((ex, mes))

    total = len(combinacoes)
    print(f"[CONF] Total de combinações: {total}")

    obs_existentes = carregar_obs_existentes(conn)
    nls_existentes = carregar_nls_existentes(conn)
    print(f"[DB] {len(obs_existentes)} OBs | {len(nls_existentes)} NLs já existentes")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=100)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, locale="pt-BR")
        page = ctx.new_page()

        for i, (exercicio, mes) in enumerate(combinacoes, 1):
            print(f"\n{'='*60}")
            print(f"# [{i}/{total}] Exercício={exercicio}  Mês={mes}")
            print(f"{'='*60}")

            log_id = log_inicio(conn, exercicio, mes)
            pag_ins = nl_ins = 0

            try:
                etapa1_pesquisar_credor(page, cnpj, t_render, t_pesq)
                etapa2_selecionar_credor(page, credor_texto, t_pesq)
                etapa3_filtros_periodo(page, exercicio, mes)
                pag_ins, nl_ins = etapa4_coletar_pagamentos(
                    page, exercicio, mes, conn,
                    obs_existentes, nls_existentes,
                    t_modal, t_fechar,
                )
                log_fim(conn, log_id, "sucesso", pag_ins, nl_ins)
                print(f"[OK] {exercicio}/{mes} — {pag_ins} pagamentos | {nl_ins} nl_itens novos")
            except Exception as e:
                import traceback
                msg = traceback.format_exc()
                print(f"\n[{exercicio}/{mes}] ✗ {e}")
                print(msg)
                log_fim(conn, log_id, "erro", pag_ins, nl_ins, str(e)[:500])

        browser.close()

    conn.close()
    fim = datetime.now()
    print(f"\n{'#'*60}")
    print(f"# CONCLUÍDO em {fim - inicio}")
    print(f"{'#'*60}\n")

if __name__ == "__main__":
    executar()

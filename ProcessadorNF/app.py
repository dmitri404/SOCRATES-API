"""
app.py — Processador de Notas Fiscais
Le PDFs de pastas SMB e envia para a Portal API conforme o perfil configurado.
"""

import configparser
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk

import requests

from extractor import extrair_dados
from pdf_reader import extrair_texto
from supabase_client import SupabaseClient

# Credenciais da API — hardcoded, não expostas ao usuário
_API_URL = 'http://187.77.240.80:9000'
_API_KEYS = {
    'portal_municipal_manaus': 'aris-22386d82643aa6e36b12688a7175698d',
    'portal_estado_am':        'estam-52394a9ff66f976ee2ab097a6844a7a4',
}
_PORTAIS = list(_API_KEYS.keys())

# Senha de acesso às configurações
_SENHA_CONFIG = 'tambaqui@'

if getattr(sys, 'frozen', False):
    CONFIG_FILE = Path(sys.executable).parent / 'conf.ini'
else:
    CONFIG_FILE = Path.home() / 'AppData' / 'Roaming' / 'ProcessadorNF' / 'conf.ini'
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def carregar_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding='utf-8')
    return cfg


def listar_perfis() -> list[dict]:
    cfg = carregar_config()
    perfis = []
    for sec in cfg.sections():
        if sec.startswith('PERFIL_'):
            perfis.append({
                'secao':    sec,
                'nome':     cfg.get(sec, 'nome',     fallback=''),
                'smb_path': cfg.get(sec, 'smb_path', fallback=''),
                'usuario':  cfg.get(sec, 'usuario',  fallback=''),
                'senha':    cfg.get(sec, 'senha',    fallback=''),
                'portal':   cfg.get(sec, 'portal',   fallback='portal_municipal_manaus'),
            })
    return perfis


def salvar_perfil(secao: str, nome: str, smb_path: str, usuario: str, senha: str, portal: str) -> None:
    cfg = carregar_config()
    cfg[secao] = {
        'nome':     nome,
        'smb_path': smb_path,
        'usuario':  usuario,
        'senha':    senha,
        'portal':   portal,
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        cfg.write(f)


def remover_perfil(secao: str) -> None:
    cfg = carregar_config()
    if cfg.has_section(secao):
        cfg.remove_section(secao)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        cfg.write(f)


def proximo_secao() -> str:
    perfis = listar_perfis()
    indices = [int(p['secao'].replace('PERFIL_', '')) for p in perfis if p['secao'].replace('PERFIL_', '').isdigit()]
    return f'PERFIL_{max(indices) + 1}' if indices else 'PERFIL_1'


def autenticar_smb(path: str, usuario: str, senha: str) -> None:
    partes = path.lstrip('\\').split('\\')
    unc = f'\\\\{partes[0]}\\{partes[1]}' if len(partes) >= 2 else path
    subprocess.run(
        ['net', 'use', unc, f'/user:{usuario}', senha],
        capture_output=True, text=True,
    )


def processar_perfil(perfil: dict, log_fn, progress_fn):
    nome    = perfil['nome']
    portal  = perfil['portal']
    api_key = _API_KEYS.get(portal)

    if not api_key:
        log_fn(f'[{nome}] ERRO: portal "{portal}" nao reconhecido.')
        return

    log_fn(f'\n[{nome}] Autenticando na rede...')
    autenticar_smb(perfil['smb_path'], perfil['usuario'], perfil['senha'])

    pasta = Path(perfil['smb_path'])
    if not pasta.exists():
        log_fn(f'[{nome}] ERRO: pasta nao encontrada: {perfil["smb_path"]}')
        return

    pdfs = [p for p in pasta.rglob('*.pdf')
            if not any(x in p.parts for x in ('processados', 'erro'))]

    if not pdfs:
        log_fn(f'[{nome}] Nenhum PDF encontrado.')
        return

    log_fn(f'[{nome}] {len(pdfs)} PDF(s) encontrado(s) → {portal}')
    progress_fn(0, len(pdfs))

    try:
        db = SupabaseClient(_API_URL, api_key, portal)
        db.carregar_numeros_existentes()
        log_fn(f'[{nome}] Cache: {len(db._numeros_cache)} nota(s) existentes.')
    except Exception as e:
        log_fn(f'[{nome}] ERRO ao conectar servidor: {e}')
        return

    pasta_proc = pasta / 'processados'
    pasta_erro = pasta / 'erro'
    pasta_proc.mkdir(exist_ok=True)
    pasta_erro.mkdir(exist_ok=True)

    inseridos = duplicatas = erros = 0

    for i, pdf in enumerate(pdfs, 1):
        progress_fn(i, len(pdfs))
        try:
            texto = extrair_texto(pdf)
            if not texto:
                raise ValueError('PDF vazio ou ilegivel')

            dados = extrair_dados(texto, pdf.name)
            if not dados:
                raise ValueError('Campos obrigatorios nao encontrados')

            inserido = db.inserir_nota(dados)

            if inserido:
                inseridos += 1
                log_fn(f'[{nome}] [{i}/{len(pdfs)}] OK: {pdf.name} | Nota {dados["NumeroNota"]} | R$ {dados["ValorLiquido"]}')
            else:
                duplicatas += 1
                log_fn(f'[{nome}] [{i}/{len(pdfs)}] DUPLICATA: {pdf.name}')

            shutil.move(str(pdf), str(pasta_proc / pdf.name))

        except Exception as e:
            erros += 1
            log_fn(f'[{nome}] [{i}/{len(pdfs)}] ERRO: {pdf.name} — {e}')
            try:
                shutil.move(str(pdf), str(pasta_erro / pdf.name))
            except Exception:
                pass

    log_fn(f'[{nome}] Concluido: {inseridos} inserido(s) | {duplicatas} duplicata(s) | {erros} erro(s)')


def disparar_scraper(portal: str, api_key: str, log_fn, btn):
    endpoint = portal.replace('_', '-')
    try:
        resp = requests.post(
            f'{_API_URL}/{endpoint}/trigger',
            headers={'x-api-key': api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get('status')
        servico = data.get('servico', endpoint)
        if status == 'iniciado':
            log_fn(f'[Scraper] {servico} iniciado com sucesso.')
        elif status == 'ja_rodando':
            log_fn(f'[Scraper] {servico} ja esta rodando.')
        else:
            log_fn(f'[Scraper] Resposta inesperada: {data}')
    except Exception as e:
        log_fn(f'[Scraper] ERRO ao disparar {endpoint}: {e}')
    finally:
        btn.config(state=tk.NORMAL)


def processar(perfis_selecionados, log_fn, progress_fn, btn):
    if not perfis_selecionados:
        log_fn('Nenhum perfil selecionado.')
        btn.config(state=tk.NORMAL)
        return

    for perfil in perfis_selecionados:
        processar_perfil(perfil, log_fn, progress_fn)

    log_fn('\n' + '=' * 50)
    log_fn('Todos os perfis processados.')
    progress_fn(1, 1)
    btn.config(state=tk.NORMAL)


# ── Diálogo de perfil (adicionar/editar) ─────────────────────────────────────

class DialogPerfil(tk.Toplevel):

    def __init__(self, parent, perfil: dict = None):
        super().__init__(parent)
        self.title('Novo Perfil' if perfil is None else 'Editar Perfil')
        self.resizable(False, False)
        self.grab_set()
        self.resultado = None
        self._perfil = perfil

        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack()

        campos = [
            ('Nome do perfil:', 'nome'),
            ('Pasta SMB:',      'smb_path'),
            ('Usuario:',        'usuario'),
            ('Senha SMB:',      'senha'),
        ]
        self._entries = {}
        for row, (label, key) in enumerate(campos):
            tk.Label(frame, text=label, anchor='w', font=('Segoe UI', 9)).grid(row=row, column=0, sticky='w', pady=4)
            show = '*' if key == 'senha' else ''
            entry = tk.Entry(frame, width=42, font=('Segoe UI', 9), show=show)
            entry.grid(row=row, column=1, padx=8, pady=4)
            if perfil:
                entry.insert(0, perfil.get(key, ''))
            self._entries[key] = entry

        tk.Label(frame, text='Portal:', anchor='w', font=('Segoe UI', 9)).grid(row=len(campos), column=0, sticky='w', pady=4)
        self._portal_var = tk.StringVar(value=perfil['portal'] if perfil else _PORTAIS[0])
        portal_cb = ttk.Combobox(frame, textvariable=self._portal_var, values=_PORTAIS,
                                  state='readonly', width=40, font=('Segoe UI', 9))
        portal_cb.grid(row=len(campos), column=1, padx=8, pady=4)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text='Salvar', font=('Segoe UI', 10, 'bold'),
                  bg='#2563eb', fg='white', relief='flat', padx=16, pady=6,
                  command=self._salvar).pack(side='left', padx=6)
        tk.Button(btn_frame, text='Cancelar', font=('Segoe UI', 10),
                  relief='flat', padx=16, pady=6,
                  command=self.destroy).pack(side='left', padx=6)

    def _salvar(self):
        dados = {k: e.get().strip() for k, e in self._entries.items()}
        dados['portal'] = self._portal_var.get()
        if not all([dados['nome'], dados['smb_path'], dados['usuario'], dados['senha']]):
            messagebox.showwarning('Aviso', 'Preencha todos os campos.', parent=self)
            return
        self.resultado = dados
        self.destroy()


# ── Diálogo de configurações (lista de perfis) ───────────────────────────────

class DialogConfiguracoes(tk.Toplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.title('Configuracoes — Perfis')
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()
        self._atualizar_lista()

    def _build_ui(self):
        tk.Label(self, text='Perfis configurados', font=('Segoe UI', 11, 'bold')).pack(padx=16, pady=(12, 4))

        frame_lista = tk.Frame(self)
        frame_lista.pack(padx=16, pady=4, fill='both', expand=True)

        self._listbox = tk.Listbox(frame_lista, width=55, height=6, font=('Segoe UI', 9),
                                    selectmode='single', activestyle='dotbox')
        self._listbox.pack(side='left', fill='both', expand=True)

        scroll = tk.Scrollbar(frame_lista, orient='vertical', command=self._listbox.yview)
        scroll.pack(side='right', fill='y')
        self._listbox.config(yscrollcommand=scroll.set)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=8)
        tk.Button(btn_frame, text='+ Adicionar', font=('Segoe UI', 9),
                  bg='#16a34a', fg='white', relief='flat', padx=10, pady=4,
                  command=self._adicionar).pack(side='left', padx=4)
        tk.Button(btn_frame, text='✎ Editar', font=('Segoe UI', 9),
                  relief='flat', padx=10, pady=4,
                  command=self._editar).pack(side='left', padx=4)
        tk.Button(btn_frame, text='✕ Remover', font=('Segoe UI', 9),
                  bg='#dc2626', fg='white', relief='flat', padx=10, pady=4,
                  command=self._remover).pack(side='left', padx=4)
        tk.Button(btn_frame, text='Fechar', font=('Segoe UI', 9),
                  relief='flat', padx=10, pady=4,
                  command=self.destroy).pack(side='left', padx=4)

    def _atualizar_lista(self):
        self._perfis = listar_perfis()
        self._listbox.delete(0, 'end')
        for p in self._perfis:
            self._listbox.insert('end', f"{p['nome']}  →  {p['portal']}  |  {p['smb_path']}")

    def _adicionar(self):
        dlg = DialogPerfil(self)
        self.wait_window(dlg)
        if dlg.resultado:
            secao = proximo_secao()
            r = dlg.resultado
            salvar_perfil(secao, r['nome'], r['smb_path'], r['usuario'], r['senha'], r['portal'])
            self._atualizar_lista()

    def _editar(self):
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showwarning('Aviso', 'Selecione um perfil.', parent=self)
            return
        perfil = self._perfis[sel[0]]
        dlg = DialogPerfil(self, perfil=perfil)
        self.wait_window(dlg)
        if dlg.resultado:
            r = dlg.resultado
            salvar_perfil(perfil['secao'], r['nome'], r['smb_path'], r['usuario'], r['senha'], r['portal'])
            self._atualizar_lista()

    def _remover(self):
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showwarning('Aviso', 'Selecione um perfil.', parent=self)
            return
        perfil = self._perfis[sel[0]]
        if messagebox.askyesno('Confirmar', f'Remover perfil "{perfil["nome"]}"?', parent=self):
            remover_perfil(perfil['secao'])
            self._atualizar_lista()


# ── App principal ─────────────────────────────────────────────────────────────

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('Processador de Notas Fiscais')
        self.resizable(False, False)
        self._build_ui()
        self._atualizar_perfis()

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=4, pady=4)

        tab_principal = tk.Frame(notebook)
        notebook.add(tab_principal, text='Principal')
        self._build_tab_principal(tab_principal)

        tab_conf = tk.Frame(notebook)
        notebook.add(tab_conf, text='Configurações BD')
        self._build_tab_conf(tab_conf)

    def _build_tab_principal(self, frame):
        pad = {'padx': 12, 'pady': 6}

        tk.Label(frame, text='Processador de Notas Fiscais',
                 font=('Segoe UI', 13, 'bold')).pack(**pad)

        frame_perfis = tk.LabelFrame(frame, text='Perfis', font=('Segoe UI', 9))
        frame_perfis.pack(fill='x', padx=12, pady=4)

        self._perfis_vars = []
        self._frame_checks = tk.Frame(frame_perfis)
        self._frame_checks.pack(fill='x', padx=8, pady=4)

        tk.Label(frame_perfis, text='Nenhum perfil configurado.',
                 font=('Segoe UI', 9), fg='gray').pack(padx=8, anchor='w')
        self._lbl_vazio = frame_perfis.winfo_children()[-1]

        tk.Button(frame_perfis, text='⚙ Configuracoes', font=('Segoe UI', 8),
                  relief='flat', cursor='hand2',
                  command=self._abrir_config).pack(anchor='e', padx=8, pady=4)

        frame_scraper = tk.LabelFrame(frame, text='Disparo de Scrapers', font=('Segoe UI', 9))
        frame_scraper.pack(fill='x', padx=12, pady=4)
        frame_scraper_btns = tk.Frame(frame_scraper)
        frame_scraper_btns.pack(padx=8, pady=6)
        self._btn_mun = tk.Button(
            frame_scraper_btns, text='Atualizar Portal Municipal',
            font=('Segoe UI', 9), relief='flat', padx=10, pady=4,
            bg='#0369a1', fg='white', cursor='hand2',
            command=self._disparar_municipal,
        )
        self._btn_mun.pack(side='left', padx=4)
        self._btn_est = tk.Button(
            frame_scraper_btns, text='Atualizar Portal Estado AM',
            font=('Segoe UI', 9), relief='flat', padx=10, pady=4,
            bg='#7c3aed', fg='white', cursor='hand2',
            command=self._disparar_estado,
        )
        self._btn_est.pack(side='left', padx=4)

        self._progress = ttk.Progressbar(frame, length=460, mode='determinate')
        self._progress.pack(**pad)
        self._lbl_progress = tk.Label(frame, text='', font=('Segoe UI', 8))
        self._lbl_progress.pack()

        self._btn = tk.Button(
            frame, text='Processar PDFs',
            font=('Segoe UI', 11, 'bold'),
            bg='#2563eb', fg='white',
            activebackground='#1d4ed8',
            relief='flat', cursor='hand2',
            padx=20, pady=8,
            command=self._iniciar,
        )
        self._btn.pack(**pad)

        frame_log = tk.LabelFrame(frame, text='Log', font=('Segoe UI', 9))
        frame_log.pack(fill='both', expand=True, padx=12, pady=4)
        self._log = scrolledtext.ScrolledText(
            frame_log, height=14, width=64,
            font=('Consolas', 9), state='disabled', wrap='word',
        )
        self._log.pack(padx=4, pady=4)

        tk.Button(frame, text='Limpar log', font=('Segoe UI', 8),
                  command=self._limpar_log).pack(pady=(0, 8))

    def _build_tab_conf(self, frame):
        # ── Scrollable container ───────────────────────────────────────────────
        canvas = tk.Canvas(frame, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        inner = tk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor='nw')

        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(inner_id, width=e.width))
        canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units'))

        # ── Seletor de portal ──────────────────────────────────────────────────
        top = tk.Frame(inner)
        top.pack(fill='x', padx=12, pady=(10, 4))
        tk.Label(top, text='Portal:', font=('Segoe UI', 10, 'bold')).pack(side='left')
        self._conf_portal_var = tk.StringVar(value='municipal')
        for txt, val in [('Municipal', 'municipal'), ('Estado AM', 'estado-am')]:
            tk.Radiobutton(
                top, text=txt, variable=self._conf_portal_var, value=val,
                font=('Segoe UI', 9), command=self._conf_carregar,
            ).pack(side='left', padx=8)
        tk.Button(top, text='Recarregar', font=('Segoe UI', 8), relief='flat',
                  cursor='hand2', padx=8, pady=2,
                  command=self._conf_carregar).pack(side='right', padx=4)

        # ── Configuração Geral ─────────────────────────────────────────────────
        frame_geral = tk.LabelFrame(inner, text='Configuração Geral (conf)', font=('Segoe UI', 9))
        frame_geral.pack(fill='x', padx=12, pady=4)

        row_url = tk.Frame(frame_geral)
        row_url.pack(fill='x', padx=8, pady=(6, 2))
        tk.Label(row_url, text='URL Base:', font=('Segoe UI', 9), width=12, anchor='w').pack(side='left')
        self._conf_url_var = tk.StringVar()
        tk.Entry(row_url, textvariable=self._conf_url_var, font=('Segoe UI', 9), width=48).pack(side='left', padx=4)

        tk.Button(row_url, text='Salvar', bg='#2563eb', fg='white', relief='flat',
                  font=('Segoe UI', 8), padx=10, pady=2, cursor='hand2',
                  command=self._conf_salvar_geral).pack(side='left', padx=4)

        # ── E-mails ────────────────────────────────────────────────────────────
        frame_email = tk.LabelFrame(inner, text='E-mails (conf_emails)', font=('Segoe UI', 9))
        frame_email.pack(fill='x', padx=12, pady=4)

        cols_email = ('ID', 'E-mail', 'Ativo')
        self._tv_email = ttk.Treeview(frame_email, columns=cols_email, show='headings', height=3)
        for col, width, anchor in [('ID', 40, 'center'), ('E-mail', 260, 'w'), ('Ativo', 50, 'center')]:
            self._tv_email.heading(col, text=col)
            self._tv_email.column(col, width=width, anchor=anchor)
        self._tv_email.pack(side='left', fill='x', padx=(4, 0), pady=4)

        btn_email = tk.Frame(frame_email)
        btn_email.pack(side='left', padx=8)
        for txt, bg, fg, cmd in [
            ('+ Adicionar',      '#16a34a', 'white', self._conf_add_email),
            ('Ativar/Desativar', '#475569', 'white', self._conf_toggle_email),
        ]:
            tk.Button(btn_email, text=txt, bg=bg, fg=fg, relief='flat',
                      font=('Segoe UI', 8), padx=8, pady=4, cursor='hand2',
                      command=cmd).pack(pady=3)

        # ── Credores ───────────────────────────────────────────────────────────
        frame_cred = tk.LabelFrame(inner, text='Credores (conf_cpfs)', font=('Segoe UI', 9))
        frame_cred.pack(fill='x', padx=12, pady=4)

        cols_cred = ('ID', 'CPF/CNPJ', 'Nome', 'Ativo')
        self._tv_cred = ttk.Treeview(frame_cred, columns=cols_cred, show='headings', height=5)
        for col, width, anchor in [
            ('ID', 40, 'center'), ('CPF/CNPJ', 130, 'w'),
            ('Nome', 190, 'w'),   ('Ativo', 50, 'center'),
        ]:
            self._tv_cred.heading(col, text=col)
            self._tv_cred.column(col, width=width, anchor=anchor)
        self._tv_cred.pack(side='left', fill='x', padx=(4, 0), pady=4)

        btn_cred = tk.Frame(frame_cred)
        btn_cred.pack(side='left', padx=8)
        for txt, bg, fg, cmd in [
            ('+ Adicionar',      '#16a34a', 'white', self._conf_add_credor),
            ('Ativar/Desativar', '#475569', 'white', self._conf_toggle_credor),
        ]:
            tk.Button(btn_cred, text=txt, bg=bg, fg=fg, relief='flat',
                      font=('Segoe UI', 8), padx=8, pady=4, cursor='hand2',
                      command=cmd).pack(pady=3)

        # ── Exercícios ─────────────────────────────────────────────────────────
        frame_ex = tk.LabelFrame(inner, text='Exercícios (conf_exercicios)', font=('Segoe UI', 9))
        frame_ex.pack(fill='x', padx=12, pady=4)

        cols_ex = ('ID', 'Exercício', 'Ativo')
        self._tv_ex = ttk.Treeview(frame_ex, columns=cols_ex, show='headings', height=3)
        for col, width in [('ID', 40), ('Exercício', 100), ('Ativo', 60)]:
            self._tv_ex.heading(col, text=col)
            self._tv_ex.column(col, width=width, anchor='center')
        self._tv_ex.pack(side='left', fill='x', padx=(4, 0), pady=4)

        btn_ex = tk.Frame(frame_ex)
        btn_ex.pack(side='left', padx=8)
        for txt, bg, fg, cmd in [
            ('+ Adicionar',      '#16a34a', 'white', self._conf_add_exercicio),
            ('Ativar/Desativar', '#475569', 'white', self._conf_toggle_exercicio),
        ]:
            tk.Button(btn_ex, text=txt, bg=bg, fg=fg, relief='flat',
                      font=('Segoe UI', 8), padx=8, pady=4, cursor='hand2',
                      command=cmd).pack(pady=3)

        # ── Status ─────────────────────────────────────────────────────────────
        self._conf_status = tk.Label(inner, text='', font=('Segoe UI', 8), fg='gray')
        self._conf_status.pack(pady=(2, 8))

        self._conf_carregar()

    # ── Helpers da aba Configurações ──────────────────────────────────────────

    def _conf_api_call(self, method: str, path: str, **kwargs):
        portal = self._conf_portal_var.get()
        key = _API_KEYS['portal_municipal_manaus' if portal == 'municipal' else 'portal_estado_am']
        url = f'{_API_URL}/conf/{portal}/{path}'
        resp = requests.request(method, url, headers={'x-api-key': key}, timeout=10, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _conf_carregar(self):
        self._conf_status.config(text='Carregando...', fg='gray')
        self.update_idletasks()
        try:
            geral      = self._conf_api_call('GET', 'geral')
            emails     = self._conf_api_call('GET', 'emails')
            credores   = self._conf_api_call('GET', 'credores')
            exercicios = self._conf_api_call('GET', 'exercicios')

            self._conf_url_var.set(geral.get('url_base', ''))

            self._tv_email.delete(*self._tv_email.get_children())
            for e in emails:
                self._tv_email.insert('', 'end', values=(
                    e['id'], e['email'], 'Sim' if e['ativo'] else 'Não',
                ))

            self._tv_cred.delete(*self._tv_cred.get_children())
            for c in credores:
                self._tv_cred.insert('', 'end', values=(
                    c['id'], c['cpf_cnpj'],
                    c.get('nome_credor') or '',
                    'Sim' if c['ativo'] else 'Não',
                ))

            self._tv_ex.delete(*self._tv_ex.get_children())
            for e in exercicios:
                self._tv_ex.insert('', 'end', values=(
                    e['id'], e['exercicio'], 'Sim' if e['ativo'] else 'Não',
                ))

            self._conf_status.config(
                text=f'{len(emails)} e-mail(s)  |  {len(credores)} credor(es)  |  {len(exercicios)} exercício(s)',
                fg='#16a34a',
            )
        except Exception as ex:
            self._conf_status.config(text=f'Erro: {ex}', fg='red')

    def _conf_salvar_geral(self):
        try:
            self._conf_api_call('PUT', 'geral', json={
                'url_base': self._conf_url_var.get().strip(),
                'modo_limpar': False,
            })
            self._conf_status.config(text='Configuração salva.', fg='#16a34a')
        except Exception as ex:
            messagebox.showerror('Erro', str(ex), parent=self)

    def _conf_add_email(self):
        email = simpledialog.askstring('Novo E-mail', 'E-mail:', parent=self)
        if not email:
            return
        try:
            self._conf_api_call('POST', 'emails', json={'email': email.strip()})
            self._conf_carregar()
        except Exception as ex:
            messagebox.showerror('Erro', str(ex), parent=self)

    def _conf_toggle_email(self):
        sel = self._tv_email.selection()
        if not sel:
            messagebox.showwarning('Aviso', 'Selecione um e-mail.', parent=self)
            return
        email_id = self._tv_email.item(sel[0])['values'][0]
        try:
            self._conf_api_call('PATCH', f'emails/{email_id}/toggle')
            self._conf_carregar()
        except Exception as ex:
            messagebox.showerror('Erro', str(ex), parent=self)

    def _conf_add_credor(self):
        cnpj = simpledialog.askstring('Novo Credor', 'CPF/CNPJ:', parent=self)
        if not cnpj:
            return
        nome = simpledialog.askstring('Novo Credor', 'Nome do credor:', parent=self)
        try:
            self._conf_api_call('POST', 'credores',
                                json={'cpf_cnpj': cnpj.strip(), 'nome_credor': nome})
            self._conf_carregar()
        except Exception as ex:
            messagebox.showerror('Erro', str(ex), parent=self)

    def _conf_toggle_credor(self):
        sel = self._tv_cred.selection()
        if not sel:
            messagebox.showwarning('Aviso', 'Selecione um credor.', parent=self)
            return
        credor_id = self._tv_cred.item(sel[0])['values'][0]
        try:
            self._conf_api_call('PATCH', f'credores/{credor_id}/toggle')
            self._conf_carregar()
        except Exception as ex:
            messagebox.showerror('Erro', str(ex), parent=self)

    def _conf_add_exercicio(self):
        ano = simpledialog.askstring('Novo Exercício', 'Ano (ex: 2026):', parent=self)
        if not ano:
            return
        try:
            self._conf_api_call('POST', 'exercicios', json={'exercicio': ano.strip()})
            self._conf_carregar()
        except Exception as ex:
            messagebox.showerror('Erro', str(ex), parent=self)

    def _conf_toggle_exercicio(self):
        sel = self._tv_ex.selection()
        if not sel:
            messagebox.showwarning('Aviso', 'Selecione um exercício.', parent=self)
            return
        ex_id = self._tv_ex.item(sel[0])['values'][0]
        try:
            self._conf_api_call('PATCH', f'exercicios/{ex_id}/toggle')
            self._conf_carregar()
        except Exception as ex:
            messagebox.showerror('Erro', str(ex), parent=self)

    def _atualizar_perfis(self):
        for w in self._frame_checks.winfo_children():
            w.destroy()
        self._perfis_vars = []

        perfis = listar_perfis()
        if perfis:
            self._lbl_vazio.pack_forget()
            for p in perfis:
                var = tk.BooleanVar(value=True)
                cb = tk.Checkbutton(
                    self._frame_checks,
                    text=f"{p['nome']}  ({p['portal']})",
                    variable=var,
                    font=('Segoe UI', 9),
                    anchor='w',
                )
                cb.pack(fill='x', pady=1)
                self._perfis_vars.append((var, p))
        else:
            self._lbl_vazio.pack(padx=8, anchor='w')

    def _abrir_config(self):
        senha = simpledialog.askstring('Autenticacao', 'Senha:', show='*', parent=self)
        if senha is None:
            return
        if senha != _SENHA_CONFIG:
            messagebox.showerror('Acesso negado', 'Senha incorreta.')
            return
        dlg = DialogConfiguracoes(self)
        self.wait_window(dlg)
        self._atualizar_perfis()

    def _log_write(self, msg: str):
        self._log.config(state='normal')
        self._log.insert('end', msg + '\n')
        self._log.see('end')
        self._log.config(state='disabled')

    def _limpar_log(self):
        self._log.config(state='normal')
        self._log.delete('1.0', 'end')
        self._log.config(state='disabled')

    def _atualizar_progress(self, atual: int, total: int):
        self._progress['maximum'] = total
        self._progress['value']   = atual
        self._lbl_progress.config(text=f'{atual} / {total}')

    def _disparar_municipal(self):
        self._btn_mun.config(state=tk.DISABLED)
        threading.Thread(
            target=disparar_scraper,
            args=('portal-municipal-manaus', _API_KEYS['portal_municipal_manaus'],
                  self._log_write, self._btn_mun),
            daemon=True,
        ).start()

    def _disparar_estado(self):
        self._btn_est.config(state=tk.DISABLED)
        threading.Thread(
            target=disparar_scraper,
            args=('portal-estado-am', _API_KEYS['portal_estado_am'],
                  self._log_write, self._btn_est),
            daemon=True,
        ).start()

    def _iniciar(self):
        perfis_selecionados = [p for var, p in self._perfis_vars if var.get()]
        if not perfis_selecionados:
            messagebox.showwarning('Aviso', 'Selecione ao menos um perfil.')
            return
        self._btn.config(state=tk.DISABLED)
        self._limpar_log()
        self._progress['value'] = 0
        self._lbl_progress.config(text='')
        threading.Thread(
            target=processar,
            args=(perfis_selecionados, self._log_write, self._atualizar_progress, self._btn),
            daemon=True,
        ).start()


if __name__ == '__main__':
    app = App()
    app.mainloop()

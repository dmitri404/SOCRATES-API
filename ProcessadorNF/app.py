"""
app.py — Processador de Notas Fiscais
Le PDFs de pasta SMB e envia para a Portal API.
"""

import configparser
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from extractor import extrair_dados
from pdf_reader import extrair_texto
from supabase_client import SupabaseClient

# Credenciais da API — hardcoded, não expostas ao usuário
_API_URL     = 'http://187.77.240.80:9000'
_API_KEY     = 'aris-22386d82643aa6e36b12688a7175698d'

# Senha de acesso às configurações
_SENHA_CONFIG = 'tambaqui@'

CONFIG_FILE = Path.home() / 'AppData' / 'Roaming' / 'ProcessadorNF' / 'conf.ini'
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def carregar_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding='utf-8')
    return cfg


def salvar_config(path: str, usuario: str, senha: str) -> None:
    cfg = configparser.ConfigParser()
    cfg['SMB'] = {'path': path, 'usuario': usuario, 'senha': senha}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        cfg.write(f)


def autenticar_smb(path: str, usuario: str, senha: str) -> None:
    partes = path.lstrip('\\').split('\\')
    unc = f'\\\\{partes[0]}\\{partes[1]}' if len(partes) >= 2 else path
    subprocess.run(
        ['net', 'use', unc, f'/user:{usuario}', senha],
        capture_output=True, text=True,
    )


def processar(log_fn, progress_fn, btn):
    try:
        cfg      = carregar_config()
        smb_path = cfg['SMB']['path']
        usuario  = cfg['SMB']['usuario']
        senha    = cfg['SMB']['senha']
    except Exception as e:
        log_fn(f'ERRO ao ler configuracoes: {e}')
        log_fn('Acesse Configuracoes para definir a pasta SMB.')
        btn.config(state=tk.NORMAL)
        return

    log_fn('Autenticando na rede...')
    autenticar_smb(smb_path, usuario, senha)

    pasta = Path(smb_path)
    if not pasta.exists():
        log_fn(f'ERRO: pasta nao encontrada: {smb_path}')
        btn.config(state=tk.NORMAL)
        return

    pdfs = [p for p in pasta.rglob('*.pdf')
            if not any(x in p.parts for x in ('processados', 'erro'))]

    if not pdfs:
        log_fn('Nenhum PDF encontrado na pasta.')
        btn.config(state=tk.NORMAL)
        return

    log_fn(f'{len(pdfs)} PDF(s) encontrado(s).')
    progress_fn(0, len(pdfs))

    log_fn('Conectando ao servidor...')
    try:
        db = SupabaseClient(_API_URL, _API_KEY, '')
        db.carregar_numeros_existentes()
        log_fn(f'Cache carregado: {len(db._numeros_cache)} nota(s) existentes.')
    except Exception as e:
        log_fn(f'ERRO ao conectar servidor: {e}')
        btn.config(state=tk.NORMAL)
        return

    pasta_proc = pasta / 'processados'
    pasta_erro = pasta / 'erro'
    pasta_proc.mkdir(exist_ok=True)
    pasta_erro.mkdir(exist_ok=True)

    inseridos  = 0
    duplicatas = 0
    erros      = 0

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
                log_fn(f'[{i}/{len(pdfs)}] OK: {pdf.name} | Nota {dados["NumeroNota"]} | R$ {dados["ValorLiquido"]}')
            else:
                duplicatas += 1
                log_fn(f'[{i}/{len(pdfs)}] DUPLICATA: {pdf.name}')

            shutil.move(str(pdf), str(pasta_proc / pdf.name))

        except Exception as e:
            erros += 1
            log_fn(f'[{i}/{len(pdfs)}] ERRO: {pdf.name} — {e}')
            try:
                shutil.move(str(pdf), str(pasta_erro / pdf.name))
            except Exception:
                pass

    log_fn('-' * 50)
    log_fn(f'Concluido: {inseridos} inserido(s) | {duplicatas} duplicata(s) | {erros} erro(s)')
    progress_fn(len(pdfs), len(pdfs))
    btn.config(state=tk.NORMAL)


class DialogConfiguracoes(tk.Toplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.title('Configuracoes')
        self.resizable(False, False)
        self.grab_set()

        pad = {'padx': 12, 'pady': 6}

        tk.Label(self, text='Configuracoes SMB', font=('Segoe UI', 11, 'bold')).pack(**pad)

        frame = tk.Frame(self)
        frame.pack(padx=12, pady=4, fill='x')

        tk.Label(frame, text='Pasta SMB:', anchor='w', font=('Segoe UI', 9)).grid(row=0, column=0, sticky='w', pady=4)
        self._path = tk.Entry(frame, width=45, font=('Segoe UI', 9))
        self._path.grid(row=0, column=1, padx=8, pady=4)

        tk.Label(frame, text='Usuario:', anchor='w', font=('Segoe UI', 9)).grid(row=1, column=0, sticky='w', pady=4)
        self._usuario = tk.Entry(frame, width=45, font=('Segoe UI', 9))
        self._usuario.grid(row=1, column=1, padx=8, pady=4)

        tk.Label(frame, text='Senha:', anchor='w', font=('Segoe UI', 9)).grid(row=2, column=0, sticky='w', pady=4)
        self._senha = tk.Entry(frame, width=45, font=('Segoe UI', 9), show='*')
        self._senha.grid(row=2, column=1, padx=8, pady=4)

        # Preenche com valores atuais
        try:
            cfg = carregar_config()
            self._path.insert(0, cfg.get('SMB', 'path', fallback=''))
            self._usuario.insert(0, cfg.get('SMB', 'usuario', fallback=''))
            self._senha.insert(0, cfg.get('SMB', 'senha', fallback=''))
        except Exception:
            pass

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text='Salvar', font=('Segoe UI', 10, 'bold'),
                  bg='#2563eb', fg='white', relief='flat', padx=16, pady=6,
                  command=self._salvar).pack(side='left', padx=6)
        tk.Button(btn_frame, text='Cancelar', font=('Segoe UI', 10),
                  relief='flat', padx=16, pady=6,
                  command=self.destroy).pack(side='left', padx=6)

    def _salvar(self):
        path    = self._path.get().strip()
        usuario = self._usuario.get().strip()
        senha   = self._senha.get()
        if not path or not usuario or not senha:
            messagebox.showwarning('Aviso', 'Preencha todos os campos.', parent=self)
            return
        salvar_config(path, usuario, senha)
        messagebox.showinfo('Sucesso', 'Configuracoes salvas.', parent=self)
        self.destroy()


class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('Processador de Notas Fiscais')
        self.resizable(False, False)
        self._build_ui()
        self._carregar_info_config()

    def _build_ui(self):
        pad = {'padx': 12, 'pady': 6}

        tk.Label(self, text='Processador de Notas Fiscais',
                 font=('Segoe UI', 13, 'bold')).pack(**pad)

        frame_cfg = tk.LabelFrame(self, text='Configuracao', font=('Segoe UI', 9))
        frame_cfg.pack(fill='x', padx=12, pady=4)

        self._lbl_smb = tk.Label(frame_cfg, text='', anchor='w', font=('Segoe UI', 9))
        self._lbl_smb.pack(fill='x', padx=8, pady=2)

        tk.Button(frame_cfg, text='⚙ Configuracoes', font=('Segoe UI', 8),
                  relief='flat', cursor='hand2',
                  command=self._abrir_config).pack(anchor='e', padx=8, pady=4)

        self._progress = ttk.Progressbar(self, length=460, mode='determinate')
        self._progress.pack(**pad)
        self._lbl_progress = tk.Label(self, text='', font=('Segoe UI', 8))
        self._lbl_progress.pack()

        self._btn = tk.Button(
            self, text='Processar PDFs',
            font=('Segoe UI', 11, 'bold'),
            bg='#2563eb', fg='white',
            activebackground='#1d4ed8',
            relief='flat', cursor='hand2',
            padx=20, pady=8,
            command=self._iniciar,
        )
        self._btn.pack(**pad)

        frame_log = tk.LabelFrame(self, text='Log', font=('Segoe UI', 9))
        frame_log.pack(fill='both', expand=True, padx=12, pady=4)
        self._log = scrolledtext.ScrolledText(
            frame_log, height=14, width=64,
            font=('Consolas', 9), state='disabled',
            wrap='word',
        )
        self._log.pack(padx=4, pady=4)

        tk.Button(self, text='Limpar log', font=('Segoe UI', 8),
                  command=self._limpar_log).pack(pady=(0, 8))

    def _carregar_info_config(self):
        try:
            cfg = carregar_config()
            self._lbl_smb.config(text=f"SMB: {cfg['SMB']['path']}")
        except Exception:
            self._lbl_smb.config(text='SMB: nao configurado')

    def _abrir_config(self):
        senha = simpledialog.askstring('Autenticacao', 'Senha:', show='*', parent=self)
        if senha is None:
            return
        if senha != _SENHA_CONFIG:
            messagebox.showerror('Acesso negado', 'Senha incorreta.')
            return
        dlg = DialogConfiguracoes(self)
        self.wait_window(dlg)
        self._carregar_info_config()

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

    def _iniciar(self):
        self._btn.config(state=tk.DISABLED)
        self._limpar_log()
        self._progress['value'] = 0
        self._lbl_progress.config(text='')
        threading.Thread(
            target=processar,
            args=(self._log_write, self._atualizar_progress, self._btn),
            daemon=True,
        ).start()


if __name__ == '__main__':
    app = App()
    app.mainloop()

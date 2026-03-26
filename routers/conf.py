import os
import re
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from auth import verificar_api_key
from routers.auth_rbac import usuario_atual

router = APIRouter(prefix="/conf", tags=["Configurações"])

# schema_bd, key_name (None = sem api_key legada), cpf_col, nome_cpf_col, email_tem_nome
_PORTAIS = {
    "municipal":     ("public",                "portal_municipal_manaus", "cpf_cnpj", "nome_credor", False),
    "estado-am":     ("portal_estado_am",      "portal_estado_am",        "cpf_cnpj", "nome_credor", False),
    "municipio-pvh": ("portal_municipio_pvh",  None,                      "cpf",      "nome",        True),
    "estado-ms":     ("portal_estado_ms",      "portal_estado_ms",        "cpf",      "nome",        True),
    "estado-ro":     ("portal_estado_ro",      "portal_estado_ro",        "cpf",      "nome",        True),
}


def _resolver_portal(portal: str) -> tuple:
    if portal not in _PORTAIS:
        raise HTTPException(status_code=404, detail="Portal não encontrado")
    return _PORTAIS[portal]


def _conectar(schema: str):
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "supabase-db"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=10,
        options=f"-c search_path={schema}",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def _autorizar(portal: str, x_api_key: Optional[str], authorization: Optional[str], pode_editar: bool = False):
    """Aceita JWT (Authorization: Bearer) ou API key legada (x-api-key)."""
    if authorization:
        usuario = usuario_atual(authorization)
        if usuario["role"] != "admin":
            # verifica acesso ao portal via rbac.tem_acesso()
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "supabase-db"),
                port=int(os.getenv("DB_PORT", "5432")),
                dbname=os.getenv("DB_NAME", "postgres"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD"),
                connect_timeout=10,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT rbac.tem_acesso(%s, %s, %s)", (usuario["id"], portal, pode_editar))
                    if not cur.fetchone()["tem_acesso"]:
                        raise HTTPException(status_code=403, detail="Sem permissão neste portal")
            finally:
                conn.close()
        return

    if x_api_key:
        schema, key_name, *_ = _PORTAIS.get(portal, (None, None))
        if key_name:
            verificar_api_key(key_name, x_api_key)
        return

    raise HTTPException(status_code=401, detail="Autenticação necessária")


# ── Modelos ───────────────────────────────────────────────────────────────────

class ConfGeralBody(BaseModel):
    url_base: str
    modo_limpar: bool = False

class EmailBody(BaseModel):
    email: str
    nome: Optional[str] = None
    ativo: bool = True

class CredorBody(BaseModel):
    cpf: str
    nome: Optional[str] = None
    ativo: bool = True

class ExercicioBody(BaseModel):
    exercicio: str
    ativo: bool = True

class CronBody(BaseModel):
    cron_expression: str


# ── Configuração Geral ────────────────────────────────────────────────────────

@router.get("/{portal}/geral")
def get_conf_geral(
    portal: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, url_base, modo_limpar FROM conf LIMIT 1")
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    return dict(row)


@router.put("/{portal}/geral")
def update_conf_geral(
    portal: str,
    body: ConfGeralBody,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conf SET url_base = %s, modo_limpar = %s, atualizado_em = NOW() WHERE id = 1",
                (body.url_base, body.modo_limpar),
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": "atualizado"}


# ── E-mails ───────────────────────────────────────────────────────────────────

@router.get("/{portal}/emails")
def listar_emails(
    portal: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization)
    schema, _, __, ___, email_tem_nome = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            if email_tem_nome:
                cur.execute("SELECT id, email, nome, ativo FROM conf_emails ORDER BY id")
            else:
                cur.execute("SELECT id, email, NULL AS nome, ativo FROM conf_emails ORDER BY id")
            rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.post("/{portal}/emails")
def adicionar_email(
    portal: str,
    body: EmailBody,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, _, __, ___, email_tem_nome = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            if email_tem_nome:
                cur.execute(
                    "INSERT INTO conf_emails (email, nome, ativo) VALUES (%s, %s, %s) RETURNING id",
                    (body.email, body.nome, body.ativo),
                )
            else:
                cur.execute(
                    "INSERT INTO conf_emails (email, ativo) VALUES (%s, %s) RETURNING id",
                    (body.email, body.ativo),
                )
            new_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()
    return {"status": "criado", "id": new_id}


@router.delete("/{portal}/emails/{email_id}")
def remover_email(
    portal: str,
    email_id: int,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conf_emails WHERE id = %s", (email_id,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "removido"}


@router.patch("/{portal}/emails/{email_id}/toggle")
def toggle_email(
    portal: str,
    email_id: int,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE conf_emails SET ativo = NOT ativo WHERE id = %s RETURNING ativo", (email_id,))
            row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    return {"status": "atualizado", "ativo": row["ativo"] if row else None}


# ── Credores ──────────────────────────────────────────────────────────────────

@router.get("/{portal}/credores")
def listar_credores(
    portal: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization)
    schema, _, cpf_col, nome_col, ___ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, {cpf_col} AS cpf, {nome_col} AS nome, ativo FROM conf_cpfs ORDER BY id")
            rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.post("/{portal}/credores")
def adicionar_credor(
    portal: str,
    body: CredorBody,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, _, cpf_col, nome_col, ___ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO conf_cpfs ({cpf_col}, {nome_col}, ativo) VALUES (%s, %s, %s) RETURNING id",
                (body.cpf, body.nome, body.ativo),
            )
            new_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()
    return {"status": "criado", "id": new_id}


@router.delete("/{portal}/credores/{credor_id}")
def remover_credor(
    portal: str,
    credor_id: int,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conf_cpfs WHERE id = %s", (credor_id,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "removido"}


@router.patch("/{portal}/credores/{credor_id}/toggle")
def toggle_credor(
    portal: str,
    credor_id: int,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE conf_cpfs SET ativo = NOT ativo WHERE id = %s RETURNING ativo", (credor_id,))
            row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    return {"status": "atualizado", "ativo": row["ativo"] if row else None}


# ── Exercícios ────────────────────────────────────────────────────────────────

@router.get("/{portal}/exercicios")
def listar_exercicios(
    portal: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, exercicio, ativo FROM conf_exercicios ORDER BY exercicio")
            rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.post("/{portal}/exercicios")
def adicionar_exercicio(
    portal: str,
    body: ExercicioBody,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conf_exercicios (exercicio, ativo) VALUES (%s, %s) RETURNING id",
                (body.exercicio, body.ativo),
            )
            new_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()
    return {"status": "criado", "id": new_id}


@router.delete("/{portal}/exercicios/{exercicio_id}")
def remover_exercicio(
    portal: str,
    exercicio_id: int,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conf_exercicios WHERE id = %s", (exercicio_id,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "removido"}


@router.patch("/{portal}/exercicios/{exercicio_id}/toggle")
def toggle_exercicio(
    portal: str,
    exercicio_id: int,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conf_exercicios SET ativo = NOT ativo WHERE id = %s RETURNING ativo",
                (exercicio_id,),
            )
            row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    return {"status": "atualizado", "ativo": row["ativo"] if row else None}


# ── Cron ──────────────────────────────────────────────────────────────────────

CRONTAB_PATH = "/var/spool/cron/crontabs/root"

_CRON_CONTAINER = {
    "municipal":     "portal-municipal-mao",
    "estado-am":     "portal-estado-am",
    "municipio-pvh": "portal-municipio-pvh",
    "estado-ms":     "portal-estado-ms",
    "estado-ro":     "portal-estado-ro",
}

_CRON_RE = re.compile(r"^(\S+\s+\S+\s+\S+\s+\S+\s+\S+)(\s+.*)$")


def _cron_valido(expr: str) -> bool:
    return bool(re.match(r"^\S+\s+\S+\s+\S+\s+\S+\s+\S+$", expr.strip()))


def _ler_crontab() -> list:
    try:
        with open(CRONTAB_PATH, "r") as f:
            return f.readlines()
    except FileNotFoundError:
        return []


def _escrever_crontab(linhas: list) -> None:
    with open(CRONTAB_PATH, "w") as f:
        f.writelines(linhas)


@router.get("/{portal}/cron")
def get_cron(
    portal: str,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization)
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cron_expression FROM conf LIMIT 1")
            row = cur.fetchone()
    finally:
        conn.close()
    return {"cron_expression": row["cron_expression"] if row else None}


@router.put("/{portal}/cron")
def update_cron(
    portal: str,
    body: CronBody,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _autorizar(portal, x_api_key, authorization, pode_editar=True)

    expr = body.cron_expression.strip()
    if not _cron_valido(expr):
        raise HTTPException(status_code=422, detail="Expressão cron inválida (esperado 5 campos)")

    container = _CRON_CONTAINER.get(portal)
    if not container:
        raise HTTPException(status_code=404, detail="Portal não mapeado para container")

    # Atualiza crontab
    linhas = _ler_crontab()
    nova_linha = None
    novas_linhas = []
    for linha in linhas:
        m = _CRON_RE.match(linha)
        if m and container in linha:
            nova_linha = expr + m.group(2)
            if not nova_linha.endswith("\n"):
                nova_linha += "\n"
            novas_linhas.append(nova_linha)
        else:
            novas_linhas.append(linha)

    if nova_linha is None:
        raise HTTPException(status_code=404, detail=f"Entrada cron para '{container}' não encontrada no crontab")

    _escrever_crontab(novas_linhas)

    # Persiste no banco
    schema, *_ = _resolver_portal(portal)
    conn = _conectar(schema)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE conf SET cron_expression = %s WHERE id = 1", (expr,))
        conn.commit()
    finally:
        conn.close()

    return {"status": "atualizado", "cron_expression": expr}

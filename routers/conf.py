import os
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

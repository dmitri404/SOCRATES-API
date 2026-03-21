import os
import psycopg2
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from auth import verificar_api_key

router = APIRouter(prefix="/conf", tags=["Configurações"])

_PORTAIS = {
    "municipal": ("public",           "portal_municipal_manaus"),
    "estado-am": ("portal_estado_am", "portal_estado_am"),
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
    )


class ConfGeralBody(BaseModel):
    url_base: str
    modo_limpar: bool = False


class EmailBody(BaseModel):
    email: str
    ativo: bool = True


class CredorBody(BaseModel):
    cpf_cnpj: str
    nome_credor: Optional[str] = None
    ativo: bool = True


class ExercicioBody(BaseModel):
    exercicio: str
    ativo: bool = True


# ── Configuração Geral ────────────────────────────────────────────────────────

@router.get("/{portal}/geral")
def get_conf_geral(portal: str, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute("SELECT id, url_base, modo_limpar FROM conf LIMIT 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    return {"id": row[0], "url_base": row[1], "modo_limpar": row[2]}


@router.put("/{portal}/geral")
def update_conf_geral(portal: str, body: ConfGeralBody, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute(
        "UPDATE conf SET url_base = %s, modo_limpar = %s, atualizado_em = NOW() WHERE id = 1",
        (body.url_base, body.modo_limpar),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "atualizado"}


# ── E-mails ───────────────────────────────────────────────────────────────────

@router.get("/{portal}/emails")
def listar_emails(portal: str, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute("SELECT id, email, ativo FROM conf_emails ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "email": r[1], "ativo": r[2]} for r in rows]


@router.post("/{portal}/emails")
def adicionar_email(portal: str, body: EmailBody, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conf_emails (email, ativo) VALUES (%s, %s) RETURNING id",
        (body.email, body.ativo),
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "criado", "id": new_id}


@router.patch("/{portal}/emails/{email_id}/toggle")
def toggle_email(portal: str, email_id: int, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute(
        "UPDATE conf_emails SET ativo = NOT ativo WHERE id = %s RETURNING ativo",
        (email_id,),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "atualizado", "ativo": row[0] if row else None}


# ── Credores ──────────────────────────────────────────────────────────────────

@router.get("/{portal}/credores")
def listar_credores(portal: str, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute("SELECT id, cpf_cnpj, nome_credor, ativo FROM conf_cpfs ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "cpf_cnpj": r[1], "nome_credor": r[2], "ativo": r[3]} for r in rows]


@router.post("/{portal}/credores")
def adicionar_credor(portal: str, body: CredorBody, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conf_cpfs (cpf_cnpj, nome_credor, ativo) VALUES (%s, %s, %s) RETURNING id",
        (body.cpf_cnpj, body.nome_credor, body.ativo),
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "criado", "id": new_id}


@router.delete("/{portal}/credores/{credor_id}")
def remover_credor(portal: str, credor_id: int, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute("DELETE FROM conf_cpfs WHERE id = %s", (credor_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "removido"}


@router.patch("/{portal}/credores/{credor_id}/toggle")
def toggle_credor(portal: str, credor_id: int, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute("UPDATE conf_cpfs SET ativo = NOT ativo WHERE id = %s RETURNING ativo", (credor_id,))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "atualizado", "ativo": row[0] if row else None}


# ── Exercícios ────────────────────────────────────────────────────────────────

@router.get("/{portal}/exercicios")
def listar_exercicios(portal: str, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute("SELECT id, exercicio, ativo FROM conf_exercicios ORDER BY exercicio")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "exercicio": r[1], "ativo": r[2]} for r in rows]


@router.post("/{portal}/exercicios")
def adicionar_exercicio(portal: str, body: ExercicioBody, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO conf_exercicios (exercicio, ativo) VALUES (%s, %s) RETURNING id",
        (body.exercicio, body.ativo),
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "criado", "id": new_id}


@router.delete("/{portal}/exercicios/{exercicio_id}")
def remover_exercicio(portal: str, exercicio_id: int, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute("DELETE FROM conf_exercicios WHERE id = %s", (exercicio_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "removido"}


@router.patch("/{portal}/exercicios/{exercicio_id}/toggle")
def toggle_exercicio(portal: str, exercicio_id: int, x_api_key: str = Header(...)):
    schema, key_name = _resolver_portal(portal)
    verificar_api_key(key_name, x_api_key)
    conn = _conectar(schema)
    cur = conn.cursor()
    cur.execute(
        "UPDATE conf_exercicios SET ativo = NOT ativo WHERE id = %s RETURNING ativo",
        (exercicio_id,),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "atualizado", "ativo": row[0] if row else None}

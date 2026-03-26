"""
Gestão de usuários — Sistema Socrates
Acessível por: admin (todas as operações), supervisor (apenas role 'usuario')
"""
import os
import secrets
import string
import psycopg2
import psycopg2.extras
import bcrypt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from routers.auth_rbac import requer_role

router = APIRouter(prefix="/admin", tags=["admin"])

_ROLES = {"admin": 1, "supervisor": 2, "usuario": 3}


def _conectar():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ── Modelos ───────────────────────────────────────────────────────────────────

class NovoUsuarioBody(BaseModel):
    usuario: str
    nome: str
    email: str
    role: str
    senha: str

class EditarUsuarioBody(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    ativo: Optional[bool] = None

class PortaisBody(BaseModel):
    portais: list


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/usuarios")
def listar_usuarios(atual=Depends(requer_role("admin", "supervisor"))):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.usuario, u.nome, u.email, r.nome AS role,
                       u.ativo, u.senha_temp, u.ultimo_login, u.criado_em,
                       COALESCE(
                           json_agg(
                               json_build_object(
                                   'slug',       p.slug,
                                   'nome',       p.nome,
                                   'pode_editar', up.pode_editar
                               ) ORDER BY p.id
                           ) FILTER (WHERE p.id IS NOT NULL), '[]'
                       ) AS portais
                FROM rbac.usuarios u
                JOIN rbac.roles r ON r.id = u.role_id
                LEFT JOIN rbac.usuario_portais up ON up.usuario_id = u.id
                LEFT JOIN rbac.portais p ON p.id = up.portal_id AND p.ativo = TRUE
                GROUP BY u.id, u.usuario, u.nome, u.email, r.nome,
                         u.ativo, u.senha_temp, u.ultimo_login, u.criado_em
                ORDER BY u.criado_em
            """)
            rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/portais")
def listar_portais(atual=Depends(requer_role("admin", "supervisor"))):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, slug, nome FROM rbac.portais WHERE ativo = TRUE ORDER BY id")
            rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.post("/usuarios")
def criar_usuario(body: NovoUsuarioBody, atual=Depends(requer_role("admin", "supervisor"))):
    role_id = _ROLES.get(body.role)
    if not role_id:
        raise HTTPException(status_code=422, detail="Role inválido")
    if atual["role"] == "supervisor" and body.role != "usuario":
        raise HTTPException(status_code=403, detail="Supervisor só pode criar usuários com role 'usuario'")

    senha_hash = bcrypt.hashpw(body.senha.encode(), bcrypt.gensalt(rounds=12)).decode()
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rbac.usuarios (usuario, nome, email, senha_hash, role_id, senha_temp, criado_por)
                VALUES (%s, %s, %s, %s, %s, TRUE, %s)
                RETURNING id
            """, (body.usuario, body.nome, body.email, senha_hash, role_id, atual["id"]))
            new_id = cur.fetchone()["id"]
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado")
    finally:
        conn.close()
    return {"status": "criado", "id": str(new_id)}


@router.patch("/usuarios/{usuario_id}")
def editar_usuario(usuario_id: str, body: EditarUsuarioBody, atual=Depends(requer_role("admin", "supervisor"))):
    fields, values = [], []
    if body.nome is not None:
        fields.append("nome = %s"); values.append(body.nome)
    if body.email is not None:
        fields.append("email = %s"); values.append(body.email)
    if body.role is not None:
        role_id = _ROLES.get(body.role)
        if not role_id:
            raise HTTPException(status_code=422, detail="Role inválido")
        if atual["role"] == "supervisor" and body.role != "usuario":
            raise HTTPException(status_code=403, detail="Supervisor só pode atribuir role 'usuario'")
        fields.append("role_id = %s"); values.append(role_id)
    if body.ativo is not None:
        fields.append("ativo = %s"); values.append(body.ativo)

    if not fields:
        return {"status": "sem alterações"}

    values.append(usuario_id)
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE rbac.usuarios SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()
    finally:
        conn.close()
    return {"status": "atualizado"}


@router.post("/usuarios/{usuario_id}/resetar-senha")
def resetar_senha(usuario_id: str, atual=Depends(requer_role("admin", "supervisor"))):
    chars = string.ascii_letters + string.digits
    nova_senha = ''.join(secrets.choice(chars) for _ in range(10))
    senha_hash = bcrypt.hashpw(nova_senha.encode(), bcrypt.gensalt(rounds=12)).decode()

    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rbac.usuarios SET senha_hash = %s, senha_temp = TRUE WHERE id = %s",
                (senha_hash, usuario_id)
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": "resetado", "senha_temp": nova_senha}


@router.put("/usuarios/{usuario_id}/portais")
def atribuir_portais(usuario_id: str, body: PortaisBody, atual=Depends(requer_role("admin", "supervisor"))):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rbac.usuario_portais WHERE usuario_id = %s", (usuario_id,))
            for p in body.portais:
                cur.execute("""
                    INSERT INTO rbac.usuario_portais (usuario_id, portal_id, pode_editar, atribuido_por)
                    SELECT %s, id, %s, %s FROM rbac.portais WHERE slug = %s
                """, (usuario_id, p.get("pode_editar", True), atual["id"], p["slug"]))
        conn.commit()
    finally:
        conn.close()
    return {"status": "atualizado"}

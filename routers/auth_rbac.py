"""
Autenticação JWT + RBAC — Sistema Socrates
"""
import os
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from jose import JWTError, jwt
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

JWT_SECRET      = os.environ.get("JWT_SECRET", "changeme")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", 8))


# ─── Modelos ────────────────────────────────────────────────────────────────

class LoginInput(BaseModel):
    usuario: str
    senha: str

class AlterarSenhaInput(BaseModel):
    senha_atual: str
    senha_nova: str


# ─── Banco ──────────────────────────────────────────────────────────────────

def _conectar():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ─── Dependência: usuário autenticado ────────────────────────────────────────

def usuario_atual(authorization: Optional[str] = Header(None)):
    """Extrai e valida o JWT do header Authorization: Bearer <token>."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token não fornecido")

    token = authorization.split(" ", 1)[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    token_hash = _hash_token(token)
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.email, u.nome, u.role_id, u.ativo, u.senha_temp,
                       r.nome AS role
                FROM rbac.sessoes s
                JOIN rbac.usuarios u ON u.id = s.usuario_id
                JOIN rbac.roles   r ON r.id = u.role_id
                WHERE s.token_hash = %s
                  AND s.revogada_em IS NULL
                  AND s.expira_em > NOW()
            """, (token_hash,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")
            if not row["ativo"]:
                raise HTTPException(status_code=403, detail="Usuário desativado")

            # Atualiza ultimo_uso da sessão
            cur.execute(
                "UPDATE rbac.sessoes SET ultimo_uso = NOW() WHERE token_hash = %s",
                (token_hash,)
            )
            conn.commit()
            return dict(row)
    finally:
        conn.close()


def requer_role(*roles: str):
    """Dependência que exige um dos roles informados."""
    def dep(usuario=Depends(usuario_atual)):
        if usuario["role"] not in roles:
            raise HTTPException(status_code=403, detail="Permissão insuficiente")
        return usuario
    return dep


def requer_portal(portal_slug: str, pode_editar: bool = False):
    """Dependência que verifica acesso do usuário a um portal específico."""
    def dep(usuario=Depends(usuario_atual)):
        if usuario["role"] == "admin":
            return usuario
        conn = _conectar()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rbac.tem_acesso(%s, %s, %s)",
                    (usuario["id"], portal_slug, pode_editar)
                )
                if not cur.fetchone()["tem_acesso"]:
                    raise HTTPException(status_code=403, detail="Sem permissão neste portal")
        finally:
            conn.close()
        return usuario
    return dep


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/login")
def login(body: LoginInput, request: Request):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, nome, role_id, senha_hash, ativo, senha_temp FROM rbac.usuarios WHERE usuario = %s",
                (body.usuario,)
            )
            usuario = cur.fetchone()

        if not usuario or not bcrypt.checkpw(body.senha.encode(), usuario["senha_hash"].encode()):
            raise HTTPException(status_code=401, detail="Email ou senha incorretos")

        if not usuario["ativo"]:
            raise HTTPException(status_code=403, detail="Usuário desativado")

        expira_em = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
        payload = {
            "sub":     str(usuario["id"]),
            "email":   usuario["email"],
            "role_id": usuario["role_id"],
            "exp":     expira_em,
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        token_hash = _hash_token(token)

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rbac.sessoes (usuario_id, token_hash, ip_origem, user_agent, expira_em)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                usuario["id"],
                token_hash,
                request.client.host if request.client else None,
                request.headers.get("user-agent"),
                expira_em,
            ))
            cur.execute(
                "UPDATE rbac.usuarios SET ultimo_login = NOW() WHERE id = %s",
                (usuario["id"],)
            )
            cur.execute("""
                INSERT INTO rbac.audit_log (usuario_id, acao, ip_origem, resultado)
                VALUES (%s, 'login', %s, 'ok')
            """, (usuario["id"], request.client.host if request.client else None))
            conn.commit()

        return {
            "access_token": token,
            "token_type":   "bearer",
            "expira_em":    expira_em.isoformat(),
            "senha_temp":   usuario["senha_temp"],
        }
    finally:
        conn.close()


@router.post("/logout")
def logout(authorization: Optional[str] = Header(None), usuario=Depends(usuario_atual)):
    token = authorization.split(" ", 1)[1]
    token_hash = _hash_token(token)
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rbac.sessoes SET revogada_em = NOW() WHERE token_hash = %s",
                (token_hash,)
            )
            cur.execute("""
                INSERT INTO rbac.audit_log (usuario_id, acao, resultado)
                VALUES (%s, 'logout', 'ok')
            """, (usuario["id"],))
            conn.commit()
    finally:
        conn.close()
    return {"detail": "Sessão encerrada"}


@router.get("/me")
def me(usuario=Depends(usuario_atual)):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            # Portais acessíveis
            if usuario["role"] == "admin":
                cur.execute("SELECT slug, nome FROM rbac.portais WHERE ativo = TRUE ORDER BY id")
                portais = [{"slug": r["slug"], "nome": r["nome"], "pode_editar": True} for r in cur.fetchall()]
            else:
                cur.execute("""
                    SELECT p.slug, p.nome, up.pode_editar
                    FROM rbac.usuario_portais up
                    JOIN rbac.portais p ON p.id = up.portal_id
                    WHERE up.usuario_id = %s AND p.ativo = TRUE
                    ORDER BY p.id
                """, (usuario["id"],))
                portais = [dict(r) for r in cur.fetchall()]

        return {
            "id":         str(usuario["id"]),
            "email":      usuario["email"],
            "nome":       usuario["nome"],
            "role":       usuario["role"],
            "senha_temp": usuario["senha_temp"],
            "portais":    portais,
        }
    finally:
        conn.close()


@router.post("/alterar-senha")
def alterar_senha(body: AlterarSenhaInput, usuario=Depends(usuario_atual)):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT senha_hash FROM rbac.usuarios WHERE id = %s",
                (usuario["id"],)
            )
            row = cur.fetchone()

        if not bcrypt.checkpw(body.senha_atual.encode(), row["senha_hash"].encode()):
            raise HTTPException(status_code=400, detail="Senha atual incorreta")

        novo_hash = bcrypt.hashpw(body.senha_nova.encode(), bcrypt.gensalt(rounds=12)).decode()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE rbac.usuarios SET senha_hash = %s, senha_temp = FALSE WHERE id = %s
            """, (novo_hash, usuario["id"]))
            conn.commit()
    finally:
        conn.close()
    return {"detail": "Senha alterada com sucesso"}

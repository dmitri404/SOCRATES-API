"""
Router FastAPI – Portal Estado RO
Prefixo: /portal-estado-ro
"""
import os
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Header, HTTPException, Query
from typing import Optional

from auth import verificar_api_key

router = APIRouter(prefix="/portal-estado-ro", tags=["portal-estado-ro"])


def _conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "supabase-db"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=10,
    )


# ────────────────────────────────────────────────────────────────
# RESUMO
# ────────────────────────────────────────────────────────────────
@router.get("/resumo")
def resumo(x_api_key: str = Header(...)):
    verificar_api_key("portal_estado_ro", x_api_key)
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM portal_estado_ro.empenhos")
            total_empenhos = cur.fetchone()[0]

            cur.execute("""
                SELECT exercicio, COUNT(*) AS qtd,
                       SUM(valor_empenhado) AS empenhado,
                       SUM(valor_pago)      AS pago
                FROM portal_estado_ro.empenhos
                GROUP BY exercicio
                ORDER BY exercicio
            """)
            por_exercicio = [
                {"exercicio": r[0], "qtd": r[1],
                 "empenhado": float(r[2] or 0), "pago": float(r[3] or 0)}
                for r in cur.fetchall()
            ]

            cur.execute("""
                SELECT status, COUNT(*) FROM portal_estado_ro.execucao_logs
                WHERE iniciado_em >= NOW() - INTERVAL '30 days'
                GROUP BY status
            """)
            logs_30d = {r[0]: r[1] for r in cur.fetchall()}

        return {
            "total_empenhos": total_empenhos,
            "por_exercicio":  por_exercicio,
            "logs_30_dias":   logs_30d,
        }
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# EMPENHOS
# ────────────────────────────────────────────────────────────────
@router.get("/empenhos")
def listar_empenhos(
    exercicio:       Optional[str] = Query(None),
    num_ne:          Optional[str] = Query(None),
    unidade_gestora: Optional[str] = Query(None),
    credor:          Optional[str] = Query(None),
    limit:           int           = Query(100, le=1000),
    offset:          int           = Query(0),
    x_api_key:       str           = Header(...),
):
    verificar_api_key("portal_estado_ro", x_api_key)
    conn = _conectar()
    try:
        filtros, params = [], []
        if exercicio:
            filtros.append("exercicio = %s"); params.append(exercicio)
        if num_ne:
            filtros.append("num_ne ILIKE %s"); params.append(f"%{num_ne}%")
        if unidade_gestora:
            filtros.append("unidade_gestora ILIKE %s"); params.append(f"%{unidade_gestora}%")
        if credor:
            filtros.append("credor ILIKE %s"); params.append(f"%{credor}%")

        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        params += [limit, offset]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT * FROM portal_estado_ro.empenhos
                {where}
                ORDER BY criado_em DESC
                LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()

        return {"total": len(rows), "data": [dict(r) for r in rows]}
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# LOGS DE EXECUCAO
# ────────────────────────────────────────────────────────────────
@router.get("/logs")
def listar_logs(
    limit:     int = Query(50, le=500),
    offset:    int = Query(0),
    x_api_key: str = Header(...),
):
    verificar_api_key("portal_estado_ro", x_api_key)
    conn = _conectar()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM portal_estado_ro.execucao_logs
                ORDER BY iniciado_em DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            rows = cur.fetchall()
        return {"total": len(rows), "data": [dict(r) for r in rows]}
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# CONFIGURACAO
# ────────────────────────────────────────────────────────────────
@router.get("/conf")
def listar_conf(x_api_key: str = Header(...)):
    verificar_api_key("portal_estado_ro", x_api_key)
    conn = _conectar()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM portal_estado_ro.conf")
            rows = cur.fetchall()
        return {"data": [dict(r) for r in rows]}
    finally:
        conn.close()

"""
Router FastAPI – Portal Estado MS
Prefixo: /portal-estado-ms
"""
import os
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Header, HTTPException, Query
from typing import Optional

from auth import verificar_api_key

router = APIRouter(prefix="/portal-estado-ms", tags=["portal-estado-ms"])


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
    verificar_api_key("portal_estado_ms", x_api_key)
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM portal_estado_ms.empenhos")
            total_empenhos = cur.fetchone()[0]

            cur.execute("""
                SELECT exercicio, mes, COUNT(*) AS qtd,
                       SUM(empenhado) AS empenhado,
                       SUM(liquidado) AS liquidado,
                       SUM(pago)      AS pago
                FROM portal_estado_ms.empenhos
                GROUP BY exercicio, mes
                ORDER BY exercicio, mes
            """)
            por_periodo = [
                {"exercicio": r[0], "mes": r[1], "qtd": r[2],
                 "empenhado": float(r[3] or 0), "liquidado": float(r[4] or 0), "pago": float(r[5] or 0)}
                for r in cur.fetchall()
            ]

            cur.execute("""
                SELECT status, COUNT(*) FROM portal_estado_ms.execucao_logs
                WHERE iniciado_em >= NOW() - INTERVAL '30 days'
                GROUP BY status
            """)
            logs_30d = {r[0]: r[1] for r in cur.fetchall()}

        return {
            "total_empenhos": total_empenhos,
            "por_periodo":    por_periodo,
            "logs_30_dias":   logs_30d,
        }
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# EMPENHOS
# ────────────────────────────────────────────────────────────────
@router.get("/empenhos")
def listar_empenhos(
    exercicio:    Optional[str] = Query(None),
    mes:          Optional[str] = Query(None),
    num_ne:       Optional[str] = Query(None),
    ug_nome:      Optional[str] = Query(None),
    num_processo: Optional[str] = Query(None),
    limit:        int           = Query(100, le=1000),
    offset:       int           = Query(0),
    x_api_key:    str           = Header(...),
):
    verificar_api_key("portal_estado_ms", x_api_key)
    conn = _conectar()
    try:
        filtros, params = [], []
        if exercicio:
            filtros.append("exercicio = %s"); params.append(exercicio)
        if mes:
            filtros.append("mes = %s"); params.append(mes)
        if num_ne:
            filtros.append("num_ne ILIKE %s"); params.append(f"%{num_ne}%")
        if ug_nome:
            filtros.append("ug_nome ILIKE %s"); params.append(f"%{ug_nome}%")
        if num_processo:
            filtros.append("num_processo ILIKE %s"); params.append(f"%{num_processo}%")

        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        params += [limit, offset]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT * FROM portal_estado_ms.empenhos
                {where}
                ORDER BY criado_em DESC
                LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()

        return {"total": len(rows), "data": [dict(r) for r in rows]}
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# DOCUMENTOS DO NE
# ────────────────────────────────────────────────────────────────
@router.get("/ne-documentos")
def listar_ne_documentos(
    num_ne:    Optional[str] = Query(None),
    tipo:      Optional[str] = Query(None),
    limit:     int           = Query(100, le=1000),
    offset:    int           = Query(0),
    x_api_key: str           = Header(...),
):
    verificar_api_key("portal_estado_ms", x_api_key)
    conn = _conectar()
    try:
        filtros, params = [], []
        if num_ne:
            filtros.append("num_ne ILIKE %s"); params.append(f"%{num_ne}%")
        if tipo:
            filtros.append("tipo ILIKE %s"); params.append(f"%{tipo}%")

        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        params += [limit, offset]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT * FROM portal_estado_ms.ne_documentos
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
    verificar_api_key("portal_estado_ms", x_api_key)
    conn = _conectar()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM portal_estado_ms.execucao_logs
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
    verificar_api_key("portal_estado_ms", x_api_key)
    conn = _conectar()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM portal_estado_ms.conf ORDER BY chave")
            rows = cur.fetchall()
        return {"data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.put("/conf/{chave}")
def atualizar_conf(chave: str, valor: str, x_api_key: str = Header(...)):
    verificar_api_key("portal_estado_ms", x_api_key)
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE portal_estado_ms.conf
                SET valor = %s, atualizado_em = NOW()
                WHERE chave = %s
            """, (valor, chave))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Chave '{chave}' nao encontrada")
        return {"ok": True, "chave": chave, "valor": valor}
    finally:
        conn.close()

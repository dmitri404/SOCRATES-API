"""
Router FastAPI – Portal Estado AM
Prefixo: /portal-estado-am
Copiar para: api/routers/portal_estado_am.py
"""
import os
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from auth import verificar_api_key

router = APIRouter(prefix="/portal-estado-am", tags=["portal-estado-am"])


def _conectar():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


# ────────────────────────────────────────────────────────────────
# PAGAMENTOS
# ────────────────────────────────────────────────────────────────
@router.get("/pagamentos")
def listar_pagamentos(
    exercicio: Optional[str] = Query(None),
    mes:       Optional[str] = Query(None),
    orgao:     Optional[str] = Query(None),
    num_ob:    Optional[str] = Query(None),
    limit:     int           = Query(100, le=1000),
    offset:    int           = Query(0),
    _: str = Depends(verificar_api_key),
):
    conn = _conectar()
    try:
        filtros = []
        params  = []
        if exercicio:
            filtros.append("exercicio = %s"); params.append(exercicio)
        if mes:
            filtros.append("mes = %s"); params.append(mes)
        if orgao:
            filtros.append("orgao ILIKE %s"); params.append(f"%{orgao}%")
        if num_ob:
            filtros.append("num_ob = %s"); params.append(num_ob)

        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        params += [limit, offset]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT * FROM portal_estado_am.pagamentos
                {where}
                ORDER BY criado_em DESC
                LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()

        return {"total": len(rows), "data": [dict(r) for r in rows]}
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# NL / ITENS
# ────────────────────────────────────────────────────────────────
@router.get("/nl-itens")
def listar_nl_itens(
    exercicio: Optional[str] = Query(None),
    mes:       Optional[str] = Query(None),
    num_nl:    Optional[str] = Query(None),
    num_ne:    Optional[str] = Query(None),
    limit:     int           = Query(100, le=1000),
    offset:    int           = Query(0),
    _: str = Depends(verificar_api_key),
):
    conn = _conectar()
    try:
        filtros = []
        params  = []
        if exercicio:
            filtros.append("exercicio = %s"); params.append(exercicio)
        if mes:
            filtros.append("mes = %s"); params.append(mes)
        if num_nl:
            filtros.append("num_nl = %s"); params.append(num_nl)
        if num_ne:
            filtros.append("num_empenho = %s"); params.append(num_ne)

        where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
        params += [limit, offset]

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT * FROM portal_estado_am.nl_itens
                {where}
                ORDER BY criado_em DESC
                LIMIT %s OFFSET %s
            """, params)
            rows = cur.fetchall()

        return {"total": len(rows), "data": [dict(r) for r in rows]}
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# LOGS DE EXECUÇÃO
# ────────────────────────────────────────────────────────────────
@router.get("/logs")
def listar_logs(
    limit:  int = Query(50, le=500),
    offset: int = Query(0),
    _: str = Depends(verificar_api_key),
):
    conn = _conectar()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM portal_estado_am.execucao_logs
                ORDER BY iniciado_em DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            rows = cur.fetchall()
        return {"total": len(rows), "data": [dict(r) for r in rows]}
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ────────────────────────────────────────────────────────────────
@router.get("/conf")
def listar_conf(_: str = Depends(verificar_api_key)):
    conn = _conectar()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM portal_estado_am.conf ORDER BY chave")
            rows = cur.fetchall()
        return {"data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.put("/conf/{chave}")
def atualizar_conf(chave: str, valor: str, _: str = Depends(verificar_api_key)):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE portal_estado_am.conf
                SET valor = %s, atualizado_em = NOW()
                WHERE chave = %s
            """, (valor, chave))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Chave '{chave}' não encontrada")
        return {"ok": True, "chave": chave, "valor": valor}
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# RESUMO
# ────────────────────────────────────────────────────────────────
@router.get("/resumo")
def resumo(_: str = Depends(verificar_api_key)):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM portal_estado_am.pagamentos")
            total_pag = cur.fetchone()[0]

            cur.execute("SELECT COUNT(DISTINCT num_nl) FROM portal_estado_am.nl_itens WHERE num_nl IS NOT NULL")
            total_nl = cur.fetchone()[0]

            cur.execute("""
                SELECT exercicio, mes, COUNT(*) as qtd
                FROM portal_estado_am.pagamentos
                GROUP BY exercicio, mes
                ORDER BY exercicio, mes
            """)
            por_periodo = [{"exercicio": r[0], "mes": r[1], "qtd": r[2]} for r in cur.fetchall()]

            cur.execute("""
                SELECT status, COUNT(*) FROM portal_estado_am.execucao_logs
                WHERE iniciado_em >= NOW() - INTERVAL '30 days'
                GROUP BY status
            """)
            logs_30d = {r[0]: r[1] for r in cur.fetchall()}

        return {
            "total_pagamentos": total_pag,
            "total_nl":         total_nl,
            "por_periodo":      por_periodo,
            "logs_30_dias":     logs_30d,
        }
    finally:
        conn.close()

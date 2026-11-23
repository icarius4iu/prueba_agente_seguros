"""
Backend HTTP (FastAPI) para la PWA de Seguros Horizonte S.A.

Expone dos portales autenticados sobre el mismo agente de IA y capa de datos
(BigQuery en producción / DuckDB en local):
1. Portal Cliente: login por DNI + nombre completo (demo) validado contra `clientes`,
   con sesión firmada en servidor (HMAC-SHA256 en cookie HttpOnly) que inyecta
   `rol='cliente'` y `usuario_id=cliente_id` de forma inmutable al agente.
2. Portal Asesor / Admin: login contra `asesores` (`ASE01`, `ASE02` o correo) con acceso
   al asistente en modo asesor, monitor de chats de clientes, alertas de seguridad y tickets.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.agent import AgenteSeguros
from src.config import (
    APP_SECRET_KEY,
    BIGQUERY_DATASET,
    BIGQUERY_LOGS_DATASET,
    DB_BACKEND,
    FECHA_REFERENCIA,
    GCP_PROJECT_ID,
    GEMINI_MODEL,
    WEB_DIR,
)
from src.database import obtener_repositorio
from src.logger import (
    listar_interacciones,
    listar_tickets,
    obtener_metricas_auditoria,
)

SESSION_COOKIE = "sh_session"
SESSION_TTL_SECONDS = 12 * 3600

app = FastAPI(
    title="Seguros Horizonte S.A. — Asistente PWA",
    version="1.0.0",
    description="PWA de atención de pólizas y siniestros con agente Gemini + BigQuery/DuckDB.",
)

_agente = AgenteSeguros()


# ---------------------------------------------------------------------------
# Tokens de sesión firmados (HMAC-SHA256, stateless -> listo para Cloud Run)
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def crear_token_sesion(payload: dict[str, Any]) -> str:
    cuerpo = dict(payload)
    cuerpo["exp"] = int(time.time()) + SESSION_TTL_SECONDS
    raw = json.dumps(cuerpo, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    encoded = _b64url_encode(raw)
    firma = hmac.new(
        APP_SECRET_KEY.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded}.{_b64url_encode(firma)}"


def verificar_token_sesion(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    try:
        encoded, firma_b64 = token.split(".", 1)
        esperada = hmac.new(
            APP_SECRET_KEY.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        recibida = _b64url_decode(firma_b64)
        if not hmac.compare_digest(esperada, recibida):
            return None
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def _extraer_token(request: Request) -> str | None:
    cookie_tok = request.cookies.get(SESSION_COOKIE)
    if cookie_tok:
        return cookie_tok
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def obtener_sesion_actual(request: Request) -> dict[str, Any]:
    sesion = verificar_token_sesion(_extraer_token(request))
    if not sesion:
        raise HTTPException(status_code=401, detail="Sesión no autenticada o expirada.")
    return sesion


def requerir_cliente(sesion: dict[str, Any] = Depends(obtener_sesion_actual)) -> dict[str, Any]:
    if sesion.get("rol") != "cliente":
        raise HTTPException(status_code=403, detail="Este endpoint es exclusivo para clientes.")
    return sesion


def requerir_asesor(sesion: dict[str, Any] = Depends(obtener_sesion_actual)) -> dict[str, Any]:
    if sesion.get("rol") != "asesor":
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado: se requiere una sesión de asesor comercial / administrador.",
        )
    return sesion


def _fijar_cookie_sesion(response: Response, token: str, request: Request) -> None:
    es_https = (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=es_https,
        path="/",
    )


# ---------------------------------------------------------------------------
# Esquemas de entrada
# ---------------------------------------------------------------------------

class LoginClienteRequest(BaseModel):
    dni: str = Field(..., min_length=6, max_length=15)
    nombre_completo: str = Field(..., min_length=3, max_length=120)


class LoginAsesorRequest(BaseModel):
    identificador: str = Field(..., min_length=3, max_length=120)


class ChatRequest(BaseModel):
    consulta: str = Field(..., min_length=1, max_length=2000)


# ---------------------------------------------------------------------------
# Endpoints de infraestructura y salud
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check() -> dict[str, Any]:
    repo = obtener_repositorio()
    estado_db = await asyncio.to_thread(repo.verificar_conexion)
    return {
        "status": "ok" if estado_db.get("ok") else "degraded",
        "db_backend": DB_BACKEND,
        "db": estado_db,
        "gcp_project": GCP_PROJECT_ID or None,
        "dataset": BIGQUERY_DATASET if DB_BACKEND == "bigquery" else "seguros_horizonte.duckdb",
        "logs_dataset": BIGQUERY_LOGS_DATASET if DB_BACKEND == "bigquery" else "salidas/logs/*.jsonl",
        "modelo": _agente.model_name,
        "modo_online": _agente.modo_online,
        "fecha_referencia": FECHA_REFERENCIA,
    }


# ---------------------------------------------------------------------------
# Endpoints de autenticación
# ---------------------------------------------------------------------------

@app.post("/api/auth/cliente")
async def login_cliente(
    body: LoginClienteRequest, request: Request, response: Response
) -> dict[str, Any]:
    repo = obtener_repositorio()
    cliente = await asyncio.to_thread(
        repo.autenticar_cliente, body.dni, body.nombre_completo
    )
    if not cliente:
        raise HTTPException(
            status_code=401,
            detail="No se encontró un titular con ese DNI y nombre completo. Verifica los datos e intenta nuevamente.",
        )

    nombre = f"{cliente['nombres']} {cliente['apellidos']}".strip()
    payload = {
        "rol": "cliente",
        "usuario_id": cliente["cliente_id"],
        "nombre": nombre,
        "dni": str(cliente.get("dni", "")),
        "email": cliente.get("email", ""),
        "distrito": cliente.get("distrito", ""),
    }
    token = crear_token_sesion(payload)
    _fijar_cookie_sesion(response, token, request)
    return {"exito": True, "usuario": payload, "token": token}


@app.post("/api/auth/asesor")
async def login_asesor(
    body: LoginAsesorRequest, request: Request, response: Response
) -> dict[str, Any]:
    repo = obtener_repositorio()
    asesor = await asyncio.to_thread(repo.autenticar_asesor, body.identificador)
    if not asesor:
        raise HTTPException(
            status_code=401,
            detail="Asesor no encontrado. Ingresa un ID válido (ej. ASE01 o ASE02) o correo corporativo.",
        )

    nombre = f"{asesor['nombres']} {asesor['apellidos']}".strip()
    payload = {
        "rol": "asesor",
        "usuario_id": asesor["asesor_id"],
        "nombre": nombre,
        "cargo": asesor.get("rol", "asesor_comercial"),
        "email": asesor.get("email", ""),
    }
    token = crear_token_sesion(payload)
    _fijar_cookie_sesion(response, token, request)
    return {"exito": True, "usuario": payload, "token": token}


@app.post("/api/auth/logout")
async def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"exito": True}


@app.get("/api/auth/me")
async def obtener_perfil(sesion: dict[str, Any] = Depends(obtener_sesion_actual)) -> dict[str, Any]:
    usuario = {k: v for k, v in sesion.items() if k != "exp"}
    return {"autenticado": True, "usuario": usuario}


# ---------------------------------------------------------------------------
# Endpoints de chat y contexto del cliente
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def enviar_mensaje_chat(
    body: ChatRequest, sesion: dict[str, Any] = Depends(obtener_sesion_actual)
) -> dict[str, Any]:
    consulta = body.consulta.strip()
    if not consulta:
        raise HTTPException(status_code=400, detail="La consulta no puede estar vacía.")

    resultado = await asyncio.to_thread(
        _agente.responder,
        consulta=consulta,
        rol=sesion["rol"],
        usuario_id=sesion["usuario_id"],
    )
    log_entry = resultado.get("log_entry") or {}
    return {
        "exito": True,
        "interaccion_id": log_entry.get("interaccion_id"),
        "timestamp_utc": log_entry.get("timestamp_utc"),
        "rol": resultado["rol"],
        "usuario_id": resultado["usuario_id"],
        "consulta": resultado["consulta"],
        "respuesta": resultado["respuesta"],
        "herramientas_usadas": resultado["herramientas_usadas"],
        "alertas_seguridad": log_entry.get("alertas_seguridad", []),
        "metricas": resultado["metricas"],
    }


@app.get("/api/cliente/resumen")
async def resumen_cliente(sesion: dict[str, Any] = Depends(requerir_cliente)) -> dict[str, Any]:
    repo = obtener_repositorio()
    resumen = await asyncio.to_thread(repo.obtener_resumen_cliente, sesion["usuario_id"])
    return {"exito": True, **resumen}


@app.get("/api/cliente/historial")
async def historial_cliente(
    limite: int = Query(default=30, ge=1, le=100),
    sesion: dict[str, Any] = Depends(requerir_cliente),
) -> dict[str, Any]:
    registros = await asyncio.to_thread(
        listar_interacciones,
        limite=limite,
        rol="cliente",
        usuario_id=sesion["usuario_id"],
    )
    # Orden cronológico ascendente para renderizar como chat
    return {"exito": True, "mensajes": list(reversed(registros))}


# ---------------------------------------------------------------------------
# Endpoints del Portal Asesor / Admin
# ---------------------------------------------------------------------------

@app.get("/api/admin/chats")
async def admin_listar_chats(
    limite: int = Query(default=100, ge=1, le=300),
    rol: str | None = Query(default=None),
    usuario_id: str | None = Query(default=None),
    solo_alertas: bool = Query(default=False),
    buscar: str | None = Query(default=None),
    _sesion: dict[str, Any] = Depends(requerir_asesor),
) -> dict[str, Any]:
    rol_filtro = rol.strip().lower() if rol and rol.strip() else None
    uid_filtro = usuario_id.strip() if usuario_id and usuario_id.strip() else None
    chats = await asyncio.to_thread(
        listar_interacciones,
        limite=limite,
        rol=rol_filtro,
        usuario_id=uid_filtro,
        solo_alertas=solo_alertas,
        buscar=buscar,
    )
    return {"exito": True, "total": len(chats), "chats": chats}


@app.get("/api/admin/tickets")
async def admin_listar_tickets(
    limite: int = Query(default=100, ge=1, le=300),
    _sesion: dict[str, Any] = Depends(requerir_asesor),
) -> dict[str, Any]:
    tickets = await asyncio.to_thread(listar_tickets, limite=limite)
    return {"exito": True, "total": len(tickets), "tickets": tickets}


@app.get("/api/admin/metricas")
async def admin_metricas(
    _sesion: dict[str, Any] = Depends(requerir_asesor),
) -> dict[str, Any]:
    metricas = await asyncio.to_thread(obtener_metricas_auditoria)
    return {"exito": True, "metricas": metricas}


# ---------------------------------------------------------------------------
# PWA: Manifest, Service Worker y archivos estáticos
# ---------------------------------------------------------------------------

@app.get("/manifest.json")
async def pwa_manifest() -> FileResponse:
    return FileResponse(
        WEB_DIR / "manifest.json", media_type="application/manifest+json"
    )


@app.get("/sw.js")
async def pwa_service_worker() -> FileResponse:
    return FileResponse(
        WEB_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def index_page() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.exception_handler(404)
async def fallback_404(request: Request, exc: HTTPException) -> Response:
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"detail": "Ruta API no encontrada."})
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": "No encontrado."})

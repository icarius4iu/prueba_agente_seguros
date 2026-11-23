"""
Módulo de registro de auditoría (Regla 8) y gestión de tickets de escalamiento a humano.

Soporta almacenamiento dual:
- Siempre persiste en archivos JSON Lines locales (`salidas/logs/*.jsonl`) para trazabilidad local
  y compatibilidad total con `run_casos.py` y `evaluar.py`.
- Cuando `DB_BACKEND=bigquery`, además escribe y consulta un dataset de auditoría separado
  (`BIGQUERY_LOGS_DATASET`, por defecto `seguros_horizonte_logs`) para que los chats y tickets
  persistan en Cloud Run sin otorgar permisos de escritura sobre el dataset transaccional
  `seguros_horizonte` (principio de mínimo privilegio).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import (
    BIGQUERY_LOGS_DATASET,
    DB_BACKEND,
    FECHA_REFERENCIA,
    GCP_PROJECT_ID,
    LOGS_DIR,
    SALIDAS_DIR,
)

logger = logging.getLogger(__name__)

_BQ_LOGS_CLIENT: Any = None


def asegurar_directorios() -> None:
    SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _usar_bigquery_logs() -> bool:
    return DB_BACKEND == "bigquery" and bool(GCP_PROJECT_ID) and bool(BIGQUERY_LOGS_DATASET)


def _get_bq_logs_client() -> Any:
    global _BQ_LOGS_CLIENT
    if _BQ_LOGS_CLIENT is None:
        from google.cloud import bigquery  # type: ignore

        _BQ_LOGS_CLIENT = bigquery.Client(project=GCP_PROJECT_ID)
    return _BQ_LOGS_CLIENT


def _insertar_fila_bq_logs(tabla: str, fila: dict[str, Any]) -> bool:
    """Inserta una fila en el dataset de auditoría de BigQuery (best-effort sin romper el chat)."""
    if not _usar_bigquery_logs():
        return False
    try:
        client = _get_bq_logs_client()
        table_id = f"{GCP_PROJECT_ID}.{BIGQUERY_LOGS_DATASET}.{tabla}"
        errors = client.insert_rows_json(table_id, [fila])
        if errors:
            logger.warning("Error insertando en BigQuery logs (%s): %s", table_id, errors)
            return False
        return True
    except Exception as exc:
        logger.warning("No se pudo escribir en BigQuery logs (%s): %s", tabla, exc)
        return False


def _extraer_alertas(herramientas_usadas: list[dict[str, Any]]) -> list[str]:
    alertas: list[str] = []
    for h in herramientas_usadas or []:
        for a in h.get("alertas_seguridad") or []:
            if a and a not in alertas:
                alertas.append(str(a))
    return alertas


def registrar_ticket_escalamiento(
    rol: str,
    usuario_id: str,
    destino: str,
    motivo: str,
    resumen_caso: str,
) -> dict[str, Any]:
    """
    Crea y persiste un ticket de derivación a un asesor comercial o evaluador de siniestros.
    """
    asegurar_directorios()
    tickets_path = LOGS_DIR / "tickets_escalamiento.jsonl"

    correlativo = 1
    if tickets_path.exists():
        with tickets_path.open("r", encoding="utf-8") as f:
            correlativo = sum(1 for _ in f) + 1

    # En BigQuery/Cloud Run múltiples réplicas pueden escribir simultáneamente; agregamos sufijo único si aplica
    if _usar_bigquery_logs():
        sufijo = uuid.uuid4().hex[:4].upper()
        ticket_id = f"TCK-20261015-{correlativo:04d}-{sufijo}"
    else:
        ticket_id = f"TCK-20261015-{correlativo:04d}"

    ahora_utc = datetime.now(timezone.utc).isoformat()

    ticket = {
        "ticket_id": ticket_id,
        "fecha_referencia_sistema": FECHA_REFERENCIA,
        "timestamp_creacion_utc": ahora_utc,
        "estado_ticket": "abierto",
        "sesion_usuario": {
            "rol": rol,
            "usuario_id": usuario_id,
        },
        "area_destino": destino,
        "motivo_escalamiento": motivo,
        "resumen_caso": resumen_caso,
        "canales_contacto": {
            "central_telefonica": "(01) 555-0100 (Lunes a sábado de 8:00 a 20:00)",
            "correo": "atencion@seguroshorizonte-ficticio.pe",
        },
    }

    with tickets_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ticket, ensure_ascii=False) + "\n")

    _insertar_fila_bq_logs(
        "tickets_escalamiento",
        {
            "ticket_id": ticket_id,
            "timestamp_creacion_utc": ahora_utc,
            "fecha_referencia": FECHA_REFERENCIA,
            "estado_ticket": "abierto",
            "rol": rol,
            "usuario_id": usuario_id,
            "area_destino": destino,
            "motivo_escalamiento": motivo,
            "resumen_caso": resumen_caso,
        },
    )

    return ticket


def registrar_interaccion_auditoria(
    consulta: str,
    rol: str,
    usuario_id: str,
    herramientas_usadas: list[dict[str, Any]],
    respuesta: str,
    metricas: dict[str, Any],
    caso_id: str | None = None,
    archivo_log: Path | None = None,
    alertas_extra: list[str] | None = None,
) -> dict[str, Any]:
    """
    Guarda un registro de auditoría completo de la interacción en formato JSONL (Regla 8)
    y, cuando `DB_BACKEND=bigquery`, también en el dataset de auditoría `BIGQUERY_LOGS_DATASET`.
    """
    asegurar_directorios()
    destino = archivo_log or (LOGS_DIR / "interacciones.jsonl")
    ahora_utc = datetime.now(timezone.utc).isoformat()
    interaccion_id = f"INT-{uuid.uuid4().hex[:10].upper()}"
    alertas = _extraer_alertas(herramientas_usadas)
    for a in alertas_extra or []:
        if a and a not in alertas:
            alertas.append(str(a))

    registro = {
        "interaccion_id": interaccion_id,
        "timestamp_utc": ahora_utc,
        "fecha_referencia": FECHA_REFERENCIA,
        "caso_id": caso_id,
        "usuario_sesion": {
            "rol": rol,
            "usuario_id": usuario_id,
        },
        "consulta": consulta,
        "herramientas_usadas": herramientas_usadas,
        "alertas_seguridad": alertas,
        "respuesta": respuesta,
        "metricas": metricas,
    }

    with destino.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")

    # Solo duplicar a BigQuery si es log principal (evita contaminar con pruebas en archivo_log custom)
    if archivo_log is None:
        _insertar_fila_bq_logs(
            "interacciones",
            {
                "interaccion_id": interaccion_id,
                "timestamp_utc": ahora_utc,
                "fecha_referencia": FECHA_REFERENCIA,
                "caso_id": caso_id,
                "rol": rol,
                "usuario_id": usuario_id,
                "consulta": consulta,
                "respuesta": respuesta,
                "herramientas_json": json.dumps(herramientas_usadas, ensure_ascii=False),
                "alertas_json": json.dumps(alertas, ensure_ascii=False),
                "tiene_alerta_seguridad": len(alertas) > 0,
                "modelo": str(metricas.get("modelo", "")),
                "latencia_ms": float(metricas.get("latencia_ms", 0.0) or 0.0),
                "tokens_entrada": int(metricas.get("tokens_entrada", 0) or 0),
                "tokens_salida": int(metricas.get("tokens_salida", 0) or 0),
                "tokens_totales": int(metricas.get("tokens_totales", 0) or 0),
                "costo_estimado_usd": float(metricas.get("costo_estimado_usd", 0.0) or 0.0),
            },
        )

    return registro


def _leer_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    registros: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                registros.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return registros


def listar_interacciones(
    limite: int = 100,
    rol: str | None = None,
    usuario_id: str | None = None,
    solo_alertas: bool = False,
    buscar: str | None = None,
) -> list[dict[str, Any]]:
    """
    Devuelve interacciones registradas ordenadas de más reciente a más antigua.
    Usa BigQuery (`BIGQUERY_LOGS_DATASET.interacciones`) cuando `DB_BACKEND=bigquery`,
    con respaldo automático a los archivos JSONL locales.
    """
    registros: list[dict[str, Any]] = []

    if _usar_bigquery_logs():
        try:
            from google.cloud import bigquery  # type: ignore

            client = _get_bq_logs_client()
            table_id = f"`{GCP_PROJECT_ID}.{BIGQUERY_LOGS_DATASET}.interacciones`"
            condiciones = ["1=1"]
            params: list[Any] = []
            if rol:
                condiciones.append("rol = @rol")
                params.append(bigquery.ScalarQueryParameter("rol", "STRING", rol))
            if usuario_id:
                condiciones.append("usuario_id = @usuario_id")
                params.append(bigquery.ScalarQueryParameter("usuario_id", "STRING", usuario_id))
            if solo_alertas:
                condiciones.append("tiene_alerta_seguridad = TRUE")

            sql = (
                f"SELECT interaccion_id, timestamp_utc, fecha_referencia, caso_id, rol, usuario_id, "
                f"consulta, respuesta, herramientas_json, alertas_json, modelo, latencia_ms, "
                f"tokens_entrada, tokens_salida, tokens_totales, costo_estimado_usd "
                f"FROM {table_id} WHERE {' AND '.join(condiciones)} "
                f"ORDER BY timestamp_utc DESC LIMIT @limite"
            )
            params.append(bigquery.ScalarQueryParameter("limite", "INT64", max(1, min(limite, 500))))
            job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
            for row in job.result():
                herramientas = json.loads(row.herramientas_json) if row.herramientas_json else []
                alertas = json.loads(row.alertas_json) if row.alertas_json else _extraer_alertas(herramientas)
                ts = row.timestamp_utc.isoformat() if hasattr(row.timestamp_utc, "isoformat") else str(row.timestamp_utc)
                registros.append(
                    {
                        "interaccion_id": row.interaccion_id,
                        "timestamp_utc": ts,
                        "fecha_referencia": row.fecha_referencia,
                        "caso_id": row.caso_id,
                        "usuario_sesion": {"rol": row.rol, "usuario_id": row.usuario_id},
                        "consulta": row.consulta,
                        "respuesta": row.respuesta,
                        "herramientas_usadas": herramientas,
                        "alertas_seguridad": alertas,
                        "metricas": {
                            "modelo": row.modelo,
                            "latencia_ms": float(row.latencia_ms or 0.0),
                            "tokens_entrada": int(row.tokens_entrada or 0),
                            "tokens_salida": int(row.tokens_salida or 0),
                            "tokens_totales": int(row.tokens_totales or 0),
                            "costo_estimado_usd": float(row.costo_estimado_usd or 0.0),
                        },
                    }
                )
            if buscar:
                q = buscar.strip().lower()
                registros = [
                    r
                    for r in registros
                    if q in (r.get("consulta") or "").lower()
                    or q in (r.get("respuesta") or "").lower()
                    or q in (r.get("usuario_sesion", {}).get("usuario_id") or "").lower()
                ]
            return registros[:limite]
        except Exception as exc:
            logger.warning("Fallback a JSONL al leer interacciones de BigQuery: %s", exc)

    # Lectura local JSONL
    brutos = _leer_jsonl(LOGS_DIR / "interacciones.jsonl")
    if not brutos:
        brutos = _leer_jsonl(SALIDAS_DIR / "muestra_log_interacciones.jsonl")

    filtrados: list[dict[str, Any]] = []
    q = (buscar or "").strip().lower()
    for r in reversed(brutos):
        sesion = r.get("usuario_sesion") or {}
        r_rol = sesion.get("rol")
        r_uid = sesion.get("usuario_id")
        alertas = r.get("alertas_seguridad")
        if alertas is None:
            alertas = _extraer_alertas(r.get("herramientas_usadas") or [])
            r["alertas_seguridad"] = alertas

        if rol and r_rol != rol:
            continue
        if usuario_id and r_uid != usuario_id:
            continue
        if solo_alertas and not alertas:
            continue
        if q and not (
            q in (r.get("consulta") or "").lower()
            or q in (r.get("respuesta") or "").lower()
            or q in str(r_uid or "").lower()
        ):
            continue
        filtrados.append(r)
        if len(filtrados) >= limite:
            break
    return filtrados


def listar_tickets(limite: int = 100) -> list[dict[str, Any]]:
    """Lista tickets de escalamiento desde BigQuery logs o JSONL local."""
    if _usar_bigquery_logs():
        try:
            from google.cloud import bigquery  # type: ignore

            client = _get_bq_logs_client()
            table_id = f"`{GCP_PROJECT_ID}.{BIGQUERY_LOGS_DATASET}.tickets_escalamiento`"
            sql = (
                f"SELECT ticket_id, timestamp_creacion_utc, fecha_referencia, estado_ticket, "
                f"rol, usuario_id, area_destino, motivo_escalamiento, resumen_caso "
                f"FROM {table_id} ORDER BY timestamp_creacion_utc DESC LIMIT @limite"
            )
            params = [bigquery.ScalarQueryParameter("limite", "INT64", max(1, min(limite, 500)))]
            job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
            tickets: list[dict[str, Any]] = []
            for row in job.result():
                ts = (
                    row.timestamp_creacion_utc.isoformat()
                    if hasattr(row.timestamp_creacion_utc, "isoformat")
                    else str(row.timestamp_creacion_utc)
                )
                tickets.append(
                    {
                        "ticket_id": row.ticket_id,
                        "timestamp_creacion_utc": ts,
                        "fecha_referencia_sistema": row.fecha_referencia,
                        "estado_ticket": row.estado_ticket,
                        "sesion_usuario": {"rol": row.rol, "usuario_id": row.usuario_id},
                        "area_destino": row.area_destino,
                        "motivo_escalamiento": row.motivo_escalamiento,
                        "resumen_caso": row.resumen_caso,
                    }
                )
            return tickets
        except Exception as exc:
            logger.warning("Fallback a JSONL al leer tickets de BigQuery: %s", exc)

    brutos = _leer_jsonl(LOGS_DIR / "tickets_escalamiento.jsonl")
    return list(reversed(brutos))[:limite]


def obtener_metricas_auditoria() -> dict[str, Any]:
    """Agrega KPIs operativos y de seguridad para el panel Asesor / Admin."""
    interacciones = listar_interacciones(limite=500)
    tickets = listar_tickets(limite=200)

    total = len(interacciones)
    clientes_unicos = {
        (r.get("usuario_sesion") or {}).get("usuario_id")
        for r in interacciones
        if (r.get("usuario_sesion") or {}).get("rol") == "cliente"
    }
    alertas_total = sum(1 for r in interacciones if r.get("alertas_seguridad"))
    latencias = [float((r.get("metricas") or {}).get("latencia_ms") or 0.0) for r in interacciones]
    tokens_total = sum(int((r.get("metricas") or {}).get("tokens_totales") or 0) for r in interacciones)
    costo_total = round(
        sum(float((r.get("metricas") or {}).get("costo_estimado_usd") or 0.0) for r in interacciones),
        6,
    )

    return {
        "total_interacciones": total,
        "clientes_atendidos": len(clientes_unicos),
        "total_tickets": len(tickets),
        "alertas_seguridad_detectadas": alertas_total,
        "latencia_promedio_ms": round(sum(latencias) / total, 1) if total else 0.0,
        "tokens_totales": tokens_total,
        "costo_total_usd": costo_total,
        "backend_datos": DB_BACKEND,
        "almacen_auditoria": f"bigquery:{BIGQUERY_LOGS_DATASET}" if _usar_bigquery_logs() else "local:jsonl",
    }

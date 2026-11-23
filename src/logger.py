"""
Módulo de registro de auditoría (Regla 8) y gestión de tickets de escalamiento a humano.

Cada interacción con el agente se persiste en formato JSON Lines (`.jsonl`) incluyendo:
- Timestamp ISO-8601 y fecha de referencia del negocio
- Identidad autenticada de la sesión (`rol` y `usuario_id`)
- Consulta original del usuario
- Lista ordenada de herramientas invocadas (con argumentos y resumen de salida)
- Respuesta final entregada
- Métricas de uso (latencia, tokens de entrada/salida y costo estimado en USD)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import FECHA_REFERENCIA, LOGS_DIR, SALIDAS_DIR


def asegurar_directorios() -> None:
    SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


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

    # Contar tickets existentes para generar un correlativo limpio y trazable
    correlativo = 1
    if tickets_path.exists():
        with tickets_path.open("r", encoding="utf-8") as f:
            correlativo = sum(1 for _ in f) + 1

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
) -> dict[str, Any]:
    """
    Guarda un registro de auditoría completo de la interacción en formato JSONL (Regla 8).
    """
    asegurar_directorios()
    destino = archivo_log or (LOGS_DIR / "interacciones.jsonl")

    registro = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "fecha_referencia": FECHA_REFERENCIA,
        "caso_id": caso_id,
        "usuario_sesion": {
            "rol": rol,
            "usuario_id": usuario_id,
        },
        "consulta": consulta,
        "herramientas_usadas": herramientas_usadas,
        "respuesta": respuesta,
        "metricas": metricas,
    }

    with destino.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")

    return registro

"""
Definición y ejecución de las tres herramientas del agente:
1. `consultar_datos_sql`: ejecuta SQL SELECT sobre las tablas de clientes, pólizas y siniestros.
2. `buscar_en_condicionados`: recupera artículos relevantes de las condiciones generales y particulares.
3. `escalar_a_humano`: registra un ticket de atención para un asesor comercial o evaluador de siniestros.

Seguridad por diseño:
El contexto de sesión (`rol` y `usuario_id`) NO es un parámetro que el modelo de lenguaje pueda
modificar en la llamada a la herramienta. Se inyecta directamente desde la sesión autenticada
mediante `ContextoSesion`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.condicionados import obtener_buscador
from src.database import DataRepository, obtener_repositorio
from src.logger import registrar_ticket_escalamiento


@dataclass
class ContextoSesion:
    """Representa la identidad autenticada del usuario y almacena la traza de herramientas invocadas."""

    rol: str
    usuario_id: str
    repositorio: DataRepository = field(default_factory=obtener_repositorio)
    traza_herramientas: list[dict[str, Any]] = field(default_factory=list)


def ejecutar_herramienta(
    nombre: str,
    argumentos: dict[str, Any],
    sesion: ContextoSesion,
) -> dict[str, Any]:
    """
    Despacha la ejecución de una herramienta inyectando la identidad autenticada de `sesion`
    y registra la llamada para trazabilidad y auditoría (Reglas 6 y 8).
    """
    if nombre == "consultar_datos_sql":
        consulta_sql = str(argumentos.get("consulta_sql", "")).strip()
        motivo = str(argumentos.get("motivo_consulta", "")).strip()
        resultado = sesion.repositorio.ejecutar_consulta(
            sql=consulta_sql,
            rol=sesion.rol,
            usuario_id=sesion.usuario_id,
        )
        sesion.traza_herramientas.append(
            {
                "herramienta": "consultar_datos_sql",
                "argumentos": {"consulta_sql": consulta_sql, "motivo_consulta": motivo},
                "exito": resultado.get("exito", False),
                "total_filas": resultado.get("total_filas", 0),
                "alertas_seguridad": resultado.get("alertas_seguridad", []),
            }
        )
        return resultado

    if nombre == "buscar_en_condicionados":
        consulta = str(argumentos.get("consulta", "")).strip()
        ramo = str(argumentos.get("ramo", "todos")).strip().lower()
        top_k = int(argumentos.get("top_k", 5))
        buscador = obtener_buscador()
        fragmentos = buscador.buscar(consulta=consulta, ramo=ramo, top_k=top_k)
        resultado = {
            "exito": True,
            "consulta": consulta,
            "ramo_filtro": ramo,
            "total_fragmentos": len(fragmentos),
            "fragmentos": fragmentos,
        }
        sesion.traza_herramientas.append(
            {
                "herramienta": "buscar_en_condicionados",
                "argumentos": {"consulta": consulta, "ramo": ramo, "top_k": top_k},
                "exito": True,
                "fuentes_recuperadas": [
                    f"{f['documento']} ({f['articulo']})" for f in fragmentos
                ],
            }
        )
        return resultado

    if nombre == "escalar_a_humano":
        destino = str(argumentos.get("destino", "asesor_comercial")).strip()
        motivo = str(argumentos.get("motivo", "")).strip()
        resumen_caso = str(argumentos.get("resumen_caso", "")).strip()
        ticket = registrar_ticket_escalamiento(
            rol=sesion.rol,
            usuario_id=sesion.usuario_id,
            destino=destino,
            motivo=motivo,
            resumen_caso=resumen_caso,
        )
        resultado = {
            "exito": True,
            "mensaje": f"Caso derivado exitosamente a '{destino}' con ticket {ticket['ticket_id']}.",
            "ticket": ticket,
        }
        sesion.traza_herramientas.append(
            {
                "herramienta": "escalar_a_humano",
                "argumentos": {
                    "destino": destino,
                    "motivo": motivo,
                    "resumen_caso": resumen_caso,
                },
                "exito": True,
                "ticket_id": ticket["ticket_id"],
            }
        )
        return resultado

    error_res = {
        "exito": False,
        "error": f"Herramienta desconocida: '{nombre}'.",
    }
    sesion.traza_herramientas.append(
        {
            "herramienta": nombre,
            "argumentos": argumentos,
            "exito": False,
            "error": error_res["error"],
        }
    )
    return error_res


# Declaraciones de herramientas compatibles con Google GenAI SDK (function declarations)
DECLARACIONES_HERRAMIENTAS_GEMINI: list[dict[str, Any]] = [
    {
        "name": "consultar_datos_sql",
        "description": (
            "Ejecuta una consulta SQL de SOLO LECTURA (SELECT) en DuckDB sobre las vistas "
            "`clientes`, `polizas`, `siniestros` y `asesores`. "
            "IMPORTANTE: Si el usuario autenticado tiene rol 'cliente', las vistas ya están "
            "filtradas automáticamente por seguridad (Row-Level Security) para devolver únicamente "
            "los registros cuyo titular es el `usuario_id` de la sesión actual. "
            "Si el usuario tiene rol 'asesor', las vistas contienen todos los registros de la aseguradora."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "consulta_sql": {
                    "type": "STRING",
                    "description": (
                        "Sentencia SQL SELECT válida en DuckDB usando las tablas `clientes`, `polizas`, "
                        "`siniestros` o `asesores`. No uses funciones read_csv_auto ni punto y coma múltiple. "
                        "Columnas clave: "
                        "clientes(cliente_id, nombres, apellidos, dni, fecha_nacimiento, distrito, telefono, email, fecha_alta); "
                        "polizas(poliza_id, cliente_id, ramo, producto, fecha_inicio, fecha_fin, prima_mensual_soles, suma_asegurada_soles, deducible_soles, estado, placa_vehiculo); "
                        "siniestros(siniestro_id, poliza_id, fecha_ocurrencia, fecha_aviso, tipo_evento, descripcion, monto_reclamado_soles, monto_aprobado_soles, estado, motivo_rechazo, clausula_referencia, fecha_ultima_actualizacion)."
                    ),
                },
                "motivo_consulta": {
                    "type": "STRING",
                    "description": "Breve explicación de qué dato se busca verificar con esta consulta SQL.",
                },
            },
            "required": ["consulta_sql", "motivo_consulta"],
        },
    },
    {
        "name": "buscar_en_condicionados",
        "description": (
            "Busca artículos y cláusulas relevantes en los documentos normativos de los seguros "
            "(condicionados): `condiciones_generales.md`, `vehicular.md`, `salud.md` y `vida.md`. "
            "Úsala SIEMPRE que necesites verificar coberturas, exclusiones, plazos de aviso, "
            "periodos de carencia, vigencia, estados de siniestros, protección de datos personales "
            "o reglas sobre ahorro e inversión, y para citar documento y artículo exacto (Regla 6)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "consulta": {
                    "type": "STRING",
                    "description": (
                        "Palabras clave, pregunta o número de cláusula a buscar "
                        "(ej. 'choque poste aviso procedimiento', 'cirugia programada vesicula carencia', "
                        "'Vehicular 5.2 ebriedad', 'proteccion datos personales titular conyuge')."
                    ),
                },
                "ramo": {
                    "type": "STRING",
                    "description": "Ramo para priorizar resultados: 'todos', 'general', 'vehicular', 'salud' o 'vida'.",
                    "enum": ["todos", "general", "vehicular", "salud", "vida"],
                },
                "top_k": {
                    "type": "INTEGER",
                    "description": "Cantidad de artículos a recuperar (entre 3 y 6, por defecto 5).",
                },
            },
            "required": ["consulta"],
        },
    },
    {
        "name": "escalar_a_humano",
        "description": (
            "Registra un ticket de escalamiento para que un asesor comercial o un evaluador de "
            "siniestros humano atienda el caso. Debes usar esta herramienta cuando: "
            "1) El cliente solicita asesoría o recomendación financiera, de inversión (ej. seguro con ahorro vs fondo mutuo), legal o médica (Regla 7). "
            "2) El usuario solicita aprobar, rechazar o cambiar montos de un siniestro o realizar una gestión que solo compete a un humano (Regla 4 / Art. 5.1). "
            "3) El caso requiere evaluación técnica, comercial o atención especializada que el agente no puede ni debe resolver (Art. 10.3)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "destino": {
                    "type": "STRING",
                    "description": "Área o especialista humano al que se deriva el ticket.",
                    "enum": ["asesor_comercial", "evaluador_siniestros", "atencion_al_cliente"],
                },
                "motivo": {
                    "type": "STRING",
                    "description": "Motivo concreto por el cual el agente deriva el caso a un humano.",
                },
                "resumen_caso": {
                    "type": "STRING",
                    "description": "Resumen estructurado con el ID del cliente, póliza/siniestro involucrado y solicitud del usuario.",
                },
            },
            "required": ["destino", "motivo", "resumen_caso"],
        },
    },
]

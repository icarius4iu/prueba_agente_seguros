"""
Interfaz de Línea de Comandos (CLI) interactiva para demostración en vivo durante la sustentación.

Permite:
- Probar consultas libres eligiendo el `rol` (cliente o asesor) y `usuario_id` (ej. C001..C040, ASE01).
- Cambiar de usuario en caliente con el comando `/sesion <rol> <usuario_id>` (ej. `/sesion asesor ASE01`).
- Ejecutar cualquiera de los 12 casos oficiales en vivo con `/caso CP-01` .. `/caso CP-12`.
- Ver las herramientas invocadas, tiempo de respuesta y consumo de tokens en cada turno.
"""

from __future__ import annotations

import argparse
import json
import sys

from src.agent import AgenteSeguros
from src.config import CASOS_PRUEBA_PATH, FECHA_REFERENCIA, GEMINI_MODEL


def cargar_casos_dict() -> dict[str, dict[str, str]]:
    if not CASOS_PRUEBA_PATH.exists():
        return {}
    data = json.loads(CASOS_PRUEBA_PATH.read_text(encoding="utf-8"))
    return {c["id"].upper(): c for c in data.get("casos", [])}


def imprimir_ayuda() -> None:
    print("\nComandos disponibles en la sesión interactiva:")
    print("  /sesion <rol> <usuario_id>  -> Cambia la sesión autenticada (ej. /sesion cliente C005 o /sesion asesor ASE01)")
    print("  /caso <ID>                  -> Ejecuta en vivo un caso de prueba oficial (ej. /caso CP-04 o /caso CP-12)")
    print("  /casos                      -> Lista los 12 casos de prueba disponibles")
    print("  /ayuda                      -> Muestra esta ayuda")
    print("  /salir                      -> Cierra la CLI interactiva\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CLI interactiva del Agente de Seguros Horizonte S.A."
    )
    parser.add_argument("--rol", type=str, default="cliente", choices=["cliente", "asesor"], help="Rol inicial de sesión")
    parser.add_argument("--usuario", type=str, default="C001", help="ID del usuario autenticado inicial (ej. C001, ASE01)")
    args = parser.parse_args()

    try:
        agente = AgenteSeguros()
    except ValueError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1

    casos_map = cargar_casos_dict()
    rol_actual = args.rol.lower()
    usuario_actual = args.usuario.upper()

    print("=" * 75)
    print(" ASISTENTE VIRTUAL - SEGUROS HORIZONTE S.A. (MODO INTERACTIVO)")
    print(f" Fecha de referencia: {FECHA_REFERENCIA} | Modelo: {GEMINI_MODEL}")
    print("=" * 75)
    imprimir_ayuda()

    while True:
        try:
            prompt_str = f"[{rol_actual}:{usuario_actual}] > "
            entrada = input(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCerrando asistente interactivo.")
            break

        if not entrada:
            continue

        if entrada.lower() in {"/salir", "/exit", "exit", "quit"}:
            print("Cerrando asistente interactivo.")
            break

        if entrada.lower() in {"/ayuda", "/help"}:
            imprimir_ayuda()
            continue

        if entrada.lower() == "/casos":
            print("\nCasos de prueba oficiales:")
            for cid, c in casos_map.items():
                print(f"  {cid} ({c['rol']}:{c['usuario_id']}): {c['mensaje']}")
            print()
            continue

        if entrada.lower().startswith("/sesion"):
            partes = entrada.split()
            if len(partes) != 3 or partes[1].lower() not in {"cliente", "asesor"}:
                print("Uso correcto: /sesion <cliente|asesor> <usuario_id> (ej. /sesion cliente C004)")
                continue
            rol_actual = partes[1].lower()
            usuario_actual = partes[2].upper()
            print(f"-> Sesión autenticada actualizada a: rol='{rol_actual}', usuario_id='{usuario_actual}'\n")
            continue

        caso_id_actual: str | None = None
        if entrada.lower().startswith("/caso"):
            partes = entrada.split()
            if len(partes) != 2:
                print("Uso correcto: /caso <CP-01..CP-12>")
                continue
            cid = partes[1].upper()
            if cid not in casos_map:
                print(f"No existe el caso '{cid}'. Usa /casos para ver la lista.")
                continue
            caso = casos_map[cid]
            rol_actual = caso["rol"].lower()
            usuario_actual = caso["usuario_id"].upper()
            entrada = caso["mensaje"]
            caso_id_actual = cid
            print(f"\n-> Cargando {cid} [Sesión: {rol_actual}:{usuario_actual}]")
            print(f"-> Consulta: {entrada}")

        print("\nProcesando consulta...")
        res = agente.responder(
            consulta=entrada,
            rol=rol_actual,
            usuario_id=usuario_actual,
            caso_id=caso_id_actual,
        )

        print("\n--- Trazabilidad de Herramientas ---")
        if not res["herramientas_usadas"]:
            print("  (Ninguna herramienta invocada)")
        else:
            for idx, h in enumerate(res["herramientas_usadas"], start=1):
                print(f"  {idx}. {h['herramienta']} -> args={json.dumps(h['argumentos'], ensure_ascii=False)}")

        m = res["metricas"]
        print(
            f"\n--- Métricas: {m['latencia_ms']} ms | "
            f"Tokens: {m['tokens_totales']} (in={m['tokens_entrada']}, out={m['tokens_salida']}) | "
            f"Costo est.: ${m['costo_estimado_usd']:.6f} USD ---"
        )
        print("\n--- Respuesta del Agente ---")
        print(res["respuesta"])
        print("-" * 75 + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

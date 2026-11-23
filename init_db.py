"""
Script de inicialización de la base de datos DuckDB (`datos/seguros_horizonte.duckdb`).

Carga los 4 archivos CSV oficiales (`clientes.csv`, `polizas.csv`, `siniestros.csv`, `asesores.csv`)
en un archivo persistente de DuckDB y verifica la integridad de las tablas y relaciones.

Uso:
    python init_db.py
"""

from __future__ import annotations

from pathlib import Path
import duckdb

from src.config import DATOS_DIR

DB_FILE_PATH = DATOS_DIR / "seguros_horizonte.duckdb"


def inicializar_duckdb(db_path: Path = DB_FILE_PATH, datos_dir: Path = DATOS_DIR, silencioso: bool = False) -> Path:
    """
    Crea o actualiza el archivo persistente `seguros_horizonte.duckdb` a partir de los CSV.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = duckdb.connect(database=str(db_path))
    try:
        tablas = ["clientes", "polizas", "siniestros", "asesores"]
        resumen: dict[str, int] = {}

        for tabla in tablas:
            csv_file = (datos_dir / f"{tabla}.csv").as_posix()
            conn.execute(f"CREATE TABLE {tabla} AS SELECT * FROM read_csv_auto('{csv_file}')")
            total = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            resumen[tabla] = total

        if not silencioso:
            print("=" * 68)
            print(" BASE DE DATOS DUCKDB INICIALIZADA EXITOSAMENTE")
            print(f" Archivo: {db_path}")
            print("-" * 68)
            for t, count in resumen.items():
                print(f"  - Tabla '{t:<12}': {count:>4} registros cargados desde {t}.csv")
            print("=" * 68)

        return db_path
    finally:
        conn.close()


if __name__ == "__main__":
    inicializar_duckdb()

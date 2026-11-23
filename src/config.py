"""Configuración centralizada del agente."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Regla de negocio 1: Fecha de referencia fija
FECHA_REFERENCIA = "2026-10-15"

# Rutas del proyecto
DATOS_DIR = BASE_DIR / "datos"
CONDICIONADOS_DIR = BASE_DIR / "condicionados"
CASOS_PRUEBA_PATH = BASE_DIR / "casos_prueba" / "casos_prueba.json"
SALIDAS_DIR = BASE_DIR / "salidas"
LOGS_DIR = SALIDAS_DIR / "logs"

# Configuración del modelo de IA (Google Gemini)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

# Backend de base de datos ('duckdb' en local, 'bigquery' en nube)
DB_BACKEND = os.getenv("DB_BACKEND", "duckdb").strip().lower()
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "seguros_horizonte")

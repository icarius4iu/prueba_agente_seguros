"""Configuración centralizada del agente y servidor PWA (con soporte Vertex AI IAM)."""

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
WEB_DIR = BASE_DIR / "web"

# Configuración GCP / BigQuery
DB_BACKEND = os.getenv("DB_BACKEND", "duckdb").strip().lower()
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "").strip().removeprefix("projects/")
GCP_LOCATION = os.getenv("GCP_LOCATION", "global").strip()
BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "seguros_horizonte").strip()
BIGQUERY_LOGS_DATASET = os.getenv("BIGQUERY_LOGS_DATASET", "seguros_horizonte_logs").strip()

# Configuración del modelo de IA (Vertex AI por IAM o Google AI Studio por API Key)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

_use_vertex_raw = os.getenv("USE_VERTEX_AI", "").strip().lower()
if _use_vertex_raw in ("1", "true", "yes", "si"):
    USE_VERTEX_AI = True
elif _use_vertex_raw in ("0", "false", "no"):
    USE_VERTEX_AI = False
else:
    # Auto-detección: si hay proyecto GCP sin API key estática (ej. Cloud Run con IAM), usa Vertex AI
    USE_VERTEX_AI = bool(GCP_PROJECT_ID) and not bool(
        GEMINI_API_KEY and GEMINI_API_KEY != "tu_api_key_aqui"
    )

# Seguridad de sesiones web (PWA) y puerto HTTP (Cloud Run usa PORT=8080)
APP_SECRET_KEY = os.getenv(
    "APP_SECRET_KEY", "seguros-horizonte-demo-secret-cambiar-en-prod"
).strip()
PORT = int(os.getenv("PORT", "8080"))

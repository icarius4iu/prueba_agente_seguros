# Prueba Técnica: Agente de Consultas de Pólizas y Siniestros — Seguros Horizonte S.A.

Solución completa para el caso de **Asistente Virtual de Pólizas y Siniestros** de Seguros Horizonte S.A., construida en **Python 3.10+** con **Google Gemini (`google-genai`)** y **DuckDB**.

---

## 1. Requisitos previos

- **Python 3.10 o superior** (probado hasta Python 3.14).
- Una clave de API de **Google Gemini** (puedes obtener una gratuita en segundos desde [Google AI Studio](https://aistudio.google.com/apikey)).

---

## 2. Instalación y ejecución en menos de 5 minutos

### Paso 1: Instalar dependencias

```bash
pip install -r requirements.txt
```

### Paso 2: Configurar variables de entorno (`.env`)

Copia el archivo de ejemplo `.env.example` a `.env` y coloca tu `GEMINI_API_KEY`:

```powershell
# En Windows PowerShell:
Copy-Item .env.example .env
```

```bash
# En Linux / macOS / Git Bash:
cp .env.example .env
```

Edita el archivo `.env` y reemplaza `tu_api_key_aqui` por tu clave real:

```env
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-3.8-flash
DB_BACKEND=duckdb
```

### Paso 3: Ejecutar los 12 casos de prueba con un solo comando

```bash
python run_casos.py
```

Este comando ejecuta automáticamente los 12 casos de `casos_prueba/casos_prueba.json` y genera:
- `salidas/respuestas_casos.json`: archivo estructurado con la respuesta, herramientas usadas y métricas (latencia, tokens y costo estimado) de cada caso.
- `salidas/respuestas_casos.md`: reporte legible en Markdown con las respuestas de los 12 casos.
- `salidas/muestra_log_interacciones.jsonl` (y `salidas/logs/interacciones.jsonl`): registro de auditoría completo de cada interacción (Regla 8).
- `salidas/logs/tickets_escalamiento.jsonl`: tickets registrados por la herramienta `escalar_a_humano`.

> **Tip:** También puedes ejecutar un único caso puntual pasando `--caso`:
> ```bash
> python run_casos.py --caso CP-12
> ```

### Opción alternativa con Docker / Docker Compose (en local o GitHub Codespaces)

Si prefieres ejecutar todo aislado en contenedor junto con la base de datos DuckDB:

```bash
# Ejecutar los 12 casos y la evaluación automática en contenedor:
docker compose up --build

# Abrir la CLI interactiva dentro del contenedor:
docker compose run --rm agente-seguros python cli.py
```

---

## 3. Funcionalidades adicionales (Opcionales implementados)

### A. Script de evaluación automática (`evaluar.py`)

Verifica automáticamente si las respuestas generadas en `salidas/respuestas_casos.json` cumplen los criterios fácticos, de herramientas, trazabilidad y seguridad (incluyendo privacidad en `CP-06` y resistencia a *Indirect Prompt Injection* en `CP-12`):

```bash
python evaluar.py
```

### B. Interfaz de línea de comandos interactiva (`cli.py`)

Ideal para probar consultas en vivo o demostrar modificaciones durante la sustentación:

```bash
python cli.py
```

Dentro de la CLI interactiva puedes usar:
- `/sesion cliente C005` o `/sesion asesor ASE01` para cambiar en caliente el usuario y rol autenticado.
- `/caso CP-04` (del `CP-01` al `CP-12`) para disparar en vivo cualquiera de los casos de prueba oficiales.
- `/casos` para listar los 12 casos.
- `/salir` para terminar.

### C. Medición de tokens y costo estimado por consulta

Cada ejecución registra en consola, en `salidas/respuestas_casos.json` y en el log de auditoría (`interacciones.jsonl`) la latencia en milisegundos, los tokens de entrada/salida y el costo estimado en USD por consulta.

---

## 4. Estructura del proyecto

```text
prueba_agente_seguros/
├── README.md                  # Guía de instalación, ejecución y declaración de IA
├── DISENO.md                  # Documento de diseño arquitectónico y decisiones (Entregable 3)
├── RESULTADOS.md              # Evaluación detallada y honesta de los 12 casos (Entregable 4)
├── requirements.txt           # Dependencias mínimas (duckdb, google-genai, python-dotenv)
├── .env.example               # Plantilla de configuración sin credenciales expuestas
├── run_casos.py               # Ejecutor en lote de los 12 casos en un solo comando
├── cli.py                     # CLI interactiva para sustentación y pruebas en vivo
├── evaluar.py                 # Evaluador automático de respuestas y reglas de negocio
├── src/
│   ├── config.py              # Configuración centralizada y fecha de referencia (2026-10-15)
│   ├── database.py            # Capa de datos (DuckDBRepository + BigQueryRepository + RLS + Anti-Injection)
│   ├── condicionados.py       # Indexador por Artículo y buscador híbrido sobre los .md
│   ├── tools.py               # Definición y despacho seguro de las 3 herramientas del agente
│   ├── logger.py              # Registro de auditoría JSONL y tickets de escalamiento
│   └── agent.py               # Ciclo Tool-Calling con Google Gemini y reglas de negocio
├── datos/                     # CSV de clientes, pólizas, siniestros, asesores y diccionario
├── condicionados/             # Condiciones generales y particulares (vehicular, salud, vida)
├── casos_prueba/              # 12 casos de prueba (.md y .json)
└── salidas/                   # Archivos generados por la ejecución y muestras de logs (Entregable 5)
```

---

## 5. Declaración de uso de asistentes de IA

Conforme al punto 6 de los entregables del enunciado:

- **Herramienta utilizada:** Asistente de codificación con IA (Antigravity / Gemini).
- **Para qué se utilizó:**
  - Acelerar la estructuración modular del repositorio (`src/database.py`, `src/condicionados.py`, `src/tools.py`, `src/agent.py`, `src/logger.py`).
  - Diseñar las expresiones regulares de validación SQL de solo lectura y el detector de *Indirect Prompt Injection* sobre columnas de texto libre.
  - Construir los scripts de automatización (`run_casos.py`, `evaluar.py`, `cli.py`) y dar formato a las tablas y diagramas Mermaid de la documentación (`DISENO.md` y `RESULTADOS.md`).
- **Validación humana:** Todas las reglas de negocio, el cruce manual de los 12 casos de prueba contra los archivos CSV y los condicionados, los criterios de evaluación y las decisiones de arquitectura fueron verificados sobre los datos del caso.

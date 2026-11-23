FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usuario no-root para mejores prácticas de seguridad en Cloud Run / Docker
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/salidas/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Listo para Google Cloud Run (escucha en $PORT, por defecto 8080)
CMD ["sh", "-c", "uvicorn src.web:app --host 0.0.0.0 --port ${PORT:-8080}"]

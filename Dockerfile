FROM python:3.12-slim

WORKDIR /app

# Evitar archivos .pyc y habilitar salida sin buffer en consola
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Por defecto ejecuta los 12 casos de prueba y luego la evaluación automática
CMD ["sh", "-c", "python run_casos.py && python evaluar.py"]

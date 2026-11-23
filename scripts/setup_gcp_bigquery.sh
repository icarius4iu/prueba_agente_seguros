#!/usr/bin/env bash
# =============================================================================
# Aprovisionamiento de auditoría e IAM de mínimo privilegio en GCP para
# Seguros Horizonte S.A. (BigQuery + Cloud Run)
#
# Ejecutar en Google Cloud Shell dentro del proyecto `my-jenny-514602`.
# =============================================================================
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-my-jenny-514602}"
LOCATION="${BQ_LOCATION:-US}"
DATASET_DATA="${BIGQUERY_DATASET:-seguros_horizonte}"
DATASET_LOGS="${BIGQUERY_LOGS_DATASET:-seguros_horizonte_logs}"
SA_NAME="${SA_NAME:-agente-seguros-bq}"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> 1. Creando dataset de auditoría separado: ${PROJECT_ID}:${DATASET_LOGS}"
bq --location="${LOCATION}" mk -d --exists "${PROJECT_ID}:${DATASET_LOGS}" 2>/dev/null \
  || bq --location="${LOCATION}" mk -d "${PROJECT_ID}:${DATASET_LOGS}" || true

echo "==> 2. Creando tablas de auditoría (interacciones y tickets_escalamiento)"
bq mk --table "${PROJECT_ID}:${DATASET_LOGS}.interacciones" \
  interaccion_id:STRING,timestamp_utc:TIMESTAMP,fecha_referencia:STRING,caso_id:STRING,rol:STRING,usuario_id:STRING,consulta:STRING,respuesta:STRING,herramientas_json:STRING,alertas_json:STRING,tiene_alerta_seguridad:BOOL,modelo:STRING,latencia_ms:FLOAT64,tokens_entrada:INT64,tokens_salida:INT64,tokens_totales:INT64,costo_estimado_usd:FLOAT64 \
  || true

bq mk --table "${PROJECT_ID}:${DATASET_LOGS}.tickets_escalamiento" \
  ticket_id:STRING,timestamp_creacion_utc:TIMESTAMP,fecha_referencia:STRING,estado_ticket:STRING,rol:STRING,usuario_id:STRING,area_destino:STRING,motivo_escalamiento:STRING,resumen_caso:STRING \
  || true

echo "==> 3. Creando cuenta de servicio (si no existe): ${SA_EMAIL}"
gcloud iam service-accounts create "${SA_NAME}" \
  --project="${PROJECT_ID}" \
  --display-name="Agente Seguros Horizonte (BQ Solo Lectura + Logs)" || true

# Esperar breve propagación de IAM tras crear una cuenta de servicio nueva
sleep 8

echo "==> 4. Aplicando IAM de mínimo privilegio:"
echo "    - roles/bigquery.jobUser a nivel proyecto (permite correr queries)"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser" >/dev/null

echo "    - SOLO LECTURA (roles/bigquery.dataViewer) sobre ${DATASET_DATA}"
bq query --use_legacy_sql=false \
  "GRANT \`roles/bigquery.dataViewer\` ON SCHEMA \`${PROJECT_ID}.${DATASET_DATA}\` TO 'serviceAccount:${SA_EMAIL}'"

echo "    - ESCRITURA/LECTURA (roles/bigquery.dataEditor) SOLO sobre ${DATASET_LOGS}"
bq query --use_legacy_sql=false \
  "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`${PROJECT_ID}.${DATASET_LOGS}\` TO 'serviceAccount:${SA_EMAIL}'"

echo ""
echo "Listo. Si necesitas la clave JSON para probar desde tu PC/Codespaces:"
echo "  gcloud iam service-accounts keys create bq-sa.json --iam-account=${SA_EMAIL}"
echo "  cloudshell download bq-sa.json"
echo ""
echo "Para desplegar la PWA en Google Cloud Run (sin archivo JSON, usando identidad IAM nativa):"
echo "  gcloud run deploy seguros-horizonte-pwa \\"
echo "    --source . \\"
echo "    --region us-central1 \\"
echo "    --service-account ${SA_EMAIL} \\"
echo "    --allow-unauthenticated \\"
echo "    --set-env-vars \"DB_BACKEND=bigquery,GCP_PROJECT_ID=${PROJECT_ID},BIGQUERY_DATASET=${DATASET_DATA},BIGQUERY_LOGS_DATASET=${DATASET_LOGS},GEMINI_MODEL=gemini-3.8-flash,GEMINI_API_KEY=TU_GEMINI_API_KEY,APP_SECRET_KEY=\$(openssl rand -hex 24)\""

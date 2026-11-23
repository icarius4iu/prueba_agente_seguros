# Prueba técnica: Agente de consultas de pólizas y siniestros

Lee primero **ENUNCIADO.pdf**: ahí están el caso, las reglas, los entregables y cómo te evaluaremos.

## Contenido

| Carpeta | Qué contiene |
| --- | --- |
| `datos/` | Tablas de clientes, pólizas, siniestros y asesores en CSV, más el diccionario de datos |
| `condicionados/` | Condiciones generales y condicionados de los seguros vehicular, salud y vida |
| `casos_prueba/` | Las 12 consultas que tu agente debe resolver (en .md y .json) |
| `plantillas/` | Plantillas de DISENO.md y RESULTADOS.md para tu entrega |

## Datos clave

- **Fecha de referencia:** 15 de octubre de 2026.
- **Plazo:** 3 días calendario desde que recibes la prueba.
- **Todos los datos son ficticios.**

## Para empezar a explorar los datos

```bash
pip install duckdb
python -c "import duckdb; print(duckdb.sql(\"SELECT ramo, estado, COUNT(*) FROM read_csv_auto('datos/polizas.csv') GROUP BY ALL\"))"
```

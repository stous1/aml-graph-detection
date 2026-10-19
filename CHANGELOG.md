# Cambios

## Hito 1 (2026-10-19)

- Ingesta de AMLworld Small (HI y LI) a DuckDB: cuentas, transacciones con `tx_id`
  determinista y monto en USD, patrones cruzados al 100 % y tasas implícitas.
- Partición temporal: arranque (día 1, solo historia), desarrollo (2–6), prueba (7–10) y
  cola excluida; intentos puente ignorados en ambos períodos.
- Exploración: volúmenes, artefactos del día 1 y de la cola, historias por cuenta.
- Grafo temporal dirigido en DuckDB y consultas sin etiquetas para el futuro agente.
- Detector de abanicos por forma y regla simple; búsqueda de 1.024 configuraciones en HI
  desarrollo; parámetros congelados en `hito1-congelado`.
- Evaluación única en prueba en HI y LI: precisión en el top-k, F1 ilícita y recall por tipo.
- Mini-AMLworld sintético para pruebas deterministas y CI.

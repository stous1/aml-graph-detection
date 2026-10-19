# Cambios

## Hito 2 (2026-10-19)

- Ablación de la mezcla de monedas en el detector del hito 1 (desarrollo y prueba).
- Pares de paso (recibir y reenviar un monto parecido) como base de ciclos temporales
  acotados, cadenas de paso y dispersión-concentración; concentración-dispersión.
- Abanicos de entrada y salida por forma pura; abanicos con dirección.
- Variables por cuenta (dinero de paso, velocidad, contrapartes nuevas) e Isolation Forest.
- Combinación por percentiles congelados de desarrollo; cada detector con y sin señales
  sospechosas de artefacto.
- Diagnóstico de LI en desarrollo y del truncamiento al fin de la ventana.
- Parámetros congelados en hito2-congelado; prueba medida una vez.

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

# Preregistro: prueba fresca con HI-Medium y LI-Medium

[← Volver a la portada](index.md) ·
[Versión legible por máquina, con las huellas de los artefactos](resultados/preregistro_medium.json)

**Estado: preregistrado, pendiente de ejecutar (v1.1).** Este documento y su JSON se fijaron con
el tag `medium-preregistrado` **antes de descargar los archivos de Medium**. La v1.1 los
ejecutará tal cual, una sola vez. Cualquier desviación se informará como tal.

## Por qué

El período de prueba de Small (días 7 a 10) se midió en los cuatro hitos. Cada medición fue
única y con parámetros congelados, pero las decisiones de cada hito pudieron estar influidas
por lo visto en los anteriores. Medium es otro mundo generado por AMLworld (otras cuentas,
unos 16 días), que nadie ha mirado: es la prueba que resuelve ese sesgo.

## Qué se evalúa (sin ningún ajuste)

Todo sale de Small y se aplica tal cual: los parámetros de HI-Small van a HI-Medium y los de
LI-Small, a LI-Medium.

| Modelo | Papel | Qué se congela |
|---|---|---|
| **GNN solo estructurales** | **modelo final** | pesos, estadísticas de estandarización, fracción de alertas |
| Red sin grafo con las mismas variables | comparación declarada (H3) | pesos, fracción de alertas |
| Combinado estructural (hito 2) | comparación sin etiquetas (H2) | configuraciones, percentiles de Small (`congelados/`), umbral absoluto y fracción de alertas |
| Regla simple | referencia (H1) | umbral absoluto (contrapartes en 24 h) |
| Abanicos del hito 1 (mezcla de monedas) | referencia del artefacto | umbral absoluto; solo para ver si la huella del simulador se repite |

## Umbrales

- **Modelo final, red sin grafo y combinado estructural:** umbral relativo. En cada bloque de
  evaluación se marca la misma fracción de transferencias (y de cuentas) que dio el mejor F1
  en el desarrollo de Small.
- **Regla simple, abanicos del hito 1 y combinado estructural:** también con su umbral absoluto
  congelado.
- Las métricas de ranking (precisión en el top-k, precisión promedio) no dependen del umbral.

## Métricas

- **Precisión en el top-k de cuentas** con k = 100, 500, 1.000 y el número de cuentas
  ilícitas, con intervalo de Wilson.
- **F1 de la clase ilícita**, por transacción y por cuenta, con bootstrap de Poisson por cuenta
  de origen.
- **Precisión promedio por transacción.**
- **Recall por tipo de patrón:** un intento cuenta como detectado si al menos la mitad de sus
  transferencias evaluadas quedan marcadas; el lavado sin patrón se mide por transacción.
- **Nunca exactitud global.**

## Comparaciones declaradas

- **H1. Modelo final contra regla simple:** precisión promedio y top-100.
- **H2. Modelo final contra combinado estructural:** precisión promedio, top-100 y F1.
- **H3. Modelo final contra red sin grafo:** diferencia de precisión promedio con IC 95 %
  bootstrap pareado por cuenta de origen. Regla de lectura, fijada ahora:
  - **el grafo aporta** si el intervalo queda por encima de 0 en las dos variantes;
  - **empeora** si queda por debajo de 0 en las dos;
  - en cualquier otro caso, **no hay evidencia de aporte**.

Se reportan todas, salgan como salgan, en HI-Medium y en LI-Medium.

## Partición y ejecución

- **Día 1:** solo historia; nunca se mide, aunque no muestre el artefacto de arranque.
- **Cola:** se excluyen los días finales con menos del 1 % del volumen diario mediano de los
  días 2 en adelante. Si no hay cola, no se excluye nada.
- **Evaluación:** todos los demás días. No hay desarrollo ni intentos puente; los intentos
  cortados por el fin de la ventana se evalúan con lo que se ve.
- **Bloques de 4 días** desde el día 2, cada uno con su historia previa (el último puede ser
  más corto). Se reportan las métricas de todo el período evaluado y las de cada bloque.
- **Recursos:** base aparte (`data/aml_medium.duckdb`; la de Small no se toca), DuckDB limitado
  a 16 GB con desborde a disco en `data/duckdb_tmp`. Pico estimado de 25 a 35 GB.

## Orden de la v1.1

1. Descargar los seis archivos Medium en `data/raw/`. Lo hace el usuario.
2. Escribir y probar el código de la evaluación con el mini-AMLworld, sin abrir Medium.
3. Comprobar que las huellas SHA-256 de los artefactos coinciden con el JSON preregistrado.
4. Tag `medium-codigo` con el código final, antes de leer los datos.
5. Ingesta de Medium y **una sola** ejecución. Publicar todo, incluido lo que salga mal.

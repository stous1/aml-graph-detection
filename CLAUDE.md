# CLAUDE.md

Guía para trabajar en este repositorio.

## Objetivo

Caso de uso 2 del portafolio de ciencia de datos y agentes aplicado a banca: **detección de
lavado de activos en redes de transferencias**. Sobre AMLworld (IBM), el proyecto detecta
cuentas y transferencias de lavado combinando la forma de la red (abanicos, ciclos,
dispersión-concentración), el comportamiento de cada cuenta (CoLES) y redes neuronales sobre
grafos, y mide cuánto aporta cada parte. Más adelante, un agente investigará las alertas.

Hitos:

1. Ingesta en DuckDB, exploración, grafo temporal dirigido y detector de abanicos.
2. Ciclos acotados, dispersión-concentración, variables por cuenta e Isolation Forest.
3. Huella de comportamiento con CoLES y "no te pareces a ti mismo" (antes, verificar si las
   historias alcanzan y preguntar).
4. PyGOD y una GNN con embeddings de CoLES: CoLES solo, grafo solo y combinados.
5. Visualización con Cosmograph y publicación en Pages.

Trabajo futuro (no se implementa aún): agente investigador. Por eso las consultas de
`consultas.py` son funciones limpias, sin etiquetas y acotadas en el tiempo.

## Stack

- Python 3.12, manejado por **uv** (`.python-version` fija 3.12).
- **DuckDB** local (`data/aml.duckdb`), sin servicios externos.
- pandas, numpy, python-igraph, scikit-learn; Altair + vl-convert para gráficos HTML y PNG.
- pytorch-lifestream (CoLES) sobre torch **CPU**: el índice de PyTorch CPU está fijado en
  `pyproject.toml` para que local y CI usen la misma variante. La máquina tiene una GPU
  (RTX 4080 SUPER) que hoy no se usa; si un hito la necesita, se agrega aparte sin romper CI.
- **pytest** para pruebas y **ruff** para lint y formato.

## Comandos

```bash
uv sync                                       # crea .venv e instala dependencias (incluye dev)
uv run pytest                                 # todas las pruebas (mini-AMLworld sintético)
uv run pytest -m "not integracion"            # solo pruebas rápidas
uv run ruff check . && uv run ruff format .   # lint y formato
uv run python scripts/hito1.py preparar       # CSV de data/raw -> data/aml.duckdb (~30 s)
uv run python scripts/hito1.py explorar       # -> reports/hito1/exploracion.json y gráficos
uv run python scripts/hito1.py desarrollar    # rejilla en HI desarrollo -> reports/hito1/
uv run python scripts/hito1.py evaluar        # prueba, con docs/resultados/hito1/parametros.json
uv run python scripts/hito2.py desarrollar    # selección en HI desarrollo -> reports/hito2/ (~45 min)
uv run python scripts/hito2.py evaluar        # prueba, con docs/resultados/hito2/parametros.json
uv run python scripts/hito3.py desarrollar    # entrena CoLES (CPU, ~20 min por variante)
uv run python scripts/hito3.py evaluar        # prueba, con docs/resultados/hito3 (congelado)
uv run python scripts/publicar_resultados.py --hito 1   # o 2, 3: reports/hitoN -> docs/resultados/hitoN
```

## Datos

- `data/raw/`: los seis archivos Small de AMLworld (HI y LI: `_Trans.csv`, `_Patterns.txt`,
  `_accounts.csv`). **No se versionan.** Las variantes Medium y Large **no se descargan ni se
  procesan sin preguntarle antes al usuario.**
- **Medium (aprobado como prueba fresca final, después del hito 4):** el usuario descarga los
  archivos cuando se lo pidan. Se evalúa una sola vez el modelo final con artefactos congelados
  de Small (`docs/resultados/congelados/`), sin ajustes, por bloques de 4 días y con DuckDB
  limitado a 16 GB con desborde a disco. Ver la propuesta en `INFORME_TECNICO.md`.
- **Large:** no por ahora. Trabajo futuro: "no te pareces a ti mismo" con una muestra de
  cuentas y sus 97 días, filtrada sin cargar el archivo completo.
- Cada variante vive en su esquema de DuckDB (`hi`, `li`): `cuentas`, `transacciones`,
  `patrones`, `tasas`, `intentos`, `etiquetas`, `aristas` y `estructuras`.
- Cuenta = banco (entero, sin ceros a la izquierda) + número. El CSV repite la columna
  `Account`: se lee con nombres explícitos. `tx_id` = posición tras ordenar por todos los
  campos (no depende de la lectura en paralelo). Montos en USD con tasas implícitas estimadas
  en días 1 a 6.

## Estructura

- `src/lavado/`: toda la lógica, como funciones reutilizables.
  - `rutas.py`: rutas del proyecto. **Toda ruta se obtiene de aquí.**
  - `ingesta.py`, `patrones.py`, `tasas.py`: CSV a DuckDB.
  - `particion.py`: corte temporal, intentos puente y tabla de etiquetas.
  - `exploracion.py`, `tableros.py`: resúmenes y gráficos.
  - `grafo.py`: tabla de aristas (multigrafo dirigido temporal) y subgrafos en igraph.
  - `consultas.py`: transacciones de una cuenta, vecinos, flujo temporal y patrones detectados.
    **No leen etiquetas** (lo verifica `tests/test_consultas.py`) y aceptan `hasta`.
  - `detectores/abanicos.py`: abanicos de entrada y salida puntuados por forma; la regla
    simple es el mismo código sin variables de forma.
  - Hito 2: `paso.py` (pares de paso: recibe y reenvía un monto parecido dentro de Δ),
    `detectores/ciclos.py`, `detectores/cadenas.py`, `detectores/dispersion.py`
    (dispersión-concentración y concentración-dispersión), `variables_cuenta.py` +
    `detectores/aislamiento.py` (Isolation Forest), `combinacion.py` (percentiles congelados
    de desarrollo) y `flujo_hito2.py` (registro de detectores, selección, ablación,
    diagnóstico de LI). Congelado en `hito2-congelado` con `docs/resultados/hito2/parametros.json`.
  - Hito 3: `secuencias.py` (eventos por cuenta, sin moneda ni formato), `coles.py` (CoLES de
    pytorch-lifestream, determinista en CPU), `detectores/coles_atipico.py` (rareza de la huella)
    y `flujo_hito3.py` (cobertura, entrenamiento con el desarrollo de cada variante, combinado
    estructural + CoLES, viabilidad de "no te pareces a ti mismo"). Congelado en
    `hito3-congelado` con `docs/resultados/hito3/parametros.json` y los modelos
    `docs/resultados/hito3/modelos/coles_{hi,li}.pt` (versionados; `evaluar` los carga, no
    reentrena).
  - `evaluacion.py`: **el único módulo que lee la verdad.**
  - `sintetico.py`: mini-AMLworld para pruebas y CI.
  - `flujo_hito1.py`: preparar, explorar, desarrollar y evaluar.
- `scripts/`: puntos de entrada delgados que orquestan funciones de `src/`.
- `notebooks/`: solo exploración. Nada en `src/` ni `scripts/` importa de notebooks.
- `tests/`: pytest. Las lentas se marcan con `@pytest.mark.integracion`. Todas corren sobre el
  mini-AMLworld, así CI no necesita los datos reales.
- `data/` y `reports/` (ignoradas): datos, base DuckDB y salidas de trabajo.
- `README.md` es la puerta de entrada corta; el detalle con todas las cifras está en
  `INFORME_TECNICO.md`.
- `docs/`: documentación y fuente de GitHub Pages (rama `main`, carpeta `/docs`).
  `docs/resultados/` se versiona y solo se actualiza con `scripts/publicar_resultados.py`.

## Convenciones

- La lógica vive en `src/` como funciones reutilizables **con type hints**.
- Los notebooks son solo para exploración; si algo sirve, se pasa a `src/` con su test.
- Las pruebas no dependen de internet ni de `data/raw`.
- **Las pruebas son deterministas**: semillas fijas y nada que dependa del reloj ni de la
  zona horaria. La conexión fija `TimeZone = 'UTC'` y las ventanas se calculan con aritmética
  de intervalos sobre `TIMESTAMP` sin zona (nunca `to_timestamp(...)::TIMESTAMP`, que convierte
  con la zona de la máquina).
- Documentación, docstrings y mensajes de commit **en español**.
- Rutas centralizadas en `lavado.rutas`; **nunca rutas absolutas** en el código.
- Commits pequeños y enfocados. En modo autónomo no se pide confirmación antes de cada commit:
  al cerrar cada hito se hace push y se entrega un resumen de lo subido.

## Regla de evaluación

- **Partición temporal** dentro de los 10 días (fin exclusivo):
  - arranque = día 1: artefacto del generador (22 % del volumen, 46 % autotransferencias).
    Solo sirve como historia para calcular variables; no se miden métricas sobre él.
  - desarrollo = días 2 a 6; prueba = días 7 a 10.
  - cola = día 11 en adelante: ~60 % lavado, artefacto. Se excluye de todo.
- **Intentos puente** (con transferencias en desarrollo y en prueba): sus transferencias se
  ignoran en las métricas de ambos períodos, y también las cuentas cuyo único lavado del
  período está en ellos.
- En prueba, los detectores pueden usar transferencias de desarrollo como historia (es el
  pasado), nunca sus etiquetas. Un detector trabajando en desarrollo no ve nada de prueba.
- Toda decisión que mire etiquetas (variables, ventana, umbral) se toma solo en
  **desarrollo**; la configuración se elige en HI y se congela (tag `hito1-congelado` con
  `docs/resultados/hito1/parametros.json`, verificado por `tests/test_flujo_hito1.py`). Prueba
  se mide **una sola vez**. Cifras de desarrollo se presentan marcadas como optimistas.
- En la fase no supervisada, las etiquetas solo se usan para evaluar (y para elegir entre
  configuraciones en desarrollo, documentado como tal).
- Métricas: **precisión en el top-k** de cuentas, **recall por tipo de patrón** (intentos; los
  de lavado sin patrón, por transacción) y **F1 de la clase ilícita**. **Nunca exactitud.**
- Siempre en **HI y en LI**, y siempre contra la **regla simple** (contrapartes en 24 h).
- Los anillos se detectan por su **forma** y no solo por su tamaño.
- **Señales sospechosas de artefacto** del generador: moneda (mezcla de monedas, número de
  monedas) y formato de pago (participación de formatos, abanicos por canal). Se prefieren
  las estructurales (tiempo, montos, topología). Cada detector se declara con o sin
  sospechosas (`flujo_hito2.Detector.sospechosas`, verificado por `tests/test_hito2.py`) y se
  reporta con y sin ellas. La ablación del hito 1 mostró que sin mezcla de monedas el
  detector de abanicos no funciona.
- **El período de prueba (días 7 a 10) se evalúa en varios hitos.** Cada hito lo mide una
  sola vez, al final y con sus parámetros congelados, pero ya no es una prueba virgen: las
  decisiones de un hito pueden estar influidas por lo que se vio en prueba en hitos
  anteriores. Se anota en el informe de cada hito.

## Regla de procesos (para Claude y cualquier subagente)

- **Nunca terminar procesos que no hayas iniciado tú.** Nada de `taskkill /IM`, `pkill`,
  `killall` ni `kill` generales por nombre: pueden cerrar procesos del usuario o de otras
  sesiones.
- Si un comando se traba, termina solo ese proceso por su identificador (el que lanzaste
  tú) o pregúntale al usuario.
- Al delegar en un subagente, incluye esta regla en sus instrucciones.

## Regla de credenciales (para Claude y cualquier subagente)

- Las credenciales guardadas en la máquina (git, tokens, llaveros) solo se usan para
  `git push`. Para cualquier otra cosa (leer logs de CI, llamar la API de GitHub u otro
  servicio) hay que preguntarle antes al usuario.

## Regla dura de datos

- **Nunca usar datos reales de clientes.** Solo datasets públicos (AMLworld y, más adelante,
  los listados en la descripción del caso) o sintéticos.
- **Tampoco** código, reglas ni ideas de proyectos internos de ningún banco.
- Otros repositorios hermanos (por ejemplo `../identity-resolution`) son solo de referencia:
  no se modifican desde aquí.

## Docker

No se usa: todo corre local con DuckDB. Si más adelante hace falta, se añade un
`docker-compose.yml` en la raíz y se documenta aquí cómo levantarlo.

<div align="center">

# Detección de lavado en redes de transferencias

**¿Qué cuentas de una red de transferencias están lavando dinero?** Detectores por forma,
huellas de comportamiento y redes sobre grafos, evaluados con partición temporal contra la
verdad del simulador AMLworld y siempre comparados con una regla simple.

[![CI](https://github.com/stous1/aml-graph-detection/actions/workflows/ci.yml/badge.svg)](https://github.com/stous1/aml-graph-detection/actions/workflows/ci.yml)
[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-sitio-2ea44f?logo=github)](https://stous1.github.io/aml-graph-detection/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776ab?logo=python&logoColor=white)](.python-version)
[![Licencia MIT](https://img.shields.io/badge/licencia-MIT-blue)](LICENSE)

[![Universo de prueba en Cosmograph](docs/resultados/hito5/universo_escritorio.png)](https://stous1.github.io/aml-graph-detection/hito5_universo.html)

<sub>Cuentas del período de prueba de HI: en azul, alertas acertadas del modelo final; en
naranja, falsas alarmas; en aguamarina, lavado no detectado.
[Abrir el universo interactivo →](https://stous1.github.io/aml-graph-detection/hito5_universo.html)</sub>

**[Universo interactivo](https://stous1.github.io/aml-graph-detection/hito5_universo.html)** ·
**[Sitio](https://stous1.github.io/aml-graph-detection/)** ·
**[Informe técnico](INFORME_TECNICO.md)** ·
**[Preregistro de la prueba con Medium](docs/preregistro_medium.md)**

</div>

## En un minuto

**El problema.** El lavado se esconde en la red: abanicos de cuentas nuevas, ciclos que
devuelven el dinero al origen, cadenas de cuentas que reenvían casi el mismo monto. Una regla
que solo cuenta contrapartes se llena de comercios legítimos.

**Qué se construyó.** Un sistema local en DuckDB sobre AMLworld (IBM, sintético: HI con 5,1
millones de transferencias y 1 de cada 981 de lavado; LI con 6,9 millones y 1 de cada 1.942).
Tiene cinco hitos:

1. **Abanicos por forma.**
2. **Detectores estructurales:** ciclos, cadenas y dispersión-concentración con monto
   conservado, más Isolation Forest.
3. **CoLES:** huella de comportamiento por cuenta, sin etiquetas.
4. **Redes sobre grafos:** con etiquetas, y PyGOD sin ellas.
5. **Un universo navegable en Cosmograph.**

Solo usa señales que existirían en un banco real: tiempo, montos y topología.

**Resultados** (período de prueba, días 7 a 10, medido una vez por hito con parámetros
congelados):

- **Modelo final:** una GNN entrenada con las etiquetas de desarrollo, solo con variables
  estructurales. En HI, **98 de las 100 primeras alertas son cuentas ilícitas** y el F1 de
  la clase ilícita es **0,276**, contra 0,003 de la regla simple. En LI, top-100 de 0,29 y F1
  0,045.
- **Sin etiquetas,** el combinado de detectores estructurales llega a la mitad: F1 0,118 y
  top-100 de 0,48 en HI.
- **El mérito es de las variables, no del grafo:** con las mismas variables, una red sin
  paso de mensajes rinde lo mismo en prueba.
- **LI es mucho más difícil:** el 82 % de su lavado son transferencias sueltas, sin patrón.

**Lo que falta, y está escrito antes de mirar:** la prueba fresca con HI-Medium y LI-Medium
está [preregistrada](docs/preregistro_medium.md) (modelos, umbrales, métricas y
comparaciones, con tag `medium-preregistrado`) y se ejecutará en la v1.1.

## Qué se puede ver

| Página | Qué muestra |
|---|---|
| [Universo de prueba](https://stous1.github.io/aml-graph-detection/hito5_universo.html) | Cosmograph con las alertas del modelo final, el lavado por tipo y el no detectado (HI y LI; carga en celular) |
| [Hito 1](https://stous1.github.io/aml-graph-detection/hito1.html) | Datos, artefactos del simulador (día 1 y cola), partición y primer detector |
| [Hito 2](https://stous1.github.io/aml-graph-detection/hito2.html) | Ablación de monedas y detectores estructurales |
| [Hito 3](https://stous1.github.io/aml-graph-detection/hito3.html) | CoLES y "no te pareces a ti mismo" |
| [Hito 4](https://stous1.github.io/aml-graph-detection/hito4.html) | GNN, PyGOD y el diagnóstico del grafo |
| [Hito 5](https://stous1.github.io/aml-graph-detection/hito5.html) | Qué muestra el universo |
| [Preregistro de Medium](docs/preregistro_medium.md) | El protocolo de la prueba fresca, con las huellas de los artefactos |
| [Informe técnico](INFORME_TECNICO.md) | Todas las cifras, supuestos, diagnósticos y limitaciones |

## Resultados

Período de prueba (días 7 a 10). Cuentas ilícitas evaluadas: 2.072 en HI y 1.991 en LI.

| Detector | Etiquetas | F1 tx HI | Top-100 HI | Top-1.000 HI | F1 tx LI | Top-100 LI | Top-1.000 LI |
|---|---|---|---|---|---|---|---|
| Regla simple (contrapartes en 24 h) | no | 0,003 | 0,01 | 0,02 | 0,003 | 0,02 | 0,02 |
| Combinado estructural (hito 2) | no | 0,118 | 0,48 | 0,18 | 0,028 | 0,04 | 0,06 |
| CoLES, huella atípica (hito 3) | no | 0,003 | 0,10 | 0,03 | 0,002 | 0,07 | 0,02 |
| PyGOD, CoLA (hito 4) | no | 0,003 | 0,16 | 0,04 | 0,003 | 0,18 | 0,03 |
| GNN, estructurales + CoLES | sí | 0,158 | 0,77 | 0,26 | 0,034 | 0,14 | 0,06 |
| Red sin grafo, solo estructurales (diagnóstico) | sí | 0,264 | 1,00 | 0,42 | 0,059 | 0,33 | 0,11 |
| **GNN, solo estructurales (modelo final)** | sí | **0,276** | **0,98** | **0,40** | **0,045** | **0,29** | **0,10** |

Intervalos de 95 % del modelo final: F1 tx de 0,217 a 0,335 en HI y de 0,030 a 0,062 en LI;
top-100 de 0,93 a 0,99 en HI y de 0,21 a 0,39 en LI.

**Referencia, con señales que dependen del simulador:** el detector de abanicos del hito 1
(F1 0,143 y top-100 de 0,91 en HI) se apoyaba en que el centro de un abanico de lavado paga en
varias monedas. Sin esa señal, cae a F1 0,005 y top-100 de 0,01. No se trasladaría a un banco
de una sola moneda, y por eso no es una cifra principal.

## Rigor, historia y limitaciones

**Cómo se evalúa.**
- **Partición temporal:** el día 1 se usa solo como historia (es un artefacto de arranque:
  22 % del volumen y 46 % de autotransferencias); desarrollo, días 2 a 6; prueba, días 7 a 10.
  La cola de los días 11 a 18 (cerca del 60 % es lavado) se excluye.
- Los intentos de lavado que cruzan el corte se ignoran en ambos lados.
- Toda decisión se toma en desarrollo y se congela con un tag por hito (`hito1-congelado` a
  `hito4-congelado`); una prueba verifica que los parámetros y modelos no cambien.
- **Métricas:** precisión en el top-k, recall por tipo de patrón y F1 de la clase ilícita, con
  intervalos. Nunca exactitud. Siempre en HI y LI, y siempre contra la regla simple.
- Las pruebas son deterministas, sobre un mini-AMLworld sintético, y corren en CI.

**Historia de los hitos, con los hallazgos incómodos.**
1. **Hito 1, abanicos por forma:** top-100 de 0,91 en HI. Parecía un gran resultado.
2. **Hito 2, la ablación:** ese detector dependía casi por completo de la mezcla de monedas, una
   huella del simulador. Reconstruido con forma pura recuperó el 79 % del top-100. El dinero de
   paso con monto conservado resultó la señal estructural más útil: el detector de ciclos
   encuentra los 7 ciclos de HI que se cierran dentro de la ventana. Desde entonces, moneda y
   formato de pago se tratan como sospechosos de artefacto.
3. **Hito 3, CoLES:** como detector de rareza no aporta. En HI encontró lavado sin patrón, pero
   con más de 114 mil falsas alarmas, porque su calibración no se trasladó a prueba. "No te
   pareces a ti mismo" no es viable con 10 días (AUC de 0,55 a 0,58). Con etiquetas, los
   embeddings sí contienen señal (AUC de 0,78 a 0,81 en desarrollo).
4. **Hito 4, grafos:** la GNN supervisada duplica al combinado no supervisado. Pero CoLES la
   empeora, PyGOD queda cerca del azar y, con las mismas variables, la red sin grafo rinde lo
   mismo en prueba. La ventaja del grafo que se veía en desarrollo (+0,079 de AP en HI) no se
   repitió.
5. **Hito 5:** el universo de Cosmograph muestra qué detecta y qué no el modelo final.

En el camino también se corrigió una fuente de no determinismo: las sumas en paralelo de
DuckDB cambiaban el último bit y rompían empates entre puntajes.

**Limitaciones.**
- **El período de prueba se usó cuatro veces,** una por hito. Cada medición fue única y con
  parámetros congelados, pero las decisiones de cada hito pudieron estar influidas por lo visto
  en los anteriores. Las cifras de prueba son, por eso, algo optimistas.
- **La prueba fresca con Medium está preregistrada pero pendiente.** Es la que resuelve el punto
  anterior.
- **Son datos sintéticos de plantilla,** con artefactos (monedas, ACH, día 1, cola) que no
  existirían en un banco. No se validó todavía con otros generadores (TransXion, SAML-D).
- **LI** tiene pocos intentos por tipo (3 a 8 en prueba) y su lavado es casi todo sin patrón: sus
  cifras son bajas y con intervalos anchos.
- Cada red se entrenó con una sola semilla, y la validación de las redes es un solo día.
- El lavado sin patrón y los abanicos de entrada siguen casi sin detectarse.

## Lo que viene

- **v1.1:** ejecutar una sola vez la [prueba preregistrada con Medium](docs/preregistro_medium.md).
- "No te pareces a ti mismo" con una muestra de cuentas de Large (97 días de historia).
- Un agente investigador que use las consultas de `consultas.py` como herramientas.
- Validación con otros generadores (TransXion, SAML-D).

## Uso

```bash
uv sync
# Copiar los seis archivos Small de AMLworld a data/raw/ (no se versionan)
uv run python scripts/hito1.py preparar
uv run python scripts/hito1.py desarrollar && uv run python scripts/hito1.py evaluar
uv run python scripts/hito2.py desarrollar && uv run python scripts/hito2.py evaluar
uv run python scripts/hito3.py desarrollar && uv run python scripts/hito3.py evaluar
uv run python scripts/hito4.py desarrollar && uv run python scripts/hito4.py evaluar
uv run python scripts/hito5.py && uv run python scripts/capturas.py
uv run pytest            # pruebas sobre un mini-AMLworld sintético
# GPU opcional: uv sync --no-group cpu --group gpu, y luego uv run --no-sync ...
```

Datos: [IBM Transactions for Anti Money Laundering (AMLworld)](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml).
Licencia del código: MIT.

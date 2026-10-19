# Informe técnico

Detección de lavado de activos en redes de transferencias con AMLworld (caso 2 del
portafolio de banca). Cada hito deja aquí todas sus cifras, supuestos y limitaciones.

## Hito 1: ingesta, exploración y abanicos por forma

### Datos

AMLworld (IBM) es un generador sintético de transferencias con lavado sembrado. Se usan las
variantes **Small**: HI (más lavado) y LI (menos lavado).

| | HI-Small | LI-Small |
|---|---|---|
| Transacciones | 5.078.345 | 6.924.049 |
| Cuentas | 518.581 | 712.688 |
| Transacciones de lavado | 5.177 (1 de cada 981) | 3.565 (1 de cada 1.942) |
| Intentos documentados (`_Patterns.txt`) | 370 | 117 |
| Lavado cubierto por intentos | 3.209 tx (62 %) | 1.023 tx (29 %) |

- Las 4.232 líneas de patrones cruzan con una transacción de lavado; ninguna queda sin cruce.
- Cuenta = banco (entero) + número; todas las cuentas de las transacciones están en el
  archivo de cuentas. El CSV repite la columna `Account` y se lee con nombres explícitos.
- 15 monedas. Los montos se pasan a USD con tasas implícitas estimadas por mínimos
  cuadrados sobre las transferencias entre monedas distintas de los días 1 a 6 (por ejemplo,
  euro 1,172, yuan 0,150, bitcoin 11.794 USD en HI).
- Historias por cuenta (sin autotransferencias, días 1 a 10): mediana de 10 transferencias,
  50 % de las cuentas activas con 10 o más, 38 % con 20 o más y 11 % con 50 o más (casi
  idéntico en HI y LI). Es el punto de partida para decidir en el hito 3 si alcanza para CoLES.

![Transacciones y tasa de lavado por día](docs/resultados/hito1/por_dia.png)

### Dos artefactos del generador

**Día 1 (arranque).** Concentra el 22 % de las transacciones (1,11 millones en HI, contra
440 mil de media en los días 2 a 10), el 46 % son autotransferencias `Reinvestment` (2,1 % el
resto de los días) y la tasa de lavado es 0,029 %, casi cuatro veces menor que la de los días
2 a 10 (0,106 %). En LI ocurre lo mismo: 22 %, 46 % y 0,020 % contra 0,058 %. Es el
arranque del simulador: **solo se usa como historia para calcular variables y no se miden
métricas sobre él.**

**Cola (11 al 18 de septiembre).** 1.108 transacciones en HI, de las que 655 (59 %) son de
lavado; en LI, 223 y 134 (60 %). Son intentos que siguen corriendo cuando el resto del mundo
ya se detuvo (109 intentos de HI tocan la cola; 7 viven solo en ella). Incluirla inflaría el
recall con transacciones casi siempre ilícitas: **se excluye de todo.**

### Partición temporal

| Período | Días | Uso |
|---|---|---|
| arranque | 1 | solo historia |
| desarrollo | 2 a 6 | toda decisión que mire etiquetas |
| prueba | 7 a 10 | una sola medición, con parámetros congelados |
| cola | 11 a 18 | excluida |

**Regla del corte.** Se fijó días 2–6 / 7–10, con la regla de mover el corte un día si algún
tipo de patrón quedaba con menos de 10 intentos en prueba. La decisión miró solo conteos de
etiquetas, antes de cualquier resultado de detector. Intentos por tipo (desarrollo incluye a
los que vienen del arranque; prueba, a los que siguen en la cola):

| Tipo | HI desarrollo | HI puente | HI prueba | LI desarrollo | LI puente | LI prueba |
|---|---|---|---|---|---|---|
| BIPARTITE | 25 | 2 | 18 | 6 | 2 | 8 |
| CYCLE | 20 | 15 | 18 | 1 | 4 | 7 |
| FAN-IN | 10 | 12 | 17 | 6 | 3 | 3 |
| FAN-OUT | 19 | 10 | 19 | 8 | 6 | 5 |
| GATHER-SCATTER | 10 | 20 | 20 | 3 | 4 | 4 |
| RANDOM | 14 | 10 | 17 | 7 | 2 | 6 |
| SCATTER-GATHER | 12 | 13 | 19 | 4 | 4 | 5 |
| STACK | 11 | 14 | 15 | 8 | 6 | 3 |

En HI todos los tipos tienen al menos 15 intentos en prueba: el corte se queda. **En LI
ningún corte puede cumplir la regla** (hay entre 12 y 19 intentos por tipo en todo el
archivo); la regla se aplica a HI y en LI el recall por tipo se reporta con su n y con
intervalos amplios.

**Intentos puente.** 96 intentos de HI y 31 de LI tienen transferencias en desarrollo y en
prueba. Sus transferencias se **ignoran en las métricas de ambos períodos** (no son positivas
ni negativas): 531 + 570 transacciones de lavado en HI y 185 + 225 en LI. También se ignoran
las cuentas cuyo único lavado del período está en intentos puente (621 en HI y 269 en LI en
prueba).

**Historia sin fuga.** Un detector trabajando en desarrollo ve solo transferencias anteriores
al 7 de septiembre. En prueba ve todo hasta el 10, incluido desarrollo como historia, pero
nunca etiquetas. La alerta se emite al cerrar la ventana.

### Grafo temporal dirigido

Multigrafo dirigido: cuentas como nodos y una arista por transferencia entre cuentas distintas,
con fecha, monto en USD, moneda y formato (4.486.418 aristas en HI). Vive como tabla en DuckDB;
`grafo.aristas_entre` arma subgrafos de igraph bajo demanda. Las autotransferencias se
conservan pero no son aristas.

Las consultas para el futuro agente (`consultas.py`: transacciones de una cuenta, vecinos a
k saltos, flujo por intervalos y estructuras detectadas) no leen etiquetas y aceptan `hasta`.

### Detector de abanicos por forma

Una **estructura** es una cuenta centro con todas las transferencias que envía (abanico de
salida) o recibe (abanico de entrada) en una ventana fija de W horas. Hay dos desfases (0 y
W/2), así que toda ráfaga de hasta W/2 horas cae completa en alguna ventana. Son candidatas
las que tienen al menos 3 contrapartes distintas. Opcionalmente, la estructura es de un solo
canal (formato de pago).

Variables de forma, en [0, 1]: `novedad` (contrapartes sin contacto previo), `exclusividad`
(qué parte de la actividad de cada contraparte es con el centro), `unicidad` (contrapartes /
transferencias), `homogeneidad` de montos, `formato` (participación del más frecuente),
`mezcla_monedas` (1 − participación de la moneda más frecuente) y `dispersion` (duración /
W). Puntaje = tamaño (log2 de contrapartes, o 1) × producto de las variables elegidas, con
piso 0,01.

**Regla simple** (comparación obligatoria): número de contrapartes distintas en 24 horas,
sin forma. Es el mismo código sin variables.

**Qué se aprendió en desarrollo, y se corrigió.** La primera versión suponía abanicos de una
sola moneda y concentrados en el tiempo, y con todas las variables daba un F1 de 0,015 en HI
desarrollo. Al comparar las estructuras de los 18 intentos FAN-IN y FAN-OUT de desarrollo
con 3 o más transferencias contra el resto (mediana; solo etiquetas de desarrollo):

| | abanicos de lavado | todas las estructuras |
|---|---|---|
| contrapartes | 8,5 | 3 |
| transferencias | 8,5 | 6 |
| participación de la moneda más frecuente | 0,76 | 1,00 |
| concentración temporal (1 − duración/W, W = 72 h) | 0,17 | 0,39 |

Los abanicos de lavado tienen **una transferencia por contraparte, mezclan monedas y se
reparten en el tiempo**: lo contrario de dos supuestos a priori. Se agregaron `unicidad`,
`mezcla_monedas` y `dispersion`, y se quitaron las dos variables orientadas al revés. Además,
muchos intentos son diminutos: en HI (los tres períodos) hay 16 FAN-OUT y 9 FAN-IN con grado
declarado 1 o 2, que no tienen forma de abanico.

**Selección.** Rejilla de 1.024 configuraciones: W en {24, 48, 72, 96} h, con o sin canal,
hasta 3 variables y tamaño log2 o ninguno. Criterio: máximo F1 ilícita por transacción en HI
desarrollo; empates a 3 decimales, gana la más simple. Resultado, congelado en el tag
`hito1-congelado`:

- **W = 96 h, por canal, puntaje = log2(contrapartes) × unicidad × mezcla_monedas.**
- Umbral de F1 elegido en el desarrollo de cada variante: 0,802 en HI y en LI (coinciden;
  el puntaje toma valores discretos). Regla simple: 7.280 contrapartes en HI (el máximo F1
  de la regla está en un solo centro gigante) y 11 en LI.

Cifras de desarrollo (**optimistas**, se usaron para elegir):

| | F1 tx | Precisión en top-100 |
|---|---|---|
| HI, abanicos por forma | 0,147 | 0,94 |
| HI, regla simple | 0,003 | 0,02 |
| LI, abanicos por forma | 0,073 | 0,60 |
| LI, regla simple | 0,003 | 0,01 |

### Resultados en prueba (días 7 a 10, medidos una sola vez)

Universo de prueba en HI: 1.789.315 transferencias (1.422 de lavado) y 366.967 cuentas (2.072
ilícitas). En LI: 2.440.396 transferencias (1.212 de lavado) y 501.213 cuentas (1.991
ilícitas). Intervalos de 95 %: Wilson para la precisión en el top-k, bootstrap de Poisson por
cuenta de origen para el F1 y bootstrap por intento para el recall.

**Precisión en el top-k de cuentas**

| | k = 100 | k = 500 | k = 1.000 | k = n.º de ilícitas |
|---|---|---|---|---|
| HI, abanicos por forma | **0,91** (0,84–0,95) | **0,29** (0,25–0,33) | **0,15** (0,13–0,17) | **0,075** (k = 2.072) |
| HI, regla simple | 0,01 (0,00–0,05) | 0,01 | 0,02 | 0,016 |
| LI, abanicos por forma | **0,19** (0,13–0,28) | **0,05** (0,03–0,07) | 0,03 | 0,014 (k = 1.991) |
| LI, regla simple | 0,02 (0,01–0,07) | 0,02 | 0,02 | 0,013 |

**F1 de la clase ilícita**

| | F1 tx (IC 95 %) | precisión tx | recall tx | marcadas | F1 cuenta |
|---|---|---|---|---|---|
| HI, abanicos por forma | **0,143** (0,083–0,209) | 0,344 | 0,090 | 372 | 0,118 |
| HI, regla simple | 0,003 (0,000–0,003) | 0,001 | 0,061 | 59.864 | 0,023 |
| LI, abanicos por forma | **0,025** (0,000–0,066) | 0,059 | 0,016 | 321 | 0,021 |
| LI, regla simple | 0,003 (0,003–0,004) | 0,002 | 0,372 | 290.811 | 0,018 |

En LI, el umbral de HI trasladado sin tocar da lo mismo para el detector (los umbrales
coinciden) y F1 0,003 para la regla.

![Precisión en el top-k](docs/resultados/hito1/precision_k.png)

**Recall por tipo de patrón** (intento detectado si al menos la mitad de sus transferencias
del período quedan marcadas; entre paréntesis, intentos con 3 o más transferencias en el
período, los únicos que pueden tener forma de abanico):

| Tipo | HI forma | HI regla | LI forma | LI regla |
|---|---|---|---|---|
| FAN-OUT | **7/19 = 0,37** (7/8) | 0/19 | 2/5 (2/4) | 1/5 |
| SCATTER-GATHER | **9/19 = 0,47** (8/11) | 0/19 | 1/5 (1/2) | 1/5 |
| FAN-IN | 0/17 (0/8) | 0/17 | 0/3 | 0/3 |
| GATHER-SCATTER | 0/20 | 0/20 | 0/4 | 0/4 |
| BIPARTITE, CYCLE, RANDOM, STACK | 0 | 0 | 0 | 0 |
| Sin patrón (por transacción) | 0/750 | 87/750 = 0,12 | 0/1.034 | 438/1.034 = 0,42 |

![Recall por tipo de patrón](docs/resultados/hito1/recall_tipo.png)

### Lectura

1. **La forma le gana al tamaño por mucho en HI, y la ganancia se sostiene en prueba.** El F1
   de prueba (0,143) es casi igual al de desarrollo (0,147) y 9 de las 10 primeras alertas son
   cuentas ilícitas, contra 1 de cada 100 con la regla. La regla, que solo cuenta
   contrapartes, llena el top con comercios y concentradores legítimos.
2. **Es un detector de abanicos de salida.** Todo lo que encuentra se explica por estructuras
   de salida: FAN-OUT y la mitad dispersora de SCATTER-GATHER. FAN-IN y GATHER-SCATTER quedan
   en 0. La variable decisiva, `mezcla_monedas`, mira la moneda pagada, y en AMLworld el
   centro de un abanico de salida de lavado paga en varias monedas. Es una huella del
   generador más que una ley del lavado. Encontrar abanicos de entrada necesita otra señal y
   queda para el hito 2, junto con ciclos y dispersión-concentración.
3. **LI es mucho más difícil.** La precisión en el top-100 cae de 0,60 en desarrollo a 0,19 en
   prueba, con solo 5 intentos FAN-OUT y 5 SCATTER-GATHER en prueba. El 71 % del lavado de LI
   no pertenece a ningún intento documentado. Sigue por encima de la regla (0,19 contra 0,02
   en el top-100), pero el F1 es bajo y su intervalo toca 0.
4. **Nada de esto detecta el lavado sin patrón.** La regla "recupera" el 12 % (HI) y el 42 %
   (LI) de esas transacciones marcando 59.864 y 290.811 transferencias: no es detección, es
   volumen.

### Limitaciones

- Datos sintéticos de plantilla: la forma que funciona aquí (mezcla de monedas) puede no
  existir en datos reales. El caso propone validar después en TransXion y SAML-D.
- En LI, el recall por tipo se apoya en 3 a 8 intentos por tipo: los intervalos son muy
  anchos.
- Los parámetros se eligieron en HI con etiquetas de desarrollo. Eso es selección
  supervisada de hiperparámetros sobre un detector no supervisado, y así se declara.
- Las autotransferencias no son aristas ni entran en la evaluación. Hay 11 de lavado en HI
  (5 en desarrollo y 2 en prueba, estas dentro de intentos puente) y 3 en LI.
- El F1 por transacción marca todas las transferencias de una estructura que supera el
  umbral. Un centro de lavado con actividad legítima en el mismo canal y ventana aporta
  falsos positivos.

### Reproducir

```bash
uv sync
uv run python scripts/hito1.py preparar     # ~30 s
uv run python scripts/hito1.py explorar
uv run python scripts/hito1.py desarrollar  # ~10 min (1.024 configuraciones)
uv run python scripts/hito1.py evaluar      # ~5 min, usa los parámetros congelados
```

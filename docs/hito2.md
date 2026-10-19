# Hito 2: detectores estructurales, combinación y ablación de monedas

[← Volver a la portada](index.md) ·
[Detalle en el informe técnico](https://github.com/stous1/aml-graph-detection/blob/main/INFORME_TECNICO.md#hito-2-ablación-de-monedas-detectores-estructurales-y-combinación)

> **El período de prueba (días 7 a 10) es el mismo del hito 1.** Se midió una sola vez al final
> de este hito, con parámetros congelados. Pero ya se había mirado, así que las cifras son algo
> optimistas respecto de una prueba nueva.

## ¿El hito 1 dependía de las monedas?

Sí. El detector del hito 1 puntuaba la unicidad por la **mezcla de monedas**: en AMLworld, el
centro de un abanico de lavado paga en varias monedas. Al quitarle solo esa variable, en el
período de prueba de HI su F1 cae de 0,143 a 0,005 y su top-100 de 0,91 a 0,01. Tal como
quedó, el detector no se trasladaría a un banco de una sola moneda.

Reconstruido solo con forma (abanicos de **salida**, contrapartes nuevas, una transferencia
a cada una, montos parecidos), conserva el **69 % del F1 y el 79 % del top-100** en HI.

## Señales de un banco real: tiempo, montos y topología

En desarrollo, ciclos, cadenas, capas y dispersión-concentración comparten una firma: cada
cuenta intermedia **reenvía casi el mismo monto que recibió**, horas o días después. Sobre
ese **par de paso** se construyen ciclos con monto conservado, cadenas de paso,
dispersión-concentración y las variables por cuenta (dinero de paso, velocidad, contrapartes
nuevas) para Isolation Forest. Ninguno de esos detectores usa moneda ni formato de pago, y una
prueba lo verifica.

![Precisión en el top-100 por detector](resultados/hito2/detectores_top100.png)

![F1 por detector](resultados/hito2/detectores_f1.png)

| Prueba, HI / LI | F1 tx | Top-100 | Top-1.000 |
|---|---|---|---|
| Regla simple | 0,003 / 0,003 | 0,01 / 0,02 | 0,02 / 0,02 |
| Abanicos hito 1 (moneda y canal) | 0,143 / 0,025 | **0,91** / 0,19 | 0,15 / 0,03 |
| Abanicos de salida, forma | 0,098 / 0,013 | 0,72 / 0,14 | 0,13 / 0,02 |
| Ciclos | 0,076 / 0,023 | 0,39 / 0,18 | 0,07 / 0,06 |
| Dispersión-concentración | 0,068 / 0,000 | 0,38 / 0,01 | 0,06 / 0,03 |
| Isolation Forest, forma | 0,011 / 0,003 | 0,32 / 0,18 | 0,09 / 0,04 |
| Combinado, forma | 0,118 / 0,028 | 0,48 / 0,04 | 0,18 / 0,06 |
| Combinado con moneda y formato | **0,151** / **0,049** | 0,47 / **0,23** | **0,22** / **0,08** |

- **Cada detector estructural encuentra su tipo:** los ciclos encuentran los 7 ciclos de HI
  que se cierran dentro de la ventana. Los otros 11 siguen después del día 10 y no pueden
  cerrarse.
- **La combinación amplía la cobertura** (mejor F1, top-500 y top-1.000, recall repartido en
  los 8 tipos), **pero no mejora el top-100:** ahí gana un abanico solo.
- **Abanicos de entrada** siguen sin resolverse con ninguna señal.

## ¿Por qué cae tanto LI?

Diagnóstico en desarrollo:

- El **82 %** del lavado de LI son transferencias sueltas, sin patrón (59 % en HI). Ningún
  detector estructural puede verlas.
- Hay 3 transacciones de ciclo en todo LI desarrollo (71 en HI).
- La tasa de lavado es la mitad.
- Elegir la configuración en LI en vez de HI mejora poco.

La caída es de los datos, no del desarrollo en HI.

## Archivos

[metricas.json](resultados/hito2/metricas.json) ·
[parametros.json (congelado)](resultados/hito2/parametros.json) ·
[desarrollo.json](resultados/hito2/desarrollo.json) ·
[truncamiento.json](resultados/hito2/truncamiento.json) ·
[top-100 interactivo](resultados/hito2/detectores_top100.html) ·
[F1 interactivo](resultados/hito2/detectores_f1.html)

# Detección de lavado en redes de transferencias

**¿Qué cuentas de una red de transferencias están lavando dinero?** Detectores sobre el grafo
temporal de AMLworld (IBM, sintético), evaluados con partición temporal contra las etiquetas
y los patrones del generador, y siempre comparados con una regla simple. Caso 2 de un
portafolio de ciencia de datos aplicada a banca.

## Modelo final: GNN estructural (supervisada)

Una red sobre el grafo, entrenada con las etiquetas de desarrollo, solo con tiempo, montos y
topología. Período de prueba, días 7 a 10: **F1 0,276 en HI** (98 de las 100 primeras alertas
son cuentas ilícitas) y **0,045 en LI** (top-100 de 0,29). Se evaluará una vez en Medium.
[Hito 4 →](hito4.md)

## Sin etiquetas: combinado estructural

Solo con señales que existirían en cualquier banco (**tiempo, montos y topología**), sin
moneda ni formato de pago. Período de prueba, días 7 a 10:

| | F1 ilícita por tx | Top-100 | Top-1.000 |
|---|---|---|---|
| **HI, combinado estructural** | **0,118** | **0,48** | **0,18** |
| HI, regla simple | 0,003 | 0,01 | 0,02 |
| **LI, combinado estructural** | **0,028** | **0,04** | **0,06** |
| LI, regla simple | 0,003 | 0,02 | 0,02 |

![F1 por detector](resultados/hito2/detectores_f1.png)

## En un minuto

- **Hito 4, grafos** ([página](hito4.md)). La GNN supervisada con variables estructurales
  duplica el F1 del combinado no supervisado en HI. CoLES la empeora y PyGOD, sin etiquetas,
  queda cerca del azar.
- **Hito 3, CoLES** ([página](hito3.md)). La huella de comportamiento aprendida sin etiquetas
  no mejora el combinado estructural, y "no te pareces a ti mismo" no es viable con 10 días.
  Pero los embeddings sí contienen información sobre el lavado (AUC 0,78 a 0,81 con
  etiquetas), lo que motiva el hito 4.
- **Hito 2, detectores estructurales** ([página](hito2.md)). Ciclos y dispersión-concentración
  con monto conservado, abanicos por forma pura e Isolation Forest sobre variables de
  comportamiento. Combinados, superan a la regla simple por amplio margen en HI. En LI la
  ganancia es chica: el 82 % de su lavado son transferencias sueltas, sin patrón.
- **La ablación de monedas** mostró que el detector del hito 1 dependía de una huella del
  simulador: el centro de un abanico de lavado paga en varias monedas. Sin esa señal cae de
  0,91 a 0,01 en el top-100. Las cifras con moneda y formato (hasta 0,151 de F1) se muestran
  solo como referencia.
- **Hito 1, ingesta y abanicos** ([página](hito1.md)): DuckDB, partición temporal, artefactos
  del generador (día 1 y cola) y el primer detector.

## Hitos

1. [Ingesta, exploración, grafo temporal y abanicos](hito1.md) ✔
2. [Ciclos, dispersión-concentración, variables por cuenta e Isolation Forest](hito2.md) ✔
3. [Huella de comportamiento con CoLES](hito3.md) ✔
4. [PyGOD y redes neuronales sobre grafos](hito4.md) ✔
5. Visualización con Cosmograph

El período de prueba es el mismo en todos los hitos: cada hito lo mide una sola vez, con
parámetros congelados, pero ya no es una prueba virgen.

[Código en GitHub](https://github.com/stous1/aml-graph-detection) ·
[Informe técnico](https://github.com/stous1/aml-graph-detection/blob/main/INFORME_TECNICO.md)

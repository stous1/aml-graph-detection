# Detección de lavado en redes de transferencias

**¿Qué cuentas de una red de transferencias están lavando dinero?** Detectores sobre el grafo
temporal de AMLworld (IBM, sintético), evaluados con partición temporal contra las etiquetas
y los patrones del generador, y siempre comparados con una regla simple. Caso 2 de un
portafolio de ciencia de datos aplicada a banca.

## Cifra principal: combinado estructural

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
3. Huella de comportamiento con CoLES
4. PyGOD y redes neuronales sobre grafos
5. Visualización con Cosmograph

El período de prueba es el mismo en todos los hitos: cada hito lo mide una sola vez, con
parámetros congelados, pero ya no es una prueba virgen.

[Código en GitHub](https://github.com/stous1/aml-graph-detection) ·
[Informe técnico](https://github.com/stous1/aml-graph-detection/blob/main/INFORME_TECNICO.md)

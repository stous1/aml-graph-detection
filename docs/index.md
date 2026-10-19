# Detección de lavado en redes de transferencias

**¿Qué cuentas de una red de transferencias están lavando dinero?** Detectores sobre el grafo
temporal de AMLworld (IBM, sintético), evaluados con partición temporal contra las etiquetas
y los patrones del generador, y siempre comparados con una regla simple. Caso 2 de un
portafolio de ciencia de datos aplicada a banca.

## En un minuto

- **Hito 1, abanicos por forma** ([página](hito1.md)). En el período de prueba de HI, 91 de
  las 100 primeras alertas son cuentas ilícitas, contra 1 de 100 con la regla que solo cuenta
  contrapartes. El F1 ilícito por transacción es 0,143 contra 0,003. En LI la ventaja se
  achica: 0,19 contra 0,02 en el top-100.
- Lo que separa es la **forma**: una transferencia por contraparte y monedas mezcladas, no el
  tamaño.
- Cobertura honesta: encuentra abanicos de salida (FAN-OUT, SCATTER-GATHER), pero no abanicos
  de entrada, ciclos ni lavado sin patrón. Eso es lo que sigue.

| Prueba (días 7–10) | Top-100 | Top-500 | F1 tx |
|---|---|---|---|
| **HI, abanicos por forma** | **0,91** | **0,29** | **0,143** |
| HI, regla simple | 0,01 | 0,01 | 0,003 |
| **LI, abanicos por forma** | **0,19** | **0,05** | **0,025** |
| LI, regla simple | 0,02 | 0,02 | 0,003 |

![Precisión en el top-k](resultados/hito1/precision_k.png)

## Hitos

1. [Ingesta, exploración, grafo temporal y abanicos](hito1.md) ✔
2. Ciclos, dispersión-concentración, variables por cuenta e Isolation Forest
3. Huella de comportamiento con CoLES
4. PyGOD y redes neuronales sobre grafos
5. Visualización con Cosmograph

[Código en GitHub](https://github.com/stous1/aml-graph-detection) ·
[Informe técnico](https://github.com/stous1/aml-graph-detection/blob/main/INFORME_TECNICO.md)

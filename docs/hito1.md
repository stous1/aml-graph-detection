# Hito 1: ingesta, exploración y abanicos por forma

[← Volver a la portada](index.md) ·
[Detalle en el informe técnico](https://github.com/stous1/aml-graph-detection/blob/main/INFORME_TECNICO.md#hito-1-ingesta-exploración-y-abanicos-por-forma)

## Los datos y sus trampas

AMLworld Small: HI tiene 5,1 millones de transferencias entre 519 mil cuentas, con 1 de cada
981 de lavado. LI tiene 6,9 millones, con 1 de cada 1.942. Dos artefactos del generador
cambian cómo se evalúa:

- **Día 1:** concentra el 22 % del volumen y el 46 % son autotransferencias. Es el arranque
  del simulador y solo se usa como historia.
- **Días 11 a 18:** una cola donde el 60 % es lavado. Se excluye.

![Por día](resultados/hito1/por_dia.png)

## Cómo se evalúa

- Desarrollo = días 2 a 6, prueba = días 7 a 10.
- Los intentos de lavado que cruzan el corte (96 en HI, 31 en LI) se ignoran en ambos lados.
- Todo se elige en desarrollo y se congela antes de mirar prueba.
- Métricas: precisión en el top-k de cuentas, recall por tipo de patrón y F1 de la clase
  ilícita. Nunca exactitud.

## El detector

Una **estructura** es una cuenta con todo lo que envía (abanico de salida) o recibe (de
entrada) en una ventana de tiempo. La **regla simple** cuenta contrapartes en 24 horas. El
**detector por forma** multiplica el tamaño por variables que describen cómo se ve la
estructura. En desarrollo, los abanicos de lavado resultaron tener una transferencia por
contraparte, monedas mezcladas y estar repartidos en el tiempo. Dos supuestos iniciales
(una sola moneda, ráfaga corta) estaban al revés y se corrigieron. La configuración
congelada es: ventana de 96 h, un canal de pago por estructura, puntaje = log2(contrapartes)
× unicidad × mezcla de monedas.

## Resultados en prueba

![Precisión en el top-k](resultados/hito1/precision_k.png)

| | Top-100 | Top-500 | F1 tx (IC 95 %) |
|---|---|---|---|
| HI, abanicos por forma | **0,91** | **0,29** | **0,143** (0,083–0,209) |
| HI, regla simple | 0,01 | 0,01 | 0,003 |
| LI, abanicos por forma | **0,19** | **0,05** | **0,025** (0,000–0,066) |
| LI, regla simple | 0,02 | 0,02 | 0,003 |

![Recall por tipo](resultados/hito1/recall_tipo.png)

- **Encuentra abanicos de salida:** en HI recupera 7 de 8 FAN-OUT y 8 de 11 SCATTER-GATHER con
  3 o más transferencias. No encuentra FAN-IN, GATHER-SCATTER, ciclos ni lavado sin patrón.
- La señal decisiva (mezcla de monedas en lo que paga el centro) parece una huella del
  generador. Por eso se reporta LI y se planea validar en otros datasets.
- LI es más difícil: el 71 % de su lavado no pertenece a ningún patrón documentado, y en
  prueba hay solo 5 intentos FAN-OUT.

## Archivos

[metricas.json](resultados/hito1/metricas.json) ·
[parametros.json (congelado)](resultados/hito1/parametros.json) ·
[desarrollo.json](resultados/hito1/desarrollo.json) ·
[exploracion.json](resultados/hito1/exploracion.json) ·
[precisión top-k interactiva](resultados/hito1/precision_k.html) ·
[recall por tipo interactivo](resultados/hito1/recall_tipo.html)

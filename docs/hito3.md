# Hito 3: CoLES y "no te pareces a ti mismo"

[← Volver a la portada](index.md) ·
[Detalle en el informe técnico](https://github.com/stous1/aml-graph-detection/blob/main/INFORME_TECNICO.md#hito-3-coles-y-no-te-pareces-a-ti-mismo)

> El período de prueba (días 7 a 10) es el mismo de los hitos 1 y 2. Se midió una sola vez,
> con parámetros y modelos congelados.

## En corto

- **CoLES** (pytorch-lifestream) aprende sin etiquetas una huella de comportamiento por
  cuenta, solo con señales estructurales y de comportamiento: dirección, hora, contrapartes
  nuevas, dinero de paso, montos y ritmo. Nada de moneda ni formato.
- **Cobertura:** se entrena con las cuentas con 20 o más transferencias en 5 días. Son el 18 %
  de las cuentas activas, el 22 % de las ilícitas, y tocan el 53 % del lavado.
- **Como detector de rareza no aporta.** En HI encuentra 161 transferencias de lavado sin
  patrón que la forma no veía, pero a costa de más de 114 mil falsas alarmas: la calibración
  hecha en desarrollo no se trasladó a prueba. En LI no aporta nada.
- **La huella sí sabe algo:** con etiquetas (diagnóstico solo en desarrollo), los embeddings
  separan cuentas ilícitas con AUC 0,78 a 0,81, más que las variables por cuenta. Es la base
  para el hito 4, que sí usará etiquetas.
- **"No te pareces a ti mismo" no es viable con 10 días:** AUC de 0,55 a 0,58, casi azar.

![Top-100, hito 3](resultados/hito3/hito3_top100.png)

| Prueba, HI / LI | F1 tx | Top-100 | Top-1.000 |
|---|---|---|---|
| **Combinado estructural (hito 2)** | **0,118** / **0,028** | **0,48** / 0,04 | **0,18** / 0,06 |
| Combinado estructural + CoLES | 0,005 / 0,028 | 0,48 / 0,04 | 0,18 / 0,06 |
| CoLES, huella atípica | 0,003 / 0,002 | 0,10 / 0,07 | 0,03 / 0,02 |
| Regla simple | 0,003 / 0,003 | 0,01 / 0,02 | 0,02 / 0,02 |

## Archivos

[metricas.json](resultados/hito3/metricas.json) ·
[parametros.json (congelado)](resultados/hito3/parametros.json) ·
[desarrollo.json](resultados/hito3/desarrollo.json) ·
[sonda en desarrollo](resultados/hito3/sonda_desarrollo.json) ·
[deriva de la rareza](resultados/hito3/deriva_coles.json) ·
[top-100 interactivo](resultados/hito3/hito3_top100.html) ·
[F1 interactivo](resultados/hito3/hito3_f1.html)

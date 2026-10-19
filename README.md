# Detección de lavado en redes de transferencias

**¿Qué cuentas de una red de transferencias están lavando dinero?** Caso 2 de un portafolio
de ciencia de datos aplicada a banca. Sobre AMLworld (IBM, sintético), el proyecto busca el
lavado por la **forma** de la red y por el **comportamiento** de cada cuenta, y mide cuánto
aporta cada parte contra una regla simple. Todo corre local con DuckDB.

Página del proyecto: <https://stous1.github.io/aml-graph-detection/> · Detalle con todas
las cifras: [INFORME_TECNICO.md](INFORME_TECNICO.md)

## Hito 1: abanicos por forma (prueba: días 7 a 10, medida una vez)

| | Precisión top-100 | Precisión top-500 | F1 ilícita por tx |
|---|---|---|---|
| **HI**, abanicos por forma | **0,91** | **0,29** | **0,143** |
| HI, regla simple (contrapartes en 24 h) | 0,01 | 0,01 | 0,003 |
| **LI**, abanicos por forma | **0,19** | **0,05** | **0,025** |
| LI, regla simple | 0,02 | 0,02 | 0,003 |

- La forma que separa en AMLworld es **una transferencia por contraparte y mezcla de
  monedas**, no el tamaño. La regla que solo cuenta contrapartes se llena de comercios.
- Es un detector de **abanicos de salida**: recupera 7 de 8 FAN-OUT y 8 de 11 SCATTER-GATHER
  con 3 o más transferencias en HI, y ningún FAN-IN. Ciclos y concentración llegan en el hito 2.
- LI es mucho más difícil: el 71 % de su lavado no pertenece a ningún patrón documentado.

![Precisión en el top-k](docs/resultados/hito1/precision_k.png)

## Cómo se evalúa

- **Partición temporal:** día 1 solo historia (artefacto de arranque), desarrollo días 2–6,
  prueba días 7–10. La cola de los días 11–18 (60 % lavado) se excluye.
- Los intentos que cruzan desarrollo y prueba se ignoran en ambos.
- Todo se decide en desarrollo y se congela (tag `hito1-congelado`). Prueba se mide una vez.
- Métricas: precisión en el top-k, recall por tipo de patrón y F1 de la clase ilícita.
  Nunca exactitud. Siempre en HI y LI, y siempre contra la regla simple.

## Uso

```bash
uv sync
# Copiar los seis archivos Small de AMLworld a data/raw/ (no se versionan)
uv run python scripts/hito1.py preparar
uv run python scripts/hito1.py explorar
uv run python scripts/hito1.py desarrollar
uv run python scripts/hito1.py evaluar
uv run pytest            # pruebas sobre un mini-AMLworld sintético
```

Datos: [IBM Transactions for Anti Money Laundering (AMLworld)](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml).
Licencia del código: MIT.

# Detección de lavado en redes de transferencias

**¿Qué cuentas de una red de transferencias están lavando dinero?** Caso 2 de un portafolio
de ciencia de datos aplicada a banca. Sobre AMLworld (IBM, sintético), el proyecto busca el
lavado por la **forma** de la red y por el **comportamiento** de cada cuenta, y mide cuánto
aporta cada parte contra una regla simple. Todo corre local con DuckDB.

Página del proyecto: <https://stous1.github.io/aml-graph-detection/> · Detalle con todas
las cifras: [INFORME_TECNICO.md](INFORME_TECNICO.md)

## Cifra principal: combinado estructural

Período de prueba (días 7 a 10). Solo usa señales que existirían en cualquier banco
(**tiempo, montos y topología**), sin moneda ni formato de pago.

| | F1 ilícita por tx | Precisión top-100 | Top-1.000 |
|---|---|---|---|
| **HI, combinado estructural** | **0,118** | **0,48** | **0,18** |
| HI, regla simple (contrapartes en 24 h) | 0,003 | 0,01 | 0,02 |
| **LI, combinado estructural** | **0,028** | **0,04** | **0,06** |
| LI, regla simple | 0,003 | 0,02 | 0,02 |

Es el mismo período de prueba en todos los hitos: cada hito lo mide una vez, al final y con
parámetros congelados, pero ya no es una prueba virgen.

Detectores estructurales que lo componen (HI / LI, top-100): abanicos de salida por forma
(0,72 / 0,14), ciclos con monto conservado (0,39 / 0,18), dispersión-concentración (0,38 /
0,01), cadenas de paso (0,21 / 0,12), Isolation Forest sobre variables por cuenta (0,32 /
0,18), abanicos de entrada (0,00 / 0,00) y concentración-dispersión (0,09 / 0,01).

- La señal que más rinde es el **dinero de paso con monto conservado**: recibir X y reenviar
  ≈X poco después. Con ella, el detector de ciclos encuentra los 7 ciclos de HI que se cierran
  dentro de la ventana.
- La combinación amplía la cobertura (recall repartido en los 8 tipos de patrón), pero en el
  top-100 de HI rinde menos que el mejor abanico solo.
- **LI** cae porque el 82 % de su lavado son transferencias sueltas, sin patrón; no porque la
  configuración se haya elegido en HI.
- **Hito 3 (CoLES):** la huella de comportamiento aprendida sin etiquetas no mejora esta cifra,
  y "no te pareces a ti mismo" no es viable con 10 días. Los embeddings sí contienen
  información sobre el lavado (AUC 0,78 a 0,81 con etiquetas), lo que motiva el hito 4.

### Referencia: con señales de moneda y formato (huella del simulador)

| | F1 tx HI / LI | Top-100 HI / LI |
|---|---|---|
| Abanicos del hito 1 (mezcla de monedas, por canal) | 0,143 / 0,025 | 0,91 / 0,19 |
| … el mismo, sin mezcla de monedas | 0,005 / 0,004 | 0,01 / 0,02 |
| Combinado con moneda y formato | 0,151 / 0,049 | 0,47 / 0,23 |

En AMLworld, el centro de un abanico de lavado paga en varias monedas y casi todo el lavado va
por ACH. Son plantillas del generador, no leyes del lavado: sin la mezcla de monedas, el
detector del hito 1 cae a casi nada. Estas cifras no se trasladarían a un banco de una sola
moneda y por eso no son la cifra principal.

## Cómo se evalúa

- **Partición temporal:** día 1 solo historia (artefacto de arranque), desarrollo días 2–6,
  prueba días 7–10. La cola de los días 11–18 (60 % lavado) se excluye.
- Los intentos que cruzan desarrollo y prueba se ignoran en ambos.
- Todo se decide en desarrollo y se congela con un tag por hito. Prueba se mide una vez por
  hito.
- Métricas: precisión en el top-k, recall por tipo de patrón y F1 de la clase ilícita.
  Nunca exactitud. Siempre en HI y LI, y siempre contra la regla simple.

## Uso

```bash
uv sync
# Copiar los seis archivos Small de AMLworld a data/raw/ (no se versionan)
uv run python scripts/hito1.py preparar
uv run python scripts/hito1.py explorar
uv run python scripts/hito1.py desarrollar && uv run python scripts/hito1.py evaluar
uv run python scripts/hito2.py desarrollar && uv run python scripts/hito2.py evaluar
uv run python scripts/hito3.py desarrollar && uv run python scripts/hito3.py evaluar
uv run pytest            # pruebas sobre un mini-AMLworld sintético
```

Datos: [IBM Transactions for Anti Money Laundering (AMLworld)](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml).
Licencia del código: MIT.

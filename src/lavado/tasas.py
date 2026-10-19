"""Tasas implícitas de cambio a USD, estimadas desde las propias transacciones.

En una transferencia entre monedas distintas, ``monto_recibido * tasa(recibida)`` debe igualar
``monto_pagado * tasa(pagada)``. Con la mediana del cociente por par de monedas se arma un
sistema en logaritmos que se resuelve por mínimos cuadrados con el dólar fijo en 1.
"""

from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

MONEDA_BASE = "US Dollar"


def estimar_tasas(
    con: duckdb.DuckDBPyConnection, tabla: str, hasta: datetime | None = None
) -> pd.DataFrame:
    """Devuelve ``moneda, usd_por_unidad, n_observaciones`` a partir de ``tabla``.

    ``tabla`` debe tener ``ts, monto_pagado, moneda_pagada, monto_recibido, moneda_recibida``.
    Solo se usan transacciones anteriores a ``hasta`` (si se da), para no mirar el futuro.
    """
    filtro = f"AND ts < TIMESTAMP '{hasta:%Y-%m-%d %H:%M:%S}'" if hasta else ""
    pares = con.execute(
        f"""
        SELECT moneda_pagada, moneda_recibida,
               median(ln(monto_recibido / monto_pagado)) AS log_cociente,
               count(*) AS n
        FROM {tabla}
        WHERE moneda_pagada <> moneda_recibida AND monto_pagado > 0 AND monto_recibido > 0
              {filtro}
        GROUP BY ALL
        ORDER BY ALL
        """
    ).df()
    observadas = con.execute(
        f"SELECT moneda_pagada FROM {tabla} UNION SELECT moneda_recibida FROM {tabla}"
    ).fetchall()
    monedas = sorted({m for (m,) in observadas} | {MONEDA_BASE})
    indice = {m: i for i, m in enumerate(monedas)}
    n_obs = dict.fromkeys(monedas, 0)

    # log tasa(pagada) - log tasa(recibida) = log(recibido / pagado)
    filas, objetivo = [], []
    for par in pares.itertuples(index=False):
        fila = np.zeros(len(monedas))
        fila[indice[par.moneda_pagada]] += 1.0
        fila[indice[par.moneda_recibida]] -= 1.0
        filas.append(fila)
        objetivo.append(par.log_cociente)
        n_obs[par.moneda_pagada] += int(par.n)
        n_obs[par.moneda_recibida] += int(par.n)
    ancla = np.zeros(len(monedas))
    ancla[indice[MONEDA_BASE]] = 1.0
    filas.append(ancla)
    objetivo.append(0.0)
    solucion, *_ = np.linalg.lstsq(np.vstack(filas), np.array(objetivo), rcond=None)

    conectadas = _conectadas(monedas, pares)
    return pd.DataFrame(
        {
            "moneda": monedas,
            "usd_por_unidad": [
                float(np.exp(solucion[indice[m]])) if m in conectadas else np.nan for m in monedas
            ],
            "n_observaciones": [n_obs[m] for m in monedas],
        }
    )


def _conectadas(monedas: list[str], pares: pd.DataFrame) -> set[str]:
    """Monedas unidas al dólar por alguna cadena de pares observados."""
    vecinos: dict[str, set[str]] = {m: set() for m in monedas}
    for a, b in zip(pares.moneda_pagada, pares.moneda_recibida, strict=True):
        vecinos[a].add(b)
        vecinos[b].add(a)
    vistas, pendientes = {MONEDA_BASE}, [MONEDA_BASE]
    while pendientes:
        for v in vecinos[pendientes.pop()] - vistas:
            vistas.add(v)
            pendientes.append(v)
    return vistas

"""Isolation Forest sobre las variables por cuenta.

El bosque se ajusta **sin etiquetas** con las cuentas activas en desarrollo y puntúa las
cuentas de cada período con las variables de ese período. El puntaje de una cuenta es
``-score_samples`` (mayor = más rara). El de una transferencia combina el de sus dos cuentas
(mínimo: las dos deben ser raras; máximo: basta una).
"""

from dataclasses import asdict, dataclass

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from lavado import particion, variables_cuenta
from lavado.detectores import comun

SEMILLA = 20220902


@dataclass(frozen=True)
class ConfigAislamiento:
    sospechosas: bool = False  # agrega monedas y formatos de pago
    agregacion: str = "min"  # "min" o "max" de las dos cuentas de la transferencia
    n_arboles: int = 200

    def variables(self) -> list[str]:
        base = list(variables_cuenta.ESTRUCTURALES)
        return base + list(variables_cuenta.SOSPECHOSAS) if self.sospechosas else base

    def como_dict(self) -> dict:
        return asdict(self)


def ajustar(variables: pd.DataFrame, config: ConfigAislamiento) -> IsolationForest:
    """Ajusta el bosque (determinista: semilla fija y un solo hilo)."""
    modelo = IsolationForest(n_estimators=config.n_arboles, random_state=SEMILLA, n_jobs=1)
    modelo.fit(variables[config.variables()].to_numpy(dtype=float))
    return modelo


def puntuar(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    periodo: str,
    config: ConfigAislamiento,
    cache: dict | None = None,
) -> comun.Puntajes:
    """Ajusta en desarrollo y puntúa ``periodo``. ``cache`` evita recalcular variables."""
    cache = cache if cache is not None else {}

    def variables_de(p: str) -> pd.DataFrame:
        clave = (esquema, p)
        if clave not in cache:
            cache[clave] = variables_cuenta.calcular(
                con, esquema, particion.DESDE[p], particion.HASTA[p]
            )
        return cache[clave]

    modelo = ajustar(variables_de("desarrollo"), config)
    vp = variables_de(periodo)
    total = comun.n_cuentas(con, esquema)
    cuenta = np.zeros(total)
    cuenta[vp.cuenta_id.to_numpy()] = -modelo.score_samples(
        vp[config.variables()].to_numpy(dtype=float)
    )
    tx = comun.transacciones_periodo(con, esquema, periodo)
    po, pd_ = cuenta[tx.origen.to_numpy()], cuenta[tx.destino.to_numpy()]
    if config.agregacion == "min":
        p_tx = np.minimum(po, pd_)
    elif config.agregacion == "max":
        p_tx = np.maximum(po, pd_)
    else:
        raise ValueError(f"agregacion inválida: {config.agregacion}")
    return comun.Puntajes(tx, p_tx, cuenta)

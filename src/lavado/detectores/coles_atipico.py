"""Cuentas atípicas según su huella de comportamiento (embeddings de CoLES).

Cada cuenta con suficiente historia en la ventana de puntaje (5 días que terminan donde
termina el período) se representa con su embedding de CoLES. Una cuenta es más sospechosa
cuanto más rara es su huella respecto de las cuentas de desarrollo:

- ``iforest``: Isolation Forest ajustado con los embeddings de desarrollo.
- ``knn``: distancia media a sus ``k`` vecinos más cercanos entre los embeddings de desarrollo
  (sin contarse a sí misma).

Las cuentas sin historia suficiente quedan en 0 (el detector no las ve). El puntaje de una
transferencia combina el de sus dos cuentas (mínimo o máximo). No usa etiquetas, ni moneda ni
formato de pago.
"""

from dataclasses import asdict, dataclass
from datetime import timedelta

import duckdb
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors

from lavado import coles, particion, secuencias
from lavado.detectores import comun

DIAS_VENTANA = 5
SEMILLA = 20220902


@dataclass(frozen=True)
class ConfigColesAtipico:
    metodo: str = "iforest"  # "iforest" o "knn"
    agregacion: str = "max"  # "min" o "max" de las dos cuentas de la transferencia
    min_eventos: int = 20  # historia mínima para puntuar una cuenta
    k: int = 10

    def como_dict(self) -> dict:
        return asdict(self)


def ventana(periodo: str) -> tuple:
    """Ventana de puntaje: 5 días que terminan donde termina el período."""
    hasta = particion.HASTA[periodo]
    return hasta - timedelta(days=DIAS_VENTANA), hasta


def embeddings(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    periodo: str,
    min_eventos: int,
    codificador,
    cache: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """``(cuentas, embeddings)`` de la ventana de puntaje del período."""
    clave = ("coles_emb", esquema, periodo, min_eventos)
    if clave not in cache:
        desde, hasta = ventana(periodo)
        datos = secuencias.construir(con, esquema, desde, hasta, min_eventos)
        cache[clave] = (datos.cuentas, coles.incrustar(codificador, datos))
    return cache[clave]


def rareza(
    referencia: np.ndarray, consulta: np.ndarray, config: ConfigColesAtipico, misma: bool
) -> np.ndarray:
    """Puntaje de rareza (mayor = más rara) de ``consulta`` respecto de ``referencia``."""
    if len(consulta) == 0:
        return np.zeros(0)
    if config.metodo == "iforest":
        modelo = IsolationForest(n_estimators=200, random_state=SEMILLA, n_jobs=1)
        modelo.fit(referencia)
        return -modelo.score_samples(consulta)
    if config.metodo == "knn":
        k = config.k + (1 if misma else 0)
        vecinos = NearestNeighbors(n_neighbors=k).fit(referencia)
        distancias, _ = vecinos.kneighbors(consulta)
        return distancias[:, 1:].mean(axis=1) if misma else distancias.mean(axis=1)
    raise ValueError(f"metodo inválido: {config.metodo}")


def puntuar(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    periodo: str,
    config: ConfigColesAtipico,
    cache: dict,
) -> comun.Puntajes:
    """Requiere el codificador de la variante en ``cache[("coles_modelo", esquema)]``."""
    codificador = cache[("coles_modelo", esquema)]
    _, ref = embeddings(con, esquema, "desarrollo", config.min_eventos, codificador, cache)
    cuentas, emb = embeddings(con, esquema, periodo, config.min_eventos, codificador, cache)
    clave = ("coles_rareza", esquema, periodo, config.metodo, config.min_eventos, config.k)
    if clave not in cache:
        cache[clave] = rareza(ref, emb, config, misma=periodo == "desarrollo")
    total = comun.n_cuentas(con, esquema)
    cuenta = np.zeros(total)
    cuenta[cuentas] = cache[clave]
    tx = comun.transacciones_periodo(con, esquema, periodo)
    po, pd_ = cuenta[tx.origen.to_numpy()], cuenta[tx.destino.to_numpy()]
    if config.agregacion == "min":
        p_tx = np.minimum(po, pd_)
    elif config.agregacion == "max":
        p_tx = np.maximum(po, pd_)
    else:
        raise ValueError(f"agregacion inválida: {config.agregacion}")
    return comun.Puntajes(tx, p_tx, cuenta)

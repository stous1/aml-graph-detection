"""Piezas comunes a los detectores: puntajes alineados con las transferencias de un período."""

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd


@dataclass
class Puntajes:
    """Puntaje por transferencia (alineado con ``transacciones``) y por cuenta (por id).

    ``transacciones`` trae ``tx_id, origen, destino`` del período, ordenadas por ``tx_id``.
    """

    transacciones: pd.DataFrame
    tx: np.ndarray
    cuenta: np.ndarray
    direccion: np.ndarray | None = None  # abanicos: "salida" o "entrada" por transferencia


def transacciones_periodo(
    con: duckdb.DuckDBPyConnection, esquema: str, periodo: str
) -> pd.DataFrame:
    """Aristas del período (``tx_id, origen, destino``), en el orden del universo."""
    return con.execute(
        f"SELECT tx_id, origen, destino FROM {esquema}.aristas WHERE periodo = ? ORDER BY tx_id",
        [periodo],
    ).df()


def n_cuentas(con: duckdb.DuckDBPyConnection, esquema: str) -> int:
    return int(con.execute(f"SELECT count(*) FROM {esquema}.cuentas").fetchone()[0])


def cuentas_por_maximo(
    origen: np.ndarray, destino: np.ndarray, puntaje_tx: np.ndarray, total_cuentas: int
) -> np.ndarray:
    """Puntaje de cada cuenta: el máximo de las transferencias en que participa."""
    puntaje = np.zeros(total_cuentas)
    np.maximum.at(puntaje, origen, puntaje_tx)
    np.maximum.at(puntaje, destino, puntaje_tx)
    return puntaje


def desde_tabla(transacciones: pd.DataFrame, por_tx: pd.DataFrame, total_cuentas: int) -> Puntajes:
    """Arma ``Puntajes`` desde ``por_tx`` (``tx_id, puntaje``; el máximo si hay repetidos).

    Las transferencias sin fila quedan en 0; las de ``por_tx`` fuera del período se descartan.
    """
    if por_tx.empty:
        tx = np.zeros(len(transacciones))
    else:
        maximo = por_tx.groupby("tx_id").puntaje.max()
        tx = transacciones.tx_id.map(maximo).fillna(0.0).to_numpy(dtype=float)
    cuenta = cuentas_por_maximo(
        transacciones.origen.to_numpy(), transacciones.destino.to_numpy(), tx, total_cuentas
    )
    return Puntajes(transacciones, tx, cuenta)

"""Ciclos temporales de longitud acotada con monto conservado.

Un ciclo es una secuencia de transferencias ``a → m1 → … → a`` en la que cada salto sale de
donde llegó el anterior, más tarde, con un monto parecido (cada par consecutivo es un par de
paso, ver ``lavado.paso``), sin repetir cuentas, con entre 2 y ``max_saltos`` saltos y una
duración total de a lo sumo ``duracion_horas``. Como los tiempos crecen a lo largo del ciclo,
cada ciclo se encuentra una sola vez, desde su transferencia más temprana.

Solo usa tiempo, montos y topología: ninguna señal sospechosa de ser artefacto (moneda o
formato de pago).
"""

from dataclasses import asdict, dataclass
from datetime import datetime

import duckdb
import pandas as pd

from lavado import particion, paso
from lavado.detectores import comun


@dataclass(frozen=True)
class ConfigCiclos:
    delta_horas: int = 96  # tiempo máximo entre llegar y reenviar, en cada cuenta
    tolerancia: float = 0.2  # diferencia relativa de monto permitida en cada salto
    duracion_horas: int = 144  # duración máxima del ciclo completo
    max_saltos: int = 10
    min_saltos: int = 2
    puntaje: str = "longitud"  # "longitud" o "longitud_consistencia"

    def como_dict(self) -> dict:
        return asdict(self)


def encontrar_ciclos(
    con: duckdb.DuckDBPyConnection, esquema: str, hasta: datetime, config: ConfigCiclos
) -> pd.DataFrame:
    """Ciclos anteriores a ``hasta``: ``ciclo_id, saltos, duracion_horas, consistencia, txs``.

    ``consistencia`` = monto mínimo / monto máximo a lo largo del ciclo.
    """
    paso.crear_pares_paso(con, esquema, hasta, config.delta_horas, config.tolerancia, "ci_pares")
    dur = int(config.duracion_horas)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE ci_abiertas AS
        SELECT origen AS inicio, ts_in AS ts_ini, tx_out AS tx_ult, destino AS ultima,
               2 AS saltos, [origen, cuenta, destino] AS nodos, [tx_in, tx_out] AS txs,
               least(usd_in, usd_out) AS usd_min, greatest(usd_in, usd_out) AS usd_max,
               ts_out AS ts_ult
        FROM ci_pares
        WHERE ts_out <= ts_in + INTERVAL {dur} HOUR
        """
    )
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE ci_cerradas AS
        SELECT saltos, txs, ts_ini, ts_ult, usd_min, usd_max
        FROM ci_abiertas WHERE ultima = inicio
        """
    )
    con.execute("DELETE FROM ci_abiertas WHERE ultima = inicio")
    for _ in range(3, int(config.max_saltos) + 1):
        if not con.execute("SELECT count(*) FROM ci_abiertas").fetchone()[0]:
            break
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE ci_nuevas AS
            SELECT c.inicio, c.ts_ini, p.tx_out AS tx_ult, p.destino AS ultima,
                   c.saltos + 1 AS saltos, list_append(c.nodos, p.destino) AS nodos,
                   list_append(c.txs, p.tx_out) AS txs,
                   least(c.usd_min, p.usd_out) AS usd_min,
                   greatest(c.usd_max, p.usd_out) AS usd_max, p.ts_out AS ts_ult
            FROM ci_abiertas c JOIN ci_pares p ON p.tx_in = c.tx_ult
            WHERE p.ts_out <= c.ts_ini + INTERVAL {dur} HOUR
              AND (p.destino = c.inicio OR NOT list_contains(c.nodos, p.destino))
            """
        )
        con.execute(
            """
            INSERT INTO ci_cerradas
            SELECT saltos, txs, ts_ini, ts_ult, usd_min, usd_max
            FROM ci_nuevas WHERE ultima = inicio
            """
        )
        con.execute(
            "CREATE OR REPLACE TEMP TABLE ci_abiertas AS "
            "SELECT * FROM ci_nuevas WHERE ultima <> inicio"
        )
    ciclos = con.execute(
        f"""
        SELECT row_number() OVER (ORDER BY ts_ini, txs) - 1 AS ciclo_id, saltos,
               epoch(ts_ult - ts_ini) / 3600 AS duracion_horas,
               usd_min / usd_max AS consistencia, txs
        FROM ci_cerradas WHERE saltos >= {int(config.min_saltos)}
        ORDER BY ciclo_id
        """
    ).df()
    for tabla in ("ci_pares", "ci_abiertas", "ci_cerradas", "ci_nuevas"):
        con.execute(f"DROP TABLE IF EXISTS {tabla}")
    return ciclos


def puntuar_ciclos(ciclos: pd.DataFrame, config: ConfigCiclos) -> pd.Series:
    if config.puntaje == "longitud":
        return ciclos.saltos.astype(float)
    if config.puntaje == "longitud_consistencia":
        return ciclos.saltos * ciclos.consistencia
    raise ValueError(f"puntaje inválido: {config.puntaje}")


def por_transaccion(ciclos: pd.DataFrame, config: ConfigCiclos) -> pd.DataFrame:
    """``tx_id, puntaje``: cada transferencia de un ciclo con el puntaje del ciclo."""
    if ciclos.empty:
        return pd.DataFrame({"tx_id": pd.Series(dtype="int64"), "puntaje": pd.Series(dtype=float)})
    return (
        ciclos.assign(puntaje=puntuar_ciclos(ciclos, config))[["txs", "puntaje"]]
        .explode("txs")
        .rename(columns={"txs": "tx_id"})
        .astype({"tx_id": "int64"})
    )


def puntuar(
    con: duckdb.DuckDBPyConnection, esquema: str, periodo: str, config: ConfigCiclos
) -> comun.Puntajes:
    """Puntajes de los ciclos para las transferencias de ``periodo``."""
    ciclos = encontrar_ciclos(con, esquema, particion.HASTA[periodo], config)
    return comun.desde_tabla(
        comun.transacciones_periodo(con, esquema, periodo),
        por_transaccion(ciclos, config),
        comun.n_cuentas(con, esquema),
    )

"""Dispersión-concentración y concentración-dispersión.

- **Dispersión-concentración** (scatter-gather): una cuenta ``S`` reparte entre varias
  intermediarias y cada una reenvía un monto parecido a la misma cuenta ``T``. Se cuentan las
  intermediarias distintas ``m`` con un par de paso ``S → m → T`` (``S ≠ T``).
- **Concentración-dispersión** (gather-scatter): una cuenta junta de varias y reparte a
  varias en la misma ventana, y lo que sale se parece a lo que entró (dinero de paso).

Solo usan tiempo, montos y topología.
"""

from dataclasses import asdict, dataclass

import duckdb
import numpy as np
import pandas as pd

from lavado import particion, paso
from lavado.detectores import comun


@dataclass(frozen=True)
class ConfigDispersion:
    delta_horas: int = 96
    tolerancia: float = 0.2
    min_intermediarias: int = 2

    def como_dict(self) -> dict:
        return asdict(self)


def dispersion_concentracion(
    con: duckdb.DuckDBPyConnection, esquema: str, hasta, config: ConfigDispersion
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estructuras ``(S, T)`` y sus transferencias.

    Devuelve ``estructuras`` (``origen, destino, intermediarias, consistencia``) y ``por_tx``
    (``tx_id, puntaje``, con puntaje = número de intermediarias).
    """
    paso.crear_pares_paso(con, esquema, hasta, config.delta_horas, config.tolerancia, "dc_pares")
    estructuras = con.execute(
        f"""
        SELECT origen, destino, count(DISTINCT cuenta) AS intermediarias,
               min(least(usd_in, usd_out)) / max(greatest(usd_in, usd_out)) AS consistencia
        FROM dc_pares WHERE origen <> destino
        GROUP BY origen, destino
        HAVING count(DISTINCT cuenta) >= {int(config.min_intermediarias)}
        ORDER BY origen, destino
        """
    ).df()
    con.register("dc_estr", estructuras)
    por_tx = con.execute(
        """
        WITH p AS (
            SELECT p.tx_in, p.tx_out, e.intermediarias
            FROM dc_pares p JOIN dc_estr e USING (origen, destino)
        )
        SELECT tx_id, max(intermediarias)::DOUBLE AS puntaje FROM (
            SELECT tx_in AS tx_id, intermediarias FROM p
            UNION ALL SELECT tx_out, intermediarias FROM p
        ) GROUP BY tx_id ORDER BY tx_id
        """
    ).df()
    con.unregister("dc_estr")
    con.execute("DROP TABLE dc_pares")
    return estructuras, por_tx


def puntuar_dispersion(
    con: duckdb.DuckDBPyConnection, esquema: str, periodo: str, config: ConfigDispersion
) -> comun.Puntajes:
    _, por_tx = dispersion_concentracion(con, esquema, particion.HASTA[periodo], config)
    return comun.desde_tabla(
        comun.transacciones_periodo(con, esquema, periodo), por_tx, comun.n_cuentas(con, esquema)
    )


@dataclass(frozen=True)
class ConfigConcentracion:
    ventana_horas: int = 96
    min_lado: int = 2  # contrapartes mínimas de entrada y de salida
    puntaje: str = "tamano_balance"  # "tamano", "tamano_balance" o "tamano_balance_unicidad"

    def como_dict(self) -> dict:
        return asdict(self)


def concentracion_dispersion(
    con: duckdb.DuckDBPyConnection, esquema: str, hasta, config: ConfigConcentracion
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estructuras ``(centro, ventana)`` con entradas y salidas, y sus transferencias.

    Variables: ``n_in, n_out`` (contrapartes distintas), ``balance`` = min(USD entrada, USD
    salida) / max, ``unicidad`` = contrapartes / transferencias. Se exige que alguna salida
    sea posterior a la primera entrada. Ventanas fijas con dos desfases, como los abanicos.
    """
    seg = int(config.ventana_horas) * 3600
    t0 = f"TIMESTAMP '{particion.INICIO:%Y-%m-%d %H:%M:%S}'"
    estructuras = con.execute(
        f"""
        WITH tx AS (
            SELECT tx_id, ts, origen, destino, monto_usd FROM {esquema}.aristas
            WHERE ts < TIMESTAMP '{hasta:%Y-%m-%d %H:%M:%S}'
        ),
        lados AS (
            SELECT tx_id, ts, destino AS centro, origen AS contraparte, 'entrada' AS dir,
                   monto_usd FROM tx
            UNION ALL
            SELECT tx_id, ts, origen, destino, 'salida', monto_usd FROM tx
        ),
        b AS (
            SELECT l.*, d.desfase,
                   floor((epoch(l.ts) - epoch({t0}) - d.desfase) / {seg})::INTEGER AS b
            FROM lados l CROSS JOIN (VALUES (0), ({seg // 2})) d(desfase)
        )
        SELECT centro, desfase, b,
               count(DISTINCT contraparte) FILTER (WHERE dir = 'entrada') AS n_in,
               count(DISTINCT contraparte) FILTER (WHERE dir = 'salida') AS n_out,
               count(*) AS n_tx,
               coalesce(sum(monto_usd) FILTER (WHERE dir = 'entrada'), 0) AS usd_in,
               coalesce(sum(monto_usd) FILTER (WHERE dir = 'salida'), 0) AS usd_out,
               min(ts) FILTER (WHERE dir = 'entrada') AS primera_in,
               max(ts) FILTER (WHERE dir = 'salida') AS ultima_out
        FROM b GROUP BY centro, desfase, b
        HAVING n_in >= {int(config.min_lado)} AND n_out >= {int(config.min_lado)}
           AND ultima_out > primera_in
        ORDER BY centro, desfase, b
        """
    ).df()
    estructuras["balance"] = np.minimum(estructuras.usd_in, estructuras.usd_out) / np.maximum(
        estructuras.usd_in, estructuras.usd_out
    )
    estructuras["unicidad"] = (estructuras.n_in + estructuras.n_out) / estructuras.n_tx
    tamano = np.log2(np.minimum(estructuras.n_in, estructuras.n_out))
    if config.puntaje == "tamano":
        estructuras["puntaje"] = tamano
    elif config.puntaje == "tamano_balance":
        estructuras["puntaje"] = tamano * estructuras.balance
    elif config.puntaje == "tamano_balance_unicidad":
        estructuras["puntaje"] = tamano * estructuras.balance * estructuras.unicidad
    else:
        raise ValueError(f"puntaje inválido: {config.puntaje}")
    con.register("cd_estr", estructuras[["centro", "desfase", "b", "puntaje"]])
    por_tx = con.execute(
        f"""
        WITH tx AS (
            SELECT tx_id, ts, origen, destino FROM {esquema}.aristas
            WHERE ts < TIMESTAMP '{hasta:%Y-%m-%d %H:%M:%S}'
        ),
        lados AS (
            SELECT tx_id, ts, destino AS centro FROM tx
            UNION ALL SELECT tx_id, ts, origen FROM tx
        ),
        b AS (
            SELECT l.tx_id, l.centro, d.desfase,
                   floor((epoch(l.ts) - epoch({t0}) - d.desfase) / {seg})::INTEGER AS b
            FROM lados l CROSS JOIN (VALUES (0), ({seg // 2})) d(desfase)
        )
        SELECT b.tx_id, max(e.puntaje) AS puntaje
        FROM b JOIN cd_estr e USING (centro, desfase, b)
        GROUP BY b.tx_id ORDER BY b.tx_id
        """
    ).df()
    con.unregister("cd_estr")
    return estructuras, por_tx


def puntuar_concentracion(
    con: duckdb.DuckDBPyConnection, esquema: str, periodo: str, config: ConfigConcentracion
) -> comun.Puntajes:
    _, por_tx = concentracion_dispersion(con, esquema, particion.HASTA[periodo], config)
    return comun.desde_tabla(
        comun.transacciones_periodo(con, esquema, periodo), por_tx, comun.n_cuentas(con, esquema)
    )

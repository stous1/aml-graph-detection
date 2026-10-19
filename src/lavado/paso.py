"""Pares de paso: una cuenta recibe un monto y reenvía uno parecido poco después.

Un **par de paso** es ``(e, s)``: la transferencia ``e`` llega a la cuenta ``m`` en ``t1`` y la
transferencia ``s`` sale de ``m`` en ``t2``, con ``t1 < t2 <= t1 + Δ`` y montos en USD
parecidos (``|ln(s / e)| <= ln(1 + tolerancia)``). Es la pieza común de ciclos, cadenas,
dispersión-concentración y de la velocidad por cuenta, y solo usa **tiempo, montos y
topología**: señales que existen en cualquier banco, con una o con muchas monedas.

Para no comparar todas las entradas con todas las salidas de una cuenta grande, el cruce se
hace por cubetas de log-monto de ancho ``ln(1 + tolerancia)`` (la cubeta propia y las dos
vecinas) y después se filtra exacto.
"""

import math
from datetime import datetime

import duckdb


def _ts(fecha: datetime) -> str:
    return f"TIMESTAMP '{fecha:%Y-%m-%d %H:%M:%S}'"


def crear_pares_paso(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    hasta: datetime,
    delta_horas: int,
    tolerancia: float,
    nombre: str = "pares_paso",
) -> int:
    """Crea la tabla temporal ``nombre`` con los pares de paso anteriores a ``hasta``.

    Columnas: ``tx_in, tx_out, cuenta`` (la que recibe y reenvía), ``origen`` (de dónde llega),
    ``destino`` (a dónde sale), ``ts_in, ts_out, usd_in, usd_out``. ``origen = destino`` es un
    ida y vuelta. No lee etiquetas.
    """
    ancho = math.log(1 + tolerancia)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {nombre} AS
        WITH a AS (
            SELECT tx_id, ts, origen, destino, monto_usd,
                   floor(ln(monto_usd) / {ancho})::BIGINT AS k
            FROM {esquema}.aristas WHERE ts < {_ts(hasta)} AND monto_usd > 0
        ),
        salidas AS (
            SELECT a.*, a.k + v.dk AS kk FROM a, (VALUES (-1), (0), (1)) v(dk)
        )
        SELECT e.tx_id AS tx_in, s.tx_id AS tx_out, e.destino AS cuenta,
               e.origen AS origen, s.destino AS destino,
               e.ts AS ts_in, s.ts AS ts_out, e.monto_usd AS usd_in, s.monto_usd AS usd_out
        FROM a e JOIN salidas s ON s.origen = e.destino AND s.kk = e.k
        WHERE s.ts > e.ts AND s.ts <= e.ts + INTERVAL {int(delta_horas)} HOUR
          AND abs(ln(s.monto_usd / e.monto_usd)) <= {ancho}
        ORDER BY tx_in, tx_out
        """
    )
    return int(con.execute(f"SELECT count(*) FROM {nombre}").fetchone()[0])

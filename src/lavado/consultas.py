"""Consultas sobre la red, pensadas para exponerse más adelante como herramientas de un agente.

Reglas que cumplen todas las funciones:

- Son puras: reciben la conexión y parámetros y devuelven un ``DataFrame``; no escriben nada.
- Nunca leen etiquetas (``es_lavado``, ``patrones``, ``intentos``, ``etiquetas``). Un agente que
  las use no puede ver la respuesta.
- Están acotadas por ``hasta`` (exclusivo), para no mirar el futuro del momento de la alerta.
"""

from datetime import datetime

import duckdb
import pandas as pd

from lavado import particion

_COLUMNAS_TX = "tx_id, ts, origen, destino, monto_usd, moneda, formato"


def _ts(fecha: datetime) -> str:
    return f"TIMESTAMP '{fecha:%Y-%m-%d %H:%M:%S}'"


def transacciones_cuenta(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    cuenta: int,
    desde: datetime = particion.INICIO,
    hasta: datetime = particion.FIN_VENTANA,
    limite: int | None = None,
) -> pd.DataFrame:
    """Transferencias que envía o recibe ``cuenta`` en ``[desde, hasta)``, en orden temporal.

    Agrega ``direccion`` (``salida`` o ``entrada``) y ``contraparte``.
    """
    lim = f"LIMIT {int(limite)}" if limite else ""
    return con.execute(
        f"""
        SELECT {_COLUMNAS_TX},
               CASE WHEN origen = ? THEN 'salida' ELSE 'entrada' END AS direccion,
               CASE WHEN origen = ? THEN destino ELSE origen END AS contraparte
        FROM {esquema}.aristas
        WHERE (origen = ? OR destino = ?) AND ts >= {_ts(desde)} AND ts < {_ts(hasta)}
        ORDER BY ts, tx_id {lim}
        """,
        [cuenta, cuenta, cuenta, cuenta],
    ).df()


def vecinos(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    cuenta: int,
    direccion: str = "ambas",
    desde: datetime = particion.INICIO,
    hasta: datetime = particion.FIN_VENTANA,
    saltos: int = 1,
) -> pd.DataFrame:
    """Cuentas a ``saltos`` pasos de ``cuenta`` siguiendo ``direccion``.

    ``direccion``: ``salida`` (a quién le manda), ``entrada`` (de quién recibe) o ``ambas``.
    Devuelve ``cuenta_id, salto, n_tx, monto_usd, primera, ultima`` del primer salto en que
    aparece cada cuenta. Los saltos no exigen orden temporal entre aristas; para eso está
    :func:`flujo_temporal`.
    """
    if direccion not in ("salida", "entrada", "ambas"):
        raise ValueError(f"direccion inválida: {direccion}")
    ventana = f"ts >= {_ts(desde)} AND ts < {_ts(hasta)}"
    partes = []
    if direccion in ("salida", "ambas"):
        partes.append(
            f"SELECT origen AS de, destino AS a, * FROM {esquema}.aristas WHERE {ventana}"
        )
    if direccion in ("entrada", "ambas"):
        partes.append(
            f"SELECT destino AS de, origen AS a, * FROM {esquema}.aristas WHERE {ventana}"
        )
    pasos = " UNION ALL ".join(partes)

    vistos = {cuenta}
    frontera = [cuenta]
    resultados: list[pd.DataFrame] = []
    for salto in range(1, saltos + 1):
        if not frontera:
            break
        con.register("frontera", pd.DataFrame({"cuenta_id": frontera}, dtype="int64"))
        df = con.execute(
            f"""
            SELECT a AS cuenta_id, {salto} AS salto, count(*) AS n_tx,
                   sum(monto_usd) AS monto_usd, min(ts) AS primera, max(ts) AS ultima
            FROM ({pasos}) p
            WHERE de IN (SELECT cuenta_id FROM frontera)
            GROUP BY a ORDER BY a
            """
        ).df()
        con.unregister("frontera")
        df = df[~df.cuenta_id.isin(vistos)]
        vistos.update(df.cuenta_id.tolist())
        frontera = df.cuenta_id.tolist()
        resultados.append(df)
    if not resultados:
        return pd.DataFrame(
            columns=["cuenta_id", "salto", "n_tx", "monto_usd", "primera", "ultima"]
        )
    return pd.concat(resultados, ignore_index=True)


def flujo_temporal(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    cuenta: int,
    desde: datetime = particion.INICIO,
    hasta: datetime = particion.FIN_VENTANA,
    paso_horas: int = 24,
) -> pd.DataFrame:
    """Dinero que entra y sale de ``cuenta`` por intervalos de ``paso_horas``.

    Columnas: ``inicio, n_entrada, usd_entrada, n_salida, usd_salida, contrapartes_entrada,
    contrapartes_salida, saldo_paso`` (entrada menos salida en el intervalo).
    """
    segundos = int(paso_horas) * 3600
    return con.execute(
        f"""
        WITH tx AS (
            SELECT *, {_ts(desde)} + to_seconds(
                       floor((epoch(ts) - epoch({_ts(desde)})) / {segundos})::BIGINT
                       * {segundos}) AS inicio
            FROM {esquema}.aristas
            WHERE (origen = $c OR destino = $c) AND ts >= {_ts(desde)} AND ts < {_ts(hasta)}
        )
        SELECT inicio,
               count(*) FILTER (WHERE destino = $c) AS n_entrada,
               coalesce(sum(monto_usd) FILTER (WHERE destino = $c), 0) AS usd_entrada,
               count(*) FILTER (WHERE origen = $c) AS n_salida,
               coalesce(sum(monto_usd) FILTER (WHERE origen = $c), 0) AS usd_salida,
               count(DISTINCT origen) FILTER (WHERE destino = $c) AS contrapartes_entrada,
               count(DISTINCT destino) FILTER (WHERE origen = $c) AS contrapartes_salida,
               usd_entrada - usd_salida AS saldo_paso
        FROM tx GROUP BY inicio ORDER BY inicio
        """,
        {"c": cuenta},
    ).df()


def patrones_detectados(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    cuenta: int,
    detector: str | None = None,
    hasta: datetime = particion.FIN_VENTANA,
) -> pd.DataFrame:
    """Estructuras que los detectores encontraron alrededor de ``cuenta`` (no la verdad).

    Lee ``esquema.estructuras`` (la escriben los detectores). Devuelve las estructuras en las
    que la cuenta es centro, cerradas antes de ``hasta``, de mayor a menor puntaje.
    """
    existe = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = ? AND table_name = 'estructuras'",
        [esquema],
    ).fetchone()[0]
    if not existe:
        return pd.DataFrame()
    filtro = "AND detector = ?" if detector else ""
    params = [cuenta, *([detector] if detector else [])]
    return con.execute(
        f"""
        SELECT * FROM {esquema}.estructuras
        WHERE centro = ? AND fin_ventana <= {_ts(hasta)} {filtro}
        ORDER BY puntaje DESC, detector, inicio_ventana
        """,
        params,
    ).df()

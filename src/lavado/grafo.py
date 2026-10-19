"""Grafo temporal dirigido (multigrafo) de transferencias.

El grafo completo vive como tabla de aristas en DuckDB (``esquema.aristas``): una arista por
transferencia entre cuentas distintas y dentro de la ventana observable (sin la cola). Las
autotransferencias se conservan en ``transacciones`` pero no son aristas. Para mirar una
parte del grafo se arma un subgrafo de igraph bajo demanda; nunca se carga entero en Python.
"""

from datetime import datetime

import duckdb
import igraph as ig
import pandas as pd

from lavado import particion


def crear_aristas(con: duckdb.DuckDBPyConnection, esquema: str) -> int:
    """Crea ``esquema.aristas`` y devuelve su número de filas. No incluye etiquetas."""
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {esquema}.aristas AS
        SELECT tx_id, ts, origen, destino, monto_usd, moneda_pagada AS moneda, formato,
               periodo
        FROM {esquema}.transacciones
        WHERE NOT es_autotransferencia AND periodo <> 'cola'
        ORDER BY tx_id
        """
    )
    return int(con.execute(f"SELECT count(*) FROM {esquema}.aristas").fetchone()[0])


def _ts(fecha: datetime) -> str:
    return f"TIMESTAMP '{fecha:%Y-%m-%d %H:%M:%S}'"


def aristas_entre(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    cuentas: list[int],
    desde: datetime = particion.INICIO,
    hasta: datetime = particion.FIN_VENTANA,
    solo_internas: bool = True,
) -> "ig.Graph":
    """Subgrafo dirigido con las transferencias de ``cuentas`` en ``[desde, hasta)``.

    Con ``solo_internas`` quedan solo las aristas entre cuentas de la lista; si no, también
    las que salen o llegan a cualquier otra cuenta. Cada arista lleva ``tx_id``, ``ts``,
    ``monto_usd``, ``moneda`` y ``formato``; cada vértice, su ``cuenta_id`` en ``name``.
    """
    con.register("cuentas_sub", pd.DataFrame({"cuenta_id": list(cuentas)}, dtype="int64"))
    union = "AND" if solo_internas else "OR"
    df = con.execute(
        f"""
        SELECT tx_id, ts, origen, destino, monto_usd, moneda, formato
        FROM {esquema}.aristas
        WHERE ts >= {_ts(desde)} AND ts < {_ts(hasta)}
          AND (origen IN (SELECT cuenta_id FROM cuentas_sub)
               {union} destino IN (SELECT cuenta_id FROM cuentas_sub))
        ORDER BY ts, tx_id
        """
    ).df()
    con.unregister("cuentas_sub")
    vertices = sorted(set(cuentas) | set(df.origen) | set(df.destino))
    g = ig.Graph(directed=True)
    g.add_vertices([str(v) for v in vertices])
    g.vs["cuenta_id"] = vertices
    indice = {v: i for i, v in enumerate(vertices)}
    g.add_edges([(indice[o], indice[d]) for o, d in zip(df.origen, df.destino, strict=True)])
    for col in ("tx_id", "ts", "monto_usd", "moneda", "formato"):
        g.es[col] = df[col].tolist()
    return g

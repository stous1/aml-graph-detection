"""Lectura de ``_Patterns.txt`` de AMLworld y cruce con las transacciones.

Cada intento viene entre ``BEGIN LAUNDERING ATTEMPT - TIPO: detalle`` y
``END LAUNDERING ATTEMPT``, con una transacción por línea en el formato del CSV. Las
transacciones de lavado que no aparecen en ningún intento quedan como ``SIN_PATRON``.
"""

import re
from pathlib import Path

import duckdb
import pandas as pd

SIN_PATRON = "SIN_PATRON"

_ENCABEZADO = re.compile(r"^BEGIN LAUNDERING ATTEMPT - ([A-Z-]+)(?::\s*(.*))?$")
_CAMPOS = [
    "ts",
    "banco_origen",
    "num_origen",
    "banco_destino",
    "num_destino",
    "monto_recibido",
    "moneda_recibida",
    "monto_pagado",
    "moneda_pagada",
    "formato",
    "es_lavado",
]
_LLAVE = (
    "ts, origen, destino, monto_pagado, moneda_pagada, monto_recibido, moneda_recibida, formato"
)


def leer_patrones(texto: str) -> pd.DataFrame:
    """Convierte el texto de ``_Patterns.txt`` en una fila por transacción de cada intento.

    Columnas: ``intento_id, tipo, detalle, orden`` y los campos crudos (texto) del CSV.
    """
    filas: list[dict[str, object]] = []
    intento, tipo, detalle, orden = -1, None, None, 0
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        m = _ENCABEZADO.match(linea)
        if m:
            intento += 1
            tipo, detalle, orden = m.group(1), (m.group(2) or "").strip(), 0
            continue
        if linea.startswith("END LAUNDERING ATTEMPT"):
            tipo = None
            continue
        if tipo is None:
            raise ValueError(f"Transacción fuera de un intento: {linea!r}")
        valores = linea.split(",")
        if len(valores) != len(_CAMPOS):
            raise ValueError(f"Línea con {len(valores)} campos: {linea!r}")
        filas.append(
            {"intento_id": intento, "tipo": tipo, "detalle": detalle, "orden": orden}
            | dict(zip(_CAMPOS, valores, strict=True))
        )
        orden += 1
    return pd.DataFrame(filas, columns=["intento_id", "tipo", "detalle", "orden", *_CAMPOS])


def cargar_patrones(con: duckdb.DuckDBPyConnection, esquema: str, ruta: Path) -> dict[str, int]:
    """Crea ``esquema.patrones`` (intento_id, tipo, detalle, orden, tx_id).

    Requiere ``esquema.cuentas`` y ``esquema.transacciones``. Cada línea se cruza con una
    transacción de lavado por todos sus campos; si hay transacciones idénticas, la k-ésima
    línea se empareja con la k-ésima transacción, para no usar ninguna dos veces.
    """
    crudos = leer_patrones(Path(ruta).read_text(encoding="utf-8"))
    con.register("patrones_crudos", crudos)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE patrones_lineas AS
        SELECT p.intento_id, p.tipo, p.detalle, p.orden,
               strptime(p.ts, '%Y/%m/%d %H:%M') AS ts,
               o.cuenta_id AS origen, d.cuenta_id AS destino,
               CAST(p.monto_pagado AS DOUBLE) AS monto_pagado, p.moneda_pagada,
               CAST(p.monto_recibido AS DOUBLE) AS monto_recibido, p.moneda_recibida,
               p.formato
        FROM patrones_crudos p
        LEFT JOIN {esquema}.cuentas o
          ON o.llave = CAST(p.banco_origen AS BIGINT)::VARCHAR || ':' || p.num_origen
        LEFT JOIN {esquema}.cuentas d
          ON d.llave = CAST(p.banco_destino AS BIGINT)::VARCHAR || ':' || p.num_destino
        """
    )
    con.execute(
        f"""
        CREATE TABLE {esquema}.patrones AS
        WITH lineas AS (
            SELECT *, row_number() OVER (PARTITION BY {_LLAVE} ORDER BY intento_id, orden) AS k
            FROM patrones_lineas
        ),
        candidatas AS (
            SELECT tx_id, {_LLAVE},
                   row_number() OVER (PARTITION BY {_LLAVE} ORDER BY tx_id) AS k
            FROM {esquema}.transacciones WHERE es_lavado
        )
        SELECT l.intento_id, l.tipo, l.detalle, l.orden, c.tx_id
        FROM lineas l LEFT JOIN candidatas c USING ({_LLAVE}, k)
        ORDER BY l.intento_id, l.orden
        """
    )
    con.unregister("patrones_crudos")
    con.execute("DROP TABLE patrones_lineas")
    sin_cruce, intentos = con.execute(
        f"SELECT sum((tx_id IS NULL)::INT), count(DISTINCT intento_id) FROM {esquema}.patrones"
    ).fetchone()
    return {
        "lineas_patrones": len(crudos),
        "intentos": int(intentos or 0),
        "lineas_sin_cruce": int(sin_cruce or 0),
    }

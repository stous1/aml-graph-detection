"""Ingesta de AMLworld (CSV) a DuckDB.

Cada variante (``hi``, ``li``) vive en su propio esquema de la base local con estas tablas:

- ``cuentas``: una fila por cuenta, con ``cuenta_id`` entero y la llave ``banco:cuenta``.
- ``transacciones``: una fila por transferencia, con ``tx_id`` determinista, monto en USD,
  período y etiqueta ``es_lavado``.
- ``patrones``: transacciones de los intentos de lavado documentados en ``_Patterns.txt``.
- ``tasas``: tasa implícita a USD de cada moneda.

El ``tx_id`` es la posición de la transacción tras ordenar por todos sus campos, así no
depende del orden de lectura en paralelo de DuckDB.
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb

from lavado import particion, patrones, tasas
from lavado.rutas import BASE_DUCKDB, DATA_RAW

VARIANTES: tuple[str, ...] = ("hi", "li")

COLUMNAS_TRANSACCIONES: dict[str, str] = {
    "ts": "TIMESTAMP",
    "banco_origen": "VARCHAR",
    "num_origen": "VARCHAR",
    "banco_destino": "VARCHAR",
    "num_destino": "VARCHAR",
    "monto_recibido": "DOUBLE",
    "moneda_recibida": "VARCHAR",
    "monto_pagado": "DOUBLE",
    "moneda_pagada": "VARCHAR",
    "formato": "VARCHAR",
    "es_lavado": "INTEGER",
}


@dataclass(frozen=True)
class ArchivosAML:
    """Los tres archivos de una variante de AMLworld."""

    transacciones: Path
    patrones: Path
    cuentas: Path


def archivos(variante: str, dir_raw: Path = DATA_RAW, tamano: str = "Small") -> ArchivosAML:
    """Rutas de los archivos de una variante (``hi`` o ``li``)."""
    prefijo = f"{variante.upper()}-{tamano}"
    return ArchivosAML(
        transacciones=dir_raw / f"{prefijo}_Trans.csv",
        patrones=dir_raw / f"{prefijo}_Patterns.txt",
        cuentas=dir_raw / f"{prefijo}_accounts.csv",
    )


def conectar(
    ruta: Path | str = BASE_DUCKDB, solo_lectura: bool = False
) -> duckdb.DuckDBPyConnection:
    """Abre (o crea) la base DuckDB del proyecto."""
    if ruta != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ruta), read_only=solo_lectura)
    con.execute("SET enable_progress_bar = false")
    con.execute("SET TimeZone = 'UTC'")  # nada depende de la zona horaria de la máquina
    return con


def _sql_ruta(ruta: Path) -> str:
    return str(ruta).replace("\\", "/").replace("'", "''")


def _llave(banco: str, numero: str) -> str:
    """Llave de cuenta: banco como entero (sin ceros a la izquierda) y número."""
    return f"CAST({banco} AS BIGINT)::VARCHAR || ':' || {numero}"


def cargar_variante(
    con: duckdb.DuckDBPyConnection, variante: str, dir_raw: Path = DATA_RAW
) -> dict[str, int]:
    """Carga una variante completa en el esquema ``variante`` y devuelve conteos básicos."""
    arch = archivos(variante, dir_raw)
    e = variante
    con.execute(f"DROP SCHEMA IF EXISTS {e} CASCADE")
    con.execute(f"CREATE SCHEMA {e}")

    columnas = ", ".join(f"'{c}': '{t}'" for c, t in COLUMNAS_TRANSACCIONES.items())
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE crudas AS
        SELECT * FROM read_csv('{_sql_ruta(arch.transacciones)}', header = true,
            columns = {{{columnas}}}, timestampformat = '%Y/%m/%d %H:%M')
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE cuentas_crudas AS
        SELECT * FROM read_csv('{_sql_ruta(arch.cuentas)}', header = true, all_varchar = true)
        """
    )

    # Cuentas: las del archivo de cuentas más cualquiera que aparezca solo en transacciones.
    con.execute(
        f"""
        CREATE TABLE {e}.cuentas AS
        WITH archivo AS (
            SELECT {_llave('"Bank ID"', '"Account Number"')} AS llave,
                   CAST("Bank ID" AS BIGINT) AS banco, "Account Number" AS numero,
                   "Bank Name" AS nombre_banco, "Entity ID" AS entidad_id,
                   "Entity Name" AS entidad_nombre
            FROM cuentas_crudas
            QUALIFY row_number() OVER (PARTITION BY llave ORDER BY "Entity ID") = 1
        ),
        en_transacciones AS (
            SELECT {_llave("banco_origen", "num_origen")} AS llave,
                   CAST(banco_origen AS BIGINT) AS banco, num_origen AS numero FROM crudas
            UNION
            SELECT {_llave("banco_destino", "num_destino")},
                   CAST(banco_destino AS BIGINT), num_destino FROM crudas
        ),
        todas AS (
            SELECT llave, banco, numero FROM archivo
            UNION
            SELECT llave, banco, numero FROM en_transacciones
        )
        SELECT (row_number() OVER (ORDER BY t.llave) - 1)::INTEGER AS cuenta_id,
               t.llave, t.banco, t.numero, a.nombre_banco, a.entidad_id, a.entidad_nombre,
               regexp_extract(a.entidad_nombre, '^(.*) #', 1) AS tipo_entidad
        FROM todas t LEFT JOIN archivo a USING (llave)
        ORDER BY cuenta_id
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE transacciones_sin_usd AS
        SELECT (row_number() OVER (ORDER BY ts, c.llave_o, c.llave_d, monto_pagado,
                    moneda_pagada, monto_recibido, moneda_recibida, formato, es_lavado)
                - 1)::BIGINT AS tx_id,
               ts, o.cuenta_id AS origen, d.cuenta_id AS destino,
               monto_pagado, moneda_pagada, monto_recibido, moneda_recibida, formato,
               es_lavado::BOOLEAN AS es_lavado,
               (o.cuenta_id = d.cuenta_id) AS es_autotransferencia,
               {particion.periodo_sql("ts")} AS periodo
        FROM (SELECT *, {_llave("banco_origen", "num_origen")} AS llave_o,
                        {_llave("banco_destino", "num_destino")} AS llave_d FROM crudas) c
        JOIN {e}.cuentas o ON o.llave = c.llave_o
        JOIN {e}.cuentas d ON d.llave = c.llave_d
        """
    )

    tabla_tasas = tasas.estimar_tasas(con, "transacciones_sin_usd", hasta=particion.INICIO_PRUEBA)
    con.register("tasas_df", tabla_tasas)
    con.execute(f"CREATE TABLE {e}.tasas AS SELECT * FROM tasas_df ORDER BY moneda")
    con.unregister("tasas_df")
    con.execute(
        f"""
        CREATE TABLE {e}.transacciones AS
        SELECT t.*, t.monto_pagado * r.usd_por_unidad AS monto_usd
        FROM transacciones_sin_usd t LEFT JOIN {e}.tasas r ON r.moneda = t.moneda_pagada
        ORDER BY tx_id
        """
    )

    resumen_patrones = patrones.cargar_patrones(con, e, arch.patrones)
    for tabla in ("crudas", "cuentas_crudas", "transacciones_sin_usd"):
        con.execute(f"DROP TABLE {tabla}")

    conteos = con.execute(
        f"""
        SELECT count(*), sum(es_lavado::INT),
               (SELECT count(*) FROM {e}.cuentas),
               sum((monto_usd IS NULL)::INT)
        FROM {e}.transacciones
        """
    ).fetchone()
    return {
        "transacciones": int(conteos[0]),
        "lavado": int(conteos[1]),
        "cuentas": int(conteos[2]),
        "sin_tasa": int(conteos[3]),
        **resumen_patrones,
    }

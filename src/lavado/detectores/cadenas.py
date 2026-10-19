"""Cadenas de paso: el dinero salta de cuenta en cuenta conservando el monto.

Con los pares de paso (``lavado.paso``) como aristas entre transferencias, el grafo es
acíclico (cada salto es más tarde que el anterior). Para cada transferencia se calcula la
cadena más larga que pasa por ella: la más larga que termina en ella más la más larga que
empieza en ella, menos uno. Una transferencia suelta vale 1; una cadena de 5 saltos con monto
conservado da 5 a cada una de sus transferencias. Captura capas (STACK), caminos (RANDOM) y
los tramos de ciclos y de dispersión-concentración.

Solo usa tiempo, montos y topología.
"""

from dataclasses import asdict, dataclass

import duckdb
import pandas as pd

from lavado import particion, paso
from lavado.detectores import comun


@dataclass(frozen=True)
class ConfigCadenas:
    delta_horas: int = 96
    tolerancia: float = 0.2
    max_saltos: int = 12  # tope de la búsqueda (iteraciones)

    def como_dict(self) -> dict:
        return asdict(self)


def largo_cadenas(
    con: duckdb.DuckDBPyConnection, esquema: str, hasta, config: ConfigCadenas
) -> pd.DataFrame:
    """``tx_id, adelante, atras, largo`` para las transferencias que están en algún par."""
    paso.crear_pares_paso(con, esquema, hasta, config.delta_horas, config.tolerancia, "ca_pares")
    for nombre, desde, hacia in (
        ("ca_adelante", "tx_in", "tx_out"),
        ("ca_atras", "tx_out", "tx_in"),
    ):
        # largo de la cadena más larga que termina (adelante) o empieza (atrás) en cada tx
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE {nombre} AS
            SELECT tx_id, 1 AS largo FROM (
                SELECT tx_in AS tx_id FROM ca_pares UNION SELECT tx_out FROM ca_pares
            )
            """
        )
        for _ in range(int(config.max_saltos) - 1):
            con.execute(
                f"""
                CREATE OR REPLACE TEMP TABLE ca_nuevo AS
                SELECT p.{hacia} AS tx_id, max(l.largo) + 1 AS largo
                FROM ca_pares p JOIN {nombre} l ON l.tx_id = p.{desde}
                GROUP BY p.{hacia}
                """
            )
            n = con.execute(
                f"""
                SELECT count(*) FROM ca_nuevo n JOIN {nombre} l USING (tx_id)
                WHERE n.largo > l.largo
                """
            ).fetchone()[0]
            if not n:
                break
            con.execute(
                f"""
                CREATE OR REPLACE TEMP TABLE {nombre} AS
                SELECT l.tx_id, greatest(l.largo, coalesce(n.largo, 0)) AS largo
                FROM {nombre} l LEFT JOIN ca_nuevo n USING (tx_id)
                """
            )
    resultado = con.execute(
        """
        SELECT a.tx_id, a.largo AS adelante, b.largo AS atras, a.largo + b.largo - 1 AS largo
        FROM ca_adelante a JOIN ca_atras b USING (tx_id) ORDER BY a.tx_id
        """
    ).df()
    for tabla in ("ca_pares", "ca_adelante", "ca_atras", "ca_nuevo"):
        con.execute(f"DROP TABLE IF EXISTS {tabla}")
    return resultado


def puntuar(
    con: duckdb.DuckDBPyConnection, esquema: str, periodo: str, config: ConfigCadenas
) -> comun.Puntajes:
    """Puntaje = largo de la cadena más larga que pasa por la transferencia (0 si no hay)."""
    largos = largo_cadenas(con, esquema, particion.HASTA[periodo], config)
    por_tx = largos[["tx_id"]].assign(puntaje=largos.largo.astype(float))
    return comun.desde_tabla(
        comun.transacciones_periodo(con, esquema, periodo), por_tx, comun.n_cuentas(con, esquema)
    )

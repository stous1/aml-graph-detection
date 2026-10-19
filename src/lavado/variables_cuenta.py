"""Variables de comportamiento por cuenta en un período, sin etiquetas.

Se calculan con las transferencias del período (``[desde, hasta)``) y la historia anterior
(para saber qué contrapartes son nuevas). Hay dos grupos:

- **Estructurales** (existirían en cualquier banco): volumen y grado de entrada y salida,
  unicidad, **dinero de paso** (fracción de lo recibido que se reenvía con monto parecido
  dentro de Δ, y balance entre lo que entra y sale), **velocidad** (mediana de horas entre
  recibir y reenviar), **contrapartes nuevas**, dispersión y nivel de los montos.
- **Sospechosas de artefacto** de AMLworld: número de monedas y participación de cada
  formato de pago.
"""

from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

from lavado import paso

DELTA_PASO_HORAS = 96
TOLERANCIA_PASO = 0.2

ESTRUCTURALES: tuple[str, ...] = (
    "log_n_in",
    "log_n_out",
    "log_grado_in",
    "log_grado_out",
    "unicidad_in",
    "unicidad_out",
    "frac_paso",
    "velocidad_horas",
    "balance",
    "frac_nuevas",
    "cv_montos",
    "log_monto_medio",
)
FORMATOS: tuple[str, ...] = ("ACH", "Bitcoin", "Cash", "Cheque", "Credit Card", "Wire")
SOSPECHOSAS: tuple[str, ...] = ("n_monedas",) + tuple(f"frac_{f}" for f in FORMATOS)


def _ts(fecha: datetime) -> str:
    return f"TIMESTAMP '{fecha:%Y-%m-%d %H:%M:%S}'"


def calcular(
    con: duckdb.DuckDBPyConnection, esquema: str, desde: datetime, hasta: datetime
) -> pd.DataFrame:
    """Una fila por cuenta activa en ``[desde, hasta)`` con ``cuenta_id`` y todas las variables."""
    paso.crear_pares_paso(con, esquema, hasta, DELTA_PASO_HORAS, TOLERANCIA_PASO, "vc_pares")
    formatos = ", ".join(f"avg((formato = '{f}')::INT) AS \"frac_{f}\"" for f in FORMATOS)
    df = con.execute(
        f"""
        WITH tx AS (
            SELECT * FROM {esquema}.aristas WHERE ts >= {_ts(desde)} AND ts < {_ts(hasta)}
        ),
        lados AS (
            SELECT tx_id, ts, destino AS cuenta, origen AS contraparte, 'in' AS dir,
                   monto_usd, moneda, formato FROM tx
            UNION ALL
            SELECT tx_id, ts, origen, destino, 'out', monto_usd, moneda, formato FROM tx
        ),
        primer AS (
            SELECT least(origen, destino) AS a, greatest(origen, destino) AS z, min(ts) AS primero
            FROM {esquema}.aristas WHERE ts < {_ts(hasta)} GROUP BY ALL
        ),
        nuevas AS (
            SELECT l.cuenta,
                   avg((p.primero >= {_ts(desde)})::INT) AS frac_nuevas
            FROM (SELECT DISTINCT cuenta, contraparte FROM lados) l
            JOIN primer p ON p.a = least(l.cuenta, l.contraparte)
                         AND p.z = greatest(l.cuenta, l.contraparte)
            GROUP BY l.cuenta
        ),
        pasos AS (
            SELECT cuenta, count(DISTINCT tx_in) AS n_in_paso,
                   median(epoch(ts_out - ts_in) / 3600) AS velocidad_horas
            FROM vc_pares WHERE ts_in >= {_ts(desde)} GROUP BY cuenta
        ),
        base AS (
            SELECT cuenta,
                   count(*) FILTER (WHERE dir = 'in') AS n_in,
                   count(*) FILTER (WHERE dir = 'out') AS n_out,
                   count(DISTINCT contraparte) FILTER (WHERE dir = 'in') AS grado_in,
                   count(DISTINCT contraparte) FILTER (WHERE dir = 'out') AS grado_out,
                   coalesce(sum(monto_usd) FILTER (WHERE dir = 'in'), 0) AS usd_in,
                   coalesce(sum(monto_usd) FILTER (WHERE dir = 'out'), 0) AS usd_out,
                   coalesce(stddev_pop(monto_usd) / nullif(avg(monto_usd), 0), 0) AS cv_montos,
                   ln(1 + avg(monto_usd)) AS log_monto_medio,
                   count(DISTINCT moneda) AS n_monedas,
                   {formatos}
            FROM lados GROUP BY cuenta
        )
        SELECT b.cuenta AS cuenta_id, b.*, n.frac_nuevas,
               coalesce(p.n_in_paso, 0) AS n_in_paso, p.velocidad_horas
        FROM base b LEFT JOIN nuevas n USING (cuenta) LEFT JOIN pasos p USING (cuenta)
        ORDER BY b.cuenta
        """
    ).df()
    con.execute("DROP TABLE vc_pares")
    df = df.drop(columns=["cuenta"])
    df["log_n_in"] = np.log1p(df.n_in)
    df["log_n_out"] = np.log1p(df.n_out)
    df["log_grado_in"] = np.log1p(df.grado_in)
    df["log_grado_out"] = np.log1p(df.grado_out)
    df["unicidad_in"] = np.where(df.n_in > 0, df.grado_in / df.n_in.clip(lower=1), 1.0)
    df["unicidad_out"] = np.where(df.n_out > 0, df.grado_out / df.n_out.clip(lower=1), 1.0)
    df["frac_paso"] = np.where(df.n_in > 0, df.n_in_paso / df.n_in.clip(lower=1), 0.0)
    df["velocidad_horas"] = df.velocidad_horas.fillna(float(DELTA_PASO_HORAS))
    mayor = np.maximum(df.usd_in, df.usd_out)
    df["balance"] = np.where(mayor > 0, np.minimum(df.usd_in, df.usd_out) / mayor, 0.0)
    df["frac_nuevas"] = df.frac_nuevas.fillna(1.0)
    return df

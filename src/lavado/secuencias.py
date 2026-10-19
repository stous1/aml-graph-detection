"""Secuencias de eventos por cuenta para CoLES, sin etiquetas y sin moneda ni formato.

Cada transferencia es un evento para sus dos cuentas (una salida para el origen y una entrada
para el destino). Variables de cada evento, todas estructurales o de comportamiento:

- Categóricas: ``direccion`` (1 entrada, 2 salida), ``hora`` (1 a 24), ``dia_semana`` (1 a 7),
  ``nueva`` (2 si es la primera transferencia entre las dos cuentas), ``paso`` (2 si es una
  entrada que la cuenta reenvía con monto parecido dentro de 96 h, 3 si es una salida que
  reenvía una entrada, 1 si no). El 0 queda para el relleno.
- Numéricas: ``log_monto`` (log de 1 + USD), ``log_dt`` (log de 1 + horas desde el evento
  anterior de la cuenta) y ``log_actividad`` (log de 1 + eventos de la contraparte en la
  ventana).

Se usan las transferencias de ``[desde, hasta)``; el primer contacto entre cuentas y los pares
de paso miran toda la historia anterior a ``hasta``.
"""

from dataclasses import dataclass
from datetime import datetime

import duckdb
import numpy as np
import torch

from lavado import paso

CATEGORICAS: dict[str, int] = {"direccion": 3, "hora": 25, "dia_semana": 8, "nueva": 3, "paso": 4}
NUMERICAS: tuple[str, ...] = ("log_monto", "log_dt", "log_actividad")
DELTA_PASO_HORAS = 96
TOLERANCIA_PASO = 0.2


@dataclass
class Secuencias:
    """Secuencias de una ventana: ``cuentas[i]`` es la cuenta de ``registros[i]``."""

    cuentas: np.ndarray
    largos: np.ndarray
    registros: list[dict]


def _ts(fecha: datetime) -> str:
    return f"TIMESTAMP '{fecha:%Y-%m-%d %H:%M:%S}'"


def conteo_eventos(
    con: duckdb.DuckDBPyConnection, esquema: str, desde: datetime, hasta: datetime
) -> dict[int, int]:
    """Eventos (transferencias enviadas o recibidas) por cuenta en ``[desde, hasta)``."""
    filas = con.execute(
        f"""
        SELECT c, count(*) FROM (
            SELECT origen AS c FROM {esquema}.aristas WHERE ts >= {_ts(desde)} AND ts < {_ts(hasta)}
            UNION ALL
            SELECT destino FROM {esquema}.aristas WHERE ts >= {_ts(desde)} AND ts < {_ts(hasta)}
        ) GROUP BY c
        """
    ).fetchall()
    return dict(filas)


def construir(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    desde: datetime,
    hasta: datetime,
    min_eventos: int,
    max_eventos: int = 500,
) -> Secuencias:
    """Secuencias de las cuentas con al menos ``min_eventos`` eventos en la ventana.

    De cada cuenta se conservan los últimos ``max_eventos`` eventos.
    """
    paso.crear_pares_paso(con, esquema, hasta, DELTA_PASO_HORAS, TOLERANCIA_PASO, "sq_pares")
    df = con.execute(
        f"""
        WITH tx AS (
            SELECT tx_id, ts, origen, destino, monto_usd FROM {esquema}.aristas
            WHERE ts >= {_ts(desde)} AND ts < {_ts(hasta)}
        ),
        lados AS (
            SELECT tx_id, ts, origen AS cuenta, destino AS contraparte, 2 AS direccion, monto_usd
            FROM tx
            UNION ALL
            SELECT tx_id, ts, destino, origen, 1, monto_usd FROM tx
        ),
        n AS (SELECT cuenta, count(*) AS n FROM lados GROUP BY cuenta),
        primer AS (
            SELECT least(origen, destino) AS a, greatest(origen, destino) AS z, min(ts) AS primero
            FROM {esquema}.aristas WHERE ts < {_ts(hasta)} GROUP BY ALL
        ),
        reenviadas AS (SELECT DISTINCT tx_in AS tx_id, cuenta FROM sq_pares),
        reenvios AS (SELECT DISTINCT tx_out AS tx_id, cuenta FROM sq_pares)
        SELECT l.cuenta, l.tx_id, epoch(l.ts) AS t, l.direccion,
               hour(l.ts) + 1 AS hora, isodow(l.ts) AS dia_semana,
               CASE WHEN p.primero = l.ts THEN 2 ELSE 1 END AS nueva,
               CASE WHEN r1.tx_id IS NOT NULL THEN 2 WHEN r2.tx_id IS NOT NULL THEN 3 ELSE 1 END
                   AS paso,
               ln(1 + l.monto_usd) AS log_monto, ln(1 + nc.n) AS log_actividad
        FROM lados l
        JOIN n USING (cuenta)
        JOIN n nc ON nc.cuenta = l.contraparte
        JOIN primer p ON p.a = least(l.cuenta, l.contraparte)
                     AND p.z = greatest(l.cuenta, l.contraparte)
        LEFT JOIN reenviadas r1 ON r1.tx_id = l.tx_id AND r1.cuenta = l.cuenta AND l.direccion = 1
        LEFT JOIN reenvios r2 ON r2.tx_id = l.tx_id AND r2.cuenta = l.cuenta AND l.direccion = 2
        WHERE n.n >= {int(min_eventos)}
        ORDER BY l.cuenta, l.ts, l.tx_id, l.direccion
        """
    ).df()
    con.execute("DROP TABLE sq_pares")
    if df.empty:
        return Secuencias(np.array([], dtype=np.int64), np.array([], dtype=np.int64), [])
    cuenta = df.cuenta.to_numpy()
    cortes = np.flatnonzero(np.diff(cuenta)) + 1
    inicios = np.r_[0, cortes]
    finales = np.r_[cortes, len(df)]
    t = df.t.to_numpy(dtype=np.float64)
    dt = np.r_[0.0, np.diff(t)] / 3600.0
    dt[inicios] = 0.0
    df["log_dt"] = np.log1p(np.clip(dt, 0, None))
    columnas = {c: df[c].to_numpy() for c in [*CATEGORICAS, *NUMERICAS]}
    registros, cuentas, largos = [], [], []
    for i0, i1 in zip(inicios, finales, strict=True):
        i0 = max(i0, i1 - int(max_eventos))
        registro = {"event_time": torch.tensor(t[i0:i1], dtype=torch.float64)}
        for c in CATEGORICAS:
            registro[c] = torch.tensor(columnas[c][i0:i1], dtype=torch.long)
        for c in NUMERICAS:
            registro[c] = torch.tensor(columnas[c][i0:i1], dtype=torch.float32)
        registros.append(registro)
        cuentas.append(int(cuenta[i0]))
        largos.append(i1 - i0)
    return Secuencias(np.array(cuentas, dtype=np.int64), np.array(largos), registros)

"""Abanicos de entrada y de salida en ventanas de tiempo, puntuados por su forma.

Una **estructura** es ``(centro, dirección, ventana)``: todas las transferencias que la cuenta
``centro`` envía (abanico de salida) o recibe (abanico de entrada) dentro de una ventana de
``W`` horas. Las ventanas son fijas, con dos desfases (0 y ``W/2``), así toda ráfaga de hasta
``W/2`` horas cae completa en alguna. Son candidatas las estructuras con al menos
``min_contrapartes`` contrapartes distintas.

Variables de forma, todas en [0, 1] (1 = más sospechoso):

- ``novedad``: fracción de contrapartes sin ningún contacto previo con el centro.
- ``exclusividad``: en promedio, qué parte de la actividad de cada contraparte en la ventana
  es con el centro (contrapartes "dedicadas").
- ``unicidad``: contrapartes / transferencias; 1 si cada contraparte recibe (o envía) una sola.
- ``homogeneidad``: ``1 / (1 + CV)`` de los montos en USD.
- ``formato``: participación del formato de pago más frecuente.
- ``mezcla_monedas``: 1 menos la participación de la moneda más frecuente.
- ``dispersion``: duración de la estructura / ``W``; el abanico se reparte en la ventana.

La orientación de ``mezcla_monedas`` y ``dispersion`` se corrigió en desarrollo: a priori se
esperaba un abanico de una sola moneda y concentrado en el tiempo, y en los abanicos de lavado
de desarrollo ocurre lo contrario (ver INFORME_TECNICO.md).

Puntaje: ``tamaño × Π max(variable, PISO)`` sobre las variables elegidas, con
``tamaño = log2(contrapartes)`` o 1. La **regla simple** es el caso sin variables: solo
cuenta contrapartes en 24 horas.

El detector no lee etiquetas. Ve solo transferencias anteriores a ``hasta``.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

from lavado import particion

VARIABLES_FORMA: tuple[str, ...] = (
    "novedad",
    "exclusividad",
    "unicidad",
    "homogeneidad",
    "formato",
    "mezcla_monedas",
    "dispersion",
)
PISO = 0.01


@dataclass(frozen=True)
class ConfigAbanicos:
    """Configuración del detector. La regla simple es ``variables=()`` y ``tamano='lineal'``."""

    ventana_horas: int = 24
    min_contrapartes: int = 3
    por_formato: bool = False
    variables: tuple[str, ...] = VARIABLES_FORMA
    tamano: str = "log2"  # "log2", "lineal" o "ninguno"
    direccion: str = "ambas"  # "ambas", "salida" o "entrada"

    def como_dict(self) -> dict:
        return asdict(self) | {"variables": list(self.variables)}


REGLA_SIMPLE = ConfigAbanicos(ventana_horas=24, por_formato=False, variables=(), tamano="lineal")


@dataclass
class Candidatas:
    """Estructuras candidatas de una ventana y su cruce con las transferencias de un período.

    ``estructuras``: una fila por estructura con sus variables. ``mapa``: una fila por
    transferencia del período con los índices (en ``estructuras``) de las hasta cuatro
    estructuras que la contienen (salida del origen y entrada del destino, en cada desfase),
    o -1.
    """

    ventana_horas: int
    min_contrapartes: int
    por_formato: bool
    hasta: datetime
    estructuras: pd.DataFrame
    mapa: pd.DataFrame
    indices: np.ndarray = field(repr=False)  # (n_tx, 4)


def _ts(fecha: datetime) -> str:
    return f"TIMESTAMP '{fecha:%Y-%m-%d %H:%M:%S}'"


def calcular_candidatas(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    hasta: datetime,
    periodo: str,
    ventana_horas: int,
    min_contrapartes: int = 3,
    por_formato: bool = False,
) -> Candidatas:
    """Calcula las estructuras candidatas con transferencias anteriores a ``hasta``.

    El mapa incluye las transferencias de ``periodo`` (``desarrollo`` o ``prueba``). Con
    ``por_formato`` cada estructura es de un solo canal (formato de pago): una cuenta que paga
    por ACH y por cheque tiene un abanico por canal.
    """
    seg = int(ventana_horas) * 3600
    t0 = _ts(particion.INICIO)
    e0 = f"epoch({t0})"
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE ab_lados AS
        WITH tx AS (
            SELECT tx_id, ts, origen, destino, monto_usd, moneda, formato
            FROM {esquema}.aristas WHERE ts < {_ts(hasta)}
        ),
        lados AS (
            SELECT tx_id, ts, origen AS centro, destino AS contraparte, 'salida' AS direccion,
                   monto_usd, moneda, formato FROM tx
            UNION ALL
            SELECT tx_id, ts, destino, origen, 'entrada', monto_usd, moneda, formato FROM tx
        )
        SELECT l.*, {"formato" if por_formato else "'todos'"} AS canal, d.desfase,
               floor((epoch(l.ts) - {e0} - d.desfase) / {seg})::INTEGER AS b
        FROM lados l CROSS JOIN (VALUES (0), ({seg // 2})) d(desfase)
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE ab_estructuras AS
        WITH cand AS (
            SELECT centro, direccion, canal, desfase, b,
                   count(DISTINCT contraparte) AS n_contrapartes
            FROM ab_lados GROUP BY ALL HAVING n_contrapartes >= {int(min_contrapartes)}
        ),
        miembros AS (
            SELECT l.* FROM ab_lados l SEMI JOIN cand USING (centro, direccion, canal, desfase, b)
        ),
        primer_contacto AS (
            SELECT least(origen, destino) AS a, greatest(origen, destino) AS z, min(ts) AS primero
            FROM {esquema}.aristas WHERE ts < {_ts(hasta)} GROUP BY ALL
        ),
        actividad AS (
            -- cada transferencia aparece una vez como 'salida' y otra como 'entrada' en
            -- ab_lados, así que contar por centro da la actividad total de la cuenta
            SELECT centro AS cuenta, desfase, b, count(*) AS n_act
            FROM ab_lados GROUP BY ALL
        ),
        por_contraparte AS (
            SELECT m.centro, m.direccion, m.canal, m.desfase, m.b, m.contraparte, count(*) AS n_par,
                   any_value(p.primero) AS primero
            FROM miembros m
            JOIN primer_contacto p
              ON p.a = least(m.centro, m.contraparte) AND p.z = greatest(m.centro, m.contraparte)
            GROUP BY ALL
        ),
        contrapartes AS (
            SELECT c.centro, c.direccion, c.canal, c.desfase, c.b,
                   avg((c.primero >= {t0} + to_seconds(c.desfase + c.b * {seg}))
                       ::INT) AS novedad,
                   avg(c.n_par / a.n_act) AS exclusividad
            FROM por_contraparte c
            JOIN actividad a ON a.cuenta = c.contraparte AND a.desfase = c.desfase AND a.b = c.b
            GROUP BY ALL
        ),
        modo_formato AS (
            SELECT centro, direccion, canal, desfase, b, max(n) AS n_modo FROM (
                SELECT centro, direccion, canal, desfase, b, formato, count(*) AS n
                FROM miembros GROUP BY ALL
            ) GROUP BY ALL
        ),
        modo_moneda AS (
            SELECT centro, direccion, canal, desfase, b, max(n) AS n_modo FROM (
                SELECT centro, direccion, canal, desfase, b, moneda, count(*) AS n
                FROM miembros GROUP BY ALL
            ) GROUP BY ALL
        ),
        montos AS (
            SELECT centro, direccion, canal, desfase, b, count(*) AS n_tx,
                   sum(monto_usd) AS monto_usd,
                   coalesce(stddev_pop(monto_usd) / nullif(avg(monto_usd), 0), 0) AS cv,
                   min(ts) AS primera, max(ts) AS ultima
            FROM miembros GROUP BY ALL
        )
        SELECT k.centro, k.direccion, k.canal, k.desfase, k.b,
               {t0} + to_seconds(k.desfase + k.b * {seg}) AS inicio_ventana,
               {t0} + to_seconds(k.desfase + (k.b + 1) * {seg}) AS fin_ventana,
               k.n_contrapartes, m.n_tx, m.monto_usd, m.primera, m.ultima,
               c.novedad, c.exclusividad,
               1 / (1 + m.cv) AS homogeneidad,
               k.n_contrapartes / m.n_tx AS unicidad,
               mf.n_modo / m.n_tx AS formato,
               1 - mm.n_modo / m.n_tx AS mezcla_monedas,
               least(1, epoch(m.ultima - m.primera) / {seg}) AS dispersion
        FROM cand k
        JOIN montos m USING (centro, direccion, canal, desfase, b)
        JOIN contrapartes c USING (centro, direccion, canal, desfase, b)
        JOIN modo_formato mf USING (centro, direccion, canal, desfase, b)
        JOIN modo_moneda mm USING (centro, direccion, canal, desfase, b)
        ORDER BY k.centro, k.direccion, k.canal, k.desfase, k.b
        """
    )
    estructuras = con.execute("SELECT * FROM ab_estructuras").df()
    estructuras["idx"] = np.arange(len(estructuras), dtype=np.int64)
    con.register("ab_idx", estructuras[["centro", "direccion", "canal", "desfase", "b", "idx"]])
    mapa = con.execute(
        f"""
        WITH tx AS (
            SELECT tx_id, origen, destino FROM {esquema}.aristas
            WHERE periodo = '{periodo}' AND ts < {_ts(hasta)}
        ),
        enlaces AS (
            SELECT l.tx_id, l.direccion, l.desfase, i.idx
            FROM ab_lados l JOIN ab_idx i USING (centro, direccion, canal, desfase, b)
            WHERE l.tx_id IN (SELECT tx_id FROM tx)
        )
        SELECT t.tx_id, t.origen, t.destino,
               coalesce(max(idx) FILTER (WHERE direccion = 'salida' AND desfase = 0), -1) AS e1,
               coalesce(max(idx) FILTER (WHERE direccion = 'salida' AND desfase > 0), -1) AS e2,
               coalesce(max(idx) FILTER (WHERE direccion = 'entrada' AND desfase = 0), -1) AS e3,
               coalesce(max(idx) FILTER (WHERE direccion = 'entrada' AND desfase > 0), -1) AS e4
        FROM tx t LEFT JOIN enlaces e USING (tx_id)
        GROUP BY ALL ORDER BY t.tx_id
        """
    ).df()
    con.unregister("ab_idx")
    con.execute("DROP TABLE ab_lados")
    con.execute("DROP TABLE ab_estructuras")
    indices = mapa[["e1", "e2", "e3", "e4"]].to_numpy(dtype=np.int64)
    return Candidatas(
        ventana_horas, min_contrapartes, por_formato, hasta, estructuras, mapa, indices
    )


def puntuar_estructuras(estructuras: pd.DataFrame, config: ConfigAbanicos) -> np.ndarray:
    """Puntaje de cada estructura según ``config`` (no usa etiquetas)."""
    n = estructuras["n_contrapartes"].to_numpy(dtype=float)
    if config.tamano == "log2":
        puntaje = np.log2(n)
    elif config.tamano == "lineal":
        puntaje = n.copy()
    elif config.tamano == "ninguno":
        puntaje = np.ones_like(n)
    else:
        raise ValueError(f"tamano inválido: {config.tamano}")
    for var in config.variables:
        if var not in VARIABLES_FORMA:
            raise ValueError(f"variable desconocida: {var}")
        puntaje = puntaje * np.maximum(estructuras[var].to_numpy(dtype=float), PISO)
    puntaje[n < config.min_contrapartes] = 0.0
    if config.direccion != "ambas":
        if config.direccion not in ("salida", "entrada"):
            raise ValueError(f"direccion inválida: {config.direccion}")
        puntaje[estructuras["direccion"].to_numpy() != config.direccion] = 0.0
    return puntaje


def puntuar_transacciones(candidatas: Candidatas, puntaje_estructuras: np.ndarray) -> np.ndarray:
    """Puntaje de cada transferencia del mapa: el máximo de las estructuras que la contienen."""
    extendido = np.append(puntaje_estructuras, 0.0)  # el índice -1 apunta a este 0
    return extendido[candidatas.indices].max(axis=1)


def direccion_dominante(candidatas: Candidatas, puntaje_estructuras: np.ndarray) -> np.ndarray:
    """Para cada transferencia, si su mejor estructura es de ``salida`` o de ``entrada``."""
    extendido = np.append(puntaje_estructuras, 0.0)
    p = extendido[candidatas.indices]
    salida = p[:, :2].max(axis=1)
    entrada = p[:, 2:].max(axis=1)
    return np.where(salida >= entrada, "salida", "entrada")


def puntuar_cuentas(
    origen: np.ndarray, destino: np.ndarray, puntaje_tx: np.ndarray, n_cuentas: int
) -> np.ndarray:
    """Puntaje de cada cuenta: el máximo puntaje de las transferencias en que participa."""
    puntaje = np.zeros(n_cuentas)
    np.maximum.at(puntaje, origen, puntaje_tx)
    np.maximum.at(puntaje, destino, puntaje_tx)
    return puntaje

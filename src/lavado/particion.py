"""Partición temporal de AMLworld Small en arranque, desarrollo, prueba y cola.

Los archivos Small cubren del 1 al 10 de septiembre de 2022 más una cola de transacciones,
casi todas de lavado, hasta el 18. La partición es:

- ``arranque`` (día 1): artefacto de arranque del generador. Solo sirve como historia para
  calcular variables; no se miden métricas sobre él.
- ``desarrollo`` (días 2 a 6): toda decisión que mire etiquetas se toma aquí.
- ``prueba`` (días 7 a 10): se mide una sola vez, con los parámetros congelados.
- ``cola`` (día 11 en adelante): fuera de la ventana observable. Se excluye de todo.

Un intento de lavado que tiene transacciones en desarrollo y en prueba es un **puente**: sus
transacciones se ignoran en las métricas de ambos períodos (no son positivas ni negativas).
"""

from datetime import datetime

import duckdb
import pandas as pd

INICIO: datetime = datetime(2022, 9, 1)
INICIO_DESARROLLO: datetime = datetime(2022, 9, 2)
INICIO_PRUEBA: datetime = datetime(2022, 9, 7)
FIN_VENTANA: datetime = datetime(2022, 9, 11)  # exclusivo

PERIODOS: tuple[str, ...] = ("arranque", "desarrollo", "prueba", "cola")
PERIODOS_MEDIDOS: tuple[str, ...] = ("desarrollo", "prueba")

# Fin exclusivo de los datos que puede ver un detector al trabajar en cada período medido.
HASTA: dict[str, datetime] = {"desarrollo": INICIO_PRUEBA, "prueba": FIN_VENTANA}
DESDE: dict[str, datetime] = {"desarrollo": INICIO_DESARROLLO, "prueba": INICIO_PRUEBA}


def _literal(fecha: datetime) -> str:
    return f"TIMESTAMP '{fecha:%Y-%m-%d %H:%M:%S}'"


def periodo_sql(columna: str = "ts") -> str:
    """Expresión SQL que asigna el período de una marca de tiempo."""
    return (
        f"CASE WHEN {columna} < {_literal(INICIO_DESARROLLO)} THEN 'arranque' "
        f"WHEN {columna} < {_literal(INICIO_PRUEBA)} THEN 'desarrollo' "
        f"WHEN {columna} < {_literal(FIN_VENTANA)} THEN 'prueba' ELSE 'cola' END"
    )


def periodo(ts: datetime) -> str:
    """Período de una marca de tiempo (versión Python de :func:`periodo_sql`)."""
    if ts < INICIO_DESARROLLO:
        return "arranque"
    if ts < INICIO_PRUEBA:
        return "desarrollo"
    if ts < FIN_VENTANA:
        return "prueba"
    return "cola"


def crear_etiquetas(con: duckdb.DuckDBPyConnection, esquema: str) -> None:
    """Crea ``esquema.intentos`` y ``esquema.etiquetas`` a partir de transacciones y patrones.

    ``intentos``: un intento por fila con su tipo, tamaño, inicio, fin, los períodos que toca
    y ``es_puente`` (toca desarrollo y prueba).

    ``etiquetas``: una fila por transacción de lavado con su intento (o ``SIN_PATRON``) y
    ``ignorada`` (pertenece a un intento puente). Solo ``evaluacion`` debe leer esta tabla.
    """
    e = esquema
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {e}.intentos AS
        SELECT p.intento_id, any_value(p.tipo) AS tipo, any_value(p.detalle) AS detalle,
               count(*) AS n_tx, min(t.ts) AS inicio, max(t.ts) AS fin,
               list(DISTINCT t.periodo ORDER BY t.periodo) AS periodos,
               bool_or(t.periodo = 'desarrollo') AND bool_or(t.periodo = 'prueba') AS es_puente
        FROM {e}.patrones p JOIN {e}.transacciones t USING (tx_id)
        GROUP BY p.intento_id
        ORDER BY p.intento_id
        """
    )
    # Una transacción puede aparecer en más de un intento: se conserva el de menor id, y es
    # ignorada si cualquiera de sus intentos es puente.
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {e}.etiquetas AS
        WITH por_tx AS (
            SELECT p.tx_id, min(p.intento_id) AS intento_id, bool_or(i.es_puente) AS ignorada
            FROM {e}.patrones p JOIN {e}.intentos i USING (intento_id)
            GROUP BY p.tx_id
        )
        SELECT t.tx_id, t.periodo, x.intento_id,
               coalesce(i.tipo, 'SIN_PATRON') AS tipo,
               coalesce(x.ignorada, false) AS ignorada
        FROM {e}.transacciones t
        LEFT JOIN por_tx x USING (tx_id)
        LEFT JOIN {e}.intentos i ON i.intento_id = x.intento_id
        WHERE t.es_lavado
        ORDER BY t.tx_id
        """
    )


def conteo_intentos(con: duckdb.DuckDBPyConnection, esquema: str) -> pd.DataFrame:
    """Intentos por tipo según dónde caen: solo en un período, o puente.

    Es la tabla que decide el corte (regla: al menos 10 intentos por tipo en prueba). Mira solo
    conteos de etiquetas, nunca resultados de un detector.
    """
    return con.execute(
        f"""
        SELECT tipo,
               count(*) FILTER (WHERE periodos = ['arranque']) AS solo_arranque,
               count(*) FILTER (WHERE list_contains(periodos, 'desarrollo') AND NOT es_puente)
                   AS desarrollo,
               count(*) FILTER (WHERE es_puente) AS puente,
               count(*) FILTER (WHERE list_contains(periodos, 'prueba') AND NOT es_puente)
                   AS prueba,
               count(*) FILTER (WHERE periodos = ['cola']) AS solo_cola,
               count(*) AS total
        FROM {esquema}.intentos GROUP BY tipo ORDER BY tipo
        """
    ).df()

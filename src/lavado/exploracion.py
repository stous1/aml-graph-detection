"""Exploración de una variante: volúmenes, artefactos del generador, historias y patrones.

Las cifras que usan etiquetas se limitan a conteos (tasa de lavado por día e intentos por
período, que deciden el corte) o al período de desarrollo. Nada de aquí mira resultados de
un detector.
"""

import duckdb
import pandas as pd

from lavado import particion


def _df(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    return con.execute(sql).df().to_dict(orient="records")


def por_dia(con: duckdb.DuckDBPyConnection, esquema: str) -> pd.DataFrame:
    """Transacciones, lavado y tasa de lavado por día (incluye arranque y cola)."""
    return con.execute(
        f"""
        SELECT ts::DATE AS dia, any_value(periodo) AS periodo, count(*) AS transacciones,
               sum(es_lavado::INT) AS lavado, avg(es_lavado::INT) AS tasa_lavado,
               sum(es_autotransferencia::INT) AS autotransferencias
        FROM {esquema}.transacciones GROUP BY dia ORDER BY dia
        """
    ).df()


def historias_por_cuenta(con: duckdb.DuckDBPyConnection, esquema: str) -> dict:
    """Largo de la historia de cada cuenta (transferencias enviadas o recibidas, sin
    autotransferencias ni cola). Sirve para decidir en el hito 3 si alcanza para CoLES."""
    fila = con.execute(
        f"""
        WITH n AS (
            SELECT cuenta, count(*) AS n FROM (
                SELECT origen AS cuenta FROM {esquema}.aristas
                UNION ALL SELECT destino FROM {esquema}.aristas
            ) GROUP BY cuenta
        )
        SELECT count(*) AS cuentas_activas,
               (SELECT count(*) FROM {esquema}.cuentas) AS cuentas_totales,
               avg(n) AS media, quantile_cont(n, 0.10) AS p10, median(n) AS mediana,
               quantile_cont(n, 0.90) AS p90, quantile_cont(n, 0.99) AS p99, max(n) AS maximo,
               avg((n >= 5)::INT) AS frac_ge_5, avg((n >= 10)::INT) AS frac_ge_10,
               avg((n >= 20)::INT) AS frac_ge_20, avg((n >= 50)::INT) AS frac_ge_50
        FROM n
        """
    ).df()
    return fila.iloc[0].to_dict()


def histograma_historias(con: duckdb.DuckDBPyConnection, esquema: str) -> pd.DataFrame:
    """Número de cuentas por largo de historia, en cubetas logarítmicas (base 2)."""
    return con.execute(
        f"""
        WITH n AS (
            SELECT cuenta, count(*) AS n FROM (
                SELECT origen AS cuenta FROM {esquema}.aristas
                UNION ALL SELECT destino FROM {esquema}.aristas
            ) GROUP BY cuenta
        )
        SELECT floor(log2(n))::INT AS cubeta, min(n) AS desde, max(n) AS hasta,
               count(*) AS cuentas
        FROM n GROUP BY cubeta ORDER BY cubeta
        """
    ).df()


def grados(con: duckdb.DuckDBPyConnection, esquema: str) -> dict:
    """Cuantiles de contrapartes distintas de salida y de entrada por cuenta."""
    salida = con.execute(
        f"""
        WITH g AS (SELECT origen, count(DISTINCT destino) AS g FROM {esquema}.aristas GROUP BY 1)
        SELECT median(g), quantile_cont(g, 0.99), max(g) FROM g
        """
    ).fetchone()
    entrada = con.execute(
        f"""
        WITH g AS (SELECT destino, count(DISTINCT origen) AS g FROM {esquema}.aristas GROUP BY 1)
        SELECT median(g), quantile_cont(g, 0.99), max(g) FROM g
        """
    ).fetchone()
    return {
        "salida": {"mediana": salida[0], "p99": salida[1], "maximo": salida[2]},
        "entrada": {"mediana": entrada[0], "p99": entrada[1], "maximo": entrada[2]},
    }


def resumen(con: duckdb.DuckDBPyConnection, esquema: str) -> dict:
    """Resumen completo de la variante, listo para JSON."""
    e = esquema
    dias = por_dia(con, e)
    totales = (
        con.execute(
            f"""
        SELECT count(*) AS transacciones, sum(es_lavado::INT) AS lavado,
               sum(es_autotransferencia::INT) AS autotransferencias,
               (SELECT count(*) FROM {e}.cuentas) AS cuentas,
               (SELECT count(*) FROM {e}.aristas) AS aristas
        FROM {e}.transacciones
        """
        )
        .df()
        .iloc[0]
        .to_dict()
    )
    por_periodo = _df(
        con,
        f"""
        SELECT t.periodo, count(*) AS transacciones, sum(t.es_lavado::INT) AS lavado,
               sum(coalesce(l.ignorada, false)::INT) AS lavado_ignorado_puente,
               sum((l.tipo = 'SIN_PATRON')::INT) AS lavado_sin_patron
        FROM {e}.transacciones t LEFT JOIN {e}.etiquetas l USING (tx_id)
        GROUP BY t.periodo ORDER BY min(t.ts)
        """,
    )
    # Artefactos: día 1 (arranque) y cola posterior al día 10.
    dia1 = dias[dias.periodo == "arranque"].iloc[0]
    resto = dias[dias.periodo.isin(particion.PERIODOS_MEDIDOS)]
    cola = dias[dias.periodo == "cola"]
    intentos_cola = con.execute(
        f"""
        SELECT count(*) FILTER (WHERE list_contains(periodos, 'cola')),
               count(*) FILTER (WHERE periodos = ['cola'])
        FROM {e}.intentos
        """
    ).fetchone()
    artefactos = {
        "dia1": {
            "transacciones": int(dia1.transacciones),
            "frac_transacciones": float(dia1.transacciones / totales["transacciones"]),
            "tasa_lavado": float(dia1.tasa_lavado),
            "autotransferencias": int(dia1.autotransferencias),
            "frac_autotransferencias": float(dia1.autotransferencias / dia1.transacciones),
            "media_diaria_dias_2_10": float(resto.transacciones.mean()),
            "tasa_lavado_dias_2_10": float(resto.lavado.sum() / resto.transacciones.sum()),
            "frac_autotransferencias_dias_2_10": float(
                resto.autotransferencias.sum() / resto.transacciones.sum()
            ),
        },
        "cola": {
            "dias": len(cola),
            "transacciones": int(cola.transacciones.sum()),
            "lavado": int(cola.lavado.sum()),
            "tasa_lavado": float(cola.lavado.sum() / max(cola.transacciones.sum(), 1)),
            "intentos_que_tocan_cola": int(intentos_cola[0]),
            "intentos_solo_en_cola": int(intentos_cola[1]),
        },
    }
    formato_desarrollo = _df(
        con,
        f"""
        SELECT formato, count(*) AS transacciones, sum(es_lavado::INT) AS lavado,
               avg(es_lavado::INT) AS tasa_lavado
        FROM {e}.transacciones WHERE periodo = 'desarrollo' GROUP BY formato ORDER BY 2 DESC
        """,
    )
    patrones_desarrollo = _df(
        con,
        f"""
        SELECT tipo, count(*) AS intentos, median(n_tx) AS mediana_tx,
               median(epoch(fin - inicio) / 3600) AS mediana_horas,
               quantile_cont(epoch(fin - inicio) / 3600, 0.9) AS p90_horas
        FROM {e}.intentos
        WHERE list_contains(periodos, 'desarrollo') AND NOT es_puente
        GROUP BY tipo ORDER BY tipo
        """,
    )
    intentos = particion.conteo_intentos(con, e).to_dict(orient="records")
    return {
        "variante": e,
        "totales": totales,
        "por_periodo": por_periodo,
        "por_dia": dias.assign(dia=dias.dia.astype(str)).to_dict(orient="records"),
        "artefactos": artefactos,
        "historias": historias_por_cuenta(con, e),
        "grados": grados(con, e),
        "intentos_por_periodo": intentos,
        "formato_desarrollo": formato_desarrollo,
        "patrones_desarrollo": patrones_desarrollo,
    }

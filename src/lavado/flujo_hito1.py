"""Flujo del hito 1: ingesta, exploración, desarrollo (búsqueda en HI) y evaluación en prueba.

- ``preparar``: carga cada variante en DuckDB, crea etiquetas y aristas.
- ``explorar``: resumen y gráficos de exploración.
- ``desarrollar``: elige la configuración del detector en **HI desarrollo** y el umbral de F1
  del detector y de la regla simple en el desarrollo de cada variante. Escribe
  ``parametros.json`` (lo que se congela) y ``desarrollo.json`` (cifras optimistas).
- ``evaluar``: con los parámetros congelados, mide una sola vez en prueba (HI y LI).
"""

import itertools
import json
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from lavado import evaluacion as ev
from lavado import exploracion, grafo, ingesta, particion, tableros
from lavado.detectores import abanicos as ab
from lavado.rutas import DATA_RAW

VENTANAS: tuple[int, ...] = (24, 48, 72, 96)
MAX_VARIABLES = 3
TAMANOS: tuple[str, ...] = ("log2", "ninguno")
VARIANTE_DESARROLLO = "hi"
METODOS = {"detector": "Abanicos por forma", "regla": "Regla simple"}


def _a_json(objeto: object) -> object:
    """Convierte tipos de numpy, pandas y fechas para ``json.dump``."""
    if isinstance(objeto, dict):
        return {str(k): _a_json(v) for k, v in objeto.items()}
    if isinstance(objeto, list | tuple):
        return [_a_json(v) for v in objeto]
    if isinstance(objeto, np.integer):
        return int(objeto)
    if isinstance(objeto, np.floating | float):
        return None if np.isnan(objeto) else float(objeto)
    if isinstance(objeto, np.bool_):
        return bool(objeto)
    if isinstance(objeto, datetime | pd.Timestamp):
        return objeto.isoformat()
    return objeto


def escribir_json(datos: dict, ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(_a_json(datos), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return ruta


def preparar(
    con: duckdb.DuckDBPyConnection,
    variantes: tuple[str, ...] = ingesta.VARIANTES,
    dir_raw: Path = DATA_RAW,
    forzar: bool = False,
) -> dict[str, dict]:
    """Carga las variantes que falten (o todas con ``forzar``) y crea etiquetas y aristas."""
    conteos = {}
    for v in variantes:
        existe = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = 'aristas'",
            [v],
        ).fetchone()[0]
        if forzar or not existe:
            conteos[v] = ingesta.cargar_variante(con, v, dir_raw)
            particion.crear_etiquetas(con, v)
            conteos[v]["aristas"] = grafo.crear_aristas(con, v)
    return conteos


def explorar(con: duckdb.DuckDBPyConnection, variantes: tuple[str, ...], salida: Path) -> dict:
    """Resumen de exploración por variante y gráficos de días e historias."""
    resumenes = {v: exploracion.resumen(con, v) for v in variantes}
    escribir_json(resumenes, salida / "exploracion.json")
    dias = pd.concat(
        [exploracion.por_dia(con, v).assign(variante=v) for v in variantes], ignore_index=True
    )
    dias["dia"] = dias.dia.astype(str)
    tableros.guardar(tableros.por_dia(dias, "AMLworld Small por día"), salida, "por_dia")
    hist = pd.concat(
        [exploracion.histograma_historias(con, v).assign(variante=v) for v in variantes],
        ignore_index=True,
    )
    tableros.guardar(tableros.historias(hist), salida, "historias")
    return resumenes


def configuraciones(
    ventanas: tuple[int, ...] = VENTANAS, max_variables: int = MAX_VARIABLES
) -> list[ab.ConfigAbanicos]:
    """Rejilla de configuraciones, en orden determinista."""
    salida = []
    for w in ventanas:
        for por_formato in (False, True):
            for k in range(max_variables + 1):
                for vs in itertools.combinations(ab.VARIABLES_FORMA, k):
                    for tam in TAMANOS:
                        salida.append(ab.ConfigAbanicos(w, 3, por_formato, vs, tam))
    return salida


def _clave_seleccion(fila: dict) -> tuple:
    """Mayor F1; en empate (a 3 decimales), menos variables, ventana más corta, sin canal."""
    return (
        -round(fila["f1"], 3),
        len(fila["variables"]),
        fila["ventana_horas"],
        fila["por_formato"],
        fila["tamano"] != "log2",
    )


def buscar_configuracion(
    con: duckdb.DuckDBPyConnection,
    esquema: str = VARIANTE_DESARROLLO,
    configs: list[ab.ConfigAbanicos] | None = None,
) -> pd.DataFrame:
    """Evalúa la rejilla en el desarrollo de ``esquema`` (F1 ilícita por transacción).

    Devuelve una fila por configuración, ordenada por la regla de selección.
    """
    configs = configs if configs is not None else configuraciones()
    universo = ev.cargar_universo(con, esquema, "desarrollo")
    ok = ~universo.transacciones.ignorada.to_numpy()
    y = universo.transacciones.y.to_numpy()[ok]
    filas = []
    grupos = itertools.groupby(configs, key=lambda c: (c.ventana_horas, c.por_formato))
    for (w, por_formato), grupo in grupos:
        cand = ab.calcular_candidatas(
            con, esquema, particion.HASTA["desarrollo"], "desarrollo", w, 3, por_formato
        )
        for cfg in grupo:
            puntaje = ab.puntuar_transacciones(cand, ab.puntuar_estructuras(cand.estructuras, cfg))
            filas.append(cfg.como_dict() | ev.mejor_umbral_f1(puntaje[ok], y))
    filas.sort(key=_clave_seleccion)
    return pd.DataFrame(filas)


def puntuar(
    con: duckdb.DuckDBPyConnection, esquema: str, periodo: str, config: ab.ConfigAbanicos
) -> tuple[ab.Candidatas, np.ndarray, np.ndarray]:
    """Candidatas, puntaje de estructuras y de transferencias de ``periodo``."""
    cand = ab.calcular_candidatas(
        con,
        esquema,
        particion.HASTA[periodo],
        periodo,
        config.ventana_horas,
        config.min_contrapartes,
        config.por_formato,
    )
    p_estr = ab.puntuar_estructuras(cand.estructuras, config)
    return cand, p_estr, ab.puntuar_transacciones(cand, p_estr)


def medir(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    periodo: str,
    config: ab.ConfigAbanicos,
    umbral: float,
    universo: ev.Universo | None = None,
) -> dict:
    """Todas las métricas de un método en un período, con el umbral dado."""
    universo = universo or ev.cargar_universo(con, esquema, periodo)
    cand, p_estr, p_tx = puntuar(con, esquema, periodo, config)
    tx = universo.transacciones
    if not np.array_equal(cand.mapa.tx_id.to_numpy(), tx.tx_id.to_numpy()):
        raise RuntimeError("El mapa del detector no coincide con el universo de evaluación")
    n_cuentas = int(con.execute(f"SELECT count(*) FROM {esquema}.cuentas").fetchone()[0])
    p_cta_todas = ab.puntuar_cuentas(tx.origen.to_numpy(), tx.destino.to_numpy(), p_tx, n_cuentas)
    m = ev.metricas(
        universo, p_tx, p_cta_todas, umbral, direccion=ab.direccion_dominante(cand, p_estr)
    )
    return {
        "periodo": periodo,
        "config": config.como_dict(),
        "universo": m.pop("universo"),
        "estructuras_candidatas": len(cand.estructuras),
        "estructuras_marcadas": int((p_estr >= umbral).sum()),
        **m,
    }


def _config(d: dict) -> ab.ConfigAbanicos:
    return ab.ConfigAbanicos(
        ventana_horas=d["ventana_horas"],
        min_contrapartes=d["min_contrapartes"],
        por_formato=d["por_formato"],
        variables=tuple(d["variables"]),
        tamano=d["tamano"],
        direccion=d.get("direccion", "ambas"),
    )


def desarrollar(
    con: duckdb.DuckDBPyConnection,
    variantes: tuple[str, ...],
    salida: Path,
    configs: list[ab.ConfigAbanicos] | None = None,
) -> dict:
    """Elige configuración (HI desarrollo) y umbrales (desarrollo de cada variante)."""
    rejilla = buscar_configuracion(con, VARIANTE_DESARROLLO, configs)
    elegida = _config(rejilla.iloc[0].to_dict())
    parametros: dict = {
        "criterio": "máximo F1 ilícita por transacción en HI desarrollo (días 2 a 6); "
        "empates a 3 decimales: menos variables, ventana más corta, sin canal, log2",
        "configuraciones_evaluadas": len(rejilla),
        "detector": elegida.como_dict(),
        "regla": ab.REGLA_SIMPLE.como_dict(),
        "umbrales": {},
        "particion": {
            "arranque": f"{particion.INICIO:%Y-%m-%d} a {particion.INICIO_DESARROLLO:%Y-%m-%d}",
            "desarrollo": f"{particion.INICIO_DESARROLLO:%Y-%m-%d} a "
            f"{particion.INICIO_PRUEBA:%Y-%m-%d}",
            "prueba": f"{particion.INICIO_PRUEBA:%Y-%m-%d} a {particion.FIN_VENTANA:%Y-%m-%d}",
            "fin_exclusivo": True,
        },
    }
    metricas_dev: dict = {}
    for v in variantes:
        universo = ev.cargar_universo(con, v, "desarrollo")
        ok = ~universo.transacciones.ignorada.to_numpy()
        y = universo.transacciones.y.to_numpy()[ok]
        parametros["umbrales"][v] = {}
        metricas_dev[v] = {}
        for nombre, cfg in (("detector", elegida), ("regla", ab.REGLA_SIMPLE)):
            *_, p_tx = puntuar(con, v, "desarrollo", cfg)
            mejor = ev.mejor_umbral_f1(p_tx[ok], y)
            parametros["umbrales"][v][nombre] = mejor["umbral"]
            metricas_dev[v][nombre] = medir(con, v, "desarrollo", cfg, mejor["umbral"], universo)
    escribir_json(parametros, salida / "parametros.json")
    escribir_json(
        {
            "advertencia": "cifras de desarrollo: optimistas, se usaron para elegir",
            "rejilla_top": rejilla.head(25).to_dict(orient="records"),
            "metricas": metricas_dev,
        },
        salida / "desarrollo.json",
    )
    return parametros


def evaluar(
    con: duckdb.DuckDBPyConnection, parametros: dict, variantes: tuple[str, ...], salida: Path
) -> dict:
    """Mide en prueba con los parámetros congelados y escribe métricas, gráficos y estructuras."""
    detector, regla = _config(parametros["detector"]), _config(parametros["regla"])
    metricas: dict = {"parametros": parametros, "variantes": {}}
    for v in variantes:
        universo = ev.cargar_universo(con, v, "prueba")
        umbrales = parametros["umbrales"][v]
        res = {
            "detector": medir(con, v, "prueba", detector, umbrales["detector"], universo),
            "regla": medir(con, v, "prueba", regla, umbrales["regla"], universo),
        }
        if v != VARIANTE_DESARROLLO:
            # Sensibilidad: umbrales de HI trasladados sin tocar.
            u_hi = parametros["umbrales"][VARIANTE_DESARROLLO]
            res["sensibilidad_umbral_hi"] = {
                "detector": medir(con, v, "prueba", detector, u_hi["detector"], universo)[
                    "f1_transaccion"
                ],
                "regla": medir(con, v, "prueba", regla, u_hi["regla"], universo)["f1_transaccion"],
            }
        metricas["variantes"][v] = res
        guardar_estructuras(
            con,
            v,
            {
                "abanicos": (detector, umbrales["detector"]),
                "regla_simple": (regla, umbrales["regla"]),
            },
        )
    escribir_json(metricas, salida / "metricas.json")
    graficar_resultados(metricas, salida)
    return metricas


def guardar_estructuras(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    detectores: dict[str, tuple[ab.ConfigAbanicos, float]],
) -> int:
    """Escribe ``esquema.estructuras`` con las estructuras marcadas de cada detector, sobre
    todos los datos observables. La lee ``consultas.patrones_detectados``."""
    partes = []
    for nombre, (cfg, umbral) in detectores.items():
        cand, p_estr, _ = puntuar(con, esquema, "prueba", cfg)  # ve hasta el fin de la ventana
        e = cand.estructuras.assign(detector=nombre, puntaje=p_estr)
        partes.append(e[e.puntaje >= umbral].drop(columns=["idx", "desfase", "b"]))
    tabla = pd.concat(partes, ignore_index=True)
    con.register("estructuras_df", tabla)
    con.execute(
        f"CREATE OR REPLACE TABLE {esquema}.estructuras AS SELECT * FROM estructuras_df "
        "ORDER BY detector, centro, inicio_ventana"
    )
    con.unregister("estructuras_df")
    return len(tabla)


def graficar_resultados(metricas: dict, salida: Path) -> None:
    filas_k, filas_r = [], []
    for v, res in metricas["variantes"].items():
        for nombre in ("detector", "regla"):
            m = res[nombre]
            n_pos = m["universo"]["cuentas_ilicitas"]
            for i, pk in enumerate(m["precision_k"]):
                etiqueta = f"k = {pk['k']}" if i < len(ev.KS) else "k = n.º de ilícitas"
                filas_k.append(
                    {"variante": v.upper(), "metodo": METODOS[nombre], "k_etiqueta": etiqueta}
                    | pk
                    | {"n_ilicitas": n_pos}
                )
            for r in m["recall_tipo"]:
                tipo = "SIN PATRÓN (por tx)" if r["tipo"] == "SIN_PATRON" else r["tipo"]
                filas_r.append(
                    {"variante": v.upper(), "metodo": METODOS[nombre]} | r | {"tipo": tipo}
                )
    tableros.guardar(tableros.precision_k(pd.DataFrame(filas_k)), salida, "precision_k")
    tableros.guardar(tableros.recall_tipo(pd.DataFrame(filas_r)), salida, "recall_tipo")

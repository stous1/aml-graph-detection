"""Datos de la página interactiva (``docs/demo.html``), sobre el período de prueba.

Todo sale de modelos y parámetros congelados; nada se elige mirando estos resultados:

- **Curvas de precisión en el top-k** de cuentas (regla simple, detector de forma del hito 2 y
  modelo final del hito 4), para que la página diga qué precisión tendría un equipo que revisa
  k alertas. En k = 100 coinciden con las métricas publicadas (lo verifica ``tests/test_demo``).
- **¿Forma o tamaño?**: dos casos elegidos con una regla fija. El abanico de lavado con mayor
  puntaje de forma entre los de 5 a 15 contrapartes, y la cuenta legítima con más contrapartes
  en 24 horas (la primera de la regla simple). Para cada uno: su red, sus variables de forma y
  su puesto en el ranking de cada método.
- **Explorador de alertas**: las primeras alertas acertadas, las falsas alarmas mejor puntuadas
  y las cuentas con lavado no detectadas de mayor actividad. Vecindario y línea de tiempo con
  ``lavado.consultas`` (las funciones pensadas para el agente investigador), variables
  estructurales con su percentil entre todas las cuentas de la ventana.

El puntaje de forma se reimplementa en ``docs/demo/motor.js``; ``puntaje_forma`` es la versión
de referencia (la misma de ``detectores.abanicos.puntuar_estructuras``).
"""

import json
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from lavado import consultas, particion, variables_cuenta
from lavado import evaluacion as ev
from lavado import flujo_hito2 as f2
from lavado import flujo_hito5 as f5
from lavado.detectores import abanicos as ab
from lavado.flujo_hito1 import escribir_json
from lavado.patrones import SIN_PATRON
from lavado.rutas import DOCS_RESULTADOS_HITO2

DESDE_VENTANA = datetime(2022, 9, 6)  # ventana de 5 días del modelo final en prueba
PASO_HORAS = 6
MAX_VECINOS = 40
MAX_DIBUJO = 60
NOMBRES_VARIABLES = {
    "log_n_in": "transferencias recibidas (log)",
    "log_n_out": "transferencias enviadas (log)",
    "log_grado_in": "contrapartes de entrada (log)",
    "log_grado_out": "contrapartes de salida (log)",
    "unicidad_in": "unicidad de entrada",
    "unicidad_out": "unicidad de salida",
    "frac_paso": "fracción de dinero de paso",
    "velocidad_horas": "horas entre recibir y reenviar",
    "balance": "balance entre lo que entra y sale",
    "frac_nuevas": "fracción de contrapartes nuevas",
    "cv_montos": "dispersión de montos (CV)",
    "log_monto_medio": "monto medio (log)",
}


def puntaje_forma(
    variables: dict[str, float], usadas: list[str], tamano: str, n_contrapartes: int
) -> float:
    """Puntaje de forma de una estructura (igual que ``abanicos.puntuar_estructuras``)."""
    base = {
        "log2": float(np.log2(n_contrapartes)),
        "lineal": float(n_contrapartes),
        "ninguno": 1.0,
    }[tamano]
    for v in usadas:
        base *= max(float(variables[v]), ab.PISO)
    return base if n_contrapartes >= 3 else 0.0


def rangos(puntaje: np.ndarray, ids: np.ndarray) -> dict[int, int]:
    """Puesto de cada cuenta (1 = mejor; empates comparten el mejor puesto)."""
    orden = np.sort(puntaje)[::-1]
    puesto = np.searchsorted(-orden, -puntaje, side="left") + 1
    return {int(c): int(r) for c, r in zip(ids, puesto, strict=True)}


def curva_precision(puntaje: np.ndarray, y: np.ndarray, ids: np.ndarray) -> list[dict]:
    """Precisión en el top-k para una rejilla de k (con el mismo desempate que la evaluación)."""
    orden = ev.orden_descendente(puntaje, ids)
    aciertos = np.cumsum(np.asarray(y, dtype=bool)[orden])
    n = len(orden)
    rejilla = sorted(
        {k for k in np.unique(np.geomspace(10, min(n, 20_000), 60).astype(int))} | {100, 500, 1000}
    )
    return [{"k": int(k), "precision": float(aciertos[k - 1] / k)} for k in rejilla if k <= n]


def puntajes_prueba(con: duckdb.DuckDBPyConnection, esquema: str, cache: dict) -> dict:
    """Puntajes por cuenta en prueba de la regla, el detector de forma y el modelo final."""
    p2 = json.loads((DOCS_RESULTADOS_HITO2 / "parametros.json").read_text(encoding="utf-8"))
    cfg_forma = f2._config_desde(
        "abanicos_salida_forma", p2["detectores"]["abanicos_salida_forma"]["config"]
    )
    regla = f2.puntuar_abanicos(con, esquema, "prueba", ab.REGLA_SIMPLE, cache)
    forma = f2.puntuar_abanicos(con, esquema, "prueba", cfg_forma, cache)
    universo, _, p_final, _, marcada_cta, info = f5.puntajes_modelo_final(con, esquema)
    return {
        "universo": universo,
        "regla": regla.cuenta,
        "forma": forma.cuenta,
        "final": p_final,
        "marcada_final": marcada_cta,
        "info": info,
        "cfg_forma": cfg_forma,
    }


def _red(con, esquema, centro, direccion, desde, hasta, ilicitas_tx) -> dict:
    """Transferencias de una estructura (centro, dirección, ventana) para dibujarla."""
    col_c, col_o = ("origen", "destino") if direccion == "salida" else ("destino", "origen")
    df = con.execute(
        f"""
        SELECT a.tx_id, a.ts, a.{col_o} AS contraparte, a.monto_usd, t.moneda_pagada
        FROM {esquema}.aristas a JOIN {esquema}.transacciones t USING (tx_id)
        WHERE a.{col_c} = ? AND a.ts >= ? AND a.ts < ?
        ORDER BY a.ts, a.tx_id
        """,
        [centro, desde, hasta],
    ).df()
    por = (
        df.assign(lavado=df.tx_id.isin(ilicitas_tx))
        .groupby("contraparte")
        .agg(n=("tx_id", "size"), usd=("monto_usd", "sum"), lavado=("lavado", "any"))
        .reset_index()
        .sort_values(["usd", "contraparte"], ascending=[False, True])
    )
    return {
        "direccion": direccion,
        "desde": str(desde),
        "hasta": str(hasta),
        "transferencias": len(df),
        "contrapartes": len(por),
        "usd_total": round(float(df.monto_usd.sum()), 2),
        "dibujo": [
            {"n": int(r.n), "usd": round(float(r.usd), 2), "lavado": bool(r.lavado)}
            for r in por.head(MAX_DIBUJO).itertuples()
        ],
        # solo para explicar el artefacto del hito 1: los modelos no usan la moneda
        "monedas_pagadas": df.moneda_pagada.value_counts().to_dict(),
    }


def forma_tamano(con: duckdb.DuckDBPyConnection, esquema: str, puntajes: dict, cache: dict) -> dict:
    universo = puntajes["universo"]
    tx = universo.transacciones
    ilicitas = set(universo.cuentas[universo.cuentas.y].cuenta_id.tolist())
    ilicitas_tx = set(tx[tx.y].tx_id.tolist())
    cfg = puntajes["cfg_forma"]
    cand = cache[("abanicos", esquema, "prueba", cfg.ventana_horas, cfg.por_formato)]
    e = cand.estructuras.assign(puntaje=ab.puntuar_estructuras(cand.estructuras, cfg))
    # solo ventanas que tocan el período de prueba
    e = e[e.fin_ventana > particion.INICIO_PRUEBA]
    lav = e[e.centro.isin(ilicitas) & (e.direccion == "salida") & e.n_contrapartes.between(5, 15)]
    alerta = lav.sort_values(["puntaje", "centro"], ascending=[False, True]).iloc[0]
    cand_regla = cache[("abanicos", esquema, "prueba", 24, False)]
    er = cand_regla.estructuras
    er = er[er.fin_ventana > particion.INICIO_PRUEBA]
    legit = er[~er.centro.isin(ilicitas)]
    comercio = legit.sort_values(["n_contrapartes", "centro"], ascending=[False, True]).iloc[0]
    # variables de forma del comercio en las ventanas de 48 h del detector, misma dirección
    ec = e[(e.centro == comercio.centro) & (e.direccion == comercio.direccion)]
    comercio_forma = ec.sort_values(["n_contrapartes", "b"], ascending=[False, True]).iloc[0]

    cuentas = universo.cuentas[~universo.cuentas.ignorada]
    ids = cuentas.cuenta_id.to_numpy()
    # Regla y forma se comparan como centro (el tamaño o la forma de la propia cuenta); el
    # puntaje por cuenta de la evaluación toma el máximo de sus transferencias y una cuenta
    # que le paga a un concentrador gigante heredaría su tamaño. El modelo final, por cuenta.
    como_centro = {
        "regla": er.groupby("centro").n_contrapartes.max(),
        "forma": e[e.direccion == cfg.direccion].groupby("centro").puntaje.max(),
    }
    puestos = {
        m: rangos(como_centro[m].reindex(ids).fillna(0.0).to_numpy(), ids) for m in como_centro
    }
    puestos["final"] = rangos(puntajes["final"][ids], ids)

    def caso(fila, fila_forma, etiqueta: str) -> dict:
        c = int(fila.centro)
        return {
            "etiqueta": etiqueta,
            "cuenta": c,
            "lavado": c in ilicitas,
            "contrapartes_24h": int(er[er.centro == c].n_contrapartes.max()),
            "estructura": {
                "direccion": fila_forma.direccion,
                "n_contrapartes": int(fila_forma.n_contrapartes),
                "variables": {v: round(float(fila_forma[v]), 6) for v in ab.VARIABLES_FORMA},
            },
            "puesto": {m: puestos[m].get(c) for m in puestos},
            "red": _red(
                con, esquema, c, fila.direccion, fila.inicio_ventana, fila.fin_ventana, ilicitas_tx
            ),
        }

    return {
        "variante": esquema.upper(),
        "cuentas_evaluadas": len(ids),
        "config_forma": cfg.como_dict(),
        "piso": ab.PISO,
        "alerta": caso(alerta, alerta, "abanico de lavado"),
        "comercio": caso(comercio, comercio_forma, "concentrador legítimo"),
    }


def _alerta(
    con, esquema, c, categoria, puesto, puntaje, variables, percentiles, etiquetas_tx, tipos
) -> dict:
    hasta = particion.FIN_VENTANA
    tx = consultas.transacciones_cuenta(con, esquema, c, DESDE_VENTANA, hasta)
    tx = tx.assign(lavado=tx.tx_id.isin(etiquetas_tx))
    por = (
        tx.groupby(["contraparte", "direccion"])
        .agg(n=("tx_id", "size"), usd=("monto_usd", "sum"), lavado=("lavado", "any"))
        .reset_index()
        .sort_values(["lavado", "usd", "contraparte"], ascending=[False, False, True])
    )
    flujo = consultas.flujo_temporal(con, esquema, c, DESDE_VENTANA, hasta, PASO_HORAS)
    return {
        "cuenta": c,
        "categoria": categoria,
        "puesto": puesto,
        "puntaje": round(float(puntaje), 6),
        "patrones": sorted(tipos.get(c, [])),
        "transferencias": len(tx),
        "contrapartes": int(tx.contraparte.nunique()),
        "vecinos": [
            {
                "contraparte": int(r.contraparte),
                "direccion": r.direccion,
                "n": int(r.n),
                "usd": round(float(r.usd), 2),
                "lavado": bool(r.lavado),
            }
            for r in por.head(MAX_VECINOS).itertuples()
        ],
        "vecinos_omitidos": max(len(por) - MAX_VECINOS, 0),
        "flujo": [
            {
                "inicio": str(r.inicio),
                "entra": round(float(r.usd_entrada), 2),
                "sale": round(float(r.usd_salida), 2),
                "n_entra": int(r.n_entrada),
                "n_sale": int(r.n_salida),
            }
            for r in flujo.itertuples()
        ],
        "variables": [
            {
                "nombre": v,
                "texto": NOMBRES_VARIABLES[v],
                "valor": round(float(variables[v]), 4),
                "percentil": round(float(percentiles[v]), 4),
            }
            for v in variables_cuenta.ESTRUCTURALES
        ],
    }


def explorador(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    puntajes: dict,
    n_aciertos: int = 15,
    n_falsas: int = 8,
    n_no_detectadas: int = 8,
) -> dict:
    universo = puntajes["universo"]
    tx = universo.transacciones
    cuentas = universo.cuentas[~universo.cuentas.ignorada]
    ids = cuentas.cuenta_id.to_numpy()
    p = puntajes["final"]
    marcada = puntajes["marcada_final"]
    puestos = rangos(p[ids], ids)
    y = dict(zip(cuentas.cuenta_id, cuentas.y, strict=True))
    orden = ids[ev.orden_descendente(p[ids], ids)]
    aciertos = [c for c in orden if y[c] and marcada[c]][:n_aciertos]
    falsas = [c for c in orden if not y[c] and marcada[c]][:n_falsas]
    lav = tx[tx.y & ~tx.ignorada]
    actividad = pd.concat([lav.origen, lav.destino]).value_counts()
    no_det = [int(c) for c in actividad.index if not marcada[c]][:n_no_detectadas]
    tipos: dict[int, set[str]] = {}
    for o, d, t in zip(lav.origen, lav.destino, lav.tipo, strict=True):
        nombre = "sin patrón" if t == SIN_PATRON else t
        tipos.setdefault(int(o), set()).add(nombre)
        tipos.setdefault(int(d), set()).add(nombre)
    vars_ = variables_cuenta.calcular(con, esquema, DESDE_VENTANA, particion.FIN_VENTANA)
    vars_ = vars_.set_index("cuenta_id")[list(variables_cuenta.ESTRUCTURALES)]
    pct = vars_.rank(pct=True, method="average")
    etiquetas_tx = set(tx[tx.y].tx_id.tolist())
    filas = []
    for categoria, lista in (
        ("acierto", aciertos),
        ("falsa_alarma", falsas),
        ("no_detectado", no_det),
    ):
        for c in lista:
            filas.append(
                _alerta(
                    con,
                    esquema,
                    int(c),
                    categoria,
                    puestos[int(c)],
                    p[c],
                    vars_.loc[c],
                    pct.loc[c],
                    etiquetas_tx,
                    tipos,
                )
            )
    return {
        "variante": esquema.upper(),
        "modelo": puntajes["info"]["modelo"],
        "fraccion_alertas_cuentas": puntajes["info"]["fracciones"]["cuenta"],
        "ventana": [str(DESDE_VENTANA), str(particion.FIN_VENTANA)],
        "paso_horas": PASO_HORAS,
        "cuentas": filas,
    }


def generar(con: duckdb.DuckDBPyConnection, variantes: tuple[str, ...], salida: Path) -> dict:
    """Escribe ``curvas.json``, ``forma_tamano.json`` y ``alertas_{v}.json``."""
    curvas: dict = {}
    for v in variantes:
        cache: dict = {}
        puntajes = puntajes_prueba(con, v, cache)
        universo = puntajes["universo"]
        cuentas = universo.cuentas[~universo.cuentas.ignorada]
        ids, y = cuentas.cuenta_id.to_numpy(), cuentas.y.to_numpy()
        curvas[v] = {
            "cuentas": len(ids),
            "ilicitas": int(y.sum()),
            "metodos": {
                m: curva_precision(puntajes[m][ids], y, ids) for m in ("regla", "forma", "final")
            },
        }
        if v == "hi":
            escribir_json(forma_tamano(con, v, puntajes, cache), salida / "forma_tamano.json")
        escribir_json(explorador(con, v, puntajes), salida / f"alertas_{v}.json")
    escribir_json(curvas, salida / "curvas.json")
    return curvas


def precision_interpolada(curva: list[dict], k: float) -> float:
    """Precisión en el top-k interpolada entre los puntos de la curva (igual que motor.js)."""
    ks = [c["k"] for c in curva]
    ps = [c["precision"] for c in curva]
    return float(np.interp(k, ks, ps))

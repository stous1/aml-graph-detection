"""Flujo del hito 2: más detectores por forma, variables por cuenta, combinación y ablación.

- ``desarrollar``: para cada detector elige su configuración en **HI desarrollo** (máximo F1
  ilícita por transacción; en empate, la primera de la rejilla, que va de simple a compleja),
  fija umbrales por variante en desarrollo, elige el esquema de combinación y diagnostica LI.
  Escribe ``parametros.json`` (se congela) y ``desarrollo.json`` (cifras optimistas).
- ``evaluar``: con los parámetros congelados, mide una sola vez en prueba (HI y LI).

Cada detector se declara con o sin **señales sospechosas de ser artefacto** del generador
(moneda y formato de pago). Las señales estructurales son tiempo, montos y topología.
"""

import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from lavado import combinacion, particion, tableros
from lavado import evaluacion as ev
from lavado.detectores import abanicos as ab
from lavado.detectores import aislamiento as ai
from lavado.detectores import cadenas as ca
from lavado.detectores import ciclos as ci
from lavado.detectores import comun
from lavado.detectores import dispersion as di
from lavado.flujo_hito1 import _config as config_abanicos
from lavado.flujo_hito1 import escribir_json
from lavado.rutas import DOCS_RESULTADOS_HITO1

VARIANTE_DESARROLLO = "hi"
FORMA_ABANICOS: tuple[str, ...] = (
    "novedad",
    "exclusividad",
    "unicidad",
    "homogeneidad",
    "dispersion",
)
SOSPECHOSAS_ABANICOS: tuple[str, ...] = ("formato", "mezcla_monedas")
REGLA = "regla_simple"


@dataclass
class Detector:
    nombre: str
    descripcion: str
    sospechosas: bool
    configs: list
    puntuar: Callable[..., comun.Puntajes]


def puntuar_abanicos(
    con: duckdb.DuckDBPyConnection, esquema: str, periodo: str, cfg: ab.ConfigAbanicos, cache
) -> comun.Puntajes:
    clave = ("abanicos", esquema, periodo, cfg.ventana_horas, cfg.por_formato)
    if clave not in cache:
        cache[clave] = ab.calcular_candidatas(
            con,
            esquema,
            particion.HASTA[periodo],
            periodo,
            cfg.ventana_horas,
            cfg.min_contrapartes,
            cfg.por_formato,
        )
    cand = cache[clave]
    p_estr = ab.puntuar_estructuras(cand.estructuras, cfg)
    p_tx = ab.puntuar_transacciones(cand, p_estr)
    tx = cand.mapa[["tx_id", "origen", "destino"]]
    cuentas = comun.cuentas_por_maximo(
        tx.origen.to_numpy(), tx.destino.to_numpy(), p_tx, comun.n_cuentas(con, esquema)
    )
    return comun.Puntajes(tx, p_tx, cuentas, ab.direccion_dominante(cand, p_estr))


def _sin_cache(funcion: Callable) -> Callable[..., comun.Puntajes]:
    def puntuar(con, esquema, periodo, cfg, cache):
        del cache
        return funcion(con, esquema, periodo, cfg)

    return puntuar


def _rejilla_abanicos(
    direccion: str, variables: tuple[str, ...], canales: tuple[bool, ...], max_variables: int = 3
) -> list[ab.ConfigAbanicos]:
    salida = []
    for w in (24, 48, 72, 96):
        for por_formato in canales:
            for k in range(1, max_variables + 1):
                for vs in itertools.combinations(variables, k):
                    for tam in ("log2", "ninguno"):
                        salida.append(ab.ConfigAbanicos(w, 3, por_formato, vs, tam, direccion))
    return salida


def detectores(congelado_h1: ab.ConfigAbanicos) -> list[Detector]:
    """Registro de detectores del hito 2, con sus rejillas en orden de simple a complejo."""
    sin_monedas = ab.ConfigAbanicos(
        congelado_h1.ventana_horas,
        congelado_h1.min_contrapartes,
        congelado_h1.por_formato,
        tuple(v for v in congelado_h1.variables if v != "mezcla_monedas"),
        congelado_h1.tamano,
    )
    ciclos = [
        ci.ConfigCiclos(96, tol, dur, 10, minimo, punt)
        for tol in (0.05, 0.2)
        for dur in (96, 144)
        for minimo in (2, 3)
        for punt in ("longitud", "longitud_consistencia")
    ]
    cadenas = [ca.ConfigCadenas(d, tol) for d in (24, 96) for tol in (0.05, 0.2)]
    dispersion = [di.ConfigDispersion(d, tol) for d in (24, 96) for tol in (0.05, 0.2)]
    concentracion = [
        di.ConfigConcentracion(w, 2, p)
        for w in (48, 96)
        for p in ("tamano", "tamano_balance", "tamano_balance_unicidad")
    ]
    return [
        Detector(
            REGLA,
            "contrapartes distintas en 24 h (solo tamaño)",
            False,
            [ab.REGLA_SIMPLE],
            puntuar_abanicos,
        ),
        Detector(
            "abanicos_h1",
            "abanicos del hito 1 congelados (unicidad × mezcla de monedas)",
            True,
            [congelado_h1],
            puntuar_abanicos,
        ),
        # Ablación: sin mezcla de monedas conserva el canal (formato de pago), que también es
        # sospechoso; sin monedas ni canal es la forma pura.
        Detector(
            "abanicos_h1_sin_monedas",
            "ablación: hito 1 congelado sin mezcla de monedas (conserva el canal)",
            True,
            [sin_monedas],
            puntuar_abanicos,
        ),
        Detector(
            "abanicos_h1_forma_pura",
            "ablación: hito 1 sin mezcla de monedas ni canal",
            False,
            [replace(sin_monedas, por_formato=False)],
            puntuar_abanicos,
        ),
        Detector(
            "abanicos_salida_forma",
            "abanicos de salida, forma pura",
            False,
            _rejilla_abanicos("salida", FORMA_ABANICOS, (False,)),
            puntuar_abanicos,
        ),
        Detector(
            "abanicos_entrada_forma",
            "abanicos de entrada, forma pura",
            False,
            _rejilla_abanicos("entrada", FORMA_ABANICOS, (False,)),
            puntuar_abanicos,
        ),
        Detector(
            "abanicos_entrada_con",
            "abanicos de entrada con moneda y formato",
            True,
            _rejilla_abanicos("entrada", FORMA_ABANICOS + SOSPECHOSAS_ABANICOS, (False, True)),
            puntuar_abanicos,
        ),
        Detector(
            "ciclos",
            "ciclos temporales acotados con monto conservado",
            False,
            ciclos,
            _sin_cache(ci.puntuar),
        ),
        Detector(
            "cadenas",
            "cadenas de paso con monto conservado",
            False,
            cadenas,
            _sin_cache(ca.puntuar),
        ),
        Detector(
            "dispersion_concentracion",
            "S → varias intermediarias → T",
            False,
            dispersion,
            _sin_cache(di.puntuar_dispersion),
        ),
        Detector(
            "concentracion_dispersion",
            "junta de varias y reparte a varias",
            False,
            concentracion,
            _sin_cache(di.puntuar_concentracion),
        ),
        Detector(
            "aislamiento_forma",
            "Isolation Forest, variables estructurales",
            False,
            [ai.ConfigAislamiento(False, a) for a in ("min", "max")],
            ai.puntuar,
        ),
        Detector(
            "aislamiento_con",
            "Isolation Forest con monedas y formatos",
            True,
            [ai.ConfigAislamiento(True, a) for a in ("min", "max")],
            ai.puntuar,
        ),
    ]


COMBINADOS: dict[str, tuple[str, ...]] = {
    "combinado_forma": (
        "abanicos_salida_forma",
        "abanicos_entrada_forma",
        "ciclos",
        "cadenas",
        "dispersion_concentracion",
        "concentracion_dispersion",
        "aislamiento_forma",
    ),
    "combinado_con": (
        "abanicos_h1",
        "abanicos_entrada_con",
        "ciclos",
        "cadenas",
        "dispersion_concentracion",
        "concentracion_dispersion",
        "aislamiento_con",
    ),
}


def _config_desde(nombre: str, d: dict):
    if nombre in (REGLA,) or nombre.startswith("abanicos"):
        return config_abanicos(d)
    clases = {
        "ciclos": ci.ConfigCiclos,
        "cadenas": ca.ConfigCadenas,
        "dispersion_concentracion": di.ConfigDispersion,
        "concentracion_dispersion": di.ConfigConcentracion,
        "aislamiento_forma": ai.ConfigAislamiento,
        "aislamiento_con": ai.ConfigAislamiento,
    }
    return clases[nombre](**d)


def _datos(universo: ev.Universo) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    ok = ~universo.transacciones.ignorada.to_numpy()
    cuentas = universo.cuentas[~universo.cuentas.ignorada]
    return ok, universo.transacciones.y.to_numpy(), cuentas


def _verificar(p: comun.Puntajes, universo: ev.Universo) -> None:
    if not np.array_equal(
        p.transacciones.tx_id.to_numpy(), universo.transacciones.tx_id.to_numpy()
    ):
        raise RuntimeError("Puntajes no alineados con el universo de evaluación")


def seleccionar(
    con: duckdb.DuckDBPyConnection, esquema: str, detector: Detector, cache: dict
) -> tuple[object, list[dict]]:
    """Mejor configuración de ``detector`` en el desarrollo de ``esquema`` (F1 por tx)."""
    universo = ev.cargar_universo(con, esquema, "desarrollo")
    ok, y, _ = _datos(universo)
    filas = []
    for i, cfg in enumerate(detector.configs):
        p = detector.puntuar(con, esquema, "desarrollo", cfg, cache)
        _verificar(p, universo)
        filas.append({"orden": i, "config": cfg.como_dict()} | ev.mejor_umbral_f1(p.tx[ok], y[ok]))
    filas.sort(key=lambda f: (-round(f["f1"], 3), f["orden"]))
    return detector.configs[filas[0]["orden"]], filas


def composicion(universo: ev.Universo) -> dict:
    """Lavado evaluable por tipo (transacciones), para comparar variantes."""
    tx = universo.transacciones
    tx = tx[tx.y & ~tx.ignorada]
    n = tx.tipo.value_counts().sort_index()
    return {
        "lavado_evaluable": int(len(tx)),
        "por_tipo": n.to_dict(),
        "frac_sin_patron": float((tx.tipo == "SIN_PATRON").mean()),
    }


def desarrollar(
    con: duckdb.DuckDBPyConnection,
    variantes: tuple[str, ...],
    salida: Path,
    congelado_h1: dict,
    nombres: tuple[str, ...] | None = None,
    diagnostico_li: bool = True,
) -> dict:
    """Selección en HI desarrollo, umbrales y combinación por variante, diagnóstico de LI."""
    lista = [
        d
        for d in detectores(config_abanicos(congelado_h1))
        if nombres is None or d.nombre in nombres
    ]
    cache: dict = {}
    parametros: dict = {
        "criterio": "por detector: máximo F1 ilícita por transacción en HI desarrollo; "
        "empate a 3 decimales: primera configuración de la rejilla (de simple a compleja). "
        "Umbrales de transacción y de cuenta: máximo F1 en el desarrollo de cada variante.",
        "detectores": {},
        "combinados": {},
    }
    rejillas, metricas_dev = {}, {v: {} for v in variantes}
    for det in lista:
        elegida, filas = seleccionar(con, VARIANTE_DESARROLLO, det, cache)
        rejillas[det.nombre] = filas[:10]
        parametros["detectores"][det.nombre] = {
            "descripcion": det.descripcion,
            "sospechosas": det.sospechosas,
            "config": elegida.como_dict(),
            "configuraciones_evaluadas": len(filas),
            "umbrales": {},
        }
    for v in variantes:
        cache.clear()  # las candidatas de abanicos ocupan mucha memoria
        universo = ev.cargar_universo(con, v, "desarrollo")
        ok, y, cuentas = _datos(universo)
        ids = cuentas.cuenta_id.to_numpy()
        pct_tx, pct_cta = {}, {}
        for det in lista:
            info = parametros["detectores"][det.nombre]
            p = det.puntuar(con, v, "desarrollo", _config_desde(det.nombre, info["config"]), cache)
            _verificar(p, universo)
            u_tx = ev.mejor_umbral_f1(p.tx[ok], y[ok])["umbral"]
            u_cta = ev.mejor_umbral_f1(p.cuenta[ids], cuentas.y.to_numpy())["umbral"]
            info["umbrales"][v] = {"transaccion": u_tx, "cuenta": u_cta}
            metricas_dev[v][det.nombre] = ev.metricas(
                universo, p.tx, p.cuenta, u_tx, u_cta, p.direccion
            )
            ref_tx = combinacion.Percentiles.desde(p.tx)
            ref_cta = combinacion.Percentiles.desde(p.cuenta[universo.cuentas.cuenta_id])
            pct_tx[det.nombre], pct_cta[det.nombre] = (
                ref_tx.aplicar(p.tx),
                ref_cta.aplicar(p.cuenta),
            )
        for combo, componentes in COMBINADOS.items():
            if not all(c in pct_tx for c in componentes):
                continue
            info = parametros["combinados"].setdefault(
                combo, {"componentes": list(componentes), "umbrales": {}}
            )
            if v == VARIANTE_DESARROLLO:
                f1s = {
                    e: ev.mejor_umbral_f1(
                        combinacion.combinar([pct_tx[c] for c in componentes], e)[ok], y[ok]
                    )["f1"]
                    for e in combinacion.ESQUEMAS
                }
                info["esquema"] = max(combinacion.ESQUEMAS, key=lambda e: round(f1s[e], 3))
                info["f1_por_esquema_hi_desarrollo"] = f1s
            c_tx = combinacion.combinar([pct_tx[c] for c in componentes], info["esquema"])
            c_cta = combinacion.combinar([pct_cta[c] for c in componentes], info["esquema"])
            u_tx = ev.mejor_umbral_f1(c_tx[ok], y[ok])["umbral"]
            u_cta = ev.mejor_umbral_f1(c_cta[ids], cuentas.y.to_numpy())["umbral"]
            info["umbrales"][v] = {"transaccion": u_tx, "cuenta": u_cta}
            metricas_dev[v][combo] = ev.metricas(universo, c_tx, c_cta, u_tx, u_cta)
        metricas_dev[v]["_composicion"] = composicion(universo)

    diagnostico: dict = {}
    if diagnostico_li and "li" in variantes:
        # ¿Cuánto se pierde por usar la configuración de HI en LI? (solo desarrollo)
        cache.clear()
        for det in lista:
            if len(det.configs) == 1:
                continue
            _, filas_li = seleccionar(con, "li", det, cache)
            hi_cfg = parametros["detectores"][det.nombre]["config"]
            f1_hi_cfg = next(f["f1"] for f in filas_li if f["config"] == hi_cfg)
            diagnostico[det.nombre] = {
                "f1_li_con_config_hi": f1_hi_cfg,
                "f1_li_mejor_config_li": filas_li[0]["f1"],
                "config_li": filas_li[0]["config"],
            }
    escribir_json(parametros, salida / "parametros.json")
    escribir_json(
        {
            "advertencia": "cifras de desarrollo: optimistas, se usaron para elegir",
            "rejillas": rejillas,
            "metricas": metricas_dev,
            "diagnostico_li": diagnostico,
        },
        salida / "desarrollo.json",
    )
    return parametros


def evaluar(
    con: duckdb.DuckDBPyConnection,
    parametros: dict,
    congelado_h1: dict,
    variantes: tuple[str, ...],
    salida: Path,
) -> dict:
    """Mide una vez en prueba. Los percentiles de la combinación se reconstruyen con los
    puntajes de desarrollo (deterministas, sin etiquetas)."""
    lista = [
        d for d in detectores(config_abanicos(congelado_h1)) if d.nombre in parametros["detectores"]
    ]
    metricas: dict = {"parametros": parametros, "variantes": {}}
    for v in variantes:
        cache: dict = {}
        universo_dev = ev.cargar_universo(con, v, "desarrollo")
        universo = ev.cargar_universo(con, v, "prueba")
        res, pct_tx, pct_cta = {}, {}, {}
        for det in lista:
            info = parametros["detectores"][det.nombre]
            cfg = _config_desde(det.nombre, info["config"])
            p_dev = det.puntuar(con, v, "desarrollo", cfg, cache)
            p = det.puntuar(con, v, "prueba", cfg, cache)
            _verificar(p, universo)
            u = info["umbrales"][v]
            res[det.nombre] = ev.metricas(
                universo, p.tx, p.cuenta, u["transaccion"], u["cuenta"], p.direccion
            )
            ref_tx = combinacion.Percentiles.desde(p_dev.tx)
            ref_cta = combinacion.Percentiles.desde(p_dev.cuenta[universo_dev.cuentas.cuenta_id])
            pct_tx[det.nombre], pct_cta[det.nombre] = (
                ref_tx.aplicar(p.tx),
                ref_cta.aplicar(p.cuenta),
            )
        for combo, info in parametros["combinados"].items():
            comp = info["componentes"]
            c_tx = combinacion.combinar([pct_tx[c] for c in comp], info["esquema"])
            c_cta = combinacion.combinar([pct_cta[c] for c in comp], info["esquema"])
            u = info["umbrales"][v]
            res[combo] = ev.metricas(universo, c_tx, c_cta, u["transaccion"], u["cuenta"])
        metricas["variantes"][v] = res
    escribir_json(metricas, salida / "metricas.json")
    graficar(metricas, salida)
    return metricas


ETIQUETAS = {
    REGLA: "Regla simple",
    "abanicos_h1": "Abanicos hito 1 (con monedas)",
    "abanicos_h1_sin_monedas": "Abanicos hito 1 sin monedas",
    "abanicos_h1_forma_pura": "Abanicos hito 1 sin monedas ni canal",
    "abanicos_salida_forma": "Abanicos de salida, forma",
    "abanicos_entrada_forma": "Abanicos de entrada, forma",
    "abanicos_entrada_con": "Abanicos de entrada (con)",
    "ciclos": "Ciclos",
    "cadenas": "Cadenas de paso",
    "dispersion_concentracion": "Dispersión-concentración",
    "concentracion_dispersion": "Concentración-dispersión",
    "aislamiento_forma": "Isolation Forest, forma",
    "aislamiento_con": "Isolation Forest (con)",
    "combinado_forma": "Combinado, forma",
    "combinado_con": "Combinado (con)",
}


def tabla_resumen(metricas: dict) -> pd.DataFrame:
    """Una fila por variante y detector: top-100, F1 por tx y por cuenta."""
    filas = []
    for v, res in metricas["variantes"].items():
        for nombre, m in res.items():
            info = metricas["parametros"]["detectores"].get(nombre, {})
            filas.append(
                {
                    "variante": v.upper(),
                    "detector": nombre,
                    "etiqueta": ETIQUETAS.get(nombre, nombre),
                    "senales": "regla"
                    if nombre == REGLA
                    else (
                        "con sospechosas"
                        if info.get("sospechosas") or nombre == "combinado_con"
                        else "estructurales"
                    ),
                    "precision_100": m["precision_k"][0]["precision"],
                    "p100_inf": m["precision_k"][0]["ic_inf"],
                    "p100_sup": m["precision_k"][0]["ic_sup"],
                    "f1_tx": m["f1_transaccion"]["f1"],
                    "f1_cuenta": m["f1_cuenta"]["f1"],
                }
            )
    return pd.DataFrame(filas)


def graficar(metricas: dict, salida: Path) -> None:
    tabla = tabla_resumen(metricas)
    orden = [ETIQUETAS[n] for n in ETIQUETAS if n in set(tabla.detector)]
    tableros.guardar(
        tableros.detectores(tabla, orden, "precision_100", "precisión en el top-100"),
        salida,
        "detectores_top100",
    )
    tableros.guardar(
        tableros.detectores(tabla, orden, "f1_tx", "F1 ilícita por transacción"),
        salida,
        "detectores_f1",
    )


def congelado_hito1() -> dict:
    """Configuración del detector del hito 1, tal como quedó congelada."""
    datos = json.loads((DOCS_RESULTADOS_HITO1 / "parametros.json").read_text(encoding="utf-8"))
    return datos["detector"]

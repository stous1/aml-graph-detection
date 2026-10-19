"""Flujo del hito 3: CoLES, aporte sobre el combinado estructural y "no te pareces a ti mismo".

- ``desarrollar``: mide la cobertura de las cuentas con historia suficiente, entrena CoLES sin
  etiquetas con el desarrollo de cada variante, elige en HI desarrollo cómo puntuar la rareza
  de la huella, arma el combinado estructural + CoLES y evalúa en desarrollo si "no te pareces
  a ti mismo" es viable con 10 días de datos.
- ``evaluar``: con los modelos y parámetros congelados, mide una sola vez en prueba el aporte
  de CoLES sobre el combinado estructural del hito 2 (congelado).

Todo usa solo señales estructurales y de comportamiento: nada de moneda ni formato de pago.
"""

import json
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from lavado import coles, combinacion, particion, secuencias, tableros
from lavado import evaluacion as ev
from lavado import flujo_hito2 as f2
from lavado.detectores import coles_atipico as ca
from lavado.detectores import comun
from lavado.flujo_hito1 import escribir_json
from lavado.rutas import DOCS_RESULTADOS_HITO2

VARIANTE_DESARROLLO = "hi"
COMBINADO_H2 = "combinado_forma"
COMBINADO_H3 = "combinado_forma_coles"
DETECTOR = "coles_atipico"
UMBRALES_HISTORIA: tuple[int, ...] = (10, 20, 50)
# "No te pareces a ti mismo" se considera viable solo si, en desarrollo, cubre al menos el 10 %
# de las cuentas ilícitas y su AUC entre las cuentas cubiertas es de al menos 0,60. El criterio
# se fija antes de mirar el resultado.
VIABLE_COBERTURA_MIN = 0.10
VIABLE_AUC_MIN = 0.60
NTP_HISTORIA = (datetime(2022, 9, 2), datetime(2022, 9, 5))
NTP_ACTUAL = (datetime(2022, 9, 5), datetime(2022, 9, 7))
NTP_MIN_EVENTOS: tuple[int, ...] = (5, 10)


def parametros_hito2() -> dict:
    return json.loads((DOCS_RESULTADOS_HITO2 / "parametros.json").read_text(encoding="utf-8"))


def configs_coles_atipico() -> list[ca.ConfigColesAtipico]:
    return [
        ca.ConfigColesAtipico(metodo, agregacion, minimo)
        for minimo in (20, 10)
        for metodo in ("iforest", "knn")
        for agregacion in ("max", "min")
    ]


def cobertura(con: duckdb.DuckDBPyConnection, esquema: str) -> dict:
    """Fracción de cuentas y de lavado cubierta por cuentas con historia suficiente."""
    salida = {}
    for periodo in particion.PERIODOS_MEDIDOS:
        desde, hasta = ca.ventana(periodo)
        n = secuencias.conteo_eventos(con, esquema, desde, hasta)
        universo = ev.cargar_universo(con, esquema, periodo)
        tx = universo.transacciones
        lav = tx[tx.y & ~tx.ignorada]
        ilicitas = universo.cuentas[universo.cuentas.y].cuenta_id.to_numpy()
        conteo = np.vectorize(lambda c, n=n: n.get(c, 0), otypes=[np.int64])
        n_o = conteo(lav.origen.to_numpy()) if len(lav) else np.zeros(0)
        n_d = conteo(lav.destino.to_numpy()) if len(lav) else np.zeros(0)
        filas = {}
        for k in UMBRALES_HISTORIA:
            alguna = (n_o >= k) | (n_d >= k)
            filas[k] = {
                "cuentas_activas": float(np.mean(np.array(list(n.values())) >= k)),
                "cuentas_ilicitas": float(np.mean(conteo(ilicitas) >= k)),
                "lavado_alguna_cuenta": float(alguna.mean()),
                "lavado_ambas_cuentas": float(((n_o >= k) & (n_d >= k)).mean()),
                "lavado_alguna_por_tipo": lav.assign(c=alguna).groupby("tipo").c.mean().to_dict(),
            }
        salida[periodo] = {"ventana": [str(desde), str(hasta)], "por_umbral": filas}
    return salida


def entrenar_modelo(
    con: duckdb.DuckDBPyConnection, esquema: str, config: coles.ConfigColes, ruta: Path
) -> dict:
    """Entrena CoLES con la ventana de desarrollo (días 2 a 6) y guarda el modelo."""
    datos = secuencias.construir(
        con,
        esquema,
        particion.DESDE["desarrollo"],
        particion.HASTA["desarrollo"],
        config.min_eventos,
        config.max_eventos,
    )
    codificador, perdidas = coles.entrenar(datos, config)
    coles.guardar(codificador, ruta)
    return {
        "secuencias": len(datos.registros),
        "largo_medio": float(datos.largos.mean()),
        "perdida_por_epoca": perdidas,
    }


def puntajes_detector(
    con, esquema: str, periodo: str, nombre: str, config, cache: dict, h1: dict
) -> comun.Puntajes:
    """Puntajes de un detector del hito 2 (por nombre) o del detector CoLES."""
    if nombre == DETECTOR:
        return ca.puntuar(con, esquema, periodo, config, cache)
    det = next(d for d in f2.detectores(f2.config_abanicos(h1)) if d.nombre == nombre)
    return det.puntuar(con, esquema, periodo, config, cache)


def _percentiles(con, esquema, componentes, configs, cache, h1, periodo, universo_dev):
    """Percentiles (por tx y por cuenta) de cada componente, con referencia en desarrollo."""
    pct_tx, pct_cta = {}, {}
    for nombre in componentes:
        p_dev = puntajes_detector(con, esquema, "desarrollo", nombre, configs[nombre], cache, h1)
        ref_tx = combinacion.Percentiles.desde(p_dev.tx)
        ref_cta = combinacion.Percentiles.desde(p_dev.cuenta[universo_dev.cuentas.cuenta_id])
        p = (
            p_dev
            if periodo == "desarrollo"
            else puntajes_detector(con, esquema, periodo, nombre, configs[nombre], cache, h1)
        )
        pct_tx[nombre], pct_cta[nombre] = ref_tx.aplicar(p.tx), ref_cta.aplicar(p.cuenta)
    return pct_tx, pct_cta


def no_te_pareces(con: duckdb.DuckDBPyConnection, esquema: str, codificador) -> dict:
    """Viabilidad en desarrollo: historia días 2 a 4 contra actual días 5 y 6.

    Para las cuentas con historia suficiente en las dos mitades, la distancia coseno entre los
    dos embeddings mide cuánto cambió su comportamiento. La verdad es si la cuenta tiene lavado
    (no ignorado) en la mitad actual.
    """
    etiquetas = con.execute(
        f"""
        SELECT c FROM (
            SELECT t.origen AS c
            FROM {esquema}.transacciones t JOIN {esquema}.etiquetas l USING (tx_id)
            WHERE t.ts >= ? AND t.ts < ? AND NOT l.ignorada AND NOT t.es_autotransferencia
            UNION SELECT t.destino
            FROM {esquema}.transacciones t JOIN {esquema}.etiquetas l USING (tx_id)
            WHERE t.ts >= ? AND t.ts < ? AND NOT l.ignorada AND NOT t.es_autotransferencia
        )
        """,
        [*NTP_ACTUAL, *NTP_ACTUAL],
    ).fetchall()
    ilicitas = {c for (c,) in etiquetas}
    activas = secuencias.conteo_eventos(con, esquema, *NTP_ACTUAL)
    ilicitas_activas = {c for c in ilicitas if c in activas}
    salida = {"ilicitas_en_ventana_actual": len(ilicitas_activas), "por_minimo": {}}
    for minimo in NTP_MIN_EVENTOS:
        hist = secuencias.construir(con, esquema, *NTP_HISTORIA, minimo)
        act = secuencias.construir(con, esquema, *NTP_ACTUAL, minimo)
        comunes = np.intersect1d(hist.cuentas, act.cuentas)
        fila = {
            "cuentas_cubiertas": int(len(comunes)),
            "frac_activas_cubiertas": len(comunes) / max(len(activas), 1),
        }
        if len(comunes):
            eh = coles.incrustar(codificador, hist)[np.searchsorted(hist.cuentas, comunes)]
            ea = coles.incrustar(codificador, act)[np.searchsorted(act.cuentas, comunes)]
            coseno = (eh * ea).sum(1) / (np.linalg.norm(eh, axis=1) * np.linalg.norm(ea, axis=1))
            distancia = 1 - coseno
            y = np.isin(comunes, list(ilicitas_activas))
            fila |= {
                "ilicitas_cubiertas": int(y.sum()),
                "frac_ilicitas_cubiertas": float(y.sum() / max(len(ilicitas_activas), 1)),
                "tasa_base_cubiertas": float(y.mean()),
                "auc": float(roc_auc_score(y, distancia)) if 0 < y.sum() < len(y) else None,
                "precision_k": ev.precision_en_k(distancia, y, comunes, [50, 100]),
            }
            fila["viable"] = bool(
                fila["frac_ilicitas_cubiertas"] >= VIABLE_COBERTURA_MIN
                and (fila["auc"] or 0) >= VIABLE_AUC_MIN
            )
        else:
            fila["viable"] = False
        salida["por_minimo"][minimo] = fila
    salida["viable"] = any(f["viable"] for f in salida["por_minimo"].values())
    salida["criterio"] = (
        f"cobertura de cuentas ilícitas >= {VIABLE_COBERTURA_MIN:.0%} y AUC "
        f">= {VIABLE_AUC_MIN} entre las cubiertas, fijado antes de medir"
    )
    return salida


def desarrollar(
    con: duckdb.DuckDBPyConnection,
    variantes: tuple[str, ...],
    salida: Path,
    h1: dict,
    params_h2: dict,
    config_coles: coles.ConfigColes | None = None,
    configs_atipico: list[ca.ConfigColesAtipico] | None = None,
) -> dict:
    config_coles = config_coles or coles.ConfigColes()
    cache: dict = {}
    parametros: dict = {
        "coles": config_coles.como_dict(),
        "criterio": "detector CoLES: máximo F1 ilícita por transacción en HI desarrollo, empate "
        "a la primera configuración; umbrales y esquema de combinación en desarrollo",
        "detector": {},
        "combinado": {},
        "modelos": {},
    }
    desarrollo: dict = {
        "advertencia": "cifras de desarrollo: optimistas",
        "cobertura": {},
        "entrenamiento": {},
        "metricas": {},
        "no_te_pareces": {},
    }
    for v in variantes:
        desarrollo["cobertura"][v] = cobertura(con, v)
        ruta = salida / "modelos" / f"coles_{v}.pt"
        desarrollo["entrenamiento"][v] = entrenar_modelo(con, v, config_coles, ruta)
        parametros["modelos"][v] = f"modelos/coles_{v}.pt"
        cache[("coles_modelo", v)] = coles.cargar(ruta, config_coles)

    universo = ev.cargar_universo(con, VARIANTE_DESARROLLO, "desarrollo")
    ok = ~universo.transacciones.ignorada.to_numpy()
    y = universo.transacciones.y.to_numpy()
    configs_atipico = configs_atipico or configs_coles_atipico()
    rejilla = []
    for i, cfg in enumerate(configs_atipico):
        p = ca.puntuar(con, VARIANTE_DESARROLLO, "desarrollo", cfg, cache)
        rejilla.append(
            {"orden": i, "config": cfg.como_dict()} | ev.mejor_umbral_f1(p.tx[ok], y[ok])
        )
    rejilla.sort(key=lambda f: (-round(f["f1"], 3), f["orden"]))
    elegida = configs_atipico[rejilla[0]["orden"]]
    parametros["detector"] = {"config": elegida.como_dict(), "umbrales": {}}
    desarrollo["rejilla"] = rejilla

    componentes_h2 = params_h2["combinados"][COMBINADO_H2]["componentes"]
    configs = {n: f2._config_desde(n, params_h2["detectores"][n]["config"]) for n in componentes_h2}
    configs[DETECTOR] = elegida
    componentes_h3 = [*componentes_h2, DETECTOR]
    parametros["combinado"] = {"componentes": componentes_h3, "umbrales": {}}
    for v in variantes:
        universo = ev.cargar_universo(con, v, "desarrollo")
        ok = ~universo.transacciones.ignorada.to_numpy()
        y = universo.transacciones.y.to_numpy()
        cuentas = universo.cuentas[~universo.cuentas.ignorada]
        ids = cuentas.cuenta_id.to_numpy()
        res = {}
        p = ca.puntuar(con, v, "desarrollo", elegida, cache)
        u_tx = ev.mejor_umbral_f1(p.tx[ok], y[ok])["umbral"]
        u_cta = ev.mejor_umbral_f1(p.cuenta[ids], cuentas.y.to_numpy())["umbral"]
        parametros["detector"]["umbrales"][v] = {"transaccion": u_tx, "cuenta": u_cta}
        res[DETECTOR] = ev.metricas(universo, p.tx, p.cuenta, u_tx, u_cta)
        pct_tx, pct_cta = _percentiles(
            con, v, componentes_h3, configs, cache, h1, "desarrollo", universo
        )
        info2 = params_h2["combinados"][COMBINADO_H2]
        c_tx = combinacion.combinar([pct_tx[c] for c in componentes_h2], info2["esquema"])
        c_cta = combinacion.combinar([pct_cta[c] for c in componentes_h2], info2["esquema"])
        u2 = info2["umbrales"][v]
        res[COMBINADO_H2] = ev.metricas(universo, c_tx, c_cta, u2["transaccion"], u2["cuenta"])
        if v == VARIANTE_DESARROLLO:
            f1s = {
                e: ev.mejor_umbral_f1(
                    combinacion.combinar([pct_tx[c] for c in componentes_h3], e)[ok], y[ok]
                )["f1"]
                for e in combinacion.ESQUEMAS
            }
            parametros["combinado"]["esquema"] = max(
                combinacion.ESQUEMAS, key=lambda e: round(f1s[e], 3)
            )
            parametros["combinado"]["f1_por_esquema_hi_desarrollo"] = f1s
        esquema = parametros["combinado"]["esquema"]
        c_tx = combinacion.combinar([pct_tx[c] for c in componentes_h3], esquema)
        c_cta = combinacion.combinar([pct_cta[c] for c in componentes_h3], esquema)
        u_tx = ev.mejor_umbral_f1(c_tx[ok], y[ok])["umbral"]
        u_cta = ev.mejor_umbral_f1(c_cta[ids], cuentas.y.to_numpy())["umbral"]
        parametros["combinado"]["umbrales"][v] = {"transaccion": u_tx, "cuenta": u_cta}
        res[COMBINADO_H3] = ev.metricas(universo, c_tx, c_cta, u_tx, u_cta)
        desarrollo["metricas"][v] = res
        desarrollo["no_te_pareces"][v] = no_te_pareces(con, v, cache[("coles_modelo", v)])
        for clave in [k for k in cache if k[0] != "coles_modelo"]:
            del cache[clave]  # libera memoria entre variantes
    parametros["no_te_pareces_viable"] = desarrollo["no_te_pareces"][VARIANTE_DESARROLLO]["viable"]
    escribir_json(parametros, salida / "parametros.json")
    escribir_json(desarrollo, salida / "desarrollo.json")
    return parametros


def aporte(universo: ev.Universo, marcada_base: np.ndarray, marcada_nueva: np.ndarray) -> dict:
    """Transferencias de lavado que marca el combinado con CoLES y no el estructural, y al revés."""
    tx = universo.transacciones.assign(base=marcada_base, nueva=marcada_nueva)
    tx = tx[~tx.ignorada]
    lav, legit = tx[tx.y], tx[~tx.y]
    solo_nueva = lav[lav.nueva & ~lav.base]
    return {
        "lavado_marcado_base": int(lav.base.sum()),
        "lavado_marcado_nuevo": int(lav.nueva.sum()),
        "lavado_solo_con_coles": int(len(solo_nueva)),
        "lavado_perdido_con_coles": int((lav.base & ~lav.nueva).sum()),
        "solo_con_coles_por_tipo": solo_nueva.tipo.value_counts().sort_index().to_dict(),
        "legitimas_marcadas_base": int(legit.base.sum()),
        "legitimas_marcadas_nuevo": int(legit.nueva.sum()),
    }


def evaluar(
    con: duckdb.DuckDBPyConnection,
    parametros: dict,
    params_h2: dict,
    h1: dict,
    variantes: tuple[str, ...],
    dir_modelos: Path,
    salida: Path,
) -> dict:
    """Mide una vez en prueba: regla, combinado estructural (hito 2), CoLES y combinado + CoLES."""
    config_coles = coles.ConfigColes(**parametros["coles"])
    elegida = ca.ConfigColesAtipico(**parametros["detector"]["config"])
    componentes_h2 = params_h2["combinados"][COMBINADO_H2]["componentes"]
    configs = {n: f2._config_desde(n, params_h2["detectores"][n]["config"]) for n in componentes_h2}
    configs[DETECTOR] = elegida
    metricas: dict = {"parametros": parametros, "variantes": {}, "aporte": {}}
    for v in variantes:
        cache: dict = {
            ("coles_modelo", v): coles.cargar(dir_modelos / f"coles_{v}.pt", config_coles)
        }
        universo_dev = ev.cargar_universo(con, v, "desarrollo")
        universo = ev.cargar_universo(con, v, "prueba")
        res = {}
        regla = f2._config_desde(f2.REGLA, params_h2["detectores"][f2.REGLA]["config"])
        p = puntajes_detector(con, v, "prueba", f2.REGLA, regla, cache, h1)
        u = params_h2["detectores"][f2.REGLA]["umbrales"][v]
        res[f2.REGLA] = ev.metricas(universo, p.tx, p.cuenta, u["transaccion"], u["cuenta"])
        p = ca.puntuar(con, v, "prueba", elegida, cache)
        u = parametros["detector"]["umbrales"][v]
        res[DETECTOR] = ev.metricas(universo, p.tx, p.cuenta, u["transaccion"], u["cuenta"])
        pct_tx, pct_cta = _percentiles(
            con, v, [*componentes_h2, DETECTOR], configs, cache, h1, "prueba", universo_dev
        )
        info2 = params_h2["combinados"][COMBINADO_H2]
        b_tx = combinacion.combinar([pct_tx[c] for c in componentes_h2], info2["esquema"])
        b_cta = combinacion.combinar([pct_cta[c] for c in componentes_h2], info2["esquema"])
        u2 = info2["umbrales"][v]
        res[COMBINADO_H2] = ev.metricas(universo, b_tx, b_cta, u2["transaccion"], u2["cuenta"])
        info3 = parametros["combinado"]
        c_tx = combinacion.combinar([pct_tx[c] for c in info3["componentes"]], info3["esquema"])
        c_cta = combinacion.combinar([pct_cta[c] for c in info3["componentes"]], info3["esquema"])
        u3 = info3["umbrales"][v]
        res[COMBINADO_H3] = ev.metricas(universo, c_tx, c_cta, u3["transaccion"], u3["cuenta"])
        metricas["variantes"][v] = res
        metricas["aporte"][v] = aporte(
            universo,
            (b_tx >= u2["transaccion"]) & (b_tx > 0),
            (c_tx >= u3["transaccion"]) & (c_tx > 0),
        )
    escribir_json(metricas, salida / "metricas.json")
    graficar(metricas, salida)
    return metricas


ETIQUETAS = {
    f2.REGLA: "Regla simple",
    COMBINADO_H2: "Combinado estructural (hito 2)",
    DETECTOR: "CoLES: huella atípica",
    COMBINADO_H3: "Combinado estructural + CoLES",
}


def tabla_resumen(metricas: dict) -> pd.DataFrame:
    filas = []
    for v, res in metricas["variantes"].items():
        for nombre, m in res.items():
            filas.append(
                {
                    "variante": v.upper(),
                    "detector": nombre,
                    "etiqueta": ETIQUETAS[nombre],
                    "senales": "regla" if nombre == f2.REGLA else "estructurales",
                    "precision_100": m["precision_k"][0]["precision"],
                    "f1_tx": m["f1_transaccion"]["f1"],
                    "f1_cuenta": m["f1_cuenta"]["f1"],
                }
            )
    return pd.DataFrame(filas)


def graficar(metricas: dict, salida: Path) -> None:
    tabla = tabla_resumen(metricas)
    orden = list(ETIQUETAS.values())
    tableros.guardar(
        tableros.detectores(tabla, orden, "precision_100", "precisión en el top-100"),
        salida,
        "hito3_top100",
    )
    tableros.guardar(
        tableros.detectores(tabla, orden, "f1_tx", "F1 ilícita por transacción"), salida, "hito3_f1"
    )

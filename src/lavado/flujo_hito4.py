"""Flujo del hito 4: anomalías en el grafo (PyGOD) y red neuronal supervisada sobre el grafo.

- ``desarrollar``: arma el grafo de desarrollo de cada variante (variables estructurales +
  embeddings de CoLES por cuenta), entrena las redes con las etiquetas de desarrollo (días 2 a
  5 para entrenar, día 6 para elegir la época), ajusta PyGOD sin etiquetas y fija, para cada
  detector, la **fracción de alertas** (umbral relativo) del mejor F1 en desarrollo.
- ``evaluar``: con modelos, estadísticas y fracciones congelados, mide una sola vez en prueba.

Lección del hito 3: ningún umbral es un valor absoluto de rareza. En prueba se marca la misma
fracción de transferencias (o cuentas) que en desarrollo. Solo señales estructurales y de
comportamiento: nada de moneda ni formato.
"""

import json
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from lavado import coles, combinacion, congelados, gnn, grafo_gnn, tableros
from lavado import evaluacion as ev
from lavado import flujo_hito2 as f2
from lavado.detectores import anomalias_grafo as ag
from lavado.detectores import coles_atipico as ca
from lavado.detectores import comun
from lavado.flujo_hito1 import escribir_json
from lavado.rutas import DOCS_RESULTADOS_HITO2, DOCS_RESULTADOS_HITO3

VALIDACION_DESDE = datetime(2022, 9, 6)  # desarrollo: días 2 a 5 entrenan, día 6 valida
REDES: dict[str, gnn.ConfigGNN] = {
    "gnn": gnn.ConfigGNN(),
    "gnn_sin_coles": gnn.ConfigGNN(caracteristicas="estructurales"),
    "mlp_sin_grafo": gnn.ConfigGNN(usar_grafo=False),
    "coles_supervisado": gnn.ConfigGNN(
        caracteristicas="coles", usar_grafo=False, usar_atributos_tx=False
    ),
}
COMBINADO = "combinado_forma"


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def parametros_previos() -> tuple[dict, dict]:
    return _leer(DOCS_RESULTADOS_HITO2 / "parametros.json"), _leer(
        DOCS_RESULTADOS_HITO3 / "parametros.json"
    )


def codificador_coles(esquema: str, params_h3: dict):
    return coles.cargar(
        DOCS_RESULTADOS_HITO3 / params_h3["modelos"][esquema],
        coles.ConfigColes(**params_h3["coles"]),
    )


def grafo_estandarizado(con, esquema, periodo, codificador, cache, medias=None, desvios=None):
    g = grafo_gnn.construir(con, esquema, periodo, codificador, cache)
    if medias is None:
        medias, desvios = grafo_gnn.estadisticas(g)
    return grafo_gnn.estandarizar(g, medias, desvios), medias, desvios


def _tiempos(con: duckdb.DuckDBPyConnection, esquema: str, tx_id: np.ndarray) -> np.ndarray:
    df = con.execute(
        f"SELECT tx_id, ts FROM {esquema}.aristas WHERE periodo = 'desarrollo' ORDER BY tx_id"
    ).df()
    if not np.array_equal(df.tx_id.to_numpy(), tx_id):
        raise RuntimeError("Transferencias del grafo no alineadas")
    return df.ts.to_numpy()


def _fracciones(
    universo: ev.Universo, p_tx: np.ndarray, p_cta: np.ndarray, mascara_tx: np.ndarray | None = None
) -> dict:
    """Fracción de alertas del mejor F1 (por transferencia y por cuenta) en desarrollo."""
    tx = universo.transacciones
    ok = ~tx.ignorada.to_numpy() if mascara_tx is None else mascara_tx
    y = tx.y.to_numpy()
    u_tx = ev.mejor_umbral_f1(p_tx[ok], y[ok])["umbral"]
    cuentas = universo.cuentas[~universo.cuentas.ignorada]
    ids = cuentas.cuenta_id.to_numpy()
    u_cta = ev.mejor_umbral_f1(p_cta[ids], cuentas.y.to_numpy())["umbral"]
    return {
        "transaccion": ev.fraccion_marcada(p_tx[ok], u_tx),
        "cuenta": ev.fraccion_marcada(p_cta[ids], u_cta),
    }


def metricas_relativas(
    universo: ev.Universo, p_tx: np.ndarray, p_cta: np.ndarray, fracciones: dict
) -> dict:
    """Métricas con umbrales relativos: se marca la fracción de desarrollo."""
    tx = universo.transacciones
    ok = ~tx.ignorada.to_numpy()
    cuentas = universo.cuentas[~universo.cuentas.ignorada]
    u_tx = ev.umbral_relativo(p_tx[ok], fracciones["transaccion"])
    u_cta = ev.umbral_relativo(p_cta[cuentas.cuenta_id.to_numpy()], fracciones["cuenta"])
    return ev.metricas(universo, p_tx, p_cta, u_tx, u_cta) | {"umbral_relativo": fracciones}


def _cuentas(universo: ev.Universo, p_tx: np.ndarray, total: int) -> np.ndarray:
    tx = universo.transacciones
    return comun.cuentas_por_maximo(tx.origen.to_numpy(), tx.destino.to_numpy(), p_tx, total)


def combinado_estructural(con, esquema, periodo, params_h2, params_h3, h1, cache) -> tuple:
    """Combinado estructural del hito 2 con los percentiles congelados de Small."""
    tablas = congelados.cargar_small(esquema, cache)
    info = params_h2["combinados"][COMBINADO]
    configs = congelados.componentes(params_h2, params_h3)
    detectores = {d.nombre: d for d in f2.detectores(f2.config_abanicos(h1))}
    pct_tx, pct_cta = [], []
    for nombre in info["componentes"]:
        p = detectores[nombre].puntuar(con, esquema, periodo, configs[nombre], cache)
        pct_tx.append(tablas[(nombre, "tx")].aplicar(p.tx))
        pct_cta.append(tablas[(nombre, "cuenta")].aplicar(p.cuenta))
    return (
        combinacion.combinar(pct_tx, info["esquema"]),
        combinacion.combinar(pct_cta, info["esquema"]),
    )


def desarrollar(
    con: duckdb.DuckDBPyConnection,
    variantes: tuple[str, ...],
    salida: Path,
    h1: dict,
    redes: dict[str, gnn.ConfigGNN] | None = None,
    configs_pygod: list[ag.ConfigAnomaliasGrafo] | None = None,
) -> dict:
    redes = redes or REDES
    configs_pygod = configs_pygod or ag.configs()
    params_h2, params_h3 = parametros_previos()
    parametros: dict = {
        "criterio": "redes: época por AP en el día 6; PyGOD: modelo por AP en desarrollo "
        "(HI); umbrales relativos: fracción de alertas del mejor F1 en desarrollo",
        "redes": {n: c.como_dict() for n, c in redes.items()},
        "validacion_desde": str(VALIDACION_DESDE),
        "fracciones": {},
        "modelos": {},
        "estadisticas": {},
    }
    desarrollo: dict = {
        "advertencia": "cifras de desarrollo: optimistas",
        "entrenamiento": {},
        "metricas": {},
        "pygod": {},
    }
    (salida / "modelos").mkdir(parents=True, exist_ok=True)
    for v in variantes:
        cache: dict = {}
        codificador = codificador_coles(v, params_h3)
        g, medias, desvios = grafo_estandarizado(con, v, "desarrollo", codificador, cache)
        ruta_est = salida / "modelos" / f"estadisticas_{v}.npz"
        np.savez(ruta_est, medias=medias, desvios=desvios)
        parametros["estadisticas"][v] = f"modelos/estadisticas_{v}.npz"
        universo = ev.cargar_universo(con, v, "desarrollo")
        tx = universo.transacciones
        if not np.array_equal(tx.tx_id.to_numpy(), g.tx_id):
            raise RuntimeError("Grafo y universo no alineados")
        y, ign = tx.y.to_numpy(), tx.ignorada.to_numpy()
        ts = _tiempos(con, v, g.tx_id)
        entrena = ~ign & (ts < np.datetime64(VALIDACION_DESDE))
        valida = ~ign & ~entrena
        total = comun.n_cuentas(con, v)
        parametros["fracciones"][v], parametros["modelos"][v] = {}, {}
        desarrollo["entrenamiento"][v], desarrollo["metricas"][v] = {}, {}
        for nombre, cfg in redes.items():
            modelo, historial = gnn.entrenar(g, y, entrena, valida, cfg)
            ruta = salida / "modelos" / f"{nombre}_{v}.pt"
            gnn.guardar(modelo, ruta)
            parametros["modelos"][v][nombre] = f"modelos/{nombre}_{v}.pt"
            desarrollo["entrenamiento"][v][nombre] = historial
            p_tx = gnn.puntuar(modelo, g)
            p_cta = _cuentas(universo, np.where(valida, p_tx, 0.0), total)
            # la fracción de alertas se fija en la validación (día 6), no en lo entrenado
            fr = _fracciones(universo, np.where(valida, p_tx, 0.0), p_cta, valida)
            parametros["fracciones"][v][nombre] = fr
            desarrollo["metricas"][v][nombre] = {
                "validacion_dia_6": metricas_relativas(
                    universo, np.where(valida, p_tx, 0.0), p_cta, fr
                )
            }
        # PyGOD, sin etiquetas: se elige el modelo en HI por AP en desarrollo
        resultados = []
        for i, cfg in enumerate(configs_pygod):
            detector = ag.ajustar(g, cfg)
            p_cta = ag.puntuar_cuentas(detector, g, total)
            p_tx = ag.a_transacciones(universo, p_cta)
            ap = ev.precision_promedio(p_tx[~ign], y[~ign])
            resultados.append(
                {
                    "orden": i,
                    "config": cfg.como_dict(),
                    "ap": ap,
                    "p_tx": p_tx,
                    "p_cta": p_cta,
                    "detector": detector,
                }
            )
        desarrollo["pygod"][v] = [{k: r[k] for k in ("config", "ap")} for r in resultados]
        if v == variantes[0]:
            elegido = max(resultados, key=lambda r: (round(r["ap"], 4), -r["orden"]))
            parametros["pygod"] = elegido["config"]
        elegido = next(r for r in resultados if r["config"] == parametros["pygod"])
        ag.guardar(elegido["detector"], salida / "modelos" / f"pygod_{v}.pt")
        parametros["modelos"][v]["pygod"] = f"modelos/pygod_{v}.pt"
        fr = _fracciones(universo, elegido["p_tx"], elegido["p_cta"])
        parametros["fracciones"][v]["pygod"] = fr
        desarrollo["metricas"][v]["pygod"] = metricas_relativas(
            universo, elegido["p_tx"], elegido["p_cta"], fr
        )
        # combinado estructural y CoLES del hito 3, con umbral relativo
        c_tx, c_cta = combinado_estructural(con, v, "desarrollo", params_h2, params_h3, h1, cache)
        parametros["fracciones"][v][COMBINADO] = _fracciones(universo, c_tx, c_cta)
        cache[("coles_modelo", v)] = codificador
        p = ca.puntuar(
            con, v, "desarrollo", ca.ConfigColesAtipico(**params_h3["detector"]["config"]), cache
        )
        parametros["fracciones"][v]["coles_atipico"] = _fracciones(universo, p.tx, p.cuenta)
    parametros["modelo_final"] = modelo_final(desarrollo, variantes[0])
    escribir_json(parametros, salida / "parametros.json")
    escribir_json(desarrollo, salida / "desarrollo.json")
    return parametros


def modelo_final(desarrollo: dict, variante: str = "hi") -> str:
    """Red con mejor AP en la validación (día 6) de HI: el modelo que irá a Medium."""
    entrenamiento = desarrollo["entrenamiento"][variante]
    return max(entrenamiento, key=lambda n: round(entrenamiento[n]["mejor_ap_validacion"], 4))


def evaluar(
    con: duckdb.DuckDBPyConnection,
    parametros: dict,
    h1: dict,
    variantes: tuple[str, ...],
    dir_modelos: Path,
    salida: Path,
) -> dict:
    """Mide una vez en prueba todos los detectores con sus umbrales relativos congelados."""
    params_h2, params_h3 = parametros_previos()
    metricas: dict = {"parametros": parametros, "variantes": {}}
    for v in variantes:
        cache: dict = {}
        codificador = codificador_coles(v, params_h3)
        est = np.load(dir_modelos.parent / parametros["estadisticas"][v])
        g, _, _ = grafo_estandarizado(
            con, v, "prueba", codificador, cache, est["medias"], est["desvios"]
        )
        universo = ev.cargar_universo(con, v, "prueba")
        if not np.array_equal(universo.transacciones.tx_id.to_numpy(), g.tx_id):
            raise RuntimeError("Grafo y universo no alineados")
        total = comun.n_cuentas(con, v)
        fr = parametros["fracciones"][v]
        res: dict = {}
        regla = f2._config_desde(f2.REGLA, params_h2["detectores"][f2.REGLA]["config"])
        p = f2.puntuar_abanicos(con, v, "prueba", regla, cache)
        u = params_h2["detectores"][f2.REGLA]["umbrales"][v]
        res[f2.REGLA] = ev.metricas(universo, p.tx, p.cuenta, u["transaccion"], u["cuenta"])
        c_tx, c_cta = combinado_estructural(con, v, "prueba", params_h2, params_h3, h1, cache)
        u = params_h2["combinados"][COMBINADO]["umbrales"][v]
        res[f"{COMBINADO}_absoluto"] = ev.metricas(
            universo, c_tx, c_cta, u["transaccion"], u["cuenta"]
        )
        res[COMBINADO] = metricas_relativas(universo, c_tx, c_cta, fr[COMBINADO])
        cache[("coles_modelo", v)] = codificador
        p = ca.puntuar(
            con, v, "prueba", ca.ConfigColesAtipico(**params_h3["detector"]["config"]), cache
        )
        res["coles_atipico"] = metricas_relativas(universo, p.tx, p.cuenta, fr["coles_atipico"])
        for nombre, d in parametros["redes"].items():
            cfg = gnn.ConfigGNN(**d)
            modelo = gnn.cargar(dir_modelos.parent / parametros["modelos"][v][nombre], g, cfg)
            p_tx = gnn.puntuar(modelo, g)
            res[nombre] = metricas_relativas(
                universo, p_tx, _cuentas(universo, p_tx, total), fr[nombre]
            )
        detector = ag.cargar(dir_modelos.parent / parametros["modelos"][v]["pygod"])
        p_cta = ag.puntuar_cuentas(detector, g, total)
        res["pygod"] = metricas_relativas(
            universo, ag.a_transacciones(universo, p_cta), p_cta, fr["pygod"]
        )
        metricas["variantes"][v] = res
    escribir_json(metricas, salida / "metricas.json")
    graficar(metricas, salida)
    return metricas


ETIQUETAS = {
    f2.REGLA: "Regla simple",
    f"{COMBINADO}_absoluto": "Combinado estructural (umbral absoluto)",
    COMBINADO: "Combinado estructural (umbral relativo)",
    "coles_atipico": "CoLES, huella atípica (sin etiquetas)",
    "pygod": "PyGOD (sin etiquetas)",
    "coles_supervisado": "CoLES supervisado (sin grafo)",
    "mlp_sin_grafo": "Red sin grafo (estructurales + CoLES)",
    "gnn_sin_coles": "GNN (solo estructurales)",
    "gnn": "GNN (estructurales + CoLES)",
}
SENALES = {
    f2.REGLA: "regla",
    "coles_atipico": "sin etiquetas",
    "pygod": "sin etiquetas",
    COMBINADO: "sin etiquetas",
    f"{COMBINADO}_absoluto": "sin etiquetas",
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
                    "senales": SENALES.get(nombre, "con etiquetas"),
                    "precision_100": m["precision_k"][0]["precision"],
                    "precision_1000": m["precision_k"][2]["precision"],
                    "f1_tx": m["f1_transaccion"]["f1"],
                    "f1_cuenta": m["f1_cuenta"]["f1"],
                }
            )
    return pd.DataFrame(filas)


def graficar(metricas: dict, salida: Path) -> None:
    tabla = tabla_resumen(metricas)
    orden = list(ETIQUETAS.values())
    tableros.guardar(
        tableros.detectores(
            tabla,
            orden,
            "precision_100",
            "precisión en el top-100",
            colores=tableros.COLOR_ETIQUETAS,
        ),
        salida,
        "hito4_top100",
    )
    tableros.guardar(
        tableros.detectores(
            tabla, orden, "f1_tx", "F1 ilícita por transacción", colores=tableros.COLOR_ETIQUETAS
        ),
        salida,
        "hito4_f1",
    )

"""Artefactos congelados de Small: todo lo que antes se recalculaba desde su desarrollo.

Para aplicar los detectores a otro conjunto (la prueba fresca con Medium) **sin ningún
ajuste**, se guardan en archivos:

- los Isolation Forest ajustados con el desarrollo de cada variante (``if_*.joblib``);
- las tablas de percentiles de desarrollo de cada componente de las combinaciones, por
  transferencia y por cuenta (``percentiles/*.npz``);
- los embeddings de referencia de CoLES de desarrollo para la distancia a vecinos
  (``coles_ref_*.npz``).

``cargar_small`` los pone en el ``cache`` con las claves que buscan los detectores.
"""

import json
from pathlib import Path

import duckdb
import joblib
import numpy as np

from lavado import coles, combinacion, particion, variables_cuenta
from lavado import evaluacion as ev
from lavado import flujo_hito2 as f2
from lavado.detectores import aislamiento as ai
from lavado.detectores import coles_atipico as ca
from lavado.flujo_hito1 import escribir_json
from lavado.rutas import DOCS_RESULTADOS, DOCS_RESULTADOS_HITO2, DOCS_RESULTADOS_HITO3

DIR_CONGELADOS = DOCS_RESULTADOS / "congelados"


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def componentes(params_h2: dict, params_h3: dict) -> dict[str, object]:
    """Detectores que entran en alguna combinación, con su configuración congelada."""
    nombres: list[str] = []
    for info in params_h2["combinados"].values():
        nombres += [n for n in info["componentes"] if n not in nombres]
    configs = {n: f2._config_desde(n, params_h2["detectores"][n]["config"]) for n in nombres}
    configs["coles_atipico"] = ca.ConfigColesAtipico(**params_h3["detector"]["config"])
    return configs


def congelar_small(
    con: duckdb.DuckDBPyConnection,
    variantes: tuple[str, ...],
    destino: Path = DIR_CONGELADOS,
    dir_h2: Path = DOCS_RESULTADOS_HITO2,
    dir_h3: Path = DOCS_RESULTADOS_HITO3,
) -> dict:
    """Guarda los artefactos y devuelve un resumen. No lee etiquetas."""
    params_h2, params_h3 = _leer(dir_h2 / "parametros.json"), _leer(dir_h3 / "parametros.json")
    h1 = f2.congelado_hito1()
    config_coles = coles.ConfigColes(**params_h3["coles"])
    configs = componentes(params_h2, params_h3)
    detectores = {d.nombre: d for d in f2.detectores(f2.config_abanicos(h1))}
    resumen: dict = {"variantes": {}}
    for v in variantes:
        dv = destino / v
        (dv / "percentiles").mkdir(parents=True, exist_ok=True)
        cache: dict = {
            ("coles_modelo", v): coles.cargar(dir_h3 / params_h3["modelos"][v], config_coles)
        }
        vdev = variables_cuenta.calcular(
            con, v, particion.DESDE["desarrollo"], particion.HASTA["desarrollo"]
        )
        for sospechosas in (False, True):
            modelo = ai.ajustar(vdev, ai.ConfigAislamiento(sospechosas=sospechosas))
            joblib.dump(modelo, dv / f"if_{'con' if sospechosas else 'forma'}.joblib")
            cache[("if_modelo", v, sospechosas)] = modelo
        cfg_coles = configs["coles_atipico"]
        cuentas_ref, ref = ca.embeddings(
            con, v, "desarrollo", cfg_coles.min_eventos, cache[("coles_modelo", v)], cache
        )
        np.savez_compressed(
            dv / f"coles_ref_{cfg_coles.min_eventos}.npz", cuentas=cuentas_ref, embeddings=ref
        )
        universo_dev = ev.cargar_universo(con, v, "desarrollo")
        for nombre, cfg in configs.items():
            if nombre == "coles_atipico":
                p = ca.puntuar(con, v, "desarrollo", cfg, cache)
            else:
                p = detectores[nombre].puntuar(con, v, "desarrollo", cfg, cache)
            combinacion.PercentilesCompactos.desde(p.tx).guardar(
                dv / "percentiles" / f"{nombre}_tx.npz"
            )
            combinacion.PercentilesCompactos.desde(
                p.cuenta[universo_dev.cuentas.cuenta_id]
            ).guardar(dv / "percentiles" / f"{nombre}_cuenta.npz")
        resumen["variantes"][v] = {"componentes": sorted(configs), "cuentas_ref_coles": len(ref)}
    escribir_json(
        resumen | {"origen": "desarrollo de Small (días 2 a 6)"}, destino / "resumen.json"
    )
    return resumen


def cargar_small(esquema: str, cache: dict, origen: Path = DIR_CONGELADOS) -> dict:
    """Pone en ``cache`` los bosques y la referencia de CoLES congelados de ``esquema``.

    Devuelve las tablas de percentiles congeladas: ``{(nombre, "tx" | "cuenta"): tabla}``.
    """
    d = origen / esquema
    for sospechosas in (False, True):
        cache[("if_modelo", esquema, sospechosas)] = joblib.load(
            d / f"if_{'con' if sospechosas else 'forma'}.joblib"
        )
    for ruta in d.glob("coles_ref_*.npz"):
        minimo = int(ruta.stem.rsplit("_", 1)[1])
        cache[("coles_ref", esquema, minimo)] = np.load(ruta)["embeddings"]
    tablas = {}
    for ruta in sorted((d / "percentiles").glob("*.npz")):
        nombre, nivel = ruta.stem.rsplit("_", 1)
        tablas[(nombre, nivel)] = combinacion.PercentilesCompactos.cargar(ruta)
    return tablas

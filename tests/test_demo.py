"""La página interactiva calcula lo mismo que Python (motor.js con Node) y lee datos coherentes."""

import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from lavado import demo
from lavado.detectores import abanicos as ab
from lavado.rutas import DOCS, DOCS_RESULTADOS

MOTOR = DOCS / "demo" / "motor.js"
DATOS = DOCS_RESULTADOS / "demo"


def _leer(ruta) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _node(codigo: str) -> object:
    if shutil.which("node") is None:
        pytest.skip("sin Node.js")
    r = subprocess.run(
        ["node", "-e", codigo], capture_output=True, text=True, encoding="utf-8", check=True
    )
    return json.loads(r.stdout)


def _motor() -> str:
    return f"const M=require({json.dumps(str(MOTOR))});"


def test_puntaje_forma_igual_que_python() -> None:
    datos = _leer(DATOS / "forma_tamano.json")
    combinaciones = [
        ["novedad", "unicidad", "homogeneidad"],
        ["unicidad"],
        [],
        ["mezcla_monedas", "dispersion", "exclusividad"],
    ]
    for caso in ("alerta", "comercio"):
        est = datos[caso]["estructura"]
        for usadas in combinaciones:
            for tamano in ("ninguno", "log2", "lineal"):
                js = _node(
                    _motor() + f"console.log(JSON.stringify(M.puntajeForma("
                    f"{json.dumps(est['variables'])},{json.dumps(usadas)},"
                    f"{json.dumps(tamano)},{est['n_contrapartes']},{ab.PISO})));"
                )
                py = demo.puntaje_forma(est["variables"], usadas, tamano, est["n_contrapartes"])
                ref = ab.puntuar_estructuras(
                    pd.DataFrame([est["variables"] | {"n_contrapartes": est["n_contrapartes"]}]),
                    ab.ConfigAbanicos(variables=tuple(usadas), tamano=tamano),
                )[0]
                assert abs(js - py) < 1e-12 and abs(py - ref) < 1e-12


def test_precision_interpolada_igual_que_python() -> None:
    curvas = _leer(DATOS / "curvas.json")
    ks = [10, 37, 100, 250, 999, 1000, 4321, 20_000]
    for v, c in curvas.items():
        for metodo, curva in c["metodos"].items():
            js = _node(
                _motor() + f"const c={json.dumps(curva)};"
                f"console.log(JSON.stringify({json.dumps(ks)}.map(k=>M.precisionEnK(c,k))));"
            )
            py = [demo.precision_interpolada(curva, k) for k in ks]
            np.testing.assert_allclose(js, py, atol=1e-12, err_msg=f"{v} {metodo}")


def test_curvas_coinciden_con_las_metricas_publicadas() -> None:
    curvas = _leer(DATOS / "curvas.json")
    h4 = _leer(DOCS_RESULTADOS / "hito4" / "metricas.json")["variantes"]
    h2 = _leer(DOCS_RESULTADOS / "hito2" / "metricas.json")["variantes"]
    for v in ("hi", "li"):
        k100 = {
            m: next(x["precision"] for x in curvas[v]["metodos"][m] if x["k"] == 100)
            for m in ("regla", "forma", "final")
        }
        assert k100["final"] == h4[v]["gnn_sin_coles"]["precision_k"][0]["precision"]
        assert k100["regla"] == h4[v]["regla_simple"]["precision_k"][0]["precision"]
        assert k100["forma"] == h2[v]["abanicos_salida_forma"]["precision_k"][0]["precision"]
        assert curvas[v]["ilicitas"] == h4[v]["gnn_sin_coles"]["universo"]["cuentas_ilicitas"]


def test_alertas_coherentes() -> None:
    for v in ("hi", "li"):
        datos = _leer(DATOS / f"alertas_{v}.json")
        for a in datos["cuentas"]:
            assert len(a["vecinos"]) <= demo.MAX_VECINOS
            assert all(0 <= x["percentil"] <= 1 for x in a["variables"])
            assert len(a["variables"]) == 12
            if a["categoria"] == "falsa_alarma":
                assert not a["patrones"]
            else:
                assert a["patrones"]
        aciertos = [a["puesto"] for a in datos["cuentas"] if a["categoria"] == "acierto"]
        assert aciertos == sorted(aciertos)


def test_casos_forma_tamano() -> None:
    datos = _leer(DATOS / "forma_tamano.json")
    a, c = datos["alerta"], datos["comercio"]
    assert a["lavado"] and not c["lavado"]
    assert 5 <= a["estructura"]["n_contrapartes"] <= 15
    assert c["contrapartes_24h"] > a["contrapartes_24h"]
    assert a["puesto"]["forma"] < (c["puesto"]["forma"] or 10**9)
    assert c["puesto"]["regla"] < a["puesto"]["regla"]


def test_formato_y_estrella() -> None:
    r = _node(
        _motor() + "console.log(JSON.stringify([M.coma(-0.0326,3),M.miles(12538),"
        "M.pct(0.91),M.pct(0.0154,1),M.usd(3773438.9),M.kDesdeDeslizante(0,10,1000),"
        "M.kDesdeDeslizante(1,10,1000),M.estrella(30)]));"
    )
    assert r[:7] == ["−0,033", "12.538", "91 %", "1,5 %", "3,8 M", 10, 1000]
    assert len(r[7]) == 30 and all(abs(p["x"]) <= 1 and abs(p["y"]) <= 1 for p in r[7])

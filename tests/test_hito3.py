"""Pruebas del hito 3 (CoLES) sobre el mini-AMLworld."""

import inspect
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import torch

from lavado import coles, flujo_hito2, flujo_hito3, ingesta, particion, secuencias
from lavado.detectores import coles_atipico as ca
from lavado.rutas import DOCS_RESULTADOS_HITO3, RAIZ

DESDE, HASTA = particion.DESDE["desarrollo"], particion.HASTA["desarrollo"]
CONFIG_MINI = coles.ConfigColes(
    min_eventos=4, oculto=8, epocas=2, corte_min=2, corte_max=6, lote=16
)


@pytest.fixture
def con_rw(tmp_path: Path, ruta_base: Path):
    base = tmp_path / "base.duckdb"
    shutil.copy(ruta_base, base)
    conexion = ingesta.conectar(base)
    yield conexion
    conexion.close()


@pytest.fixture
def datos(con_rw) -> secuencias.Secuencias:
    return secuencias.construir(con_rw, "hi", DESDE, HASTA, CONFIG_MINI.min_eventos)


def test_secuencias_formato(datos) -> None:
    assert len(datos.registros) > 10
    assert np.all(np.diff(datos.cuentas) > 0)
    esperadas = {"event_time", *secuencias.CATEGORICAS, *secuencias.NUMERICAS}
    for registro, largo in zip(datos.registros, datos.largos, strict=True):
        assert set(registro) == esperadas
        assert len(registro["event_time"]) == largo >= CONFIG_MINI.min_eventos
        assert torch.all(registro["event_time"][1:] >= registro["event_time"][:-1])
        assert registro["log_dt"][0] == 0
        for c, n in secuencias.CATEGORICAS.items():
            assert int(registro[c].min()) >= 1 and int(registro[c].max()) < n, c


def test_secuencias_no_usan_moneda_ni_formato() -> None:
    for modulo in (secuencias, coles, ca):
        codigo = inspect.getsource(modulo).split('"""', 2)[2]
        assert "moneda" not in codigo and "formato" not in codigo, modulo.__name__


def test_secuencias_marcan_el_paso(con_rw, mini_raw) -> None:
    c0 = con_rw.execute(
        "SELECT cuenta_id FROM hi.cuentas WHERE llave = ?", [mini_raw.especiales["CADENA_0"].llave]
    ).fetchone()[0]
    intermedia = con_rw.execute(
        "SELECT destino FROM hi.transacciones WHERE origen = ? AND es_lavado", [c0]
    ).fetchone()[0]
    datos = secuencias.construir(con_rw, "hi", DESDE, HASTA, 1)
    registro = datos.registros[int(np.searchsorted(datos.cuentas, intermedia))]
    # recibe de la cadena (entrada reenviada) y reenvía (salida que reenvía), ambas nuevas
    assert registro["paso"].tolist() == [2, 3]
    assert registro["direccion"].tolist() == [1, 2]
    assert registro["nueva"].tolist() == [2, 2]


def test_coles_determinista_y_guardado(datos, tmp_path: Path) -> None:
    a, perdidas = coles.entrenar(datos, CONFIG_MINI)
    b, _ = coles.entrenar(datos, CONFIG_MINI)
    assert len(perdidas) == CONFIG_MINI.epocas
    ea, eb = coles.incrustar(a, datos), coles.incrustar(b, datos)
    assert ea.shape == (len(datos.registros), CONFIG_MINI.oculto)
    np.testing.assert_allclose(ea, eb, atol=1e-6)
    ruta = coles.guardar(a, tmp_path / "m.pt")
    np.testing.assert_allclose(
        coles.incrustar(coles.cargar(ruta, CONFIG_MINI), datos), ea, atol=1e-6
    )


def test_rareza_knn_sin_contarse() -> None:
    ref = np.array([[0.0], [1.0], [2.0], [10.0]])
    cfg = ca.ConfigColesAtipico("knn", k=1)
    np.testing.assert_allclose(ca.rareza(ref, ref, cfg, misma=True), [1, 1, 1, 8])
    np.testing.assert_allclose(ca.rareza(ref, np.array([[3.0]]), cfg, misma=False), [1])


def test_ventana_de_puntaje() -> None:
    desde, hasta = ca.ventana("prueba")
    assert hasta == particion.FIN_VENTANA and (hasta - desde).days == 5
    assert ca.ventana("desarrollo") == (DESDE, HASTA)  # coincide con la de entrenamiento


def test_cuentas_sin_historia_quedan_en_cero(con_rw, datos) -> None:
    modelo, _ = coles.entrenar(datos, CONFIG_MINI)
    cache = {("coles_modelo", "hi"): modelo}
    p = ca.puntuar(con_rw, "hi", "desarrollo", ca.ConfigColesAtipico("iforest", "max", 4), cache)
    cubiertas = set(datos.cuentas.tolist())
    sin = [c for c in range(len(p.cuenta)) if c not in cubiertas]
    assert np.all(p.cuenta[sin] == 0) and np.all(p.cuenta[list(cubiertas)] > 0)


@pytest.mark.integracion
def test_flujo_hito3(con_rw, tmp_path: Path) -> None:
    h1 = {
        "ventana_horas": 96,
        "min_contrapartes": 3,
        "por_formato": True,
        "variables": ["unicidad", "mezcla_monedas"],
        "tamano": "log2",
    }
    p2 = flujo_hito2.desarrollar(
        con_rw, ingesta.VARIANTES, tmp_path / "h2", h1, diagnostico_li=False
    )
    salida = tmp_path / "h3"
    p3 = flujo_hito3.desarrollar(
        con_rw,
        ingesta.VARIANTES,
        salida,
        h1,
        p2,
        CONFIG_MINI,
        [ca.ConfigColesAtipico("iforest", "max", 3)],
    )
    assert (salida / "modelos" / "coles_hi.pt").exists()
    assert p3["combinado"]["componentes"][-1] == flujo_hito3.DETECTOR
    assert all(
        c in p2["combinados"]["combinado_forma"]["componentes"]
        for c in p3["combinado"]["componentes"][:-1]
    )
    m = flujo_hito3.evaluar(con_rw, p3, p2, h1, ingesta.VARIANTES, salida / "modelos", salida)
    assert set(m["variantes"]["li"]) == {
        "regla_simple",
        "coles_atipico",
        "combinado_forma",
        "combinado_forma_coles",
    }
    assert {"lavado_solo_con_coles", "solo_con_coles_por_tipo"} <= set(m["aporte"]["hi"])
    texto = (salida / "metricas.json").read_text(encoding="utf-8").lower()
    assert "exactitud" not in texto and "accuracy" not in texto


def _git(*args: str, binario: bool = False) -> subprocess.CompletedProcess:
    if binario:
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True)
    return subprocess.run(
        ["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8"
    )


def test_hito3_congelado_no_cambia() -> None:
    """Si existe el tag, parámetros y modelos de CoLES deben ser idénticos a los del tag."""
    if shutil.which("git") is None or _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("sin git")
    if _git("rev-parse", "-q", "--verify", "refs/tags/hito3-congelado").returncode != 0:
        pytest.skip("todavía no hay tag de congelamiento")
    congelado = _git("show", "hito3-congelado:docs/resultados/hito3/parametros.json")
    actual = (DOCS_RESULTADOS_HITO3 / "parametros.json").read_text(encoding="utf-8")
    assert json.loads(congelado.stdout) == json.loads(actual)
    for v in ingesta.VARIANTES:
        ruta = f"docs/resultados/hito3/modelos/coles_{v}.pt"
        assert (
            _git("show", f"hito3-congelado:{ruta}", binario=True).stdout
            == (RAIZ / ruta).read_bytes()
        )

"""Pruebas del hito 4 (grafo, GNN y PyGOD) sobre el mini-AMLworld, en CPU."""

import inspect
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import torch

from lavado import evaluacion as ev
from lavado import flujo_hito2, flujo_hito4, gnn, grafo_gnn, ingesta
from lavado.detectores import anomalias_grafo as ag
from lavado.rutas import DOCS_RESULTADOS_HITO4, RAIZ

CPU = torch.device("cpu")
MINI = gnn.ConfigGNN(oculto=8, max_epocas=20, cada=5, paciencia=2)


@pytest.fixture
def con_rw(tmp_path: Path, ruta_base: Path):
    base = tmp_path / "base.duckdb"
    shutil.copy(ruta_base, base)
    conexion = ingesta.conectar(base)
    yield conexion
    conexion.close()


@pytest.fixture
def grafo(con_rw) -> grafo_gnn.Grafo:
    g = grafo_gnn.construir(con_rw, "hi", "desarrollo")
    medias, desvios = grafo_gnn.estadisticas(g)
    return grafo_gnn.estandarizar(g, medias, desvios)


def test_grafo_alineado_con_el_universo(con_rw, grafo) -> None:
    universo = ev.cargar_universo(con_rw, "hi", "desarrollo")
    np.testing.assert_array_equal(universo.transacciones.tx_id.to_numpy(), grafo.tx_id)
    assert grafo.x.shape[0] == len(grafo.cuentas)
    assert grafo.tx_atributos.shape == (len(grafo.tx_id), len(grafo_gnn.ATRIBUTOS_TX))
    assert int(grafo.aristas.max()) < len(grafo.cuentas)
    assert not torch.isnan(grafo.x).any()
    # sin codificador de CoLES no hay embeddings
    assert not any(n.startswith("coles_") for n in grafo.nombres_x)


def test_grafo_sin_moneda_ni_formato() -> None:
    for modulo in (grafo_gnn, gnn, ag):
        codigo = inspect.getsource(modulo).split('"""', 2)[2]
        assert "moneda" not in codigo and "formato" not in codigo, modulo.__name__


def test_gnn_determinista_en_cpu(con_rw, grafo) -> None:
    universo = ev.cargar_universo(con_rw, "hi", "desarrollo")
    y = universo.transacciones.y.to_numpy()
    entrena = np.arange(len(y)) % 2 == 0
    valida = ~entrena
    a, ha = gnn.entrenar(grafo, y, entrena, valida, MINI, CPU)
    b, _ = gnn.entrenar(grafo, y, entrena, valida, MINI, CPU)
    pa, pb = gnn.puntuar(a, grafo), gnn.puntuar(b, grafo)
    np.testing.assert_array_equal(pa, pb)
    assert pa.shape == (len(grafo.tx_id),) and ((pa >= 0) & (pa <= 1)).all()
    assert ha["dispositivo"] == "cpu" and ha["mejor_epoca"] > 0


def test_gnn_sin_grafo_y_columnas(grafo, tmp_path: Path) -> None:
    sin = gnn.ConfigGNN(oculto=8, usar_grafo=False)
    modelo = gnn.crear(grafo, sin)
    assert not hasattr(modelo, "salientes")
    assert gnn.columnas(grafo, gnn.ConfigGNN(caracteristicas="estructurales")) == list(
        range(grafo.x.shape[1])
    )
    with pytest.raises(ValueError):
        gnn.columnas(grafo, gnn.ConfigGNN(caracteristicas="otra"))
    gnn.guardar(modelo, tmp_path / "m.pt")
    np.testing.assert_array_equal(
        gnn.puntuar(gnn.cargar(tmp_path / "m.pt", grafo, sin), grafo), gnn.puntuar(modelo, grafo)
    )


def test_umbral_relativo() -> None:
    p = np.array([0.9, 0.1, 0.5, 0.7, 0.3])
    assert ev.umbral_relativo(p, 0.4) == 0.7  # marca 2 de 5
    assert ev.fraccion_marcada(p, 0.7) == 0.4
    assert ev.umbral_relativo(p, 0.0) == float("inf")
    assert ev.umbral_relativo(p, 1.0) == 0.1


def test_lote_completo_de_pygod(grafo) -> None:
    lotes = list(ag._LoteCompleto(ag._datos(grafo)))
    assert len(lotes) == 1 and lotes[0].batch_size == len(grafo.cuentas)
    np.testing.assert_array_equal(lotes[0].n_id.numpy(), np.arange(len(grafo.cuentas)))


def test_pygod_ajusta_y_guarda(grafo, tmp_path: Path) -> None:
    detector = ag.ajustar(grafo, ag.ConfigAnomaliasGrafo("ocgnn", oculto=8, epocas=2))
    p = ag.puntuar_cuentas(detector, grafo, int(grafo.cuentas.max()) + 1)
    assert (p[grafo.cuentas] > 0).all()
    ag.guardar(detector, tmp_path / "d.pt")
    np.testing.assert_allclose(
        ag.puntuar_cuentas(ag.cargar(tmp_path / "d.pt"), grafo, len(p)), p, atol=1e-5
    )


@pytest.mark.integracion
def test_flujo_hito4(con_rw, tmp_path: Path) -> None:
    h1 = flujo_hito2.congelado_hito1()
    redes = {
        "gnn": MINI,
        "mlp_sin_grafo": gnn.ConfigGNN(oculto=8, usar_grafo=False, max_epocas=10, cada=5),
    }
    salida = tmp_path / "h4"
    p = flujo_hito4.desarrollar(
        con_rw,
        ingesta.VARIANTES,
        salida,
        h1,
        redes,
        [ag.ConfigAnomaliasGrafo("ocgnn", oculto=8, epocas=2)],
    )
    for v in ingesta.VARIANTES:
        assert set(p["fracciones"][v]) == {
            "gnn",
            "mlp_sin_grafo",
            "pygod",
            "combinado_forma",
            "coles_atipico",
        }
    m = flujo_hito4.evaluar(con_rw, p, h1, ingesta.VARIANTES, salida / "modelos", salida)
    assert {"gnn", "pygod", "combinado_forma", "combinado_forma_absoluto", "regla_simple"} <= set(
        m["variantes"]["hi"]
    )
    texto = (salida / "metricas.json").read_text(encoding="utf-8").lower()
    assert "exactitud" not in texto and "accuracy" not in texto


def _git(*args: str, binario: bool = False) -> subprocess.CompletedProcess:
    if binario:
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True)
    return subprocess.run(
        ["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8"
    )


def test_hito4_congelado_no_cambia() -> None:
    """Si existe el tag, parámetros y modelos del hito 4 deben ser idénticos a los del tag."""
    if shutil.which("git") is None or _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("sin git")
    if _git("rev-parse", "-q", "--verify", "refs/tags/hito4-congelado").returncode != 0:
        pytest.skip("todavía no hay tag de congelamiento")
    congelado = _git("show", "hito4-congelado:docs/resultados/hito4/parametros.json")
    actual = json.loads((DOCS_RESULTADOS_HITO4 / "parametros.json").read_text(encoding="utf-8"))
    assert json.loads(congelado.stdout) == actual
    for v in ingesta.VARIANTES:
        for ruta in actual["modelos"][v].values():
            r = f"docs/resultados/hito4/{ruta}"
            assert (
                _git("show", f"hito4-congelado:{r}", binario=True).stdout == (RAIZ / r).read_bytes()
            )

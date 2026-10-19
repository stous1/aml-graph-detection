"""Pruebas de los artefactos congelados y del redondeo determinista."""

from pathlib import Path

import numpy as np
import pandas as pd

from lavado import combinacion
from lavado.detectores import comun


def test_percentiles_compactos_exactos_en_la_parte_alta(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    puntajes = np.r_[np.zeros(5_000), rng.lognormal(size=20_000), np.full(300, 7.0)]
    exactos = combinacion.Percentiles.desde(puntajes)
    compactos = combinacion.PercentilesCompactos.desde(puntajes, k_exactos=2_000, n_cuantiles=501)
    consulta = np.r_[puntajes, [0.0, -1.0, 1e9]]
    a, b = exactos.aplicar(consulta), compactos.aplicar(consulta)
    alta = a >= 0.95  # los 2.000 más altos son exactos: más del 7 % superior
    np.testing.assert_array_equal(a[alta], b[alta])
    assert np.abs(a - b).max() < 0.01  # abajo, interpolación cercana
    assert b[-3] == 0 and b[-2] == 0 and b[-1] == 1.0
    ruta = tmp_path / "p.npz"
    compactos.guardar(ruta)
    np.testing.assert_array_equal(
        combinacion.PercentilesCompactos.cargar(ruta).aplicar(consulta), b
    )


def test_percentiles_compactos_pocos_positivos() -> None:
    puntajes = np.r_[np.zeros(10), [1.0, 2.0, 2.0, 3.0]]
    a = combinacion.Percentiles.desde(puntajes).aplicar(puntajes)
    b = combinacion.PercentilesCompactos.desde(puntajes).aplicar(puntajes)
    np.testing.assert_array_equal(a, b)


def test_redondear_absorbe_diferencias_de_ultimo_bit() -> None:
    a = pd.DataFrame({"v": [0.1 + 0.2, 1 / 3]})
    b = pd.DataFrame({"v": [0.3, 0.3333333333333333]})
    assert not a.v.equals(b.v)
    assert comun.redondear(a, ["v"]).v.equals(comun.redondear(b, ["v"]).v)

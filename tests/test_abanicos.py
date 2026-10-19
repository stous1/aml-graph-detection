"""Pruebas del detector de abanicos: forma contra tamaño en el mini-AMLworld."""

import numpy as np
import pandas as pd
import pytest

from lavado import particion
from lavado.detectores import abanicos as ab


@pytest.fixture
def cand_dev(con) -> ab.Candidatas:
    return ab.calcular_candidatas(con, "hi", particion.HASTA["desarrollo"], "desarrollo", 24)


def _mejor(cand: ab.Candidatas, cfg: ab.ConfigAbanicos) -> pd.Series:
    p = ab.puntuar_estructuras(cand.estructuras, cfg)
    return cand.estructuras.assign(p=p).sort_values(["p", "idx"], ascending=[False, True]).iloc[0]


def test_regla_simple_elige_al_comercio(cand_dev, ids) -> None:
    top = _mejor(cand_dev, ab.REGLA_SIMPLE)
    assert top.centro == ids["COMERCIO"] and top.direccion == "entrada"
    assert top.n_contrapartes == 20


def test_forma_elige_el_abanico_de_lavado(cand_dev, ids) -> None:
    cfg = ab.ConfigAbanicos(24, 3, False, ("unicidad", "mezcla_monedas"), "log2")
    top = _mejor(cand_dev, cfg)
    assert top.centro == ids["HUB_SALIDA"] and top.direccion == "salida"
    assert top.n_contrapartes == 6
    assert top.unicidad == pytest.approx(6 / 7)  # una hoja recibe dos transferencias idénticas


def test_variables_del_comercio(cand_dev, ids) -> None:
    e = cand_dev.estructuras
    com = e[(e.centro == ids["COMERCIO"]) & (e.direccion == "entrada")]
    # en la ventana sin desfase caen los dos pagos de cada cliente (8 h y 14 h)
    assert com[com.desfase == 0].unicidad.max() == pytest.approx(0.5)
    assert com.mezcla_monedas.max() == 0.0
    assert com.formato.max() == 1.0


def test_variables_en_rango(cand_dev) -> None:
    for v in ab.VARIABLES_FORMA:
        assert cand_dev.estructuras[v].between(0, 1).all(), v


def test_mapa_cubre_el_periodo(con, cand_dev) -> None:
    n = con.execute("SELECT count(*) FROM hi.aristas WHERE periodo = 'desarrollo'").fetchone()[0]
    assert len(cand_dev.mapa) == n
    assert cand_dev.indices.shape == (n, 4)


def test_detector_no_ve_el_futuro(con, ids) -> None:
    """En desarrollo, el abanico de entrada del día 8 no existe."""
    cand = ab.calcular_candidatas(con, "hi", particion.HASTA["desarrollo"], "desarrollo", 96)
    assert cand.estructuras.fin_ventana.max() <= pd.Timestamp("2022-09-07") + pd.Timedelta(hours=96)
    e = cand.estructuras
    assert e[(e.centro == ids["HUB_ENTRADA"]) & (e.direccion == "entrada")].empty


def test_ventanas_no_dependen_de_la_zona_horaria(cand_dev) -> None:
    inicios = cand_dev.estructuras.inicio_ventana
    assert set(inicios.dt.hour) <= {0, 12}


def test_por_formato_separa_canales(con, ids) -> None:
    cand = ab.calcular_candidatas(
        con, "hi", particion.HASTA["desarrollo"], "desarrollo", 24, por_formato=True
    )
    assert set(cand.estructuras.formato) == {1.0}


def test_puntuar_transacciones_y_cuentas() -> None:
    estructuras = pd.DataFrame({"n_contrapartes": [4, 8], "unicidad": [1.0, 0.5]})
    cand = ab.Candidatas(
        24,
        3,
        False,
        None,
        estructuras,
        pd.DataFrame(),
        np.array([[0, -1, 1, -1], [-1, -1, -1, -1]]),
    )
    p_estr = ab.puntuar_estructuras(estructuras, ab.ConfigAbanicos(variables=("unicidad",)))
    np.testing.assert_allclose(p_estr, [2.0, 1.5])
    p_tx = ab.puntuar_transacciones(cand, p_estr)
    np.testing.assert_allclose(p_tx, [2.0, 0.0])
    assert ab.direccion_dominante(cand, p_estr).tolist() == ["salida", "salida"]
    p_cta = ab.puntuar_cuentas(np.array([0, 1]), np.array([2, 2]), p_tx, 3)
    np.testing.assert_allclose(p_cta, [2.0, 0.0, 2.0])


def test_variable_desconocida() -> None:
    with pytest.raises(ValueError):
        ab.puntuar_estructuras(
            pd.DataFrame({"n_contrapartes": [3]}), ab.ConfigAbanicos(variables=("color",))
        )

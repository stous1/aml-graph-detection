"""Pruebas de los detectores del hito 2 sobre el mini-AMLworld."""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lavado import combinacion, flujo_hito2, ingesta, particion, paso, variables_cuenta
from lavado.detectores import abanicos as ab
from lavado.detectores import aislamiento as ai
from lavado.detectores import cadenas as ca
from lavado.detectores import ciclos as ci
from lavado.detectores import dispersion as di

DESARROLLO, FIN = particion.HASTA["desarrollo"], particion.FIN_VENTANA


def _cuenta(con, mini_raw, nombre: str) -> int:
    llave = mini_raw.especiales[nombre].llave
    return con.execute("SELECT cuenta_id FROM hi.cuentas WHERE llave = ?", [llave]).fetchone()[0]


def _lavado_de(con, origen: int) -> list[int]:
    return [
        r[0]
        for r in con.execute(
            "SELECT tx_id FROM hi.transacciones WHERE origen = ? AND es_lavado ORDER BY ts",
            [origen],
        ).fetchall()
    ]


@pytest.fixture
def con_rw(tmp_path: Path, ruta_base: Path):
    """Conexión escribible a una copia (los detectores crean tablas temporales)."""
    base = tmp_path / "base.duckdb"
    shutil.copy(ruta_base, base)
    conexion = ingesta.conectar(base)
    yield conexion
    conexion.close()


def test_pares_de_paso_de_la_cadena(con_rw, mini_raw) -> None:
    paso.crear_pares_paso(con_rw, "hi", DESARROLLO, 96, 0.05, "pp")
    c0 = _cuenta(con_rw, mini_raw, "CADENA_0")
    pares = con_rw.execute(
        "SELECT count(*) FROM pp WHERE tx_in IN (SELECT tx_id FROM hi.aristas "
        "WHERE origen BETWEEN ? AND ? + 0 OR origen = ?)",
        [c0, c0, c0],
    ).fetchone()[0]
    assert pares >= 1
    # el par de paso exige salida posterior y monto parecido
    malos = con_rw.execute(
        "SELECT count(*) FROM pp WHERE ts_out <= ts_in OR abs(ln(usd_out / usd_in)) > ln(1.05)"
    ).fetchone()[0]
    assert malos == 0


def test_ciclos_encuentra_el_anillo_y_respeta_el_tiempo(con_rw, mini_raw) -> None:
    a0 = _cuenta(con_rw, mini_raw, "ANILLO_0")
    ciclos = ci.encontrar_ciclos(con_rw, "hi", DESARROLLO, ci.ConfigCiclos(tolerancia=0.05))
    anillo = set(_lavado_de(con_rw, a0))
    assert any(set(t) & anillo and s == 3 for t, s in zip(ciclos.txs, ciclos.saltos, strict=True))
    # el ciclo puente (cierra el día 7) no existe mirando solo desarrollo
    a = _cuenta(con_rw, mini_raw, "CICLO_A")
    puente = set(_lavado_de(con_rw, a))
    assert not any(set(t) & puente for t in ciclos.txs)
    # con toda la ventana sí aparece
    todos = ci.encontrar_ciclos(con_rw, "hi", FIN, ci.ConfigCiclos(tolerancia=0.2))
    assert any(set(t) & puente for t in todos.txs)
    # el anillo pierde 0,7 % por salto: con tolerancia de 0,5 % ya no es un ciclo
    estrictos = ci.encontrar_ciclos(con_rw, "hi", DESARROLLO, ci.ConfigCiclos(tolerancia=0.005))
    assert not any(set(t) & anillo for t in estrictos.txs)


def test_cadenas_largo(con_rw, mini_raw) -> None:
    c0 = _cuenta(con_rw, mini_raw, "CADENA_0")
    largos = ca.largo_cadenas(con_rw, "hi", DESARROLLO, ca.ConfigCadenas(96, 0.05))
    primera = _lavado_de(con_rw, c0)[0]
    assert largos.set_index("tx_id").loc[primera, "largo"] == 4


def test_dispersion_concentracion(con_rw, mini_raw) -> None:
    s = _cuenta(con_rw, mini_raw, "SG_ORIGEN")
    t = _cuenta(con_rw, mini_raw, "SG_DESTINO")
    estr, por_tx = di.dispersion_concentracion(con_rw, "hi", FIN, di.ConfigDispersion(96, 0.05))
    fila = estr[(estr.origen == s) & (estr.destino == t)]
    assert len(fila) == 1 and fila.intermediarias.iloc[0] == 3
    assert (por_tx.puntaje == 3).sum() >= 6
    estr_dev, _ = di.dispersion_concentracion(con_rw, "hi", DESARROLLO, di.ConfigDispersion())
    assert estr_dev[(estr_dev.origen == s)].empty  # no ve el futuro


def test_concentracion_dispersion_variables(con_rw) -> None:
    estr, _ = di.concentracion_dispersion(con_rw, "hi", FIN, di.ConfigConcentracion())
    assert (estr.n_in >= 2).all() and (estr.n_out >= 2).all()
    assert estr.balance.between(0, 1).all()


def test_variables_por_cuenta(con_rw, mini_raw) -> None:
    v = variables_cuenta.calcular(con_rw, "hi", particion.DESDE["desarrollo"], DESARROLLO)
    c0 = _cuenta(con_rw, mini_raw, "CADENA_0")
    intermedia = con_rw.execute(
        "SELECT destino FROM hi.transacciones WHERE origen = ? AND es_lavado", [c0]
    ).fetchone()[0]
    fila = v.set_index("cuenta_id").loc[intermedia]
    assert fila.frac_paso == 1.0 and fila.velocidad_horas == pytest.approx(1.0)
    assert fila.balance == pytest.approx(2490 / 2500)
    cols = list(variables_cuenta.ESTRUCTURALES) + list(variables_cuenta.SOSPECHOSAS)
    assert not v[cols].isna().any().any()


def test_aislamiento_determinista(con_rw) -> None:
    cfg = ai.ConfigAislamiento(False, "min")
    a = ai.puntuar(con_rw, "hi", "desarrollo", cfg)
    b = ai.puntuar(con_rw, "hi", "desarrollo", cfg)
    np.testing.assert_array_equal(a.tx, b.tx)
    assert (a.cuenta >= 0).all()


def test_percentiles_y_combinacion() -> None:
    ref = combinacion.Percentiles.desde(np.array([0.0, 0.0, 1.0, 2.0, 3.0]))
    np.testing.assert_allclose(ref.aplicar(np.array([0.0, 1.0, 2.5, 9.0])), [0, 0.6, 0.8, 1.0])
    p = [np.array([0.0, 0.5, 0.9]), np.array([0.2, 0.5, 0.0])]
    np.testing.assert_allclose(combinacion.combinar(p, "max"), [0.2, 0.5, 0.9])
    np.testing.assert_allclose(combinacion.combinar(p, "media"), [0.1, 0.5, 0.45])
    np.testing.assert_allclose(combinacion.combinar(p, "noisy_or"), [0.2, 0.75, 0.9])
    with pytest.raises(ValueError):
        combinacion.combinar(p, "otro")


def test_detectores_sin_sospechosas_no_las_usan() -> None:
    """Un detector declarado estructural no puede usar moneda ni formato."""
    h1 = ab.ConfigAbanicos(96, 3, True, ("unicidad", "mezcla_monedas"), "log2")
    for det in flujo_hito2.detectores(h1):
        if det.sospechosas:
            continue
        for cfg in det.configs:
            if isinstance(cfg, ab.ConfigAbanicos):
                assert not set(cfg.variables) & set(flujo_hito2.SOSPECHOSAS_ABANICOS), det.nombre
                assert not cfg.por_formato, det.nombre
            if isinstance(cfg, ai.ConfigAislamiento):
                assert not cfg.sospechosas, det.nombre
    for nombre in flujo_hito2.COMBINADOS["combinado_forma"]:
        det = next(d for d in flujo_hito2.detectores(h1) if d.nombre == nombre)
        assert not det.sospechosas


def test_abanicos_por_direccion(con_rw) -> None:
    cand = ab.calcular_candidatas(con_rw, "hi", DESARROLLO, "desarrollo", 24)
    p = ab.puntuar_estructuras(
        cand.estructuras, ab.ConfigAbanicos(variables=(), direccion="entrada")
    )
    assert (p[cand.estructuras.direccion.to_numpy() == "salida"] == 0).all()
    assert (p[cand.estructuras.direccion.to_numpy() == "entrada"] > 0).all()


@pytest.mark.integracion
def test_flujo_hito2(con_rw, tmp_path: Path) -> None:
    h1 = {
        "ventana_horas": 96,
        "min_contrapartes": 3,
        "por_formato": True,
        "variables": ["unicidad", "mezcla_monedas"],
        "tamano": "log2",
    }
    nombres = (
        "regla_simple",
        "abanicos_h1",
        "abanicos_h1_sin_monedas",
        "ciclos",
        "cadenas",
        "dispersion_concentracion",
        "aislamiento_forma",
    )
    salida = tmp_path / "hito2"
    parametros = flujo_hito2.desarrollar(con_rw, ingesta.VARIANTES, salida, h1, nombres)
    metricas = flujo_hito2.evaluar(con_rw, parametros, h1, ingesta.VARIANTES, salida)
    for nombre in (
        "parametros.json",
        "desarrollo.json",
        "metricas.json",
        "detectores_top100.png",
        "detectores_f1.png",
    ):
        assert (salida / nombre).exists(), nombre
    texto = (salida / "metricas.json").read_text(encoding="utf-8").lower()
    assert "exactitud" not in texto and "accuracy" not in texto
    assert set(metricas["variantes"]["hi"]) == set(nombres)
    tabla = flujo_hito2.tabla_resumen(metricas)
    assert isinstance(tabla, pd.DataFrame) and set(tabla.variante) == {"HI", "LI"}
    # cada detector trae las métricas de la regla de evaluación
    for m in metricas["variantes"]["li"].values():
        assert {"f1_transaccion", "f1_cuenta", "precision_k", "recall_tipo"} <= set(m)

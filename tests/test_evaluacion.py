"""Pruebas de las métricas con valores calculados a mano."""

import numpy as np
import pandas as pd
import pytest

from lavado import evaluacion as ev


def test_wilson_valor_conocido() -> None:
    inf, sup = ev.wilson(8, 10)
    assert inf == pytest.approx(0.4902, abs=1e-4)
    assert sup == pytest.approx(0.9433, abs=1e-4)


def test_precision_en_k_con_empates_por_id() -> None:
    puntaje = np.array([0.9, 0.5, 0.5, 0.1, 0.0])
    y = np.array([1, 0, 1, 1, 0], dtype=bool)
    ids = np.array([10, 30, 20, 40, 50])
    r = ev.precision_en_k(puntaje, y, ids, [1, 2, 3, 10])
    # empate 0.5: gana el id 20 (positivo) sobre el 30
    assert [x["aciertos"] for x in r] == [1, 2, 2, 3]
    assert r[1]["precision"] == 1.0
    assert r[3]["k"] == 5  # k se recorta al universo


def test_mejor_umbral_f1() -> None:
    puntaje = np.array([0.9, 0.8, 0.7, 0.6, 0.0])
    y = np.array([1, 1, 0, 1, 1], dtype=bool)
    m = ev.mejor_umbral_f1(puntaje, y)
    # umbral 0.6: tp=3, fp=1, fn=1 -> F1 = 0.75; umbral 0.8: tp=2, fn=2 -> 0.667
    assert m["umbral"] == 0.6
    assert m["f1"] == pytest.approx(0.75)


def test_mejor_umbral_sin_puntajes() -> None:
    m = ev.mejor_umbral_f1(np.zeros(3), np.array([1, 0, 0], dtype=bool))
    assert m["f1"] == 0.0 and m["umbral"] == float("inf")


def test_f1_en_umbral_y_bootstrap_determinista() -> None:
    puntaje = np.array([0.9, 0.8, 0.7, 0.6, 0.0])
    y = np.array([1, 1, 0, 1, 1], dtype=bool)
    grupos = np.array([1, 1, 2, 3, 3])
    a = ev.f1_en_umbral(puntaje, y, 0.6, grupos=grupos)
    b = ev.f1_en_umbral(puntaje, y, 0.6, grupos=grupos)
    assert (a["tp"], a["fp"], a["fn"]) == (3, 1, 1)
    assert a["f1"] == pytest.approx(0.75)
    assert a["f1_ic"] == b["f1_ic"]
    assert "exactitud" not in a and "accuracy" not in a


def test_recall_por_tipo_e_ignoradas() -> None:
    tx = pd.DataFrame(
        {
            "tx_id": range(8),
            "origen": 0,
            "destino": 1,
            "y": [True] * 7 + [False],
            "ignorada": [False, False, False, False, True, False, False, False],
            "intento_id": [0, 0, 0, 1, 2, None, None, None],
            "tipo": ["FAN-OUT"] * 3 + ["FAN-OUT", "CYCLE", "SIN_PATRON", "SIN_PATRON", None],
        }
    )
    u = ev.Universo("prueba", tx, pd.DataFrame(columns=["cuenta_id", "y", "ignorada"]))
    marcada = np.array([1, 1, 0, 0, 1, 1, 0, 0], dtype=bool)
    r = ev.recall_por_tipo(u, marcada).set_index("tipo")
    # intento 0: 2/3 marcadas >= 0.5 -> detectado; intento 1: no. CYCLE es puente: fuera.
    assert r.loc["FAN-OUT", "n"] == 2 and r.loc["FAN-OUT", "recall"] == 0.5
    assert "CYCLE" not in r.index
    assert r.loc["SIN_PATRON", "recall"] == 0.5
    r3 = ev.recall_por_tipo(u, marcada, min_tx=3).set_index("tipo")
    assert r3.loc["FAN-OUT", "n"] == 1 and r3.loc["FAN-OUT", "recall"] == 1.0


def test_universo_excluye_cuentas_solo_puente(con) -> None:
    u = ev.cargar_universo(con, "hi", "prueba")
    ciclo_c = con.execute(
        "SELECT destino FROM hi.transacciones t JOIN hi.etiquetas l USING (tx_id) "
        "WHERE l.tipo = 'CYCLE' AND t.periodo = 'prueba' ORDER BY ts LIMIT 1"
    ).fetchone()[0]
    fila = u.cuentas.set_index("cuenta_id").loc[ciclo_c]
    assert bool(fila.ignorada) and not bool(fila.y)
    # 8 hojas del abanico de entrada + su centro + 5 cuentas de la dispersión-concentración
    assert int(u.cuentas.y.sum()) == 14

"""Pruebas de las consultas pensadas para el futuro agente."""

import inspect
from datetime import datetime

import pytest

from lavado import consultas, grafo


def test_transacciones_cuenta_respeta_hasta(con, ids) -> None:
    hub = ids["HUB_ENTRADA"]
    todo = consultas.transacciones_cuenta(con, "hi", hub)
    antes = consultas.transacciones_cuenta(con, "hi", hub, hasta=datetime(2022, 9, 8))
    assert (todo.direccion == "entrada").sum() == 8  # la del día 12 está en la cola
    assert (antes.direccion == "entrada").sum() == 0
    assert antes.ts.max() < datetime(2022, 9, 8)
    assert set(todo.columns) >= {"tx_id", "contraparte", "direccion", "monto_usd"}


def test_vecinos_dos_saltos(con, ids) -> None:
    v1 = consultas.vecinos(con, "hi", ids["CICLO_A"], "salida", saltos=1)
    v2 = consultas.vecinos(con, "hi", ids["CICLO_A"], "salida", saltos=2)
    assert ids["CICLO_B"] in v1.cuenta_id.tolist()
    assert ids["CICLO_C"] in v2[v2.salto == 2].cuenta_id.tolist()
    assert ids["CICLO_A"] not in v2.cuenta_id.tolist()


def test_flujo_temporal_suma(con, ids) -> None:
    hub = ids["HUB_SALIDA"]
    f = consultas.flujo_temporal(con, "hi", hub, paso_horas=24)
    tx = consultas.transacciones_cuenta(con, "hi", hub)
    assert f.n_salida.sum() == (tx.direccion == "salida").sum()
    assert f.usd_salida.sum() == pytest.approx(tx[tx.direccion == "salida"].monto_usd.sum())
    assert set(f.inicio.dt.hour) == {0}


def test_patrones_detectados_sin_tabla(con, ids) -> None:
    assert consultas.patrones_detectados(con, "hi", ids["HUB_SALIDA"]).empty


def test_consultas_no_leen_etiquetas() -> None:
    for modulo in (consultas, grafo):
        fuente = inspect.getsource(modulo)
        codigo = fuente.split('"""', 2)[2]  # sin la docstring del módulo
        for prohibido in ("es_lavado", ".etiquetas", ".patrones", ".intentos"):
            assert prohibido not in codigo, (modulo.__name__, prohibido)


def test_subgrafo_igraph(con, ids) -> None:
    g = grafo.aristas_entre(con, "hi", [ids["CICLO_A"], ids["CICLO_B"], ids["CICLO_C"]])
    assert g.is_directed()
    assert g.ecount() == 3
    assert sorted(g.vs["cuenta_id"]) == sorted([ids["CICLO_A"], ids["CICLO_B"], ids["CICLO_C"]])

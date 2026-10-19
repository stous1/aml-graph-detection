"""Pruebas de la partición temporal, los intentos puente y la cola."""

from datetime import datetime

import duckdb

from lavado import particion


def test_periodo_bordes() -> None:
    assert particion.periodo(datetime(2022, 9, 1, 23, 59)) == "arranque"
    assert particion.periodo(datetime(2022, 9, 2)) == "desarrollo"
    assert particion.periodo(datetime(2022, 9, 6, 23, 59)) == "desarrollo"
    assert particion.periodo(datetime(2022, 9, 7)) == "prueba"
    assert particion.periodo(datetime(2022, 9, 10, 23, 59)) == "prueba"
    assert particion.periodo(datetime(2022, 9, 11)) == "cola"


def test_periodo_sql_coincide_con_python(con: duckdb.DuckDBPyConnection) -> None:
    df = con.execute("SELECT ts, periodo FROM hi.transacciones").df()
    assert (df.ts.map(particion.periodo) == df.periodo).all()


def test_ciclo_es_puente_y_sus_tx_se_ignoran(con: duckdb.DuckDBPyConnection) -> None:
    puentes = con.execute("SELECT tipo, detalle FROM hi.intentos WHERE es_puente").fetchall()
    assert puentes == [("CYCLE", "Max 3 hops")]
    assert con.execute("SELECT count(*) FROM hi.intentos").fetchone()[0] == 6
    ign = con.execute(
        "SELECT tipo, count(*) FROM hi.etiquetas WHERE ignorada GROUP BY tipo"
    ).fetchall()
    assert ign == [("CYCLE", 3)]


def test_sin_patron_y_cola(con: duckdb.DuckDBPyConnection) -> None:
    sin = con.execute("SELECT count(*) FROM hi.etiquetas WHERE tipo = 'SIN_PATRON'").fetchone()[0]
    assert sin == 1
    # la transferencia del día 12 queda en la cola y fuera de las aristas
    cola = con.execute("SELECT count(*) FROM hi.transacciones WHERE periodo = 'cola'").fetchone()
    assert cola[0] == 1
    assert con.execute("SELECT count(*) FROM hi.aristas WHERE periodo = 'cola'").fetchone()[0] == 0


def test_conteo_intentos(con: duckdb.DuckDBPyConnection) -> None:
    c = particion.conteo_intentos(con, "hi").set_index("tipo")
    assert c.loc["FAN-OUT", "desarrollo"] == 1
    assert c.loc["FAN-IN", "prueba"] == 1
    assert c.loc["CYCLE", "puente"] == 1
    assert c.loc["CYCLE", "desarrollo"] == 1
    assert c.loc["SCATTER-GATHER", "prueba"] == 1

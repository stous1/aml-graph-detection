"""Pruebas de ingesta, patrones y tasas sobre el mini-AMLworld."""

import duckdb
import pandas as pd
import pytest

from lavado import ingesta, patrones, sintetico, tasas


def test_conteos_basicos(con: duckdb.DuckDBPyConnection) -> None:
    n, lavado = con.execute("SELECT count(*), sum(es_lavado::INT) FROM hi.transacciones").fetchone()
    # 400 de fondo + 50 autotransferencias + 57 de especiales + 40 del comercio
    # + lavado: 7 + 9 + 3 (ciclo puente) + 6 (dispersión) + 4 (cadena) + 3 (ciclo) + 1
    assert n == 580
    assert lavado == 33


def test_columnas_account_duplicadas_se_separan(con: duckdb.DuckDBPyConnection) -> None:
    """El CSV trae dos columnas 'Account': origen y destino no deben confundirse."""
    autos = con.execute(
        "SELECT count(*) FROM hi.transacciones WHERE es_autotransferencia"
    ).fetchone()[0]
    assert autos == 50  # solo las Reinvestment sembradas


def test_llave_de_cuenta_normaliza_banco(con: duckdb.DuckDBPyConnection) -> None:
    """'010' en transacciones y '10' en cuentas son el mismo banco."""
    sin_archivo = con.execute(
        "SELECT count(*) FROM hi.cuentas WHERE entidad_id IS NULL"
    ).fetchone()[0]
    assert sin_archivo == 0
    assert con.execute("SELECT count(*) FROM hi.cuentas WHERE llave LIKE '0%'").fetchone()[0] == 0


def test_tx_id_determinista(mini_raw: sintetico.MiniAMLworld) -> None:
    def cargar() -> pd.DataFrame:
        c = ingesta.conectar(":memory:")
        ingesta.cargar_variante(c, "hi", mini_raw.directorio)
        return c.execute("SELECT * FROM hi.transacciones ORDER BY tx_id").df()

    pd.testing.assert_frame_equal(cargar(), cargar())


def test_todos_los_patrones_cruzan(con: duckdb.DuckDBPyConnection) -> None:
    sin_cruce, n = con.execute(
        "SELECT sum((tx_id IS NULL)::INT), count(*) FROM hi.patrones"
    ).fetchone()
    assert (sin_cruce, n) == (0, 32)
    # las dos líneas idénticas del abanico de salida se emparejan con transacciones distintas
    assert con.execute("SELECT count(DISTINCT tx_id) FROM hi.patrones").fetchone()[0] == 32


def test_tasas_recuperan_las_del_generador(con: duckdb.DuckDBPyConnection) -> None:
    t = con.execute("SELECT moneda, usd_por_unidad FROM hi.tasas").df().set_index("moneda")
    for moneda, tasa in sintetico.TASAS_USD.items():
        assert t.loc[moneda, "usd_por_unidad"] == pytest.approx(tasa, rel=1e-3)


def test_tasas_moneda_sin_pares_queda_nan() -> None:
    c = duckdb.connect()
    c.execute(
        """CREATE TABLE t AS SELECT * FROM (VALUES
           (TIMESTAMP '2022-09-02', 10.0, 'Euro', 11.7, 'US Dollar'),
           (TIMESTAMP '2022-09-02', 5.0, 'Yen', 5.0, 'Yen'))
           v(ts, monto_pagado, moneda_pagada, monto_recibido, moneda_recibida)"""
    )
    r = tasas.estimar_tasas(c, "t").set_index("moneda")
    assert r.loc["Euro", "usd_por_unidad"] == pytest.approx(1.17)
    assert pd.isna(r.loc["Yen", "usd_por_unidad"])


def test_leer_patrones_formato() -> None:
    texto = (
        "BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 2 hops\n"
        "2022/09/01 00:06,021174,800737690,012,80011F990,1.00,Euro,1.00,Euro,ACH,1\n"
        "2022/09/01 00:07,012,80011F990,021174,800737690,1.00,Euro,1.00,Euro,ACH,1\n"
        "END LAUNDERING ATTEMPT - CYCLE\n\n"
        "BEGIN LAUNDERING ATTEMPT - STACK\n"
        "2022/09/02 00:06,1,A,2,B,3.00,Euro,3.00,Euro,ACH,1\n"
        "END LAUNDERING ATTEMPT - STACK\n"
    )
    df = patrones.leer_patrones(texto)
    assert df.intento_id.tolist() == [0, 0, 1]
    assert df.tipo.tolist() == ["CYCLE", "CYCLE", "STACK"]
    assert df.detalle.tolist() == ["Max 2 hops", "Max 2 hops", ""]
    assert df.orden.tolist() == [0, 1, 0]


def test_leer_patrones_rechaza_lineas_sueltas() -> None:
    with pytest.raises(ValueError):
        patrones.leer_patrones("2022/09/01 00:06,1,A,2,B,1,Euro,1,Euro,ACH,1\n")

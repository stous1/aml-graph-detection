"""Fixtures compartidas: un mini-AMLworld sintético cargado en una base DuckDB temporal."""

from pathlib import Path

import duckdb
import pytest

from lavado import grafo, ingesta, particion, sintetico


@pytest.fixture(scope="session")
def mini_raw(tmp_path_factory: pytest.TempPathFactory) -> sintetico.MiniAMLworld:
    """Archivos HI y LI del mini-AMLworld (semillas distintas)."""
    directorio = tmp_path_factory.mktemp("raw")
    mini = sintetico.generar(directorio, "HI", semilla=7)
    sintetico.generar(directorio, "LI", semilla=8)
    return mini


@pytest.fixture(scope="session")
def ruta_base(tmp_path_factory: pytest.TempPathFactory, mini_raw: sintetico.MiniAMLworld) -> Path:
    """Base DuckDB con HI y LI cargadas, etiquetas y aristas."""
    ruta = tmp_path_factory.mktemp("base") / "mini.duckdb"
    con = ingesta.conectar(ruta)
    for v in ingesta.VARIANTES:
        ingesta.cargar_variante(con, v, mini_raw.directorio)
        particion.crear_etiquetas(con, v)
        grafo.crear_aristas(con, v)
    con.close()
    return ruta


@pytest.fixture
def con(ruta_base: Path) -> duckdb.DuckDBPyConnection:
    """Conexión de solo lectura a la base del mini-AMLworld."""
    conexion = ingesta.conectar(ruta_base, solo_lectura=True)
    yield conexion
    conexion.close()


@pytest.fixture
def ids(con: duckdb.DuckDBPyConnection, mini_raw: sintetico.MiniAMLworld) -> dict[str, int]:
    """``cuenta_id`` de las cuentas especiales en HI."""
    return {
        nombre: con.execute(
            "SELECT cuenta_id FROM hi.cuentas WHERE llave = ?", [c.llave]
        ).fetchone()[0]
        for nombre, c in mini_raw.especiales.items()
    }

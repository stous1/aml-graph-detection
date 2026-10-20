"""Pruebas del universo de Cosmograph (hito 5) sobre el mini-AMLworld."""

import json
import shutil
from pathlib import Path

import pytest

from lavado import evaluacion as ev
from lavado import flujo_hito5, ingesta


@pytest.mark.integracion
def test_universo_consistente(tmp_path: Path, ruta_base: Path) -> None:
    base = tmp_path / "base.duckdb"
    shutil.copy(ruta_base, base)
    con = ingesta.conectar(base)
    puntos, enlaces, meta = flujo_hito5.universo(con, "hi")
    assert set(puntos.categoria) <= set(flujo_hito5.TEXTO_CATEGORIA)
    assert set(enlaces.categoria) <= {"detectado", "no_detectado", "alerta_falsa", "contexto"}
    ids = set(puntos.id)
    assert set(enlaces.origen) <= ids and set(enlaces.destino) <= ids
    assert list(puntos.columns) == ["id", "categoria", "tamano", "etiqueta"]
    universo = ev.cargar_universo(con, "hi", "prueba")
    tx = universo.transacciones
    assert meta["transferencias"]["lavado_total"] == int((tx.y & ~tx.ignorada).sum())
    assert sum(meta["cuentas"].values()) == len(puntos)
    flujo_hito5.escribir(puntos, enlaces, meta, tmp_path / "u", "hi")
    datos = json.loads((tmp_path / "u" / "universo_hi_meta.json").read_text(encoding="utf-8"))
    assert datos["modelo"] == "gnn_sin_coles"

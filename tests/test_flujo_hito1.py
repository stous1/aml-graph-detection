"""Flujo completo del hito 1 sobre el mini-AMLworld, y congelamiento de parámetros."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lavado import consultas, flujo_hito1, ingesta
from lavado.detectores import abanicos as ab
from lavado.rutas import DOCS_RESULTADOS_HITO1, RAIZ

TAG_CONGELADO = "hito1-congelado"


@pytest.mark.integracion
def test_flujo_completo(tmp_path: Path, ruta_base: Path) -> None:
    base = tmp_path / "base.duckdb"
    shutil.copy(ruta_base, base)
    con = ingesta.conectar(base)
    salida = tmp_path / "reports"
    flujo_hito1.explorar(con, ingesta.VARIANTES, salida)
    configs = flujo_hito1.configuraciones(ventanas=(24, 48), max_variables=2)
    parametros = flujo_hito1.desarrollar(con, ingesta.VARIANTES, salida, configs)
    metricas = flujo_hito1.evaluar(con, parametros, ingesta.VARIANTES, salida)

    for nombre in (
        "exploracion.json",
        "parametros.json",
        "desarrollo.json",
        "metricas.json",
        "por_dia.png",
        "precision_k.png",
        "recall_tipo.png",
    ):
        assert (salida / nombre).exists(), nombre
    texto = (salida / "metricas.json").read_text(encoding="utf-8").lower()
    assert "exactitud" not in texto and "accuracy" not in texto

    hi = metricas["variantes"]["hi"]
    assert set(hi) == {"detector", "regla"}
    assert "sensibilidad_umbral_hi" in metricas["variantes"]["li"]
    assert hi["detector"]["universo"]["ignoradas_puente"] == 2  # las tx del ciclo en prueba
    # La forma encuentra el abanico de entrada de prueba en HI.
    recall = {r["tipo"]: r for r in hi["detector"]["recall_tipo"]}
    assert recall["FAN-IN"]["recall"] == 1.0
    # Las estructuras quedan disponibles para las consultas.
    estr = con.execute("SELECT DISTINCT detector FROM hi.estructuras").fetchall()
    assert {e[0] for e in estr} <= {"abanicos", "regla_simple"}


def test_configuraciones_deterministas() -> None:
    a = flujo_hito1.configuraciones(ventanas=(24,), max_variables=1)
    assert a == flujo_hito1.configuraciones(ventanas=(24,), max_variables=1)
    assert len(a) == 2 * (1 + len(ab.VARIABLES_FORMA)) * len(flujo_hito1.TAMANOS)


def test_patrones_detectados_lee_estructuras(tmp_path: Path, ruta_base: Path) -> None:
    base = tmp_path / "base.duckdb"
    shutil.copy(ruta_base, base)
    con = ingesta.conectar(base)
    cfg = ab.ConfigAbanicos(24, 3, False, ("unicidad", "mezcla_monedas"), "log2")
    flujo_hito1.guardar_estructuras(con, "hi", {"abanicos": (cfg, 0.5)})
    hub = con.execute(
        "SELECT centro FROM hi.estructuras ORDER BY puntaje DESC, centro LIMIT 1"
    ).fetchone()[0]
    det = consultas.patrones_detectados(con, "hi", hub)
    assert not det.empty and (det.detector == "abanicos").all()


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8"
    )


def test_parametros_congelados_no_cambian() -> None:
    """Si existe el tag, ``parametros.json`` publicado debe ser idéntico al del tag."""
    ruta = DOCS_RESULTADOS_HITO1 / "parametros.json"
    if shutil.which("git") is None or _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("sin git")
    if _git("rev-parse", "-q", "--verify", f"refs/tags/{TAG_CONGELADO}").returncode != 0:
        pytest.skip("todavía no hay tag de congelamiento")
    congelado = _git("show", f"{TAG_CONGELADO}:docs/resultados/hito1/parametros.json")
    assert congelado.returncode == 0
    assert json.loads(congelado.stdout) == json.loads(ruta.read_text(encoding="utf-8"))

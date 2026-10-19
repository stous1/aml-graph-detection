"""Rutas del proyecto, centralizadas y relativas a la raíz del repositorio."""

from pathlib import Path

RAIZ: Path = Path(__file__).resolve().parents[2]

DATA: Path = RAIZ / "data"
DATA_RAW: Path = DATA / "raw"
BASE_DUCKDB: Path = DATA / "aml.duckdb"

REPORTS: Path = RAIZ / "reports"
REPORTS_HITO1: Path = REPORTS / "hito1"

DOCS: Path = RAIZ / "docs"
DOCS_RESULTADOS: Path = DOCS / "resultados"
DOCS_RESULTADOS_HITO1: Path = DOCS_RESULTADOS / "hito1"

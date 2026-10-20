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
REPORTS_HITO2: Path = REPORTS / "hito2"
DOCS_RESULTADOS_HITO2: Path = DOCS_RESULTADOS / "hito2"
REPORTS_HITO3: Path = REPORTS / "hito3"
DOCS_RESULTADOS_HITO3: Path = DOCS_RESULTADOS / "hito3"
REPORTS_HITO4: Path = REPORTS / "hito4"
DOCS_RESULTADOS_HITO4: Path = DOCS_RESULTADOS / "hito4"
DOCS_RESULTADOS_HITO5: Path = DOCS_RESULTADOS / "hito5"
DOCS_RESULTADOS_DEMO: Path = DOCS_RESULTADOS / "demo"

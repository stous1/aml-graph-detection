"""Hito 1: ingesta, exploración, desarrollo y evaluación de abanicos contra la regla simple.

Uso:
    uv run python scripts/hito1.py preparar [--forzar]   # CSV -> data/aml.duckdb
    uv run python scripts/hito1.py explorar             # -> reports/hito1/exploracion.json
    uv run python scripts/hito1.py desarrollar          # -> reports/hito1/parametros.json
    uv run python scripts/hito1.py evaluar              # usa docs/resultados/hito1/parametros.json

``evaluar`` lee los parámetros **congelados** (publicados y con tag ``hito1-congelado``), no
los de ``reports/``: prueba se mide una sola vez con lo que quedó fijo.
"""

import argparse
import json

from lavado import flujo_hito1, ingesta
from lavado.rutas import DOCS_RESULTADOS_HITO1, REPORTS_HITO1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paso", choices=["preparar", "explorar", "desarrollar", "evaluar"])
    parser.add_argument("--forzar", action="store_true", help="recarga los CSV")
    args = parser.parse_args()

    con = ingesta.conectar()
    variantes = ingesta.VARIANTES
    if args.paso == "preparar":
        print(json.dumps(flujo_hito1.preparar(con, variantes, forzar=args.forzar), indent=2))
        return
    flujo_hito1.preparar(con, variantes)
    if args.paso == "explorar":
        flujo_hito1.explorar(con, variantes, REPORTS_HITO1)
    elif args.paso == "desarrollar":
        parametros = flujo_hito1.desarrollar(con, variantes, REPORTS_HITO1)
        print(json.dumps(parametros, indent=2, ensure_ascii=False))
    else:
        ruta = DOCS_RESULTADOS_HITO1 / "parametros.json"
        if not ruta.exists():
            raise SystemExit(f"Faltan los parámetros congelados: {ruta}")
        parametros = json.loads(ruta.read_text(encoding="utf-8"))
        flujo_hito1.evaluar(con, parametros, variantes, REPORTS_HITO1)
    print(f"Salidas en {REPORTS_HITO1}")


if __name__ == "__main__":
    main()

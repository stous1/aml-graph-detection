"""Hito 2: más detectores por forma, variables por cuenta, combinación y ablación de monedas.

Uso:
    uv run python scripts/hito2.py desarrollar   # -> reports/hito2/parametros.json
    uv run python scripts/hito2.py evaluar       # usa docs/resultados/hito2/parametros.json

``evaluar`` lee los parámetros **congelados** (tag ``hito2-congelado``). El período de prueba
es el mismo que ya se usó en el hito 1: se mide una sola vez al final del hito 2.
"""

import argparse
import json

from lavado import flujo_hito1, flujo_hito2, ingesta
from lavado.rutas import DOCS_RESULTADOS_HITO2, REPORTS_HITO2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paso", choices=["desarrollar", "evaluar"])
    args = parser.parse_args()

    con = ingesta.conectar()
    variantes = ingesta.VARIANTES
    flujo_hito1.preparar(con, variantes)
    congelado_h1 = flujo_hito2.congelado_hito1()
    if args.paso == "desarrollar":
        flujo_hito2.desarrollar(con, variantes, REPORTS_HITO2, congelado_h1)
    else:
        ruta = DOCS_RESULTADOS_HITO2 / "parametros.json"
        if not ruta.exists():
            raise SystemExit(f"Faltan los parámetros congelados: {ruta}")
        parametros = json.loads(ruta.read_text(encoding="utf-8"))
        flujo_hito2.evaluar(con, parametros, congelado_h1, variantes, REPORTS_HITO2)
    print(f"Salidas en {REPORTS_HITO2}")


if __name__ == "__main__":
    main()

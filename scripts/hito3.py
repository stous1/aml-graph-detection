"""Hito 3: CoLES, aporte sobre el combinado estructural y "no te pareces a ti mismo".

Uso:
    uv run python scripts/hito3.py desarrollar   # entrena CoLES y elige en desarrollo
    uv run python scripts/hito3.py evaluar       # usa docs/resultados/hito3 (congelado)

``evaluar`` carga los modelos y parámetros **congelados** (tag ``hito3-congelado``). El
período de prueba es el mismo de los hitos 1 y 2: se mide una sola vez al final del hito 3.
"""

import argparse
import json

from lavado import flujo_hito1, flujo_hito2, flujo_hito3, ingesta
from lavado.rutas import DOCS_RESULTADOS_HITO3, REPORTS_HITO3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paso", choices=["desarrollar", "evaluar"])
    args = parser.parse_args()

    con = ingesta.conectar()
    variantes = ingesta.VARIANTES
    flujo_hito1.preparar(con, variantes)
    h1 = flujo_hito2.congelado_hito1()
    params_h2 = flujo_hito3.parametros_hito2()
    if args.paso == "desarrollar":
        flujo_hito3.desarrollar(con, variantes, REPORTS_HITO3, h1, params_h2)
    else:
        ruta = DOCS_RESULTADOS_HITO3 / "parametros.json"
        if not ruta.exists():
            raise SystemExit(f"Faltan los parámetros congelados: {ruta}")
        parametros = json.loads(ruta.read_text(encoding="utf-8"))
        flujo_hito3.evaluar(
            con,
            parametros,
            params_h2,
            h1,
            variantes,
            DOCS_RESULTADOS_HITO3 / "modelos",
            REPORTS_HITO3,
        )
    print(f"Salidas en {REPORTS_HITO3}")


if __name__ == "__main__":
    main()

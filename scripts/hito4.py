"""Hito 4: anomalías en el grafo (PyGOD) y red neuronal supervisada sobre el grafo.

Uso (con GPU: ``uv sync --no-group cpu --group gpu`` una vez y ``uv run --no-sync``):
    uv run python scripts/hito4.py desarrollar   # entrena con etiquetas de desarrollo
    uv run python scripts/hito4.py evaluar       # usa docs/resultados/hito4 (congelado)

``evaluar`` carga modelos, estadísticas y fracciones de alertas **congelados** (tag
``hito4-congelado``) y puntúa en CPU. El período de prueba es el mismo de los hitos 1 a 3.
"""

import argparse
import json

from lavado import flujo_hito1, flujo_hito2, flujo_hito4, gnn, ingesta
from lavado.rutas import DOCS_RESULTADOS_HITO4, REPORTS_HITO4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paso", choices=["desarrollar", "evaluar"])
    args = parser.parse_args()

    con = ingesta.conectar()
    variantes = ingesta.VARIANTES
    flujo_hito1.preparar(con, variantes)
    h1 = flujo_hito2.congelado_hito1()
    print(f"Dispositivo de entrenamiento: {gnn.dispositivo_disponible()}")
    if args.paso == "desarrollar":
        flujo_hito4.desarrollar(con, variantes, REPORTS_HITO4, h1)
    else:
        ruta = DOCS_RESULTADOS_HITO4 / "parametros.json"
        if not ruta.exists():
            raise SystemExit(f"Faltan los parámetros congelados: {ruta}")
        parametros = json.loads(ruta.read_text(encoding="utf-8"))
        flujo_hito4.evaluar(
            con, parametros, h1, variantes, DOCS_RESULTADOS_HITO4 / "modelos", REPORTS_HITO4
        )
    print(f"Salidas en {REPORTS_HITO4}")


if __name__ == "__main__":
    main()

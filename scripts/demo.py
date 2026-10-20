"""Datos de la página interactiva (docs/demo.html), sobre el período de prueba.

Uso:
    uv run python scripts/demo.py   # -> docs/resultados/demo/*.json

Aplica modelos y parámetros congelados; no entrena ni elige nada.
"""

from lavado import demo, flujo_hito1, ingesta
from lavado.rutas import DOCS_RESULTADOS_DEMO


def main() -> None:
    con = ingesta.conectar()
    flujo_hito1.preparar(con, ingesta.VARIANTES)
    curvas = demo.generar(con, ingesta.VARIANTES, DOCS_RESULTADOS_DEMO)
    for v, c in curvas.items():
        print(v, c["cuentas"], "cuentas;", {m: len(x) for m, x in c["metodos"].items()})


if __name__ == "__main__":
    main()

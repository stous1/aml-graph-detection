"""¿Aporta el grafo? La GNN final contra la misma red sin paso de mensajes.

Uso (con GPU: ``uv run --no-sync``):
    uv run python scripts/diagnostico_grafo.py desarrollo   # entrena y compara en el día 6
    uv run python scripts/diagnostico_grafo.py prueba       # solo diagnóstico, una vez

La decisión se toma con desarrollo; prueba se informa solo como diagnóstico.
"""

import argparse

from lavado import flujo_hito1, flujo_hito4, ingesta
from lavado.rutas import DOCS_RESULTADOS_HITO4

DESTINO = DOCS_RESULTADOS_HITO4 / "diagnostico_grafo"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paso", choices=["desarrollo", "prueba"])
    args = parser.parse_args()
    con = ingesta.conectar()
    flujo_hito1.preparar(con, ingesta.VARIANTES)
    if args.paso == "desarrollo":
        flujo_hito4.diagnostico_grafo(con, ingesta.VARIANTES, DOCS_RESULTADOS_HITO4, DESTINO)
    else:
        flujo_hito4.diagnostico_grafo_prueba(
            con, ingesta.VARIANTES, DOCS_RESULTADOS_HITO4, DESTINO, DESTINO
        )
    print(f"Salidas en {DESTINO}")


if __name__ == "__main__":
    main()

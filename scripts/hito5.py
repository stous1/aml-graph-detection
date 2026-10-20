"""Hito 5: datos del universo de Cosmograph (prueba, modelo final congelado).

Uso:
    uv run python scripts/hito5.py   # -> docs/resultados/hito5/universo_{hi,li}_*.json

No entrena ni elige nada: aplica el modelo final congelado del hito 4 y verifica que el recall
por tipo coincida con docs/resultados/hito4/metricas.json.
"""

from lavado import flujo_hito1, flujo_hito5, ingesta
from lavado.rutas import DOCS_RESULTADOS_HITO5


def main() -> None:
    con = ingesta.conectar()
    flujo_hito1.preparar(con, ingesta.VARIANTES)
    for v in ingesta.VARIANTES:
        puntos, enlaces, meta = flujo_hito5.universo(con, v)
        flujo_hito5.verificar_contra_hito4(meta, v)
        flujo_hito5.escribir(puntos, enlaces, meta, DOCS_RESULTADOS_HITO5, v)
        print(v, meta["puntos"], "puntos,", meta["enlaces"], "enlaces,", meta["cuentas"])


if __name__ == "__main__":
    main()

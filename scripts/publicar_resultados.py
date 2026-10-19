"""Copia los resultados finales de ``reports/`` a ``docs/resultados/`` (versionado, Pages).

Uso:
    uv run python scripts/publicar_resultados.py --hito 1 --solo-parametros  # para congelar
    uv run python scripts/publicar_resultados.py --hito 1                    # todo, tras evaluar
"""

import argparse
import shutil

from lavado.rutas import DOCS_RESULTADOS_HITO1, REPORTS_HITO1

PARAMETROS = ("parametros.json", "desarrollo.json")
RESULTADOS = (
    "exploracion.json",
    "metricas.json",
    "por_dia.html",
    "por_dia.png",
    "historias.html",
    "historias.png",
    "precision_k.html",
    "precision_k.png",
    "recall_tipo.html",
    "recall_tipo.png",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hito", required=True, choices=["1"])
    parser.add_argument("--solo-parametros", action="store_true")
    args = parser.parse_args()

    origen, destino = REPORTS_HITO1, DOCS_RESULTADOS_HITO1
    archivos = PARAMETROS if args.solo_parametros else PARAMETROS + RESULTADOS
    destino.mkdir(parents=True, exist_ok=True)
    faltan = [a for a in archivos if not (origen / a).exists()]
    if faltan:
        raise SystemExit(f"Faltan en {origen}: {', '.join(faltan)}")
    for nombre in archivos:
        if nombre == "parametros.json" and (destino / nombre).exists() and not args.solo_parametros:
            # los parámetros congelados no se pisan al publicar el resto
            continue
        shutil.copy2(origen / nombre, destino / nombre)
        print(f"{origen / nombre} -> {destino / nombre}")


if __name__ == "__main__":
    main()

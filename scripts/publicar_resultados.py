"""Copia los resultados finales de ``reports/`` a ``docs/resultados/`` (versionado, Pages).

Uso:
    uv run python scripts/publicar_resultados.py --hito 2 --solo-parametros  # para congelar
    uv run python scripts/publicar_resultados.py --hito 2                    # todo, tras evaluar
"""

import argparse
import shutil

from lavado.rutas import (
    DOCS_RESULTADOS_HITO1,
    DOCS_RESULTADOS_HITO2,
    DOCS_RESULTADOS_HITO3,
    DOCS_RESULTADOS_HITO4,
    REPORTS_HITO1,
    REPORTS_HITO2,
    REPORTS_HITO3,
    REPORTS_HITO4,
)

PARAMETROS = ("parametros.json", "desarrollo.json")
# Los modelos de CoLES se congelan junto con los parámetros del hito 3.
MODELOS = {
    "3": ("modelos/coles_hi.pt", "modelos/coles_li.pt"),
    "4": tuple(
        f"modelos/{n}_{v}.{e}"
        for v in ("hi", "li")
        for n, e in (
            ("gnn", "pt"),
            ("gnn_sin_coles", "pt"),
            ("mlp_sin_grafo", "pt"),
            ("coles_supervisado", "pt"),
            ("pygod", "pt"),
            ("estadisticas", "npz"),
        )
    ),
}
RESULTADOS = {
    "1": (
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
    ),
    "4": (
        "metricas.json",
        "hito4_top100.html",
        "hito4_top100.png",
        "hito4_f1.html",
        "hito4_f1.png",
    ),
    "3": (
        "metricas.json",
        "hito3_top100.html",
        "hito3_top100.png",
        "hito3_f1.html",
        "hito3_f1.png",
    ),
    "2": (
        "metricas.json",
        "detectores_top100.html",
        "detectores_top100.png",
        "detectores_f1.html",
        "detectores_f1.png",
    ),
}
RUTAS = {
    "1": (REPORTS_HITO1, DOCS_RESULTADOS_HITO1),
    "2": (REPORTS_HITO2, DOCS_RESULTADOS_HITO2),
    "3": (REPORTS_HITO3, DOCS_RESULTADOS_HITO3),
    "4": (REPORTS_HITO4, DOCS_RESULTADOS_HITO4),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hito", required=True, choices=sorted(RUTAS))
    parser.add_argument("--solo-parametros", action="store_true")
    args = parser.parse_args()

    origen, destino = RUTAS[args.hito]
    archivos = PARAMETROS + MODELOS.get(args.hito, ())
    if not args.solo_parametros:
        archivos += RESULTADOS[args.hito]
    destino.mkdir(parents=True, exist_ok=True)
    faltan = [a for a in archivos if not (origen / a).exists()]
    if faltan:
        raise SystemExit(f"Faltan en {origen}: {', '.join(faltan)}")
    for nombre in archivos:
        if nombre == "parametros.json" and (destino / nombre).exists() and not args.solo_parametros:
            # los parámetros congelados no se pisan al publicar el resto
            continue
        if (
            nombre.startswith("modelos/")
            and (destino / nombre).exists()
            and not args.solo_parametros
        ):
            continue  # los modelos congelados tampoco se pisan
        (destino / nombre).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen / nombre, destino / nombre)
        print(f"{origen / nombre} -> {destino / nombre}")


if __name__ == "__main__":
    main()

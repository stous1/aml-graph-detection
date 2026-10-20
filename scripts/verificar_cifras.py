"""Contrasta las cifras del README y de las páginas de Pages con los JSON publicados.

Uso:
    uv run python scripts/verificar_cifras.py   # sale con código 1 si algo no coincide

Cada comprobación busca la línea de un documento que contiene un texto (la fila de una tabla
o una frase) y exige que aparezcan en ella los valores sacados de ``docs/resultados``,
formateados como en el texto (coma decimal).
"""

import json
import sys

from lavado.rutas import DOCS, DOCS_RESULTADOS, RAIZ


def _j(ruta: str) -> dict:
    return json.loads((DOCS_RESULTADOS / ruta).read_text(encoding="utf-8"))


def f(x: float, d: int) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def rango(a: float, b: float, d: int) -> str:
    return f"{f(a, d)} a {f(b, d)}"


def entero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


H4 = _j("hito4/metricas.json")["variantes"]
H2 = _j("hito2/metricas.json")["variantes"]
H3 = _j("hito3/metricas.json")["variantes"]
DIAG = _j("hito4/diagnostico_grafo/diagnostico_grafo_prueba.json")["variantes"]
DIAG_DEV = _j("hito4/diagnostico_grafo/diagnostico_grafo_desarrollo.json")["variantes"]
META = {v: _j(f"hito5/universo_{v}_meta.json") for v in ("hi", "li")}
EXPL = _j("hito1/exploracion.json")


def m(fuente: dict, v: str, det: str) -> dict:
    return DIAG[v][det] if fuente is DIAG else fuente[v][det]


def fila(fuente: dict, det: str, columnas: tuple[str, ...] = ("f1", "p100", "p1000")) -> list:
    """Valores de HI y LI, en el orden de las tablas del README."""
    salida = []
    for v in ("hi", "li"):
        x = m(fuente, v, det)
        valores = {
            "f1": f(x["f1_transaccion"]["f1"], 3),
            "p100": f(x["precision_k"][0]["precision"], 2),
            "p500": f(x["precision_k"][1]["precision"], 2),
            "p1000": f(x["precision_k"][2]["precision"], 2),
        }
        salida += [valores[c] for c in columnas]
    return salida


def hi_li(fuente: dict, det: str, columnas: tuple[str, ...]) -> list:
    """Valores ``HI / LI`` como en las tablas de las páginas de hitos."""
    a, b = (
        fila(fuente, det, columnas)[: len(columnas)],
        fila(fuente, det, columnas)[len(columnas) :],
    )
    return [f"{x} / {y}" for x, y in zip(a, b, strict=True)]


final = H4["hi"]["gnn_sin_coles"]
final_li = H4["li"]["gnn_sin_coles"]
COMPROBACIONES: list[tuple[str, str, list[str]]] = [
    # README: tabla de resultados
    ("README.md", "| Regla simple (contrapartes en 24 h)", fila(H4, "regla_simple")),
    ("README.md", "| Combinado estructural (hito 2)", fila(H4, "combinado_forma_absoluto")),
    ("README.md", "| CoLES, huella atípica (hito 3)", fila(H4, "coles_atipico")),
    ("README.md", "| PyGOD, CoLA (hito 4)", fila(H4, "pygod")),
    ("README.md", "| GNN, estructurales + CoLES", fila(H4, "gnn")),
    ("README.md", "| Red sin grafo, solo estructurales", fila(DIAG, "mlp_sin_coles")),
    (
        "README.md",
        "| **GNN, solo estructurales (modelo final)**",
        [f"**{x}**" for x in fila(H4, "gnn_sin_coles")],
    ),
    (
        "README.md",
        "Intervalos de 95 % del modelo final",
        [rango(*final["f1_transaccion"]["f1_ic"], 3)],
    ),
    (
        "README.md",
        "en HI y de 0,030",
        [rango(*final_li["f1_transaccion"]["f1_ic"], 3)],
    ),
    (
        "README.md",
        "top-100 de 0,93",
        [
            rango(final["precision_k"][0]["ic_inf"], final["precision_k"][0]["ic_sup"], 2),
            rango(final_li["precision_k"][0]["ic_inf"], final_li["precision_k"][0]["ic_sup"], 2),
        ],
    ),
    (
        "README.md",
        "98 de las 100 primeras alertas",
        [
            f"{round(final['precision_k'][0]['precision'] * 100)} de las 100",
            f(final["f1_transaccion"]["f1"], 3),
        ],
    ),
    (
        "README.md",
        "En LI, top-100 de",
        [f(final_li["precision_k"][0]["precision"], 2), f(final_li["f1_transaccion"]["f1"], 3)],
    ),
    (
        "README.md",
        "(F1 0,143 y top-100 de 0,91 en HI)",
        [
            f(H2["hi"]["abanicos_h1"]["f1_transaccion"]["f1"], 3),
            f(H2["hi"]["abanicos_h1"]["precision_k"][0]["precision"], 2),
        ],
    ),
    (
        "README.md",
        "Sin esa señal, cae a F1",
        [
            f(H2["hi"]["abanicos_h1_sin_monedas"]["f1_transaccion"]["f1"], 3),
            f(H2["hi"]["abanicos_h1_sin_monedas"]["precision_k"][0]["precision"], 2),
        ],
    ),
    (
        "README.md",
        "Cuentas ilícitas evaluadas",
        [
            entero(final["universo"]["cuentas_ilicitas"]),
            entero(final_li["universo"]["cuentas_ilicitas"]),
        ],
    ),
    (
        "README.md",
        "de AP en HI) no se",
        [f(DIAG_DEV["hi"]["gnn_final_contra_sin_grafo"]["diferencia"], 3)],
    ),
    (
        "README.md",
        "HI con 5,1",
        [
            f(EXPL["hi"]["totales"]["transacciones"] / 1e6, 1),
            entero(round(EXPL["hi"]["totales"]["transacciones"] / EXPL["hi"]["totales"]["lavado"])),
        ],
    ),
    (
        "README.md",
        "LI con 6,9",
        [
            f(EXPL["li"]["totales"]["transacciones"] / 1e6, 1),
            entero(round(EXPL["li"]["totales"]["transacciones"] / EXPL["li"]["totales"]["lavado"])),
        ],
    ),
    (
        "README.md",
        "22 % del volumen",
        [
            f"{round(EXPL['hi']['artefactos']['dia1']['frac_transacciones'] * 100)} %",
            f"{round(EXPL['hi']['artefactos']['dia1']['frac_autotransferencias'] * 100)} %",
        ],
    ),
    # Portada de Pages
    (
        "docs/index.md",
        "| **HI, GNN estructural (modelo final)**",
        [f"**{x}**" for x in fila(H4, "gnn_sin_coles")[:3]],
    ),
    ("docs/index.md", "| HI, combinado estructural", fila(H4, "combinado_forma_absoluto")[:3]),
    ("docs/index.md", "| HI, regla simple", fila(H4, "regla_simple")[:3]),
    (
        "docs/index.md",
        "| **LI, GNN estructural (modelo final)**",
        [f"**{x}**" for x in fila(H4, "gnn_sin_coles")[3:]],
    ),
    ("docs/index.md", "| LI, combinado estructural", fila(H4, "combinado_forma_absoluto")[3:]),
    ("docs/index.md", "| LI, regla simple", fila(H4, "regla_simple")[3:]),
    # Hito 4
    (
        "docs/hito4.md",
        "| **GNN, solo estructurales (modelo final)**",
        [
            f"**{x.split(' / ')[0]}** / **{x.split(' / ')[1]}**"
            for x in hi_li(H4, "gnn_sin_coles", ("f1", "p100", "p1000"))
        ],
    ),
    ("docs/hito4.md", "| GNN, estructurales + CoLES", hi_li(H4, "gnn", ("f1", "p100", "p1000"))),
    (
        "docs/hito4.md",
        "| Red sin grafo (estructurales + CoLES)",
        hi_li(H4, "mlp_sin_grafo", ("f1", "p100", "p1000")),
    ),
    (
        "docs/hito4.md",
        "| Combinado estructural (hito 2)",
        hi_li(H4, "combinado_forma_absoluto", ("f1", "p100", "p1000")),
    ),
    ("docs/hito4.md", "| PyGOD (CoLA)", hi_li(H4, "pygod", ("f1", "p100", "p1000"))),
    ("docs/hito4.md", "| Regla simple", hi_li(H4, "regla_simple", ("f1", "p100", "p1000"))),
    (
        "docs/hito4.md",
        "rinde lo mismo en prueba (AP",
        [
            f(DIAG["hi"]["gnn_final_contra_sin_grafo"]["ap_b"], 3),
            f(DIAG["hi"]["gnn_final_contra_sin_grafo"]["ap_a"], 3),
        ],
    ),
    # Hito 3
    (
        "docs/hito3.md",
        "| Combinado estructural + CoLES",
        hi_li(H3, "combinado_forma_coles", ("f1", "p100", "p1000")),
    ),
    (
        "docs/hito3.md",
        "| CoLES, huella atípica",
        hi_li(H3, "coles_atipico", ("f1", "p100", "p1000")),
    ),
    # Hito 2 (cifra principal)
    (
        "docs/hito2.md",
        "| **Combinado estructural** |",
        [
            f"**{x.split(' / ')[0]}** / **{x.split(' / ')[1]}**"
            for x in hi_li(H2, "combinado_forma", ("f1", "p100", "p1000"))
        ],
    ),
    ("docs/hito2.md", "| Ciclos |", hi_li(H2, "ciclos", ("f1", "p100", "p1000"))),
    (
        "docs/hito2.md",
        "| Abanicos hito 1 (moneda y canal) |",
        hi_li(H2, "abanicos_h1", ("f1", "p100", "p1000")),
    ),
    # Hito 5
    (
        "docs/hito5.md",
        "| HI |",
        [
            entero(META["hi"]["cuentas"][c])
            for c in ("acierto", "falsa_alarma", "no_detectado", "contexto")
        ],
    ),
    (
        "docs/hito5.md",
        "| LI |",
        [
            entero(META["li"]["cuentas"][c])
            for c in ("acierto", "falsa_alarma", "no_detectado", "contexto")
        ],
    ),
    (
        "docs/hito5.md",
        "relativo): ",
        [
            f"{f(META['hi']['fracciones']['cuenta'] * 100, 2)} %",
            f"{f(META['li']['fracciones']['cuenta'] * 100, 2)} %",
        ],
    ),
]


def main() -> int:
    fallas = []
    for archivo, ancla, esperados in COMPROBACIONES:
        ruta = RAIZ / archivo if not archivo.startswith("docs/") else DOCS / archivo[5:]
        texto = ruta.read_text(encoding="utf-8").splitlines()
        posiciones = [i for i, x in enumerate(texto) if ancla in x]
        if not posiciones:
            fallas.append(f"{archivo}: no se encontró «{ancla}»")
            continue
        # la línea del ancla y la siguiente: las frases se cortan a 100 columnas
        linea = " ".join(texto[posiciones[0] : posiciones[0] + 2])
        faltan = [e for e in esperados if e not in linea]
        if faltan:
            fallas.append(f"{archivo}: «{ancla}» no tiene {faltan}\n    {linea}")
    print(f"{len(COMPROBACIONES)} comprobaciones, {len(fallas)} fallas")
    for x in fallas:
        print(" -", x)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())

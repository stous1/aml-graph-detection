"""Escribe el preregistro de la prueba fresca con HI-Medium y LI-Medium.

Uso:
    uv run python scripts/preregistrar_medium.py   # -> docs/resultados/preregistro_medium.json

Copia de los parámetros congelados todo lo que la v1.1 aplicará sin ajustes (modelos,
fracciones de alertas, umbrales) y guarda la huella SHA-256 de cada artefacto, para que
cualquier cambio posterior quede a la vista. No lee datos de Medium.
"""

import hashlib
import json
from pathlib import Path

from lavado.flujo_hito1 import escribir_json
from lavado.rutas import (
    DOCS_RESULTADOS,
    DOCS_RESULTADOS_HITO2,
    DOCS_RESULTADOS_HITO3,
    DOCS_RESULTADOS_HITO4,
    RAIZ,
)

DIAG = DOCS_RESULTADOS_HITO4 / "diagnostico_grafo"


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


TEXTO = {".json", ".md", ".csv", ".txt"}
CRLF, LF = bytes([13, 10]), bytes([10])


def _sha256(ruta: Path) -> str:
    """Huella del contenido. En archivos de texto se normaliza el fin de línea a LF (el que
    guarda git según .gitattributes), así la huella es la misma en Windows y en un clon."""
    contenido = ruta.read_bytes()
    if ruta.suffix in TEXTO:
        contenido = contenido.replace(CRLF, LF)
    return hashlib.sha256(contenido).hexdigest()


def main() -> None:
    p2 = _leer(DOCS_RESULTADOS_HITO2 / "parametros.json")
    p4 = _leer(DOCS_RESULTADOS_HITO4 / "parametros.json")
    diag = _leer(DIAG / "diagnostico_grafo_desarrollo.json")
    final = p4["modelo_final"]
    artefactos = sorted(
        [
            DOCS_RESULTADOS_HITO2 / "parametros.json",
            DOCS_RESULTADOS_HITO3 / "parametros.json",
            DOCS_RESULTADOS_HITO4 / "parametros.json",
            DIAG / "diagnostico_grafo_desarrollo.json",
        ]
        + [DOCS_RESULTADOS_HITO4 / p4["modelos"][v][final] for v in ("hi", "li")]
        + [DOCS_RESULTADOS_HITO4 / p4["estadisticas"][v] for v in ("hi", "li")]
        + [DIAG / diag["modelos"][v] for v in ("hi", "li")]
        + sorted((DOCS_RESULTADOS / "congelados").rglob("*.*"))
    )
    variantes = {}
    for v, vm in (("hi", "hi_medium"), ("li", "li_medium")):
        variantes[vm] = {
            "parametros_de": f"{v.upper()}-Small",
            "modelo_final": {
                "nombre": final,
                "pesos": p4["modelos"][v][final],
                "estadisticas": p4["estadisticas"][v],
                "fraccion_alertas": p4["fracciones"][v][final],
            },
            "red_sin_grafo": {
                "pesos": diag["modelos"][v],
                "fraccion_alertas": diag["fracciones"][v],
            },
            "combinado_estructural": {
                "umbral_absoluto": p2["combinados"]["combinado_forma"]["umbrales"][v],
                "fraccion_alertas": p4["fracciones"][v]["combinado_forma"],
            },
            "regla_simple": {"umbral_absoluto": p2["detectores"]["regla_simple"]["umbrales"][v]},
            "abanicos_h1_referencia": {
                "umbral_absoluto": p2["detectores"]["abanicos_h1"]["umbrales"][v]
            },
        }
    registro = {
        "titulo": "Preregistro de la prueba fresca con AMLworld HI-Medium y LI-Medium",
        "documento": "docs/preregistro_medium.md",
        "estado": "preregistrado, pendiente de ejecutar (v1.1)",
        "configuracion_modelo_final": p4["redes"][final],
        "configuracion_red_sin_grafo": diag["config_sin_grafo"],
        "variantes": variantes,
        "metricas": {
            "precision_k_cuentas": [100, 500, 1000, "numero_de_ilicitas"],
            "f1_ilicita": ["transaccion", "cuenta"],
            "precision_promedio_transaccion": True,
            "recall_por_tipo": "intento detectado si al menos la mitad de sus transferencias "
            "evaluadas quedan marcadas; sin patrón, por transacción",
            "intervalos": {
                "precision_k": "Wilson",
                "f1": "bootstrap de Poisson por cuenta de origen (500)",
                "recall_tipo": "bootstrap por intento (1.000)",
                "diferencia_ap": "bootstrap pareado por cuenta de origen (1.000)",
            },
            "nunca": "exactitud global",
        },
        "comparaciones": [
            {
                "id": "H1",
                "a": "modelo_final",
                "b": "regla_simple",
                "medidas": ["precision_promedio_transaccion", "precision_100"],
            },
            {
                "id": "H2",
                "a": "modelo_final",
                "b": "combinado_estructural",
                "medidas": ["precision_promedio_transaccion", "precision_100", "f1_transaccion"],
            },
            {
                "id": "H3",
                "a": "modelo_final",
                "b": "red_sin_grafo",
                "medidas": ["diferencia_ap"],
                "lectura": "el grafo aporta si el IC 95 % de la diferencia de AP queda por encima "
                "de 0 en las dos variantes; empeora si queda por debajo en las dos; en otro caso, "
                "no hay evidencia de aporte",
            },
        ],
        "particion": {
            "dia_1": "solo historia, nunca se mide",
            "cola": "se excluyen los días finales con menos del 1 % del volumen diario mediano "
            "de los días 2 en adelante",
            "evaluacion": "todos los demás días; sin desarrollo ni intentos puente",
            "bloques": "de 4 días desde el día 2, cada uno con su historia previa; el último "
            "bloque puede ser más corto",
            "umbrales_relativos_por_bloque": "en cada bloque se marca la fracción congelada de "
            "sus transferencias y de sus cuentas",
        },
        "recursos": {
            "duckdb_memory_limit": "16GB",
            "desborde": "data/duckdb_tmp",
            "base": "data/aml_medium.duckdb (la de Small no se toca)",
        },
        "huellas": "SHA-256; en archivos de texto, con fin de línea LF",
        "artefactos_sha256": {
            str(a.relative_to(RAIZ)).replace("\\", "/"): _sha256(a) for a in artefactos
        },
    }
    destino = DOCS_RESULTADOS / "preregistro_medium.json"
    escribir_json(registro, destino)
    print(f"{destino} ({len(registro['artefactos_sha256'])} artefactos con huella)")


if __name__ == "__main__":
    main()

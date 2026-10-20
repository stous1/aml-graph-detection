"""Hito 5: datos del universo de Cosmograph con las cuentas y transferencias de prueba.

Con el modelo final congelado (GNN solo estructurales) y sus fracciones de alertas, se arma por
variante un subgrafo del período de prueba que entra en un celular:

- **Puntos:** las cuentas alertadas por el modelo y las cuentas con lavado, más unas pocas
  contrapartes de contexto. Categoría: ``acierto`` (alertada y con lavado), ``falsa_alarma``
  (alertada sin lavado), ``no_detectado`` (con lavado y no alertada) o ``contexto``.
- **Enlaces:** las transferencias de lavado (``detectado`` o ``no_detectado``, con su tipo de
  patrón), las transferencias alertadas sin lavado (``alerta_falsa``) y unas pocas de contexto.
  Pares repetidos se agregan en un solo enlace.

``meta`` trae los conteos de la leyenda y el recall por tipo, que se verifica contra
``docs/resultados/hito4/metricas.json``.
"""

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from lavado import evaluacion as ev
from lavado import flujo_hito4 as f4
from lavado import gnn
from lavado.detectores import comun
from lavado.patrones import SIN_PATRON
from lavado.rutas import DOCS_RESULTADOS_HITO4

TEXTO_CATEGORIA = {
    "acierto": "alerta acertada",
    "falsa_alarma": "falsa alarma",
    "no_detectado": "lavado no detectado",
    "contexto": "contexto",
}


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def puntajes_modelo_final(
    con: duckdb.DuckDBPyConnection, esquema: str, dir_h4: Path = DOCS_RESULTADOS_HITO4
) -> tuple[ev.Universo, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Universo de prueba, puntajes del modelo final y marcas con sus umbrales relativos."""
    p4 = _leer(dir_h4 / "parametros.json")
    final = p4["modelo_final"]
    _, params_h3 = f4.parametros_previos()
    est = np.load(dir_h4 / p4["estadisticas"][esquema])
    g, _, _ = f4.grafo_estandarizado(
        con,
        esquema,
        "prueba",
        f4.codificador_coles(esquema, params_h3),
        {},
        est["medias"],
        est["desvios"],
    )
    universo = ev.cargar_universo(con, esquema, "prueba")
    modelo = gnn.cargar(
        dir_h4 / p4["modelos"][esquema][final], g, gnn.ConfigGNN(**p4["redes"][final])
    )
    p_tx = gnn.puntuar(modelo, g)
    tx = universo.transacciones
    p_cta = comun.cuentas_por_maximo(
        tx.origen.to_numpy(), tx.destino.to_numpy(), p_tx, comun.n_cuentas(con, esquema)
    )
    fr = p4["fracciones"][esquema][final]
    ok = ~tx.ignorada.to_numpy()
    cuentas = universo.cuentas[~universo.cuentas.ignorada]
    u_tx = ev.umbral_relativo(p_tx[ok], fr["transaccion"])
    u_cta = ev.umbral_relativo(p_cta[cuentas.cuenta_id.to_numpy()], fr["cuenta"])
    marcada_tx = (p_tx >= u_tx) & (p_tx > 0)
    marcada_cta = (p_cta >= u_cta) & (p_cta > 0)
    return universo, p_tx, p_cta, marcada_tx, marcada_cta, {"modelo": final, "fracciones": fr}


def universo(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    contexto_por_cuenta: int = 2,
    semilla: int = 20220907,
    dir_h4: Path = DOCS_RESULTADOS_HITO4,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """``(puntos, enlaces, meta)`` del universo de prueba de ``esquema``."""
    uni, p_tx, p_cta, marcada_tx, marcada_cta, info = puntajes_modelo_final(con, esquema, dir_h4)
    tx = uni.transacciones.assign(marcada=marcada_tx, puntaje=p_tx)
    tx = tx[~tx.ignorada]
    cuentas = uni.cuentas[~uni.cuentas.ignorada]
    ilicitas = set(cuentas[cuentas.y].cuenta_id.tolist())
    alertadas = {int(c) for c in cuentas.cuenta_id if marcada_cta[c]}
    seleccion = ilicitas | alertadas

    lavado = tx[tx.y].copy()
    detectado_intento = (
        lavado[lavado.tipo != SIN_PATRON].groupby("intento_id").marcada.mean()
        >= ev.FRACCION_INTENTO
    )
    lavado["detectado"] = np.where(
        lavado.tipo == SIN_PATRON,
        lavado.marcada,
        lavado.intento_id.map(detectado_intento).fillna(False).astype(bool),
    )
    lavado["categoria"] = np.where(lavado.detectado, "detectado", "no_detectado")
    falsas = tx[~tx.y & tx.marcada].assign(categoria="alerta_falsa", tipo="")
    resto = tx[~tx.y & ~tx.marcada]
    en_seleccion = resto.origen.isin(seleccion) | resto.destino.isin(seleccion)
    candidatos = resto[en_seleccion].sample(frac=1.0, random_state=semilla)
    candidatos["centro"] = np.where(
        candidatos.origen.isin(seleccion), candidatos.origen, candidatos.destino
    )
    contexto = (
        candidatos.groupby("centro").head(contexto_por_cuenta).assign(categoria="contexto", tipo="")
    )
    columnas = ["origen", "destino", "categoria", "tipo"]
    enlaces = (
        pd.concat([lavado[columnas], falsas[columnas], contexto[columnas]], ignore_index=True)
        .assign(tipo=lambda d: d.tipo.fillna(""))
        .groupby(columnas, as_index=False)
        .size()
        .rename(columns={"size": "n"})
    )

    todos = sorted(set(enlaces.origen) | set(enlaces.destino) | seleccion)
    tipos_por_cuenta: dict[int, set[str]] = {}
    for o, d, t in zip(lavado.origen, lavado.destino, lavado.tipo, strict=True):
        etiqueta = "sin patrón" if t == SIN_PATRON else t
        tipos_por_cuenta.setdefault(int(o), set()).add(etiqueta)
        tipos_por_cuenta.setdefault(int(d), set()).add(etiqueta)
    grado = pd.concat([enlaces.origen, enlaces.destino]).value_counts()

    def categoria(c: int) -> str:
        if c in alertadas:
            return "acierto" if c in ilicitas else "falsa_alarma"
        return "no_detectado" if c in ilicitas else "contexto"

    filas = []
    for c in todos:
        cat = categoria(c)
        etiqueta = f"Cuenta {c} · {TEXTO_CATEGORIA[cat]}"
        if c in tipos_por_cuenta:
            etiqueta += " · " + ", ".join(sorted(tipos_por_cuenta[c]))
        filas.append(
            {
                "id": f"c{c}",
                "categoria": cat,
                "tamano": round(2.0 + 1.5 * np.log2(1 + grado.get(c, 0)), 2)
                if cat != "contexto"
                else 1.5,
                "etiqueta": etiqueta,
            }
        )
    puntos = pd.DataFrame(filas)
    enlaces = enlaces.assign(
        origen="c" + enlaces.origen.astype(str), destino="c" + enlaces.destino.astype(str)
    )

    por_tipo = []
    for tipo, grupo in lavado.groupby("tipo"):
        if tipo == SIN_PATRON:
            por_tipo.append(
                {
                    "tipo": "sin patrón",
                    "unidad": "transacciones",
                    "detectados": int(grupo.detectado.sum()),
                    "total": len(grupo),
                }
            )
        else:
            intentos = grupo.drop_duplicates("intento_id")
            por_tipo.append(
                {
                    "tipo": tipo,
                    "unidad": "intentos",
                    "detectados": int(intentos.detectado.sum()),
                    "total": len(intentos),
                }
            )
    meta = {
        "variante": esquema.upper(),
        "periodo": "prueba (días 7 a 10)",
        **info,
        "puntos": len(puntos),
        "enlaces": len(enlaces),
        "cuentas": {cat: int((puntos.categoria == cat).sum()) for cat in TEXTO_CATEGORIA},
        "por_tipo": sorted(por_tipo, key=lambda r: (r["tipo"] == "sin patrón", r["tipo"])),
        "transferencias": {
            "lavado_detectado": int(lavado.detectado.sum()),
            "lavado_total": len(lavado),
            "alertas_falsas": len(falsas),
        },
    }
    return puntos, enlaces, meta


def verificar_contra_hito4(meta: dict, esquema: str, dir_h4: Path = DOCS_RESULTADOS_HITO4) -> None:
    """El recall por tipo del universo debe coincidir con el de las métricas del hito 4."""
    metricas = _leer(dir_h4 / "metricas.json")["variantes"][esquema][meta["modelo"]]
    esperado = {
        ("sin patrón" if r["tipo"] == SIN_PATRON else r["tipo"]): (r["detectados"], r["n"])
        for r in metricas["recall_tipo"]
    }
    obtenido = {r["tipo"]: (r["detectados"], r["total"]) for r in meta["por_tipo"]}
    if esperado != obtenido:
        raise RuntimeError(f"El universo no coincide con el hito 4: {esperado} != {obtenido}")


def escribir(
    puntos: pd.DataFrame, enlaces: pd.DataFrame, meta: dict, destino: Path, esquema: str
) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"universo_{esquema}_puntos.json").write_text(
        puntos.to_json(orient="records", force_ascii=False), encoding="utf-8"
    )
    (destino / f"universo_{esquema}_enlaces.json").write_text(
        enlaces.to_json(orient="records", force_ascii=False), encoding="utf-8"
    )
    (destino / f"universo_{esquema}_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )

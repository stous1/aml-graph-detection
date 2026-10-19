"""Evaluación contra etiquetas y patrones. Es el único módulo que lee la verdad.

Métricas (nunca exactitud global):

- **Precisión en el top-k** por cuenta, con intervalo de Wilson.
- **F1 de la clase ilícita**, por transacción y por cuenta, en un umbral fijado en desarrollo,
  con intervalo bootstrap de Poisson por cuenta de origen (las transferencias de una misma
  cuenta no son independientes).
- **Recall por tipo de patrón** a nivel de intento: un intento se cuenta detectado si al menos
  ``FRACCION_INTENTO`` de sus transferencias del período quedan marcadas. Las de lavado sin
  intento (``SIN_PATRON``) se miden por transacción. Intervalo bootstrap por intento.

Las transferencias de intentos puente se excluyen del universo de ambos períodos, y una
cuenta cuyo único lavado del período está en intentos puente también se excluye.
"""

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

from lavado.patrones import SIN_PATRON

FRACCION_INTENTO = 0.5
KS: tuple[int, ...] = (100, 500, 1000)
Z_95 = 1.959963984540054


@dataclass
class Universo:
    """Transferencias y cuentas evaluables de un período, con su verdad."""

    periodo: str
    transacciones: pd.DataFrame  # tx_id, origen, destino, y, ignorada, intento_id, tipo
    cuentas: pd.DataFrame  # cuenta_id, y, ignorada


def cargar_universo(con: duckdb.DuckDBPyConnection, esquema: str, periodo: str) -> Universo:
    """Universo de evaluación de ``periodo``: todas sus aristas, con etiquetas y exclusiones."""
    tx = con.execute(
        f"""
        SELECT a.tx_id, a.origen, a.destino, (l.tx_id IS NOT NULL) AS y,
               coalesce(l.ignorada, false) AS ignorada, l.intento_id, l.tipo
        FROM {esquema}.aristas a LEFT JOIN {esquema}.etiquetas l USING (tx_id)
        WHERE a.periodo = ?
        ORDER BY a.tx_id
        """,
        [periodo],
    ).df()
    lados = pd.concat(
        [
            tx[["origen", "y", "ignorada"]].rename(columns={"origen": "cuenta_id"}),
            tx[["destino", "y", "ignorada"]].rename(columns={"destino": "cuenta_id"}),
        ]
    )
    lados["positivo"] = lados.y & ~lados.ignorada
    lados["solo_ignorado"] = lados.y & lados.ignorada
    cuentas = (
        lados.groupby("cuenta_id")
        .agg(y=("positivo", "any"), toca_ignorado=("solo_ignorado", "any"))
        .reset_index()
    )
    cuentas["ignorada"] = cuentas.toca_ignorado & ~cuentas.y
    return Universo(periodo, tx, cuentas[["cuenta_id", "y", "ignorada"]])


def wilson(exitos: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Intervalo de Wilson para una proporción."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = exitos / n
    centro = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    radio = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    return (float(centro - radio), float(centro + radio))


def orden_descendente(puntaje: np.ndarray, ids: np.ndarray) -> np.ndarray:
    """Índices de mayor a menor puntaje; los empates se rompen por id ascendente."""
    return np.lexsort((ids, -puntaje))


def precision_en_k(
    puntaje: np.ndarray, y: np.ndarray, ids: np.ndarray, ks: tuple[int, ...] | list[int]
) -> list[dict]:
    """Precisión en el top-k (con Wilson) para cada ``k``."""
    orden = orden_descendente(puntaje, ids)
    y_ord = np.asarray(y, dtype=bool)[orden]
    salida = []
    for k in ks:
        k = int(min(k, len(y_ord)))
        aciertos = int(y_ord[:k].sum())
        inf, sup = wilson(aciertos, k)
        salida.append(
            {
                "k": k,
                "aciertos": aciertos,
                "precision": aciertos / k if k else float("nan"),
                "ic_inf": inf,
                "ic_sup": sup,
            }
        )
    return salida


def _prf(tp: float, fp: float, fn: float) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def mejor_umbral_f1(puntaje: np.ndarray, y: np.ndarray) -> dict:
    """Umbral que maximiza el F1 de la clase ilícita (se usa solo en desarrollo).

    Se marcan las observaciones con ``puntaje >= umbral``; un puntaje 0 nunca se marca.
    """
    puntaje = np.asarray(puntaje, dtype=float)
    y = np.asarray(y, dtype=bool)
    orden = np.argsort(-puntaje, kind="stable")
    p, yy = puntaje[orden], y[orden]
    tp = np.cumsum(yy)
    marcadas = np.arange(1, len(p) + 1)
    # solo se puede cortar donde cambia el puntaje
    corte = np.r_[p[1:] != p[:-1], True] & (p > 0)
    if not corte.any():
        return {"umbral": float("inf"), "precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp_c, m_c = tp[corte], marcadas[corte]
    precision = tp_c / m_c
    recall = tp_c / max(int(y.sum()), 1)
    suma = precision + recall
    f1 = np.divide(2 * precision * recall, suma, out=np.zeros_like(suma), where=suma > 0)
    i = int(np.argmax(f1))
    return {
        "umbral": float(p[corte][i]),
        "precision": float(precision[i]),
        "recall": float(recall[i]),
        "f1": float(f1[i]),
    }


def f1_en_umbral(
    puntaje: np.ndarray,
    y: np.ndarray,
    umbral: float,
    grupos: np.ndarray | None = None,
    n_boot: int = 500,
    semilla: int = 20220907,
) -> dict:
    """Precisión, recall y F1 de la clase ilícita al marcar ``puntaje >= umbral``.

    Con ``grupos`` agrega un intervalo bootstrap de Poisson que remuestrea grupos completos.
    """
    pred = (np.asarray(puntaje) >= umbral) & (np.asarray(puntaje) > 0)
    y = np.asarray(y, dtype=bool)
    tp, fp, fn = int((pred & y).sum()), int((pred & ~y).sum()), int((~pred & y).sum())
    precision, recall, f1 = _prf(tp, fp, fn)
    salida = {
        "umbral": float(umbral),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "marcadas": tp + fp,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
    if grupos is not None:
        codigos, inverso = np.unique(grupos, return_inverse=True)
        por_grupo = np.zeros((len(codigos), 3))
        np.add.at(por_grupo, inverso, np.c_[pred & y, pred & ~y, ~pred & y].astype(float))
        rng = np.random.default_rng(semilla)
        f1s = []
        for _ in range(n_boot):
            w = rng.poisson(1.0, len(codigos))
            t = w @ por_grupo
            f1s.append(_prf(*t)[2])
        salida["f1_ic"] = [float(np.quantile(f1s, 0.025)), float(np.quantile(f1s, 0.975))]
    return salida


def recall_por_tipo(
    universo: Universo,
    marcada: np.ndarray,
    fraccion: float = FRACCION_INTENTO,
    min_tx: int = 1,
    n_boot: int = 1000,
    semilla: int = 20220907,
) -> pd.DataFrame:
    """Recall por tipo de patrón (intentos) y de ``SIN_PATRON`` (transacciones).

    ``marcada`` está alineado con ``universo.transacciones``. Con ``min_tx`` solo cuentan los
    intentos con al menos esa cantidad de transferencias en el período (un abanico necesita
    tres o más contrapartes para tener forma).
    """
    tx = universo.transacciones.assign(marcada=np.asarray(marcada, dtype=bool))
    tx = tx[tx.y & ~tx.ignorada]
    rng = np.random.default_rng(semilla)
    filas = []

    por_intento = (
        tx[tx.tipo != SIN_PATRON]
        .groupby(["tipo", "intento_id"])
        .marcada.agg(["mean", "size"])
        .reset_index()
    )
    por_intento = por_intento[por_intento["size"] >= min_tx]
    intentos = por_intento.assign(detectado=por_intento["mean"] >= fraccion)
    for tipo, grupo in intentos.groupby("tipo"):
        d = grupo.detectado.to_numpy()
        boots = [rng.choice(d, len(d)).mean() for _ in range(n_boot)]
        filas.append(
            {
                "tipo": tipo,
                "unidad": "intento",
                "n": len(d),
                "detectados": int(d.sum()),
                "recall": float(d.mean()),
                "ic_inf": float(np.quantile(boots, 0.025)),
                "ic_sup": float(np.quantile(boots, 0.975)),
            }
        )
    sin = tx[tx.tipo == SIN_PATRON].marcada.to_numpy()
    if len(sin):
        inf, sup = wilson(int(sin.sum()), len(sin))
        filas.append(
            {
                "tipo": SIN_PATRON,
                "unidad": "transaccion",
                "n": len(sin),
                "detectados": int(sin.sum()),
                "recall": float(sin.mean()),
                "ic_inf": inf,
                "ic_sup": sup,
            }
        )
    return pd.DataFrame(filas)


def forma_por_tipo(universo: Universo, marcada: np.ndarray, direccion: np.ndarray) -> pd.DataFrame:
    """Entre las transferencias de lavado marcadas, qué parte se explica por un abanico de
    ``salida`` y qué parte por uno de ``entrada``, por tipo de patrón."""
    tx = universo.transacciones.assign(
        marcada=np.asarray(marcada, dtype=bool), direccion=np.asarray(direccion)
    )
    tx = tx[tx.y & ~tx.ignorada & tx.marcada]
    if tx.empty:
        return pd.DataFrame(columns=["tipo", "entrada", "salida"])
    tabla = pd.crosstab(tx.tipo, tx.direccion, normalize="index")
    for col in ("entrada", "salida"):
        if col not in tabla:
            tabla[col] = 0.0
    return tabla[["entrada", "salida"]].reset_index()

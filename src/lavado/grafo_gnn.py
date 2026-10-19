"""Grafo para redes neuronales: cuentas como nodos, transferencias como aristas a clasificar.

Para un período se arma, con la ventana de 5 días que termina donde termina el período:

- **Nodos:** las cuentas con alguna transferencia en la ventana. Características: las
  variables estructurales por cuenta (``variables_cuenta.ESTRUCTURALES``), el embedding de
  CoLES (ceros si la cuenta no tiene historia suficiente) y un indicador de cobertura.
- **Aristas de mensajes:** un par dirigido ``u → v`` por cada par con transferencias en la
  ventana, con ``log(1 + n)`` y ``log(1 + USD)``.
- **Transferencias a clasificar:** las del período, con atributos estructurales: log del monto,
  hora (seno y coseno), primera transferencia entre las cuentas y si es parte de un par de paso
  (entrada reenviada o salida que reenvía).

Nada de moneda ni formato de pago, y ninguna etiqueta: el grafo es el mismo con o sin verdad.
"""

from dataclasses import dataclass
from datetime import datetime

import duckdb
import numpy as np
import torch

from lavado import paso, variables_cuenta
from lavado.detectores import coles_atipico as ca

ATRIBUTOS_TX: tuple[str, ...] = (
    "log_monto",
    "hora_seno",
    "hora_coseno",
    "nueva",
    "reenviada",
    "reenvio",
)


@dataclass
class Grafo:
    """Tensores de un período. ``tx_id`` está alineado con ``tx_origen``, ``tx_destino`` y
    ``tx_atributos`` (índices de nodo, no ``cuenta_id``)."""

    cuentas: np.ndarray  # cuenta_id de cada nodo
    x: torch.Tensor  # (nodos, características)
    aristas: torch.Tensor  # (2, pares) índices de nodo
    aristas_atributos: torch.Tensor
    tx_id: np.ndarray
    tx_origen: torch.Tensor
    tx_destino: torch.Tensor
    tx_atributos: torch.Tensor
    nombres_x: list[str]


def _ts(fecha: datetime) -> str:
    return f"TIMESTAMP '{fecha:%Y-%m-%d %H:%M:%S}'"


def construir(
    con: duckdb.DuckDBPyConnection,
    esquema: str,
    periodo: str,
    codificador=None,
    cache: dict | None = None,
    min_eventos_coles: int = 20,
) -> Grafo:
    """Grafo del período. Sin ``codificador`` no lleva embeddings de CoLES."""
    cache = cache if cache is not None else {}
    desde, hasta = ca.ventana(periodo)
    nodos = (
        con.execute(
            f"""
        SELECT DISTINCT c FROM (
            SELECT origen AS c FROM {esquema}.aristas WHERE ts >= {_ts(desde)} AND ts < {_ts(hasta)}
            UNION ALL
            SELECT destino FROM {esquema}.aristas WHERE ts >= {_ts(desde)} AND ts < {_ts(hasta)}
        ) ORDER BY c
        """
        )
        .fetchnumpy()["c"]
        .astype(np.int64)
    )
    indice = {int(c): i for i, c in enumerate(nodos)}

    variables = variables_cuenta.calcular(con, esquema, desde, hasta).set_index("cuenta_id")
    nombres = list(variables_cuenta.ESTRUCTURALES)
    x = variables.reindex(nodos)[nombres].fillna(0.0).to_numpy(dtype=np.float32)
    if codificador is not None:
        cuentas_c, emb = ca.embeddings(con, esquema, periodo, min_eventos_coles, codificador, cache)
        e = np.zeros((len(nodos), emb.shape[1]), dtype=np.float32)
        cubierta = np.zeros((len(nodos), 1), dtype=np.float32)
        pos = np.searchsorted(nodos, cuentas_c)
        e[pos], cubierta[pos] = emb, 1.0
        x = np.hstack([x, e, cubierta])
        nombres += [f"coles_{i}" for i in range(emb.shape[1])] + ["coles_cubierta"]

    pares = con.execute(
        f"""
        SELECT origen, destino, ln(1 + count(*)) AS ln_n, ln(1 + sum(monto_usd)) AS ln_usd
        FROM {esquema}.aristas WHERE ts >= {_ts(desde)} AND ts < {_ts(hasta)}
        GROUP BY origen, destino ORDER BY origen, destino
        """
    ).df()
    pares["ln_usd"] = pares.ln_usd.round(6)  # suma en paralelo: ver comun.redondear

    paso.crear_pares_paso(
        con,
        esquema,
        hasta,
        variables_cuenta.DELTA_PASO_HORAS,
        variables_cuenta.TOLERANCIA_PASO,
        "gg_pares",
    )
    tx = con.execute(
        f"""
        WITH primer AS (
            SELECT least(origen, destino) AS a, greatest(origen, destino) AS z, min(ts) AS primero
            FROM {esquema}.aristas WHERE ts < {_ts(hasta)} GROUP BY ALL
        )
        SELECT t.tx_id, t.origen, t.destino, ln(1 + t.monto_usd) AS log_monto,
               sin(2 * pi() * hour(t.ts) / 24) AS hora_seno,
               cos(2 * pi() * hour(t.ts) / 24) AS hora_coseno,
               (p.primero = t.ts)::DOUBLE AS nueva,
               (t.tx_id IN (SELECT tx_in FROM gg_pares))::DOUBLE AS reenviada,
               (t.tx_id IN (SELECT tx_out FROM gg_pares))::DOUBLE AS reenvio
        FROM {esquema}.aristas t
        JOIN primer p ON p.a = least(t.origen, t.destino) AND p.z = greatest(t.origen, t.destino)
        WHERE t.periodo = '{periodo}'
        ORDER BY t.tx_id
        """
    ).df()
    con.execute("DROP TABLE gg_pares")

    def a_indices(cuentas: np.ndarray) -> torch.Tensor:
        return torch.tensor([indice[int(c)] for c in cuentas], dtype=torch.long)

    return Grafo(
        cuentas=nodos,
        x=torch.tensor(x),
        aristas=torch.stack(
            [a_indices(pares.origen.to_numpy()), a_indices(pares.destino.to_numpy())]
        ),
        aristas_atributos=torch.tensor(pares[["ln_n", "ln_usd"]].to_numpy(dtype=np.float32)),
        tx_id=tx.tx_id.to_numpy(),
        tx_origen=a_indices(tx.origen.to_numpy()),
        tx_destino=a_indices(tx.destino.to_numpy()),
        tx_atributos=torch.tensor(tx[list(ATRIBUTOS_TX)].to_numpy(dtype=np.float32)),
        nombres_x=nombres,
    )


def estandarizar(grafo: Grafo, medias: np.ndarray, desvios: np.ndarray) -> Grafo:
    """Estandariza las características de nodo con estadísticas fijadas (de desarrollo)."""
    grafo.x = (grafo.x - torch.tensor(medias)) / torch.tensor(desvios)
    return grafo


def estadisticas(grafo: Grafo) -> tuple[np.ndarray, np.ndarray]:
    x = grafo.x.numpy()
    desvios = x.std(axis=0)
    return x.mean(axis=0), np.where(desvios > 0, desvios, 1.0).astype(np.float32)

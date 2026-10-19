"""Anomalías de cuentas en el grafo con PyGOD, sin etiquetas.

Se usan detectores que entrenan por mini-lotes de vecindarios: **CoLA** (contrastivo: ¿se
parece una cuenta a su vecindario?), **OCGNN** (una clase: distancia al centro de lo normal) y
**GAE** reconstruyendo solo características. DOMINANT y AnomalyDAE quedan fuera: reconstruyen
la matriz de adyacencia densa (cuentas × cuentas), unos 580 GB con ~380 mil cuentas.

PyGOD muestrea vecindarios con ``NeighborLoader``, que exige ``pyg-lib`` o ``torch-sparse``
(extensiones compiladas sin ruedas para torch 2.14). Como el grafo entra completo en memoria
(y en la GPU), se reemplaza por un cargador que entrega el grafo entero en un solo lote: es lo
mismo que ``NeighborLoader`` con todos los vecinos y un lote del tamaño del grafo.

El detector se ajusta con el grafo de desarrollo y puntúa el grafo de cualquier período
(inductivo). El puntaje de una transferencia es el máximo de sus dos cuentas. Los umbrales son
relativos (ver ``flujo_hito4``): no se fija ningún valor absoluto de rareza.
"""

from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch_geometric.data import Data

from lavado import evaluacion as ev
from lavado.grafo_gnn import Grafo


@dataclass(frozen=True)
class ConfigAnomaliasGrafo:
    modelo: str = "cola"  # "cola", "ocgnn" o "gae"
    oculto: int = 64
    capas: int = 2
    epocas: int = 100
    semilla: int = 20220902

    def como_dict(self) -> dict:
        return asdict(self)


def configs() -> list[ConfigAnomaliasGrafo]:
    return [ConfigAnomaliasGrafo(m) for m in ("cola", "ocgnn", "gae")]


class _LoteCompleto:
    """Reemplazo de ``NeighborLoader``: el grafo completo en un solo lote, sin muestrear."""

    def __init__(self, data: Data, num_neighbors=None, batch_size=None, **kwargs) -> None:
        self.data = data

    def __len__(self) -> int:
        return 1

    def __iter__(self):
        lote = self.data.clone()
        lote.n_id = torch.arange(lote.num_nodes)
        lote.batch_size = lote.num_nodes
        yield lote


def _datos(grafo: Grafo) -> Data:
    return Data(x=grafo.x.float(), edge_index=grafo.aristas)


def _detector(config: ConfigAnomaliasGrafo):
    import pygod.detector.base as base
    from pygod.detector import GAE, OCGNN, CoLA

    base.NeighborLoader = _LoteCompleto

    clases = {"cola": CoLA, "ocgnn": OCGNN, "gae": GAE}
    if config.modelo not in clases:
        raise ValueError(f"modelo inválido: {config.modelo}")
    extra = {"recon_s": False} if config.modelo == "gae" else {}
    return clases[config.modelo](
        hid_dim=config.oculto,
        num_layers=config.capas,
        epoch=config.epocas,
        batch_size=0,
        gpu=0 if torch.cuda.is_available() else -1,
        verbose=0,
        **extra,
    )


def ajustar(grafo: Grafo, config: ConfigAnomaliasGrafo):
    """Ajusta el detector sin etiquetas con el grafo dado (de desarrollo)."""
    torch.manual_seed(config.semilla)
    np.random.seed(config.semilla)
    detector = _detector(config)
    detector.fit(_datos(grafo))
    return detector


def puntuar_cuentas(detector, grafo: Grafo, total_cuentas: int) -> np.ndarray:
    """Puntaje de anomalía de cada cuenta (indexado por ``cuenta_id``; 0 si no está)."""
    torch.manual_seed(0)
    puntajes = detector.decision_function(_datos(grafo)).detach().cpu().numpy().astype(float)
    # se desplaza para que todos sean positivos: 0 queda para "el detector no la vio"
    puntajes = puntajes - puntajes.min() + 1e-9
    cuenta = np.zeros(total_cuentas)
    cuenta[grafo.cuentas] = puntajes
    return cuenta


def a_transacciones(universo: ev.Universo, puntaje_cuentas: np.ndarray) -> np.ndarray:
    """Puntaje de cada transferencia del universo: el máximo de sus dos cuentas."""
    tx = universo.transacciones
    return np.maximum(puntaje_cuentas[tx.origen.to_numpy()], puntaje_cuentas[tx.destino.to_numpy()])


def guardar(detector, ruta) -> None:
    """Guarda el detector ajustado completo (PyGOD no separa arquitectura y pesos)."""
    torch.save(detector, ruta)


def cargar(ruta):
    _detector(ConfigAnomaliasGrafo())  # aplica el reemplazo del cargador antes de usarlo
    return torch.load(ruta, weights_only=False)

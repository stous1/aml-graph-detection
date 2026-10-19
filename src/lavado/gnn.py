"""Red neuronal sobre el grafo de transferencias (fase supervisada).

Arquitectura: una capa lineal lleva las características de cada cuenta a ``oculto``
dimensiones; luego ``capas`` rondas de GraphSAGE en las dos direcciones (lo que la cuenta
recibe y lo que envía se agregan por separado) con conexión residual. Cada transferencia se
clasifica con una cabeza MLP sobre los estados de su origen y su destino y sus atributos.
``usar_grafo=False`` es la misma red sin paso de mensajes (un MLP por cuenta), para medir cuánto
aporta el grafo.

Entrenamiento con las etiquetas de **desarrollo**: pérdida logística con todos los positivos y
una muestra de negativos en cada época; parada temprana por precisión promedio (una métrica de
ranking) en una validación temporal dentro de desarrollo.

Determinismo: semillas fijas. En CPU el resultado se repite exacto. En GPU las agregaciones de
PyTorch Geometric usan sumas atómicas que no garantizan el mismo orden, así que dos
entrenamientos pueden diferir en los últimos decimales; por eso el modelo entrenado se guarda y
la evaluación lo carga y puntúa en CPU.
"""

import os
from dataclasses import asdict, dataclass

import numpy as np
import torch
from sklearn.metrics import average_precision_score
from torch import nn
from torch_geometric.nn import SAGEConv

from lavado.grafo_gnn import Grafo

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")


@dataclass(frozen=True)
class ConfigGNN:
    caracteristicas: str = "todas"  # "todas", "estructurales" o "coles"
    usar_grafo: bool = True
    usar_atributos_tx: bool = True
    oculto: int = 64
    capas: int = 2
    abandono: float = 0.2
    tasa: float = 0.003
    max_epocas: int = 1500
    cada: int = 5  # épocas entre validaciones
    paciencia: int = 10  # validaciones sin mejorar antes de parar
    negativos_por_positivo: int = 50
    semilla: int = 20220902

    def como_dict(self) -> dict:
        return asdict(self)


def columnas(grafo: Grafo, config: ConfigGNN) -> list[int]:
    """Índices de las características de nodo que usa la configuración."""
    es_coles = [n.startswith("coles_") for n in grafo.nombres_x]
    if config.caracteristicas == "todas":
        return list(range(len(es_coles)))
    if config.caracteristicas == "estructurales":
        return [i for i, c in enumerate(es_coles) if not c]
    if config.caracteristicas == "coles":
        return [i for i, c in enumerate(es_coles) if c]
    raise ValueError(f"caracteristicas inválidas: {config.caracteristicas}")


class RedTransferencias(nn.Module):
    def __init__(self, d_nodo: int, d_tx: int, config: ConfigGNN) -> None:
        super().__init__()
        self.config = config
        o = config.oculto
        self.entrada = nn.Sequential(nn.Linear(d_nodo, o), nn.ReLU())
        if config.usar_grafo:
            self.salientes = nn.ModuleList(SAGEConv(o, o) for _ in range(config.capas))
            self.entrantes = nn.ModuleList(SAGEConv(o, o) for _ in range(config.capas))
        else:
            self.capas_mlp = nn.ModuleList(nn.Linear(o, o) for _ in range(config.capas))
        self.abandono = nn.Dropout(config.abandono)
        self.cabeza = nn.Sequential(
            nn.Linear(2 * o + (d_tx if config.usar_atributos_tx else 0), o),
            nn.ReLU(),
            nn.Linear(o, 1),
        )

    def estados(self, x: torch.Tensor, aristas: torch.Tensor) -> torch.Tensor:
        h = self.entrada(x)
        if self.config.usar_grafo:
            inversas = aristas.flip(0)
            for s, e in zip(self.salientes, self.entrantes, strict=True):
                # aristas u → v: SAGEConv agrega en v lo que viene de u (lo que v recibe);
                # con las inversas, agrega en u lo que u envía.
                h = h + torch.relu(e(h, aristas) + s(h, inversas))
                h = self.abandono(h)
        else:
            for capa in self.capas_mlp:
                h = self.abandono(h + torch.relu(capa(h)))
        return h

    def forward(self, grafo: Grafo, x: torch.Tensor, cuales: torch.Tensor) -> torch.Tensor:
        h = self.estados(x, grafo.aristas)
        partes = [h[grafo.tx_origen[cuales]], h[grafo.tx_destino[cuales]]]
        if self.config.usar_atributos_tx:
            partes.append(grafo.tx_atributos[cuales])
        return self.cabeza(torch.cat(partes, dim=1)).squeeze(1)


def dispositivo_disponible(preferir_gpu: bool = True) -> torch.device:
    return torch.device("cuda" if preferir_gpu and torch.cuda.is_available() else "cpu")


def _a(grafo: Grafo, dispositivo: torch.device) -> Grafo:
    return Grafo(
        grafo.cuentas,
        grafo.x.to(dispositivo),
        grafo.aristas.to(dispositivo),
        grafo.aristas_atributos.to(dispositivo),
        grafo.tx_id,
        grafo.tx_origen.to(dispositivo),
        grafo.tx_destino.to(dispositivo),
        grafo.tx_atributos.to(dispositivo),
        grafo.nombres_x,
    )


def crear(grafo: Grafo, config: ConfigGNN) -> RedTransferencias:
    torch.manual_seed(config.semilla)
    return RedTransferencias(len(columnas(grafo, config)), grafo.tx_atributos.shape[1], config)


def entrenar(
    grafo: Grafo,
    y: np.ndarray,
    entrenar_mascara: np.ndarray,
    validar_mascara: np.ndarray,
    config: ConfigGNN,
    dispositivo: torch.device | None = None,
) -> tuple[RedTransferencias, dict]:
    """Entrena con las transferencias de ``entrenar_mascara`` y elige la época por AP en
    ``validar_mascara``. Devuelve el modelo (en CPU) con los pesos de la mejor época."""
    dispositivo = dispositivo or dispositivo_disponible()
    torch.manual_seed(config.semilla)
    np.random.seed(config.semilla)
    torch.use_deterministic_algorithms(True, warn_only=True)
    modelo = crear(grafo, config).to(dispositivo)
    g = _a(grafo, dispositivo)
    x = g.x[:, columnas(grafo, config)]
    optimizador = torch.optim.Adam(modelo.parameters(), lr=config.tasa, weight_decay=1e-5)
    perdida = nn.BCEWithLogitsLoss()
    positivos = np.flatnonzero(entrenar_mascara & y)
    negativos = np.flatnonzero(entrenar_mascara & ~y)
    validar = torch.tensor(np.flatnonzero(validar_mascara), device=dispositivo)
    y_val = y[validar_mascara]
    rng = np.random.default_rng(config.semilla)
    historial: dict = {"epoca": [], "perdida": [], "ap_validacion": []}
    mejor = {"ap": -1.0, "epoca": 0, "pesos": None}
    sin_mejorar = 0
    for epoca in range(1, config.max_epocas + 1):
        modelo.train()
        n_neg = min(len(negativos), config.negativos_por_positivo * len(positivos))
        lote = np.concatenate([positivos, rng.choice(negativos, n_neg, replace=False)])
        cuales = torch.tensor(lote, device=dispositivo)
        objetivo = torch.tensor(y[lote], dtype=torch.float32, device=dispositivo)
        optimizador.zero_grad()
        valor = perdida(modelo(g, x, cuales), objetivo)
        valor.backward()
        optimizador.step()
        if epoca % config.cada == 0:
            modelo.eval()
            with torch.no_grad():
                p = torch.sigmoid(modelo(g, x, validar)).cpu().numpy()
            ap = float(average_precision_score(y_val, p)) if y_val.any() else 0.0
            historial["epoca"].append(epoca)
            historial["perdida"].append(float(valor))
            historial["ap_validacion"].append(ap)
            if ap > mejor["ap"]:
                mejor = {
                    "ap": ap,
                    "epoca": epoca,
                    "pesos": {k: v.detach().cpu().clone() for k, v in modelo.state_dict().items()},
                }
                sin_mejorar = 0
            else:
                sin_mejorar += 1
                if sin_mejorar >= config.paciencia:
                    break
    modelo = modelo.cpu()
    if mejor["pesos"] is not None:
        modelo.load_state_dict(mejor["pesos"])
    modelo.eval()
    historial |= {
        "mejor_epoca": mejor["epoca"],
        "mejor_ap_validacion": mejor["ap"],
        "dispositivo": str(dispositivo),
    }
    return modelo, historial


def puntuar(modelo: RedTransferencias, grafo: Grafo) -> np.ndarray:
    """Probabilidad de lavado de cada transferencia del grafo (en CPU, determinista)."""
    modelo = modelo.cpu().eval()
    x = grafo.x[:, columnas(grafo, modelo.config)]
    with torch.no_grad():
        todas = torch.arange(len(grafo.tx_id))
        return torch.sigmoid(modelo(grafo, x, todas)).numpy()


def guardar(modelo: RedTransferencias, ruta) -> None:
    torch.save(modelo.state_dict(), ruta)


def cargar(ruta, grafo: Grafo, config: ConfigGNN) -> RedTransferencias:
    modelo = crear(grafo, config)
    modelo.load_state_dict(torch.load(ruta, weights_only=True))
    return modelo.eval()

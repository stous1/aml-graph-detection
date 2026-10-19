"""CoLES (pytorch-lifestream): huella de comportamiento por cuenta, aprendida sin etiquetas.

CoLES entrena un codificador de secuencias (GRU) de modo contrastivo: dos subsecuencias de la
misma cuenta deben quedar cerca y las de cuentas distintas, lejos. No usa etiquetas. El
resultado es un vector (embedding) por cuenta y ventana.

El entrenamiento es determinista en CPU (semilla fija, un solo proceso de carga y algoritmos
deterministas) y el modelo entrenado se guarda para reutilizarlo tal cual.
"""

from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path

import numpy as np
import pytorch_lightning as pl
import torch
from ptls.data_load.datasets import MemoryMapDataset, inference_data_loader
from ptls.frames import PtlsDataModule
from ptls.frames.coles import ColesDataset, CoLESModule
from ptls.frames.coles.split_strategy import SampleSlices
from ptls.nn import RnnSeqEncoder, TrxEncoder

from lavado import secuencias


@dataclass(frozen=True)
class ConfigColes:
    min_eventos: int = 20  # largo mínimo de una secuencia de entrenamiento
    oculto: int = 64  # tamaño del embedding
    epocas: int = 10
    tasa: float = 0.002
    lote: int = 128
    cortes: int = 5  # subsecuencias por cuenta y lote
    corte_min: int = 10
    corte_max: int = 60
    max_eventos: int = 500
    semilla: int = 20220902

    def como_dict(self) -> dict:
        return asdict(self)


def crear_codificador(config: ConfigColes) -> RnnSeqEncoder:
    trx = TrxEncoder(
        embeddings={c: {"in": n, "out": 4} for c, n in secuencias.CATEGORICAS.items()},
        numeric_values={c: "identity" for c in secuencias.NUMERICAS},
        embeddings_noise=0.003,
    )
    return RnnSeqEncoder(trx_encoder=trx, hidden_size=config.oculto, type="gru")


class PerdidaPorEpoca(pl.Callback):
    """Guarda la pérdida contrastiva media de cada época (para ver que el entrenamiento baja)."""

    def __init__(self) -> None:
        self.perdidas: list[float] = []
        self._suma, self._n = 0.0, 0

    def on_train_batch_end(self, trainer, pl_module, outputs, batch, batch_idx) -> None:  # noqa: ANN001
        valor = outputs["loss"] if isinstance(outputs, dict) else outputs
        self._suma += float(valor)
        self._n += 1

    def on_train_epoch_end(self, trainer: pl.Trainer, pl_module: pl.LightningModule) -> None:
        if self._n:
            self.perdidas.append(self._suma / self._n)
        self._suma, self._n = 0.0, 0


def entrenar(
    datos: secuencias.Secuencias, config: ConfigColes
) -> tuple[RnnSeqEncoder, list[float]]:
    """Entrena CoLES con las secuencias dadas (de desarrollo).

    Devuelve el codificador y la pérdida de cada época.
    """
    pl.seed_everything(config.semilla, workers=True)
    torch.use_deterministic_algorithms(True, warn_only=True)
    codificador = crear_codificador(config)
    modulo = CoLESModule(
        seq_encoder=codificador,
        optimizer_partial=partial(torch.optim.Adam, lr=config.tasa),
        lr_scheduler_partial=partial(torch.optim.lr_scheduler.StepLR, step_size=5, gamma=0.5),
    )
    datamodule = PtlsDataModule(
        train_data=ColesDataset(
            MemoryMapDataset(data=datos.registros),
            splitter=SampleSlices(
                split_count=config.cortes, cnt_min=config.corte_min, cnt_max=config.corte_max
            ),
        ),
        train_batch_size=config.lote,
        train_num_workers=0,
    )
    registro = PerdidaPorEpoca()
    entrenador = pl.Trainer(
        max_epochs=config.epocas,
        callbacks=[registro],
        accelerator="cpu",
        deterministic=True,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
    )
    entrenador.fit(modulo, datamodule)
    codificador.eval()
    return codificador, registro.perdidas


def incrustar(
    codificador: RnnSeqEncoder, datos: secuencias.Secuencias, lote: int = 512
) -> np.ndarray:
    """Embedding de cada secuencia (filas alineadas con ``datos.cuentas``)."""
    if not datos.registros:
        return np.zeros((0, codificador.embedding_size), dtype=np.float32)
    codificador.eval()
    salida = []
    with torch.no_grad():
        for lote_datos in inference_data_loader(datos.registros, batch_size=lote):
            salida.append(codificador(lote_datos).numpy())
    return np.vstack(salida)


def guardar(codificador: RnnSeqEncoder, ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    torch.save(codificador.state_dict(), ruta)
    return ruta


def cargar(ruta: Path, config: ConfigColes) -> RnnSeqEncoder:
    codificador = crear_codificador(config)
    codificador.load_state_dict(torch.load(ruta, weights_only=True))
    codificador.eval()
    return codificador

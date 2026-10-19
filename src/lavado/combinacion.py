"""Combinación de detectores en un puntaje único, sin etiquetas.

Cada detector puntúa en su propia escala. Para hacerlos comparables, cada puntaje se convierte
en su **percentil en desarrollo**: la fracción de transferencias (o cuentas) de desarrollo con
puntaje menor o igual. La tabla de percentiles se arma una vez en desarrollo y se congela; en
prueba se aplica tal cual (no mira la distribución de prueba). Un puntaje 0 (el detector no
vio nada) vale 0.

Esquemas: ``max`` (basta que un detector vea algo raro), ``media`` y ``noisy_or``
(``1 - Π(1 - p)``). El esquema se elige en desarrollo.
"""

from dataclasses import dataclass

import numpy as np

ESQUEMAS: tuple[str, ...] = ("max", "media", "noisy_or")


@dataclass(frozen=True)
class Percentiles:
    """Distribución de referencia (desarrollo) de un detector."""

    referencia: np.ndarray  # puntajes de desarrollo, ordenados

    @classmethod
    def desde(cls, puntajes: np.ndarray) -> "Percentiles":
        return cls(np.sort(np.asarray(puntajes, dtype=float)))

    def aplicar(self, puntajes: np.ndarray) -> np.ndarray:
        puntajes = np.asarray(puntajes, dtype=float)
        p = np.searchsorted(self.referencia, puntajes, side="right") / len(self.referencia)
        return np.where(puntajes > 0, p, 0.0)


def combinar(percentiles: list[np.ndarray], esquema: str) -> np.ndarray:
    """Combina percentiles alineados (todos de la misma longitud)."""
    m = np.vstack(percentiles)
    if esquema == "max":
        return m.max(axis=0)
    if esquema == "media":
        return m.mean(axis=0)
    if esquema == "noisy_or":
        return 1.0 - np.prod(1.0 - m, axis=0)
    raise ValueError(f"esquema inválido: {esquema}")

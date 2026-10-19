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


@dataclass(frozen=True)
class PercentilesCompactos:
    """Versión guardable de :class:`Percentiles`: exacta en la parte alta de la distribución.

    Guarda cuántos puntajes de referencia hay, cuántos son 0 (o menos), los ``k_exactos``
    puntajes positivos más altos tal cual y una rejilla de cuantiles para el resto. Los umbrales
    de las combinaciones están en percentiles altos (por encima de 0,99), donde el resultado es
    idéntico al de :class:`Percentiles`; más abajo es una interpolación.
    """

    total: int
    ceros: int
    altos: np.ndarray  # los positivos más altos, ordenados
    resto_valores: np.ndarray  # cuantiles de los positivos restantes
    resto_conteos: np.ndarray  # cuántos positivos restantes hay por debajo de cada cuantil

    @classmethod
    def desde(
        cls, puntajes: np.ndarray, k_exactos: int = 100_000, n_cuantiles: int = 10_001
    ) -> "PercentilesCompactos":
        p = np.sort(np.asarray(puntajes, dtype=float))
        positivos = p[p > 0]
        ceros = len(p) - len(positivos)
        altos = positivos[-k_exactos:]
        resto = positivos[: max(len(positivos) - k_exactos, 0)]
        if len(resto):
            q = np.linspace(0, 1, n_cuantiles)
            valores = np.quantile(resto, q)
            conteos = np.searchsorted(resto, valores, side="right")
        else:
            valores, conteos = np.zeros(0), np.zeros(0, dtype=np.int64)
        return cls(len(p), ceros, altos, valores, conteos)

    def aplicar(self, puntajes: np.ndarray) -> np.ndarray:
        puntajes = np.asarray(puntajes, dtype=float)
        n_resto = int(self.resto_conteos[-1]) if len(self.resto_conteos) else 0
        en_altos = np.searchsorted(self.altos, puntajes, side="right")
        conteo = np.where(
            (len(self.altos) > 0) & (puntajes >= (self.altos[0] if len(self.altos) else np.inf)),
            self.ceros + n_resto + en_altos,
            self.ceros
            + (
                np.interp(puntajes, self.resto_valores, self.resto_conteos, left=0)
                if n_resto
                else 0
            ),
        )
        return np.where(puntajes > 0, conteo / self.total, 0.0)

    def guardar(self, ruta) -> None:
        np.savez_compressed(
            ruta,
            total=self.total,
            ceros=self.ceros,
            altos=self.altos,
            resto_valores=self.resto_valores,
            resto_conteos=self.resto_conteos,
        )

    @classmethod
    def cargar(cls, ruta) -> "PercentilesCompactos":
        d = np.load(ruta)
        return cls(
            int(d["total"]), int(d["ceros"]), d["altos"], d["resto_valores"], d["resto_conteos"]
        )

"""Mini-AMLworld: archivos sintéticos con el formato exacto de AMLworld, para pruebas y CI.

Trae, con semilla fija y sin depender del reloj:

- Ruido de fondo entre 60 cuentas de tres bancos (códigos con ceros a la izquierda en las
  transacciones y sin ellos en el archivo de cuentas, como en AMLworld), monedas locales y
  autotransferencias ``Reinvestment``.
- Un **comercio legítimo** (cuenta ``COMERCIO``) que el día 3 recibe de 20 clientes, dos
  pagos de cada uno, en una sola moneda: mucho tamaño, sin forma de lavado.
- Un **abanico de salida** de lavado (desarrollo, día 3): ``HUB_SALIDA`` paga una vez a seis
  cuentas nuevas, en monedas mezcladas, por ACH.
- Un **abanico de entrada** de lavado (prueba, día 8) de ocho cuentas hacia ``HUB_ENTRADA``,
  con una transferencia más en la cola (día 12).
- Un **ciclo puente** (días 6 y 7) y una transferencia de lavado sin patrón (día 4).
- Dos transferencias de lavado idénticas dentro del abanico de salida.
- Con monto conservado: una **dispersión-concentración** (prueba, día 9: ``SG_ORIGEN`` reparte
  entre tres intermediarias que reenvían a ``SG_DESTINO``), una **cadena** de cuatro saltos
  (desarrollo, día 4) y un **ciclo** de tres cuentas (desarrollo, día 5).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

TASAS_USD = {"US Dollar": 1.0, "Euro": 1.17, "Yuan": 0.15, "UK Pound": 1.29}
BANCOS = ("010", "0220", "03208")
FORMATOS_FONDO = ("Cheque", "Credit Card", "ACH", "Cash", "Wire")
ENCABEZADO_TX = (
    "Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,"
    "Amount Paid,Payment Currency,Payment Format,Is Laundering"
)


@dataclass(frozen=True)
class Cuenta:
    banco: str
    numero: str
    moneda: str

    @property
    def llave(self) -> str:
        return f"{int(self.banco)}:{self.numero}"


@dataclass
class Tx:
    ts: datetime
    origen: Cuenta
    destino: Cuenta
    monto_pagado: float
    moneda_pagada: str
    moneda_recibida: str
    formato: str
    lavado: int

    def linea(self) -> str:
        recibido = (
            self.monto_pagado * TASAS_USD[self.moneda_pagada] / TASAS_USD[self.moneda_recibida]
        )
        return (
            f"{self.ts:%Y/%m/%d %H:%M},{self.origen.banco},{self.origen.numero},"
            f"{self.destino.banco},{self.destino.numero},{recibido:.2f},{self.moneda_recibida},"
            f"{self.monto_pagado:.2f},{self.moneda_pagada},{self.formato},{self.lavado}"
        )


@dataclass
class MiniAMLworld:
    """Rutas escritas y cuentas especiales, para que las pruebas sepan qué buscar."""

    directorio: Path
    especiales: dict[str, Cuenta]


def _cuenta(i: int, moneda: str) -> Cuenta:
    return Cuenta(BANCOS[i % len(BANCOS)], f"8{i:07X}0", moneda)


def generar(directorio: Path, prefijo: str = "HI", semilla: int = 7) -> MiniAMLworld:
    """Escribe ``{prefijo}-Small_Trans.csv``, ``_Patterns.txt`` y ``_accounts.csv``."""
    rng = np.random.default_rng(semilla)
    directorio.mkdir(parents=True, exist_ok=True)
    inicio = datetime(2022, 9, 1)

    fondo = [_cuenta(i, "Euro" if i % 7 == 0 else "US Dollar") for i in range(60)]
    esp = {
        "COMERCIO": _cuenta(100, "US Dollar"),
        "HUB_SALIDA": _cuenta(101, "US Dollar"),
        "HUB_ENTRADA": _cuenta(102, "US Dollar"),
        "CICLO_A": _cuenta(103, "US Dollar"),
        "CICLO_B": _cuenta(104, "Euro"),
        "CICLO_C": _cuenta(105, "US Dollar"),
    }
    hojas_salida = [_cuenta(200 + i, "US Dollar") for i in range(6)]
    hojas_entrada = [_cuenta(300 + i, "US Dollar") for i in range(9)]
    clientes = [_cuenta(400 + i, "US Dollar") for i in range(20)]
    esp |= {"SG_ORIGEN": _cuenta(500, "US Dollar"), "SG_DESTINO": _cuenta(501, "US Dollar")}
    intermediarias = [_cuenta(502 + i, "US Dollar") for i in range(3)]
    cadena = [_cuenta(510 + i, "US Dollar") for i in range(5)]
    anillo = [_cuenta(520 + i, "US Dollar") for i in range(3)]
    esp |= {"CADENA_0": cadena[0], "ANILLO_0": anillo[0]}
    todas = (
        fondo
        + list(esp.values())
        + hojas_salida
        + hojas_entrada
        + clientes
        + intermediarias
        + cadena[1:]
        + anillo[1:]
    )

    txs: list[Tx] = []
    for dia in range(10):
        for _ in range(40):
            o, d = rng.choice(len(fondo), 2, replace=False)
            ts = inicio + timedelta(days=dia, minutes=int(rng.integers(0, 1440)))
            co, cd = fondo[o], fondo[d]
            txs.append(
                Tx(
                    ts,
                    co,
                    cd,
                    float(np.round(rng.lognormal(7, 1), 2)),
                    co.moneda,
                    cd.moneda,
                    str(rng.choice(FORMATOS_FONDO)),
                    0,
                )
            )
        for c in fondo[:5]:
            ts = inicio + timedelta(days=dia, hours=1)
            txs.append(Tx(ts, c, c, 500.0, c.moneda, c.moneda, "Reinvestment", 0))
    # Cuentas especiales con algo de actividad normal para que tengan historia.
    for c in [*esp.values(), *hojas_entrada]:
        for dia in (0, 1, 8):
            ts = inicio + timedelta(days=dia, hours=10)
            d = fondo[int(rng.integers(0, len(fondo)))]
            txs.append(Tx(ts, c, d, 120.0, c.moneda, d.moneda, "Cheque", 0))
    # Comercio legítimo: 20 clientes, dos pagos cada uno, día 3, misma moneda.
    for j, cli in enumerate(clientes):
        for rep in range(2):
            ts = inicio + timedelta(days=2, hours=8 + rep * 6, minutes=j)
            txs.append(
                Tx(ts, cli, esp["COMERCIO"], 35.0 + j, "US Dollar", "US Dollar", "Credit Card", 0)
            )

    patrones: list[tuple[str, str, list[Tx]]] = []
    monedas = ["US Dollar", "Euro", "Yuan", "UK Pound", "Euro", "Yuan"]
    salida = [
        Tx(
            inicio + timedelta(days=2, hours=3 + 2 * i),
            esp["HUB_SALIDA"],
            h,
            9000.0 + 37 * i,
            monedas[i],
            "US Dollar",
            "ACH",
            1,
        )
        for i, h in enumerate(hojas_salida)
    ]
    salida.append(
        Tx(
            salida[0].ts,
            salida[0].origen,
            salida[0].destino,
            salida[0].monto_pagado,
            salida[0].moneda_pagada,
            salida[0].moneda_recibida,
            "ACH",
            1,
        )
    )
    patrones.append(("FAN-OUT", "Max 6-degree Fan-Out", salida))
    entrada = [
        Tx(
            inicio + timedelta(days=7, hours=2 + 3 * i),
            h,
            esp["HUB_ENTRADA"],
            7000.0 + 51 * i,
            monedas[i % len(monedas)],
            "US Dollar",
            "ACH",
            1,
        )
        for i, h in enumerate(hojas_entrada[:8])
    ]
    entrada.append(
        Tx(
            inicio + timedelta(days=11, hours=4),
            hojas_entrada[8],
            esp["HUB_ENTRADA"],
            6500.0,
            "Euro",
            "US Dollar",
            "ACH",
            1,
        )
    )
    patrones.append(("FAN-IN", "Max 9-degree Fan-In", entrada))
    ciclo = [
        Tx(
            inicio + timedelta(days=5, hours=20),
            esp["CICLO_A"],
            esp["CICLO_B"],
            5000.0,
            "US Dollar",
            "Euro",
            "ACH",
            1,
        ),
        Tx(
            inicio + timedelta(days=6, hours=2),
            esp["CICLO_B"],
            esp["CICLO_C"],
            4200.0,
            "Euro",
            "US Dollar",
            "ACH",
            1,
        ),
        Tx(
            inicio + timedelta(days=6, hours=9),
            esp["CICLO_C"],
            esp["CICLO_A"],
            4800.0,
            "US Dollar",
            "US Dollar",
            "ACH",
            1,
        ),
    ]
    patrones.append(("CYCLE", "Max 3 hops", ciclo))
    sg = []
    for i, m in enumerate(intermediarias):
        monto = 4000.0 + 300 * i
        sg.append(
            Tx(
                inicio + timedelta(days=8, hours=1 + i),
                esp["SG_ORIGEN"],
                m,
                monto,
                "US Dollar",
                "US Dollar",
                "ACH",
                1,
            )
        )
        sg.append(
            Tx(
                inicio + timedelta(days=8, hours=6 + i),
                m,
                esp["SG_DESTINO"],
                round(monto * 0.99, 2),
                "US Dollar",
                "US Dollar",
                "ACH",
                1,
            )
        )
    patrones.append(("SCATTER-GATHER", "", sg))
    tramo = [
        Tx(
            inicio + timedelta(days=3, hours=2 + i),
            cadena[i],
            cadena[i + 1],
            2500.0 - 10 * i,
            "US Dollar",
            "US Dollar",
            "ACH",
            1,
        )
        for i in range(4)
    ]
    patrones.append(("RANDOM", "Max 4 hops", tramo))
    vuelta = [
        Tx(
            inicio + timedelta(days=4, hours=3 + 2 * i),
            anillo[i],
            anillo[(i + 1) % 3],
            3000.0 - 20 * i,
            "US Dollar",
            "US Dollar",
            "ACH",
            1,
        )
        for i in range(3)
    ]
    patrones.append(("CYCLE", "Max 3 hops", vuelta))
    txs += sg + tramo + vuelta
    sin_patron = Tx(
        inicio + timedelta(days=3, hours=5),
        fondo[1],
        fondo[2],
        3333.0,
        fondo[1].moneda,
        fondo[2].moneda,
        "ACH",
        1,
    )
    txs += salida + entrada + ciclo + [sin_patron]

    # El CSV real no viene ordenado: se baraja con la semilla.
    orden = rng.permutation(len(txs))
    lineas = [ENCABEZADO_TX] + [txs[i].linea() for i in orden]
    (directorio / f"{prefijo}-Small_Trans.csv").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8"
    )

    bloques = []
    for tipo, detalle, lista in patrones:
        cuerpo = "\n".join(t.linea() for t in lista)
        bloques.append(
            f"BEGIN LAUNDERING ATTEMPT - {tipo}:  {detalle}\n{cuerpo}\n"
            f"END LAUNDERING ATTEMPT - {tipo}\n"
        )
    (directorio / f"{prefijo}-Small_Patterns.txt").write_text("\n".join(bloques), encoding="utf-8")

    cuentas = ["Bank Name,Bank ID,Account Number,Entity ID,Entity Name"]
    for i, c in enumerate(todas):
        cuentas.append(f"Banco #{int(c.banco)},{int(c.banco)},{c.numero},E{i:06d},Corporation #{i}")
    (directorio / f"{prefijo}-Small_accounts.csv").write_text(
        "\n".join(cuentas) + "\n", encoding="utf-8"
    )
    return MiniAMLworld(directorio, esp)

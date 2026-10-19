"""Gráficos del proyecto con Altair (HTML interactivo y PNG con vl-convert).

Paleta: dos series categóricas fijas (detector y regla simple) de la paleta de referencia
validada; texto en tinta neutra, nunca en el color de la serie; un solo eje por gráfico.
"""

from pathlib import Path

import altair as alt
import pandas as pd

AZUL = "#2a78d6"  # serie 1: detector
NARANJA = "#eb6834"  # serie 2: regla simple
GRIS = "#8a8984"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
SUPERFICIE = "#fcfcfb"

AQUA = "#1baf7a"  # serie 3: detectores con señales sospechosas de artefacto
COLOR_SENALES = alt.Scale(
    domain=["estructurales", "con sospechosas", "regla"], range=[AZUL, AQUA, NARANJA]
)
COLOR_METODO = alt.Scale(domain=["Abanicos por forma", "Regla simple"], range=[AZUL, NARANJA])


def _tema(grafico: alt.Chart) -> alt.Chart:
    return (
        grafico.configure(background=SUPERFICIE)
        .configure_axis(
            labelColor=TINTA_2,
            titleColor=TINTA_2,
            gridColor="#e6e5e1",
            domainColor="#c9c8c3",
            labelFontSize=11,
            titleFontSize=11,
        )
        .configure_legend(labelColor=TINTA, titleColor=TINTA_2, orient="top")
        .configure_title(color=TINTA, fontSize=14, anchor="start")
        .configure_header(labelColor=TINTA, titleColor=TINTA_2, labelFontSize=12)
        .configure_view(stroke=None)
    )


def guardar(grafico: alt.Chart, destino: Path, nombre: str) -> list[Path]:
    """Guarda ``nombre.html`` y ``nombre.png`` en ``destino``."""
    destino.mkdir(parents=True, exist_ok=True)
    grafico = _tema(grafico)
    html, png = destino / f"{nombre}.html", destino / f"{nombre}.png"
    grafico.save(str(html))
    grafico.save(str(png), scale_factor=2)
    return [html, png]


def por_dia(dias: pd.DataFrame, titulo: str) -> alt.Chart:
    """Transacciones por día y tasa de lavado por día, en dos gráficos apilados (un eje cada uno).

    ``dias`` trae ``variante, dia, periodo, transacciones, tasa_lavado``.
    """
    base = alt.Chart(dias).encode(
        x=alt.X("dia:N", title=None, axis=alt.Axis(labelAngle=-45)),
        tooltip=[
            alt.Tooltip("variante:N"),
            alt.Tooltip("dia:N"),
            alt.Tooltip("periodo:N"),
            alt.Tooltip("transacciones:Q", format=","),
            alt.Tooltip("tasa_lavado:Q", format=".3%", title="tasa de lavado"),
        ],
    )
    medidos = alt.condition(
        "datum.periodo == 'desarrollo' || datum.periodo == 'prueba'",
        alt.value(AZUL),
        alt.value(GRIS),
    )
    volumen = (
        base.mark_point(filled=True, size=90, opacity=1)
        .encode(
            y=alt.Y("transacciones:Q", title="transacciones", scale=alt.Scale(type="log")),
            color=medidos,
        )
        .properties(width=420, height=150, title="Transacciones por día (gris: no se mide)")
    )
    tasa = (
        base.mark_point(filled=True, size=90, opacity=1)
        .encode(
            y=alt.Y(
                "tasa_lavado:Q",
                title="tasa de lavado",
                axis=alt.Axis(format="%"),
                scale=alt.Scale(type="log"),
            ),
            color=medidos,
        )
        .properties(width=420, height=150, title="Tasa de lavado por día (escala log)")
    )
    columnas = [
        alt.vconcat(
            volumen.transform_filter(alt.datum.variante == v).properties(
                title=f"{v.upper()}: transacciones por día (log; gris: no se mide)"
            ),
            tasa.transform_filter(alt.datum.variante == v).properties(
                title=f"{v.upper()}: tasa de lavado por día (escala log)"
            ),
        )
        for v in sorted(dias.variante.unique())
    ]
    return alt.hconcat(*columnas).properties(title=titulo)


def historias(hist: pd.DataFrame) -> alt.Chart:
    """Cuentas por largo de historia (cubetas log2). ``hist``: variante, desde, hasta, cuentas."""
    hist = hist.assign(rango=hist.desde.astype(str) + "–" + hist.hasta.astype(str))
    return (
        alt.Chart(hist)
        .mark_bar(size=12, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=AZUL)
        .encode(
            x=alt.X("cubeta:O", title="transferencias por cuenta (cubeta log2: 1, 2–3, 4–7, …)"),
            y=alt.Y("cuentas:Q", title="cuentas"),
            tooltip=[
                "variante:N",
                alt.Tooltip("rango:N", title="transferencias"),
                alt.Tooltip("cuentas:Q", format=","),
            ],
        )
        .properties(width=300, height=180)
        .facet(column=alt.Column("variante:N", title=None))
        .properties(title="Largo de la historia por cuenta (días 1 a 10)")
    )


def precision_k(tabla: pd.DataFrame) -> alt.Chart:
    """Precisión en el top-k por cuenta, detector contra regla, con IC de Wilson.

    ``tabla``: variante, metodo, k_etiqueta, precision, ic_inf, ic_sup.
    """
    base = alt.Chart(tabla).encode(
        x=alt.X("metodo:N", title=None, axis=alt.Axis(labels=False, ticks=False)),
    )
    barras = base.mark_bar(size=18, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        y=alt.Y(
            "precision:Q",
            title="precisión en el top-k",
            scale=alt.Scale(domain=[0, 1]),
            axis=alt.Axis(format="%"),
        ),
        color=alt.Color("metodo:N", scale=COLOR_METODO, title=None),
        tooltip=[
            "variante:N",
            "metodo:N",
            "k_etiqueta:N",
            alt.Tooltip("k:Q", title="k"),
            alt.Tooltip("precision:Q", format=".1%"),
            alt.Tooltip("ic_inf:Q", format=".1%", title="IC 95 % inf."),
            alt.Tooltip("ic_sup:Q", format=".1%", title="IC 95 % sup."),
        ],
    )
    barras_error = base.mark_rule(color=TINTA_2, strokeWidth=1.5).encode(
        y="ic_inf:Q", y2="ic_sup:Q"
    )
    orden_k = list(dict.fromkeys(tabla.k_etiqueta))
    return (
        (barras + barras_error)
        .properties(width=70, height=200)
        .facet(
            column=alt.Column("k_etiqueta:N", title=None, sort=orden_k),
            row=alt.Row("variante:N", title=None),
        )
        .properties(title="Precisión en el top-k de cuentas, período de prueba")
    )


def recall_tipo(tabla: pd.DataFrame) -> alt.Chart:
    """Recall por tipo de patrón, detector contra regla, con IC.

    ``tabla``: variante, metodo, tipo, recall, ic_inf, ic_sup, n.
    """
    base = alt.Chart(tabla).encode(
        y=alt.Y("metodo:N", title=None, axis=alt.Axis(labels=False, ticks=False)),
    )
    barras = base.mark_bar(size=10, cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
        x=alt.X(
            "recall:Q", title="recall", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%")
        ),
        color=alt.Color("metodo:N", scale=COLOR_METODO, title=None),
        tooltip=[
            "variante:N",
            "tipo:N",
            "metodo:N",
            alt.Tooltip("recall:Q", format=".1%"),
            alt.Tooltip("ic_inf:Q", format=".1%", title="IC 95 % inf."),
            alt.Tooltip("ic_sup:Q", format=".1%", title="IC 95 % sup."),
            alt.Tooltip("n:Q", title="n (intentos o tx)"),
        ],
    )
    barras_error = base.mark_rule(color=TINTA_2, strokeWidth=1.5).encode(
        x="ic_inf:Q", x2="ic_sup:Q"
    )
    return (
        (barras + barras_error)
        .properties(width=220, height=28)
        .facet(
            row=alt.Row("tipo:N", title=None, header=alt.Header(labelAngle=0, labelAlign="left")),
            column=alt.Column("variante:N", title=None),
        )
        .properties(title="Recall por tipo de patrón, período de prueba")
    )


def detectores(tabla: pd.DataFrame, orden: list[str], medida: str, titulo: str) -> alt.Chart:
    """Barras horizontales por detector, coloreadas por el tipo de señales que usa.

    ``tabla``: variante, etiqueta, senales y la columna ``medida``.
    """
    barras = (
        alt.Chart(tabla)
        .mark_bar(size=10, cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
        .encode(
            y=alt.Y("etiqueta:N", sort=orden, title=None),
            x=alt.X(
                f"{medida}:Q",
                title=titulo,
                scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%" if medida.startswith("precision") else ".2f"),
            ),
            color=alt.Color("senales:N", scale=COLOR_SENALES, title="señales"),
            tooltip=[
                "variante:N",
                "etiqueta:N",
                "senales:N",
                alt.Tooltip(f"{medida}:Q", format=".3f"),
            ],
        )
    )
    texto = barras.mark_text(align="left", dx=4, color=TINTA_2, fontSize=10).encode(
        text=alt.Text(f"{medida}:Q", format=".2f"), color=alt.value(TINTA_2)
    )
    return (
        (barras + texto)
        .properties(width=260, height=alt.Step(18))
        .facet(column=alt.Column("variante:N", title=None))
        .properties(title=f"{titulo[0].upper()}{titulo[1:]} por detector, período de prueba")
    )

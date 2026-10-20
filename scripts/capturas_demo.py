"""Capturas y GIF de ``docs/demo.html`` con Playwright.

Uso:
    uv run python scripts/capturas_demo.py   # -> docs/resultados/demo/*.png y monedas.gif

Sirve ``docs/`` en un puerto local, abre la página en escritorio y en celular (390 px),
**falla si hay errores de consola o desborde horizontal**, toma capturas de las tres pestañas y
graba como GIF la animación del artefacto de las monedas.
"""

import functools
import http.server
import io
import sys
import threading

from PIL import Image
from playwright.sync_api import sync_playwright

from lavado.rutas import DOCS
from lavado.rutas import DOCS_RESULTADOS_DEMO as SALIDA


def _servidor() -> tuple[http.server.ThreadingHTTPServer, int]:
    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

    manejador = functools.partial(Silencioso, directory=str(DOCS))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _desborde(pag) -> bool:
    return pag.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")


def main() -> int:
    srv, puerto = _servidor()
    url = f"http://127.0.0.1:{puerto}/demo.html"
    errores: list[str] = []
    SALIDA.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        nav = p.chromium.launch()
        for nombre, vista, escala in (
            ("escritorio", {"width": 1200, "height": 900}, 1),
            ("celular", {"width": 390, "height": 844}, 2),
        ):
            pag = nav.new_page(viewport=vista, device_scale_factor=escala, color_scheme="light")
            pag.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
            pag.on("pageerror", lambda e: errores.append(str(e)))
            pag.goto(url)
            pag.wait_for_selector("body[data-listo='1']", timeout=60_000)
            for pestana in ("forma", "monedas", "alertas"):
                pag.click(f"#tab-{pestana}")
                pag.wait_for_timeout(7500 if pestana == "monedas" else 600)
                if _desborde(pag):
                    errores.append(f"{nombre} ({pestana}): desborde horizontal")
                pag.screenshot(path=str(SALIDA / f"{nombre}_{pestana}.png"), full_page=True)
            pag.close()

        # GIF de la animación de las monedas
        pag = nav.new_page(
            viewport={"width": 760, "height": 900}, device_scale_factor=1, color_scheme="light"
        )
        pag.goto(url)
        pag.wait_for_selector("body[data-listo='1']", timeout=60_000)
        pag.click("#tab-monedas")
        tarjeta = pag.wait_for_selector("#anim")
        tarjeta.scroll_into_view_if_needed()
        pag.click("#anim-repetir")
        cuadros, duraciones = [], []
        for _ in range(85):
            cuadros.append(Image.open(io.BytesIO(tarjeta.screenshot())).convert("RGB"))
            duraciones.append(120)
            pag.wait_for_timeout(100)
        duraciones[-1] = 2500
        cuadros[0].save(
            SALIDA / "monedas.gif",
            save_all=True,
            append_images=cuadros[1:],
            duration=duraciones,
            loop=0,
            optimize=True,
        )
        cuadros[-1].save(SALIDA / "monedas.png")
        nav.close()
    srv.shutdown()
    for e in errores:
        print("ERROR:", e)
    print(f"capturas en {SALIDA}; {len(errores)} errores")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())

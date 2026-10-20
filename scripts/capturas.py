"""Capturas del universo de Cosmograph (escritorio y celular) y revisión de errores de consola.

Uso:
    uv run python scripts/capturas.py   # -> docs/resultados/hito5/universo_*.png

Levanta un servidor local sobre docs/ (y lo cierra al terminar), abre la página con Chromium
sin ventana y guarda capturas. Requiere internet: Cosmograph se carga desde esm.sh.
"""

import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

from lavado.rutas import DOCS, DOCS_RESULTADOS_HITO5

PUERTO = 8765
URL = f"http://localhost:{PUERTO}/hito5_universo.html"


def esperar_carga(pagina, tiempo_s: float = 12.0) -> str:
    pagina.wait_for_function(
        "document.getElementById('estado').textContent.includes('cuentas')"
        " || document.getElementById('estado').textContent.includes('No se pudo')",
        timeout=120_000,
    )
    time.sleep(tiempo_s)  # deja correr la simulación de fuerzas
    return pagina.text_content("#estado")


def main() -> int:
    servidor = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PUERTO), "--directory", str(DOCS)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    errores: list[str] = []
    try:
        time.sleep(1.5)
        with sync_playwright() as p:
            navegador = p.chromium.launch(args=["--use-gl=angle", "--enable-unsafe-swiftshader"])
            pantallas = {
                "escritorio": {"viewport": {"width": 1400, "height": 860}},
                "movil": p.devices["iPhone 13"],
            }
            for nombre, opciones in pantallas.items():
                contexto = navegador.new_context(**opciones)
                pagina = contexto.new_page()
                pagina.on(
                    "console",
                    lambda m, n=nombre: (
                        errores.append(f"{n}: {m.text}") if m.type == "error" else None
                    ),
                )
                pagina.on("pageerror", lambda e, n=nombre: errores.append(f"{n}: {e}"))
                pagina.goto(URL)
                print(nombre, "HI:", esperar_carga(pagina))
                pagina.screenshot(path=str(DOCS_RESULTADOS_HITO5 / f"universo_{nombre}.png"))
                if nombre == "escritorio":
                    pagina.click("[data-variante='li']")
                    print(nombre, "LI:", esperar_carga(pagina))
                    pagina.screenshot(path=str(DOCS_RESULTADOS_HITO5 / "universo_li.png"))
                    pagina.click("[data-variante='hi']")
                    esperar_carga(pagina, 1)
                    pagina.select_option("#tipo", "CYCLE")
                    time.sleep(3)
                    print(nombre, "CYCLE:", pagina.text_content("#estado"))
                    pagina.screenshot(path=str(DOCS_RESULTADOS_HITO5 / "universo_ciclos.png"))
                contexto.close()
            navegador.close()
    finally:
        servidor.terminate()
        servidor.wait(timeout=10)
    print("Errores de consola:", errores or "ninguno")
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())

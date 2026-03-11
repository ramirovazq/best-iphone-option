#!/usr/bin/env python3
"""
Script para obtener TODOS los modelos disponibles para una marca concreta
desde el comparador de Telcel y guardarlos en un CSV.

Salida CSV (un renglón por modelo):
    marca, modelo

Ejemplo:
    uv run python scraper_telcel_modelos.py --marca "Apple" --csv modelos_apple.csv
"""

import argparse
import csv
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


URL_COMPARADOR = "https://www.telcel.com/tienda/comparador"
CSV_DEFAULT = "modelos_telcel.csv"


def ensure_csv_header(csv_path: Path) -> None:
    """Crea el CSV con cabecera si no existe."""
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["marca", "modelo"])


def append_row(csv_path: Path, marca: str, modelo: str) -> None:
    """Añade una fila (marca, modelo) al CSV."""
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerow([marca, modelo])


def main() -> None:
    parser = argparse.ArgumentParser(description="Enumera todos los modelos de una marca en el comparador Telcel")
    parser.add_argument("--marca", "-m", required=True, help='Marca a buscar (ej. "Apple")')
    parser.add_argument(
        "--csv",
        "-o",
        default=CSV_DEFAULT,
        help=f"Archivo CSV de salida (default: {CSV_DEFAULT})",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Mostrar ventana del navegador (por defecto va en segundo plano)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Guardar capturas para depurar (opcional)",
    )
    args = parser.parse_args()

    marca_buscada = args.marca.strip()
    csv_path = Path(args.csv)
    ensure_csv_header(csv_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.no_headless)
        context = browser.new_context(
            locale="es-MX",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            # Ir al comparador
            page.goto(URL_COMPARADOR, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # Bloque principal del comparador (columna izquierda)
            page.get_by_text("Selecciona un equipo para comparar", exact=False).first.wait_for(
                state="visible", timeout=10000
            )
            compare_item = page.locator(".cx-compare-izq").first
            if not compare_item.count():
                compare_item = page.locator(".cx-compare-item:not(.cx-compare-item-hide)").first
            compare_item.wait_for(state="visible", timeout=5000)
            compare_item.scroll_into_view_if_needed()

            # Selector de marca (primer ng-select)
            marca_trigger = compare_item.get_by_placeholder(re.compile(r"elige\s+una\s+opc", re.I)).first
            if not marca_trigger.count():
                marca_trigger = compare_item.locator("input[placeholder*='opcion'], input[placeholder*='opción']").first
            if not marca_trigger.count():
                marca_trigger = compare_item.locator("input").first
            if not marca_trigger.count():
                raise RuntimeError("No se encontró el selector de Marca dentro de la columna izquierda.")

            def abrir_dropdown_marca() -> None:
                try:
                    ng_select = compare_item.locator(".ng-select").first
                    if ng_select.count():
                        ng_select.scroll_into_view_if_needed()
                        ng_select.click(force=True)
                        return
                except Exception:
                    pass
                try:
                    marca_trigger.evaluate("el => { el.focus(); el.click(); }")
                    return
                except Exception:
                    pass
                marca_trigger.click(force=True)

            abrir_dropdown_marca()
            time.sleep(1)

            # Panel de marcas y selección de la marca deseada
            panel_marcas = page.locator(".ng-dropdown-panel, .ng-select-bottom").first
            panel_marcas.wait_for(state="visible", timeout=5000)
            opcion_marca = panel_marcas.locator(".ng-option").filter(
                has_text=re.compile(re.escape(marca_buscada), re.I)
            ).first
            if not opcion_marca.count():
                opcion_marca = panel_marcas.locator(".ng-option").get_by_text(marca_buscada, exact=False).first
            if not opcion_marca.count():
                raise RuntimeError(f"No se encontró la marca '{marca_buscada}' en el dropdown de marcas.")
            opcion_marca.click(force=True)
            time.sleep(1.5)

            # Selector de modelo (segundo ng-select en el mismo bloque)
            modelo_trigger = compare_item.get_by_placeholder(re.compile(r"elige\s+una\s+opc", re.I)).nth(1)
            if not modelo_trigger.count():
                modelo_trigger = compare_item.locator("input[placeholder*='opcion'], input[placeholder*='opción']").nth(1)
            if not modelo_trigger.count():
                modelo_trigger = compare_item.locator("input").nth(1)
            if not modelo_trigger.count():
                raise RuntimeError("No se encontró el selector de Modelo dentro de la columna izquierda.")

            # Abrir dropdown de modelo
            modelo_trigger.scroll_into_view_if_needed()
            modelo_trigger.click(force=True)
            time.sleep(1)

            # Panel de modelos: usar el último .ng-dropdown-panel (el de modelo)
            for _ in range(3):
                try:
                    page.wait_for_selector(".ng-dropdown-panel .ng-option", state="visible", timeout=5000)
                    panel_modelos = page.locator(".ng-dropdown-panel").last
                    if panel_modelos.locator(".ng-option").count() > 0:
                        break
                except Exception:
                    time.sleep(0.5)
            else:
                raise RuntimeError("No se pudo abrir el dropdown de modelos para la marca seleccionada.")

            # Recoger textos de opciones; intentar cargar más con scroll por si hay virtual scroll
            textos_modelos: list[str] = []
            vistos = set()
            for _ in range(5):
                for op in panel_modelos.locator(".ng-option").all():
                    try:
                        t = op.inner_text().strip()
                        if t and t not in vistos:
                            vistos.add(t)
                            textos_modelos.append(t)
                    except Exception:
                        continue
                try:
                    panel_modelos.evaluate("el => { el.scrollTop = el.scrollHeight; }")
                    time.sleep(0.4)
                except Exception:
                    break

            # Cerrar dropdown
            page.keyboard.press("Escape")
            time.sleep(0.3)

            if not textos_modelos:
                print(f"No se encontraron modelos para la marca '{marca_buscada}'.")
                return

            print(f"Modelos encontrados para '{marca_buscada}': {len(textos_modelos)}")
            for modelo in textos_modelos:
                append_row(csv_path, marca_buscada, modelo)

            print(f"Modelos guardados en: {csv_path.absolute()}")

        finally:
            browser.close()


if __name__ == "__main__":
    main()


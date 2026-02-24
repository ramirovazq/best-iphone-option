#!/usr/bin/env python3
"""
Script para extraer modelo y precio de equipos desde el comparador de Telcel.
Uso: python scraper_telcel.py --marca "Apple" [--modelo "iPhone 16"] [--csv salida.csv]
"""

import argparse
import csv
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


URL_COMPARADOR = "https://www.telcel.com/tienda/comparador"
CSV_DEFAULT = "equipos_telcel.csv"


def ensure_csv_header(csv_path: Path) -> None:
    """Crea el CSV con cabecera si no existe."""
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["marca", "modelo", "precio", "url_detalle"])


def append_row(csv_path: Path, marca: str, modelo: str, precio: str, url_detalle: str) -> None:
    """Añade una fila al CSV."""
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([marca, modelo, precio, url_detalle])


def normalizar_precio(texto: str) -> str:
    """Extrae el precio en formato legible (ej. $10,999)."""
    if not texto:
        return ""
    # Quitar espacios y dejar números, $ y comas
    return re.sub(r"\s+", " ", texto.strip())


def scrape_detalle(page, url_detalle: str, marca: str, csv_path: Path) -> bool:
    """
    Entra a la página de detalle, extrae modelo y precio, y guarda en CSV.
    Devuelve True si se pudo extraer y guardar.
    """
    page.goto(url_detalle, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)

    # Selectores habituales en páginas de detalle: título del producto y precio
    modelo = ""
    precio = ""

    # Intentar por data attributes, h1, o clases comunes de e-commerce
    titulo_el = page.locator("h1").first
    if titulo_el.count():
        modelo = titulo_el.inner_text().strip()

    # Precio: suele estar en [data-testid="price"], .price, o similar
    for selector in [
        '[data-testid*="price"]',
        '[data-testid*="precio"]',
        ".price",
        ".precio",
        "[class*='price']",
        "[class*='Price']",
    ]:
        try:
            el = page.locator(selector).first
            if el.count() and el.is_visible():
                precio = normalizar_precio(el.inner_text())
                if precio and ("$" in precio or re.search(r"\d", precio)):
                    break
        except Exception:
            continue

    if not modelo and not precio:
        # Fallback: título de la página
        modelo = page.title() or ""

    if modelo or precio:
        append_row(csv_path, marca, modelo, precio, url_detalle)
        print(f"  Guardado: {modelo} | {precio}")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae modelo y precio del comparador Telcel")
    parser.add_argument("--marca", "-m", required=True, help='Marca a buscar (ej. "Apple")')
    parser.add_argument(
        "--modelo",
        "-M",
        default=None,
        help='Modelo concreto (opcional). Si no se pasa, se intentan todos los modelos de la marca.',
    )
    parser.add_argument("--csv", "-o", default=CSV_DEFAULT, help=f"Archivo CSV de salida (default: {CSV_DEFAULT})")
    parser.add_argument("--no-headless", action="store_true", help="Mostrar ventana del navegador (por defecto va en segundo plano)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    ensure_csv_header(csv_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.no_headless)
        context = browser.new_context(
            locale="es-MX",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            page.goto(URL_COMPARADOR, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Selector de MARCA (primer bloque del comparador)
            # La página tiene dos columnas; usamos la primera para "Marca" y "Modelo"
            marca_label = page.get_by_text("Marca", exact=True).first
            # Ir al contenedor del comparador y abrir el dropdown de marca
            comparador = page.locator("[class*='comparador'], [class*='comparison']").first
            if not comparador.count():
                comparador = page.locator("main").first
            if not comparador.count():
                comparador = page

            # Abrir dropdown Marca: clic en el input/trigger que muestra "Elige una..."
            marca_trigger = comparador.get_by_placeholder(re.compile("elige una", re.I)).first
            if not marca_trigger.count():
                marca_trigger = comparador.locator("button, [role='combobox'], [role='listbox']").first
            if not marca_trigger.count():
                # Fallback: primer clickable cerca del texto "Marca"
                marca_trigger = marca_label.locator("..").locator("button, input, [tabindex='0']").first

            marca_trigger.click()
            time.sleep(0.8)

            # Seleccionar la marca indicada
            opcion_marca = page.get_by_text(args.marca, exact=True).first
            if not opcion_marca.count():
                opcion_marca = page.get_by_role("option").filter(has_text=args.marca).first
            if not opcion_marca.count():
                opcion_marca = page.locator(f"li:has-text('{args.marca}'), div:has-text('{args.marca}')").first
            opcion_marca.click()
            time.sleep(1.2)

            # Abrir dropdown Modelo
            modelo_trigger = comparador.get_by_placeholder(re.compile("elige|modelo", re.I)).first
            if not modelo_trigger.count():
                modelo_trigger = comparador.get_by_text("Modelo", exact=True).locator("..").locator("button, input, [role='combobox']").first
            if not modelo_trigger.count():
                modelo_trigger = comparador.locator("button, [role='combobox']").nth(1)
            modelo_trigger.click()
            time.sleep(0.8)

            def seleccionar_modelo_y_extraer(nombre_modelo: str) -> bool:
                """Abre dropdown modelo, selecciona nombre_modelo, abre 'ver detalles' y guarda en CSV."""
                modelo_trigger.click()
                time.sleep(0.8)
                op = page.get_by_text(nombre_modelo, exact=True).first
                if not op.count():
                    op = page.get_by_role("option").filter(has_text=nombre_modelo).first
                if not op.count():
                    op = page.locator(f"li:has-text('{nombre_modelo}'), div:has-text('{nombre_modelo}')").first
                if not op.count():
                    return False
                op.click()
                time.sleep(1.5)

                ver_detalles = page.get_by_role("link", name=re.compile("ver detalles", re.I)).first
                if not ver_detalles.count():
                    ver_detalles = page.get_by_role("button", name=re.compile("ver detalles", re.I)).first
                if not ver_detalles.count():
                    ver_detalles = page.get_by_text(re.compile("ver detalles", re.I)).first
                if not ver_detalles.count() or not ver_detalles.is_visible():
                    return False

                href = ver_detalles.get_attribute("href")
                if href and not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(URL_COMPARADOR, href)
                if href:
                    return scrape_detalle(page, href, args.marca, csv_path)
                ver_detalles.click()
                time.sleep(2)
                return scrape_detalle(page, page.url, args.marca, csv_path)
            # ---

            if args.modelo:
                if not seleccionar_modelo_y_extraer(args.modelo):
                    print(f"No se encontró el modelo '{args.modelo}' o el botón 'ver detalles'.")
            else:
                # Obtener lista de modelos: abrir dropdown y leer opciones
                modelo_trigger.click()
                time.sleep(0.8)
                opciones = page.locator("[role='option'], li[class*='option'], div[class*='option']").all()
                if not opciones:
                    opciones = page.locator("ul li, [role='listbox'] > *").all()
                textos_modelos = []
                for op in opciones:
                    try:
                        if op.is_visible():
                            t = op.inner_text().strip()
                            if t and t != args.marca and t not in textos_modelos:
                                textos_modelos.append(t)
                    except Exception:
                        continue
                page.keyboard.press("Escape")  # Cerrar dropdown
                time.sleep(0.3)
                if not textos_modelos:
                    print("No se encontraron modelos para esta marca. Prueba --modelo con un nombre exacto.")
                    browser.close()
                    return
                print(f"Modelos a procesar: {len(textos_modelos)}")
                for nombre_modelo in textos_modelos:
                    if seleccionar_modelo_y_extraer(nombre_modelo):
                        page.goto(URL_COMPARADOR, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_load_state("networkidle", timeout=15000)
                        # Re-abrir marca y modelo para el siguiente
                        marca_trigger = comparador.get_by_placeholder(re.compile("elige una", re.I)).first
                        if marca_trigger.count():
                            marca_trigger.click()
                            time.sleep(0.5)
                            opcion_marca.click()
                            time.sleep(1)
                        modelo_trigger = comparador.get_by_placeholder(re.compile("elige|modelo", re.I)).first
                        if not modelo_trigger.count():
                            modelo_trigger = comparador.locator("button, [role='combobox']").nth(1)
                    else:
                        print(f"  Omitido (no detalles): {nombre_modelo}")

        except Exception as e:
            print(f"Error: {e}")
            raise
        finally:
            browser.close()

    print(f"\nDatos guardados en: {csv_path.absolute()}")


if __name__ == "__main__":
    main()

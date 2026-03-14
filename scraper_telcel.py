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
            w = csv.writer(f, delimiter=";")
            w.writerow(["marca", "modelo", "precio", "url_detalle"])


def append_row(csv_path: Path, marca: str, modelo: str, precio: str, url_detalle: str) -> None:
    """Añade una fila al CSV."""
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f,delimiter=";").writerow([marca, modelo, precio, url_detalle])


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
    time.sleep(10)

    # Selectores habituales en páginas de detalle: título del producto y precio
    modelo = ""
    precio = ""

    # Intentar por data attributes, h1, o clases comunes de e-commerce
    titulo_el = page.locator("h1").first
    if titulo_el.count():
        modelo = titulo_el.inner_text().strip()

    # Precio: suele estar en [data-testid="price"], .price, o similar
    for selector in [
        ".product-summary",
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


def cargar_modelos_desde_csv(ruta_csv: Path, marca: str) -> list[str]:
    """Lee un CSV (marca, modelo) y devuelve la lista de modelos para la marca indicada.
    Acepta delimitador coma o punto y coma (scraper_telcel_modelos.py escribe con ;)."""
    modelos: list[str] = []
    with open(ruta_csv, encoding="utf-8", newline="") as f:
        raw = f.read()
    for delimiter in (";", ","):  # scraper_telcel_modelos.py escribe con ";"
        f = iter(raw.splitlines())
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)
        if not rows:
            continue
        first = rows[0]
        if "modelo" not in first and "marca" not in first:
            continue
        for row in rows:
            m = (row.get("marca") or "").strip()
            mod = (row.get("modelo") or "").strip()
            if mod and (not m or m.lower() == marca.lower()):
                modelos.append(mod)
        if modelos:
            return modelos
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae modelo y precio del comparador Telcel")
    parser.add_argument("--marca", "-m", required=True, help='Marca a buscar (ej. "Apple")')
    parser.add_argument(
        "--modelo",
        "-M",
        default=None,
        help='Modelo concreto (opcional). Si no se pasa, se intentan todos los modelos de la marca.',
    )
    parser.add_argument(
        "--csv-modelos",
        default=None,
        metavar="ARCHIVO",
        help='CSV con columnas marca,modelo (salida de scraper_telcel_modelos.py). Itera sobre cada modelo del archivo.',
    )
    parser.add_argument("--csv", "-o", default=CSV_DEFAULT, help=f"Archivo CSV de salida (default: {CSV_DEFAULT})")
    parser.add_argument("--no-headless", action="store_true", help="Mostrar ventana del navegador (por defecto va en segundo plano)")
    parser.add_argument("--debug", action="store_true", help="Guardar capturas y pausas para depurar")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    ensure_csv_header(csv_path)

    # Si se pasó --csv-modelos, cargar lista de modelos desde ese archivo
    modelos_desde_csv: list[str] | None = None
    if args.csv_modelos:
        path_csv_modelos = Path(args.csv_modelos)
        if not path_csv_modelos.exists():
            raise FileNotFoundError(f"No se encontró el archivo de modelos: {path_csv_modelos}")
        modelos_desde_csv = cargar_modelos_desde_csv(path_csv_modelos, args.marca.strip())
        if not modelos_desde_csv:
            raise ValueError(
                f"No hay modelos para la marca '{args.marca}' en {path_csv_modelos}. "
                "Comprueba que el CSV tenga columnas 'marca' y 'modelo'."
            )
        print(f"Modelos a procesar (desde {path_csv_modelos.name}): {len(modelos_desde_csv)}")

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
            # No usar networkidle: la página suele tener peticiones continuas. Esperamos al contenido visible.
            time.sleep(2)
            # Estructura real: texto "Selecciona un equipo para comparar." y debajo 3 divs:
            # .cx-compare-izq, .cx-compare-der, .cx-compare-item-hide. Usamos el primer bloque visible.
            page.get_by_text("Selecciona un equipo para comparar", exact=False).first.wait_for(state="visible", timeout=10000)
            compare_item = page.locator(".cx-compare-izq").first
            if not compare_item.count():
                compare_item = page.locator(".cx-compare-item:not(.cx-compare-item-hide)").first
            compare_item.wait_for(state="visible", timeout=5000)
            compare_item.scroll_into_view_if_needed()
            comparador = page  # para compatibilidad con el resto del script
            marca_label = compare_item.get_by_text("Marca", exact=True).first
            if not marca_label.count():
                marca_label = page.get_by_text("Marca", exact=True).first

            # Dentro del bloque .cx-compare-izq (o el visible) hay "elige una opción": primer input = Marca
            marca_trigger = compare_item.get_by_placeholder(re.compile(r"elige\s+una\s+opc", re.I)).first
            if not marca_trigger.count():
                marca_trigger = compare_item.locator("input[placeholder*='opcion'], input[placeholder*='opción']").first
            if not marca_trigger.count():
                marca_trigger = compare_item.locator("input").first
            if not marca_trigger.count():
                if args.debug:
                    page.screenshot(path="debug_error_sin_trigger_marca.png")
                raise RuntimeError(
                    "No se encontró el selector de Marca dentro de .cx-compare-izq. Ejecuta con --debug."
                )

            marca_buscada = args.marca.strip()
            marca_label.scroll_into_view_if_needed()
            time.sleep(0.5)
            if args.debug:
                page.screenshot(path="debug_01_antes_dropdown_marca.png")
                print("Debug: captura guardada en debug_01_antes_dropdown_marca.png")

            # Abrir dropdown: ng-select suele abrir al hacer clic en el contenedor .ng-select (no solo el input)
            def _abrir_dropdown_marca():
                try:
                    # Intentar clic en el contenedor .ng-select del primer bloque (marca)
                    ng_select = compare_item.locator(".ng-select").first
                    if ng_select.count():
                        ng_select.scroll_into_view_if_needed()
                        ng_select.click(force=True)
                        return True
                except Exception:
                    pass
                try:
                    marca_trigger.evaluate("el => { el.focus(); el.click(); }")
                    return True
                except Exception:
                    pass
                try:
                    marca_trigger.click(force=True)
                    return True
                except Exception:
                    pass
                return False

            for intento in range(3):
                _abrir_dropdown_marca()
                time.sleep(1)
                panel = page.locator(".ng-dropdown-panel, .ng-select-bottom").first
                try:
                    panel.wait_for(state="visible", timeout=4000)
                    break
                except Exception:
                    if intento == 2:
                        raise RuntimeError(
                            "El dropdown de marca no se abrió después de 3 intentos. "
                            "Prueba con --no-headless y --debug para ver la página."
                        )
            if args.debug:
                page.screenshot(path="debug_02_despues_abrir_marca.png")
                print("Debug: captura guardada en debug_02_despues_abrir_marca.png")

            # Opción dentro del panel (o cualquier .ng-option visible con la marca)
            opcion_marca = panel.locator(".ng-option").filter(has_text=re.compile(re.escape(marca_buscada), re.I)).first
            if not opcion_marca.count():
                opcion_marca = panel.locator(".ng-option").get_by_text(marca_buscada, exact=True).first
            if not opcion_marca.count():
                opcion_marca = panel.locator(".ng-option").get_by_text(marca_buscada.upper(), exact=True).first
            if not opcion_marca.count():
                opcion_marca = page.locator(".ng-option").filter(has_text=re.compile(re.escape(marca_buscada), re.I)).first
            if not opcion_marca.count():
                raise RuntimeError(f"No se encontró la opción de marca '{marca_buscada}' en .ng-option.")
            opcion_marca.click(force=True)
            time.sleep(1.2)

            # Dentro del mismo compare_item, segundo "elige una opción" = Modelo
            modelo_trigger = compare_item.get_by_placeholder(re.compile(r"elige\s+una\s+opc", re.I)).nth(1)
            if not modelo_trigger.count():
                modelo_trigger = compare_item.locator("input[placeholder*='opcion'], input[placeholder*='opción']").nth(1)
            if not modelo_trigger.count():
                modelo_trigger = compare_item.locator("input").nth(1)
            modelo_trigger.scroll_into_view_if_needed()
            modelo_trigger.click(force=True)
            time.sleep(0.8)

            def seleccionar_modelo_y_extraer(nombre_modelo: str) -> bool:
                """Abre dropdown modelo, selecciona nombre_modelo, abre 'ver detalles' y guarda en CSV."""
                for _ in range(3):
                    try:
                        compare_item.locator(".ng-select").nth(1).scroll_into_view_if_needed()
                        compare_item.locator(".ng-select").nth(1).click(force=True)
                    except Exception:
                        modelo_trigger.click(force=True)
                    time.sleep(1)
                    try:
                        page.wait_for_selector(".ng-dropdown-panel .ng-option", state="visible", timeout=5000)
                        panel_modelo = page.locator(".ng-dropdown-panel").last
                        if panel_modelo.locator(".ng-option").count() > 0:
                            break
                    except Exception:
                        pass
                    panel_modelo = page.locator(".ng-dropdown-panel").first
                    if panel_modelo.locator(".ng-option").count() > 0:
                        break
                else:
                    return False
                time.sleep(0.5)

                op = panel_modelo.locator(".ng-option").filter(has_text=re.compile(re.escape(nombre_modelo), re.I)).first
                if not op.count():
                    op = panel_modelo.locator(".ng-option").get_by_text(nombre_modelo, exact=False).first
                if not op.count():
                    palabras = nombre_modelo.split()
                    if len(palabras) >= 2:
                        regex_flex = re.compile(
                            r".*".join(re.escape(p) for p in palabras),
                            re.I | re.DOTALL
                        )
                        op = panel_modelo.locator(".ng-option").filter(has_text=regex_flex).first
                    else:
                        op = panel_modelo.locator(".ng-option").get_by_text(nombre_modelo, exact=True).first
                if not op.count():
                    op = page.locator(".ng-option").filter(has_text=re.compile(re.escape(nombre_modelo), re.I)).first
                if not op.count():
                    return False
                op.click(force=True)
                time.sleep(8)

                print("[ver detalles] Buscando bloque .cx-compare-content...")
                compare_content = compare_item.locator(".cx-compare-content").first
                if not compare_content.count():
                    compare_content = page.locator(".cx-compare-content").first
                    print("[ver detalles] compare_content no en compare_item, usando page.")
                try:
                    compare_content.wait_for(state="visible", timeout=10000)
                    print("[ver detalles] .cx-compare-content visible.")
                except Exception as e:
                    print(f"[ver detalles] .cx-compare-content no apareció (timeout o no existe): {e}")
                    if args.debug:
                        page.screenshot(path="debug_ver_detalles_sin_compare_content.png")
                    return False
                compare_content.scroll_into_view_if_needed()
                if args.debug:
                    page.screenshot(path="debug_03_antes_buscar_ver_detalles.png")
                    print("Debug: captura debug_03_antes_buscar_ver_detalles.png")

                time.sleep(5)
                print("debug ramiro ...5 segs")

                boton = page.locator("button:has-text('Ver detalles')")
                boton.wait_for(state="visible")
                boton.click()
                print("debug ramiro ... ver_detalles_button", boton)
                time.sleep(5)

                page.screenshot(path="debug_04_despues_click_ver_detalles.png")
                print("Debug: captura debug_04_despues_click_ver_detalles.png")


                return scrape_detalle(page, page.url, args.marca, csv_path)
            # ---

            if args.modelo and not modelos_desde_csv:
                if not seleccionar_modelo_y_extraer(args.modelo):
                    print(f"No se encontró el modelo '{args.modelo}' o el botón 'ver detalles'.")
            elif modelos_desde_csv:
                for i, nombre_modelo in enumerate(modelos_desde_csv):
                    if i > 0:
                        page.goto(URL_COMPARADOR, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(2)
                        compare_item = page.locator(".cx-compare-izq").first
                        if not compare_item.count():
                            compare_item = page.locator(".cx-compare-item:not(.cx-compare-item-hide)").first
                        compare_item.wait_for(state="visible", timeout=5000)
                        _abrir_dropdown_marca()
                        time.sleep(1)
                        panel = page.locator(".ng-dropdown-panel, .ng-select-bottom").first
                        try:
                            panel.wait_for(state="visible", timeout=5000)
                        except Exception:
                            print(f"  Omitido (no se abrió marca): {nombre_modelo}")
                            continue
                        panel.locator(".ng-option").filter(has_text=re.compile(re.escape(marca_buscada), re.I)).first.click(force=True)
                        time.sleep(1)
                        marca_trigger = compare_item.get_by_placeholder(re.compile(r"elige\s+una\s+opc", re.I)).first
                        if not marca_trigger.count():
                            marca_trigger = compare_item.locator("input").first
                        modelo_trigger = compare_item.get_by_placeholder(re.compile(r"elige\s+una\s+opc", re.I)).nth(1)
                        if not modelo_trigger.count():
                            modelo_trigger = compare_item.locator("input").nth(1)
                    if seleccionar_modelo_y_extraer(nombre_modelo):
                        pass
                    else:
                        print(f"  Omitido (no detalles): {nombre_modelo}")
            else:
                # Obtener lista de modelos: abrir segundo .ng-select, leer .ng-option del panel
                for _ in range(3):
                    try:
                        compare_item.locator(".ng-select").nth(1).click(force=True)
                    except Exception:
                        modelo_trigger.click(force=True)
                    time.sleep(1)
                    panel_modelos = page.locator(".ng-dropdown-panel, .ng-select-bottom").first
                    try:
                        panel_modelos.wait_for(state="visible", timeout=4000)
                        break
                    except Exception:
                        pass
                else:
                    raise RuntimeError("No se pudo abrir el dropdown de modelo.")
                opciones = panel_modelos.locator(".ng-option").all()
                textos_modelos = []
                for op in opciones:
                    try:
                        t = op.inner_text().strip()
                        if t and t != marca_buscada and t not in textos_modelos:
                            textos_modelos.append(t)
                    except Exception:
                        continue
                page.keyboard.press("Escape")
                time.sleep(0.3)
                if not textos_modelos:
                    print("No se encontraron modelos para esta marca. Prueba --modelo con un nombre exacto.")
                    browser.close()
                    return
                print(f"Modelos a procesar: {len(textos_modelos)}")
                for nombre_modelo in textos_modelos:
                    if seleccionar_modelo_y_extraer(nombre_modelo):
                        page.goto(URL_COMPARADOR, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(2)
                        # Re-obtener bloque comparador y selectores
                        compare_item = page.locator(".cx-compare-izq").first
                        if not compare_item.count():
                            compare_item = page.locator(".cx-compare-item:not(.cx-compare-item-hide)").first
                        marca_trigger = compare_item.get_by_placeholder(re.compile(r"elige\s+una\s+opc", re.I)).first
                        if not marca_trigger.count():
                            marca_trigger = compare_item.locator("input").first
                        if marca_trigger.count():
                            marca_trigger.scroll_into_view_if_needed()
                            marca_trigger.click(force=True)
                            time.sleep(1)
                            panel = page.locator(".ng-dropdown-panel").first
                            panel.wait_for(state="visible", timeout=5000)
                            panel.locator(".ng-option").filter(has_text=re.compile(re.escape(marca_buscada), re.I)).first.click(force=True)
                            time.sleep(1)
                        modelo_trigger = compare_item.get_by_placeholder(re.compile(r"elige\s+una\s+opc", re.I)).nth(1)
                        if not modelo_trigger.count():
                            modelo_trigger = compare_item.locator("input").nth(1)
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

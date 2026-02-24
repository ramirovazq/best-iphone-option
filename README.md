# Comparador Telcel – extracción de precios

Script en **Python** que usa el comparador de Telcel, elige una marca (y opcionalmente un modelo), abre “Ver detalles” de cada equipo y guarda **modelo** y **precio** en un CSV.

## Por qué Python + Playwright

- La página del comparador es dinámica (dropdowns que se rellenan con JavaScript).
- **Playwright** controla un navegador real y permite hacer clic en marca, modelo y “Ver detalles” como un usuario.
- **Python** encaja con el resto del proyecto y hace muy fácil leer/escribir CSV y añadir lógica (varias marcas, reintentos, etc.).

Alternativa en Node sería Puppeteer/Playwright en JS; la lógica sería la misma.

## Requisitos

- Python 3.12+
- Navegador Chromium (lo instala Playwright)

## Instalación

```bash
# Opción A: con uv (recomendado)
uv sync
uv run playwright install chromium

# Opción B: con pip
pip install playwright
playwright install chromium
```

## Uso

```bash
# Una marca y todos sus modelos (recomendado la primera vez)
python scraper_telcel.py --marca "Apple" --csv equipos_apple.csv

# Una marca y un modelo concreto
python scraper_telcel.py --marca "Apple" --modelo "iPhone 16" --csv resultado.csv

# Ver el navegador (útil para depurar)
python scraper_telcel.py --marca "Samsung" --no-headless
```

### Parámetros

| Parámetro   | Descripción |
|------------|-------------|
| `--marca`  | Marca a buscar (ej. `Apple`, `Samsung`). Obligatorio. |
| `--modelo` | Modelo concreto. Si no se indica, se intentan todos los modelos de la marca. |
| `--csv`    | Archivo CSV de salida. Por defecto: `equipos_telcel.csv`. |
| `--headless` | Por defecto el navegador va en segundo plano; usa `--no-headless` para verlo. |

## Salida CSV

El archivo tendrá columnas:

- `marca`
- `modelo`
- `precio`
- `url_detalle`

Se crea el archivo con cabecera si no existe y se van **añadiendo** filas en cada ejecución (no se borra el CSV al volver a correr el script).

## Notas

- Si la web de Telcel cambia estructura o clases, puede que haya que ajustar los selectores en `scraper_telcel.py` (busca “Marca”, “Modelo”, “ver detalles” y los selectores de precio en la página de detalle).
- Para muchas marcas o modelos, considera añadir pausas (`time.sleep`) o límites para no saturar el sitio.

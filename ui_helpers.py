"""Helpers visuales: paletas de color y resolución de estilos."""
import json
from pathlib import Path

from textual.color import Color


TITLE_COLOR_PALETTE: dict = {}
FG_COLOR_PALETTE: dict = {}


def _load_palettes():
    """Load TITLE_COLOR_PALETTE and FG_COLOR_PALETTE from palettes.json."""
    global TITLE_COLOR_PALETTE, FG_COLOR_PALETTE
    palette_file = Path(__file__).with_name("palettes.json")
    try:
        with palette_file.open("r", encoding="utf-8") as _f:
            _data = json.load(_f)
        TITLE_COLOR_PALETTE = _data.get("title", {})
        FG_COLOR_PALETTE = _data.get("fg", {})
    except Exception as _e:
        print(f"[!] No se pudo cargar palettes.json: {_e}. Las paletas estarán vacías.")


_load_palettes()


def _resolve_color_style(color_value: str, palette: dict, default_key: str = 'default'):
    """
    Resuelve un valor de color para obtener un estilo, adaptándose al tipo de paleta.
    - Si la paleta contiene diccionarios (ej: TITLE_COLOR_PALETTE), devuelve un dict.
    - Si la paleta contiene strings (ej: FG_COLOR_PALETTE), devuelve un str.
    """
    default_style = palette.get(default_key)

    if isinstance(default_style, str):
        if color_value and color_value in palette:
            return palette[color_value]
        elif isinstance(color_value, str) and color_value.startswith('#'):
            return color_value
        else:
            return default_style

    style = {}
    if color_value and color_value in palette:
        style = palette[color_value].copy()
    elif isinstance(color_value, str) and color_value.startswith('#'):
        style['bg'] = color_value
    else:
        style = default_style.copy() if default_style else {}

    if 'fg' not in style or not style['fg']:
        try:
            bg_for_calc = style.get('bg', '#000000')
            parsed_color = Color.parse(bg_for_calc)
            luminance = parsed_color.get_luminance()
            style['fg'] = 'black' if luminance > 0.5 else 'white'
        except Exception:
            style['fg'] = default_style.get('fg', 'white') if default_style else 'white'

    return style

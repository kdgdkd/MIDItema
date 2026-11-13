# Archivo: tui.py

import html
import math
import time
import json
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from copy import copy

_HEADER_NAMED_COLORS = {
    "darkred": "#8B0000", "darkgreen": "#006400", "yellow": "#FFFF00",
    "blue": "#0000FF", "magenta": "#FF00FF", "cyan": "#00FFFF",
    "white": "#FFFFFF", "black": "#000000", "red": "#FF0000", "green": "#008000",
}

def _tint_header(bg_color: str, factor: float = 0.25) -> str:
    """Mezcla bg_color con #111111 al factor indicado. Devuelve color hex."""
    hex_c = _HEADER_NAMED_COLORS.get(bg_color.lower(), bg_color if bg_color.startswith('#') else None)
    if not hex_c:
        return "#111111"
    try:
        h = hex_c.lstrip('#')
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        cr, cg, cb = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = int(0x11 + (cr - 0x11) * factor)
        g = int(0x11 + (cg - 0x11) * factor)
        b = int(0x11 + (cb - 0x11) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#111111"

_SESSION_KEYS = "123456789abcdefghijklmnopqrstuvwxyz"

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Center, VerticalScroll
from textual.widgets import Header, Footer, Static, Button, Label, ListView, ListItem
from textual.screen import ModalScreen, Screen
from textual.events import Key, Click
from textual.binding import Binding
from textual.command import Provider, Command
from textual.reactive import var
from textual.timer import Timer 

# --- Widgets Personalizados ---

class CustomHeader(Static):
    """Un widget de cabecera personalizado que replica el layout original."""
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(id="header-left")
            yield Static(id="header-center")
            yield Static(id="header-right")

class SongTitle(Static):
    def update_content(self, miditema):
        if not miditema.song_state.song_name:
            self.update("---")
            self.styles.background = "#222222"
            self.styles.color = "white"
            return

        style_dict = miditema._resolve_color_style(miditema.song_state.song_color, miditema.TITLE_COLOR_PALETTE, 'default')
        safe_song_name = html.escape(miditema.song_state.song_name)
        title_str = safe_song_name
        if miditema.playlist_state.is_active:
            setlist_name = miditema.loaded_filename or ''
            current = miditema.playlist_state.current_song_index + 1
            total = len(miditema.playlist_state.playlist_elements)
            title_str = f"{html.escape(setlist_name)} [{current}/{total}]   {safe_song_name}"
        
        self.update(title_str)
        self.styles.background = style_dict['bg']
        self.styles.color = style_dict['fg']

class PartInfo(Vertical):
    def compose(self) -> ComposeResult:
        yield Static(id="part-title")
        
    def update_content(self, miditema):
        part_index = miditema.song_state.current_part_index
        if part_index == -1 and miditema.song_state.parts:
            part_index = 0
        
        if part_index != -1:
            part = miditema.song_state.parts[part_index]
            name = part.get('name', '---')
            bars = part.get('bars', 0)
            total_parts = len(miditema.song_state.parts)
            notes = part.get('notes', '')
            
            part_prefix = f"[{part_index + 1}/{total_parts}]"
            part_info_str = f"{part_prefix}    {html.escape(name)}    ({bars} bars)"
            
            # Añadir notas al final de la misma línea si existen
            if notes:
                part_info_str += f"    {html.escape(notes)}"
            
            style_dict = miditema._resolve_color_style(part.get('color'), miditema.TITLE_COLOR_PALETTE, 'default')
            
            if miditema.part_loop_active and part_index == miditema.part_loop_index:
                style_dict = {'bg': 'red', 'fg': 'white'}

            self.query_one("#part-title", Static).update(part_info_str)
            self.styles.background = style_dict['bg']
            self.styles.color = style_dict['fg']
            self.query_one("#part-title", Static).styles.color = style_dict['fg']
        else:
            self.query_one("#part-title", Static).update("---")
            self.styles.background = "#222222"

class Counters(Horizontal):
    def compose(self) -> ComposeResult:
        yield Counter("Set", id="counter-set")
        yield Counter("Song", id="counter-song")
        yield Counter("Bars", id="counter-bars")
        yield Counter("Part/Song", id="counter-part")
        yield Counter("Song/Set", id="counter-song-set")

    def update_content(self, miditema):
        def get_set_time():
            total_seconds = miditema.clock_state.paused_set_elapsed_time
            if miditema.clock_state.status == "PLAYING" and miditema.clock_state.start_time > 0:
                total_seconds += time.time() - miditema.clock_state.start_time
            if total_seconds > 0 or miditema.clock_state.status == "PLAYING":
                m, s = divmod(int(total_seconds), 60)
                return f"{m:02d}:{s:02d}"
            return "--:--"

        def get_song_time():
            total_seconds = miditema.song_state.paused_song_elapsed_time
            if miditema.clock_state.status == "PLAYING" and miditema.song_state.start_time > 0:
                total_seconds += time.time() - miditema.song_state.start_time
            if total_seconds > 0 or (miditema.clock_state.status == "PLAYING" and miditema.song_state.current_part_index != -1):
                m, s = divmod(int(total_seconds), 60)
                return f"{m:02d}:{s:02d}"
            return "--:--"

        self.query_one("#counter-set .value").update(get_set_time())
        self.query_one("#counter-song .value").update(get_song_time())

        part_val = f"{miditema.song_state.current_part_index + 1:02d}/{len(miditema.song_state.parts):02d}" if miditema.song_state.parts else "--/--"
        self.query_one("#counter-part .value").update(part_val)

        song_set_val = f"{miditema.playlist_state.current_song_index + 1:02d}/{len(miditema.playlist_state.playlist_elements):02d}" if miditema.playlist_state.is_active else "--/--"
        self.query_one("#counter-song-set .value").update(song_set_val)
        

class ActionStatus(Static):
    def update_content(self, miditema, goto_input_active, goto_input_buffer,
                       plusminus_active=False, plusminus_sign=1):
        """Muestra el estado de la acción o el modo de entrada de texto."""
        if plusminus_active:
            sign_char = "+" if plusminus_sign > 0 else "-"
            self.update(f"[on cyan black] Salto: {sign_char}_ [/]")
            return
        if goto_input_active:
            self.update(f"[on yellow black] Ir a Parte: {goto_input_buffer}_ [/]")
            return

        quant_str = miditema.quantize_mode.replace("_", " ").upper()
        action_str = "Ø"
        
        if miditema.pending_action:
            quant = (miditema.pending_action.get("dynamic_quantize") or miditema.pending_action.get("quantize", "")).replace("_", " ").upper()
            target = miditema.pending_action.get("target")

            if miditema.pending_action.get("target_type") in ["global_part", "cue_jump"]:
                song_idx = miditema.pending_action.get("target_song")
                part_idx = miditema.pending_action.get("target_part")
                if 0 <= song_idx < len(miditema.playlist_state.playlist_elements):
                    song_element = miditema.playlist_state.playlist_elements[song_idx]
                    # Usamos _get_parts_from_playlist_element para leer del disco si es necesario
                    parts = miditema._get_parts_from_playlist_element(song_element)
                    song_name = song_element.get("song_name", Path(song_element.get("filepath", "N/A")).stem)
                    part_name = parts[part_idx].get("name", "N/A") if part_idx < len(parts) else "N/A"
                    prefix = "Cue" if miditema.pending_action.get("target_type") == "cue_jump" else "Global"
                    action_str = f"{prefix}: {html.escape(song_name)} - {html.escape(part_name)} ({quant})"
            elif miditema.pending_action.get("target_type") == "song":
                action_str = f"Song Jump ({quant})"
            elif isinstance(target, dict) and target.get("type") == "relative":
                action_str = f"Jump {target.get('value', 0):+} ({quant})"
            elif target == "restart":
                action_str = f"Restart Part ({quant})"
            elif isinstance(target, int):
                action_str = f"Go to Part {target + 1} ({quant})"

        if miditema.part_loop_active:
            mode_style = "[on red] Loop Part [/]"
        elif miditema.repeat_override_active:
            mode_style = "[on green] Song Mode [/]"
        else:
            mode_style = "[on blue] Loop Mode [/]"

        session_badge = "[on purple] Clips [/]" if miditema.session_mode else ""

        # Status indicators for outputs and silent mode
        output_status = ""
        if not miditema.outputs_enabled:
            output_status += "[on red] SILENT [/]"

        status_separator = " | " if output_status else ""

        self.update(f"{mode_style}{session_badge} | [bold]Quant:[/] [yellow]{quant_str}[/] | [bold]Action:[/] [cyan]{action_str}[/]{status_separator}{output_status}")

class Feedback(Static):
    def update_content(self, miditema):
        lines = []
        if time.time() < miditema.feedback_expiry_time:
            lines.append(miditema.ui_feedback_message)
        if (miditema._bus_clock_alias
                and miditema.presence is not None
                and not miditema.presence.is_alive("midimod")):
            lines.append("[bold red]⚠ midimod: NO DETECTADO[/]")
        self.update("\n".join(lines) if lines else "")

class Countdown(Static): pass
class StepSequencer(Static): pass
class NextPart(Static): pass


# --- Live View ---

@dataclass
class LiveRow:
    global_part_idx: int      # índice en global_parts_manager.global_parts
    part_info: object         # GlobalPartInfo
    bar_offset: int           # primer compás del chunk (0, 8, 16...)
    is_first_chunk: bool      # True = primera fila de esta parte


def _build_live_rows(global_parts: list) -> list:
    rows = []
    for gp_idx, part_info in enumerate(global_parts):
        total_bars = part_info.bars
        n_chunks = max(1, math.ceil(total_bars / 8))
        for chunk_idx in range(n_chunks):
            rows.append(LiveRow(
                global_part_idx=gp_idx,
                part_info=part_info,
                bar_offset=chunk_idx * 8,
                is_first_chunk=(chunk_idx == 0),
            ))
    return rows


def _format_live_midi_hints(output_list: list) -> str:
    if not output_list:
        return ""
    parts = []
    for msg in output_list:
        msg_type = msg.get("type")
        if msg_type is None:
            if "program" in msg:
                msg_type = "program_change"
            elif "control" in msg:
                msg_type = "control_change"
            elif "note" in msg:
                msg_type = "note_on"
            elif "song" in msg:
                msg_type = "song_select"
            else:
                continue
        ch = msg.get("channel", 0)
        if msg_type == "program_change":
            parts.append(f"ch{ch} pc{msg.get('program', '?')}")
        elif msg_type == "control_change":
            parts.append(f"ch{ch} cc{msg.get('control', '?')}")
        elif msg_type in ("note_on", "note_off"):
            parts.append(f"ch{ch} nt{msg.get('note', '?')}")
        elif msg_type == "song_select":
            parts.append(f"ss{msg.get('song', '?')}")
    return "  ".join(parts)


def _resolve_msg_type(msg: dict):
    t = msg.get("type")
    if t:
        return t
    if "program" in msg:
        return "program_change"
    if "control" in msg:
        return "control_change"
    if "note" in msg:
        return "note_on"
    if "song" in msg:
        return "song_select"
    return None


def _collect_output_columns(global_parts: list) -> list:
    """Ordered unique (device, channel) columns across all parts; channel=None for song_select."""
    seen: dict = {}
    for pi in global_parts:
        for msg in pi.output:
            dev = msg.get("device", "")
            mt = _resolve_msg_type(msg)
            if mt is None:
                continue
            ch = None if mt == "song_select" else msg.get("channel", 0)
            key = (dev, ch)
            if key not in seen:
                seen[key] = len(seen)
    return list(seen.keys())


def _col_label(dev: str, ch) -> str:
    d = dev[:3] if dev else "???"
    return f"{d}:{ch}" if ch is not None else f"{d}:s"


def _matrix_cell(output_list: list, col_dev: str, col_ch, col_w: int) -> str:
    """Fixed-width cell for the given (device, channel) column, or spaces if no match."""
    for msg in output_list:
        if msg.get("device", "") != col_dev:
            continue
        mt = _resolve_msg_type(msg)
        if mt is None:
            continue
        if col_ch is None:
            if mt == "song_select":
                return f"s{msg.get('song', '?')}"[:col_w].ljust(col_w)
        else:
            if msg.get("channel", 0) != col_ch:
                continue
            if mt == "program_change":
                raw = f"p{msg.get('program', '?')}"
            elif mt == "control_change":
                raw = f"c{msg.get('control', '?')}"
            elif mt in ("note_on", "note_off"):
                raw = f"n{msg.get('note', '?')}"
            else:
                continue
            return raw[:col_w].ljust(col_w)
    return " " * col_w


class LiveInfoBar(Static):
    def update_content(self, miditema) -> None:
        if miditema.playlist_state.is_active:
            si = miditema.playlist_state.current_song_index + 1
            st = len(miditema.playlist_state.playlist_elements)
            song_pos = f"{{{si}/{st}}}"
        else:
            song_pos = "{1/1}"

        song_name = html.escape(miditema.song_state.song_name or "---")

        pi = miditema.song_state.current_part_index
        tp = len(miditema.song_state.parts)
        part_pos = f"({pi + 1}/{tp})" if pi >= 0 and tp > 0 else "(--/--)"

        def _fmt(secs):
            m, s = divmod(int(max(0, secs)), 60)
            return f"{m:02d}:{s:02d}"

        ss = miditema.song_state.paused_song_elapsed_time
        if miditema.clock_state.status == "PLAYING" and miditema.song_state.start_time > 0:
            ss += time.time() - miditema.song_state.start_time

        es = miditema.clock_state.paused_set_elapsed_time
        if miditema.clock_state.status == "PLAYING" and miditema.clock_state.start_time > 0:
            es += time.time() - miditema.clock_state.start_time

        self.update(
            f" {song_pos} [bold]{song_name}[/]  {part_pos}"
            f"  {_fmt(ss)} / {_fmt(es)}"
        )


class LiveSequencer(Static):
    pass

class SetProgress(Static):
    """Tiempo restante de canción y set en una sola fila con barras de progreso."""

    _BAR_WIDTH = 20

    def update_content(self, miditema) -> None:
        bpm = miditema.clock_state.bpm
        sig_num = miditema.song_state.time_signature_numerator or 4

        if bpm < 1 or not miditema.song_state.parts:
            self.update("")
            return

        spb = 60.0 / bpm  # segundos por beat

        # --- Tiempo restante de canción actual ---
        song_total_bars = sum(p.get("bars", 0) for p in miditema.song_state.parts)
        song_total_sec = song_total_bars * sig_num * spb
        song_elapsed = miditema.song_state.paused_song_elapsed_time
        if miditema.clock_state.status == "PLAYING" and miditema.song_state.start_time > 0:
            song_elapsed += time.time() - miditema.song_state.start_time
        song_remaining = max(0, song_total_sec - song_elapsed)
        song_progress = min(1.0, song_elapsed / song_total_sec) if song_total_sec > 0 else 0

        # --- Tiempo restante del set completo ---
        set_total_bars = 0
        if miditema.playlist_state.is_active:
            for element in miditema.playlist_state.playlist_elements:
                for part in miditema._get_parts_from_playlist_element(element):
                    set_total_bars += part.get("bars", 0)
        else:
            set_total_bars = song_total_bars
        set_total_sec = set_total_bars * sig_num * spb
        set_elapsed = miditema.clock_state.paused_set_elapsed_time
        if miditema.clock_state.status == "PLAYING" and miditema.clock_state.start_time > 0:
            set_elapsed += time.time() - miditema.clock_state.start_time
        set_remaining = max(0, set_total_sec - set_elapsed)
        set_progress = min(1.0, set_elapsed / set_total_sec) if set_total_sec > 0 else 0

        def _bar(progress: float) -> str:
            filled = int(progress * self._BAR_WIDTH)
            return f"[green]{'█' * filled}[/][#333333]{'░' * (self._BAR_WIDTH - filled)}[/]"

        def _fmt(seconds: float) -> str:
            m, s = divmod(int(seconds), 60)
            return f"{m:02d}:{s:02d}"

        self.update(
            f"[#777777]♪[/] {_bar(song_progress)} [dim]{_fmt(song_remaining)}[/]"
            f"    "
            f"[#777777]♫[/] {_bar(set_progress)} [dim]{_fmt(set_remaining)}[/]"
        )


_MAP_WIDTH = 60

class MiniMap(Static):
    """Mapa horizontal proporcional de partes con playhead en tiempo real."""

    def update_content(self, miditema) -> None:
        parts = miditema.song_state.parts
        if not parts:
            self.update("")
            return

        total_bars = sum(p.get("bars", 1) for p in parts) or 1
        current_idx = miditema.song_state.current_part_index
        sig_num = miditema.song_state.time_signature_numerator
        remaining = miditema.song_state.remaining_beats_in_part
        is_playing = miditema.clock_state.status == "PLAYING"

        # Proportional widths (last part absorbs rounding error)
        widths, allocated = [], 0
        for i, p in enumerate(parts):
            w = (_MAP_WIDTH - allocated) if i == len(parts) - 1 else max(1, round(p.get("bars", 1) / total_bars * _MAP_WIDTH))
            widths.append(w)
            allocated += w

        segments = []
        for i, (part, w) in enumerate(zip(parts, widths)):
            style_dict = miditema._resolve_color_style(part.get("color"), miditema.TITLE_COLOR_PALETTE, "default")
            bg = style_dict.get("bg", "#222222")
            if i == current_idx:
                if is_playing and remaining > 0:
                    part_beats = part.get("bars", 1) * sig_num
                    progress = (part_beats - remaining) / part_beats
                    ph = max(0, min(w - 1, int(progress * w)))
                    block = ""
                    if ph > 0:
                        block += f"[{bg} on {bg}]{'█' * ph}[/]"
                    block += f"[bold white on {bg}]▶[/]"
                    after = w - ph - 1
                    if after > 0:
                        block += f"[{bg} on {bg}]{'█' * after}[/]"
                    segments.append(block)
                else:
                    segments.append(f"[{bg} on {bg}]{'█' * w}[/]")
            else:
                tinted = _tint_header(bg, 0.35)
                segments.append(f"[{tinted} on {tinted}]{'█' * w}[/]")

        row1 = "".join(segments)
        row2 = ""

        if miditema.playlist_state.is_active:
            songs = miditema.playlist_state.playlist_elements
            parts_per_song = [len(miditema._get_parts_from_playlist_element(s)) for s in songs]
            total_parts = sum(parts_per_song) or 1
            current_song = miditema.playlist_state.current_song_index
            song_segs, alloc2 = [], 0
            for si, (song, nparts) in enumerate(zip(songs, parts_per_song)):
                w2 = (_MAP_WIDTH - alloc2) if si == len(songs) - 1 else max(1, round(nparts / total_parts * _MAP_WIDTH))
                alloc2 += w2
                sc = song.get("color")
                if sc:
                    sd = miditema._resolve_color_style(sc, miditema.TITLE_COLOR_PALETTE, "default")
                    bg2 = sd.get("bg", "#333333")
                else:
                    bg2 = "#333333"
                if si == current_song:
                    song_segs.append(f"[white on {bg2}]{'█' * w2}[/]")
                else:
                    t2 = _tint_header(bg2, 0.25)
                    song_segs.append(f"[{t2} on {t2}]{'█' * w2}[/]")
            row2 = "\n" + "".join(song_segs)

        self.update(row1 + row2)


class Counter(Vertical):
    def __init__(self, title: str, id: str) -> None:
        super().__init__(id=id)
        self._title = title
    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="label")
        yield Static("--/--", classes="value")


class FileContentScreen(Screen):
    """Muestra el contenido de un archivo de texto con formato JSON."""

    def __init__(self, file_path: Path, *, name: str | None = None, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.file_path = file_path
        self.content = ""

    def on_mount(self) -> None:
        """Lee y formatea el contenido del archivo al montar la pantalla."""
        try:
            raw_content = self.file_path.read_text(encoding='utf-8')
            # Intentamos parsear como JSON para mostrarlo bonito
            try:
                json_data = self.app.miditema.json5.loads(raw_content)
                self.content = json.dumps(json_data, indent=2)
            except Exception:
                # Si no es JSON válido, mostramos el texto plano
                self.content = raw_content
        except Exception as e:
            self.content = f"Error al leer el archivo:\n\n{e}"
        
        self.query_one("#file-content", Static).update(self.content)
        self.query_one("#file-title", Static).update(f"Contenido de: {self.file_path.name}")

    def compose(self) -> ComposeResult:
        with Vertical(id="info-screen-container"):
            yield Static("", id="file-title", classes="menu-title")
            with VerticalScroll(classes="info-screen-content"):
                yield Static(id="file-content")
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen":
            self.app.pop_screen()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()


class RulesListScreen(ModalScreen):
    """Pantalla para seleccionar un archivo de configuración o canción para ver."""

    def on_mount(self) -> None:
        """Puebla la lista de archivos disponibles."""
        list_view = self.query_one(ListView)
        miditema = self.app.miditema


        # 1. Archivo de configuración principal
        config_filename = miditema.config.get('_source_file')
        if config_filename:
            config_path = Path(config_filename)
            if config_path.is_file():
                item = ListItem(Label(f"Configuración: {config_path.name}"), name=str(config_path.resolve()))
                list_view.append(item)

        # 2. Archivo de canción/playlist actual
        if miditema.loaded_filename:
            song_path = miditema.SONGS_DIR / f"{miditema.loaded_filename}.json"
            if not song_path.exists(): # Probar con .json5
                 song_path = miditema.SONGS_DIR / f"{miditema.loaded_filename}.json5"
            
            if song_path.is_file():
                label = "Playlist" if miditema.playlist_state.is_active else "Canción"
                item = ListItem(Label(f"{label}: {song_path.name}"), name=str(song_path.resolve()))
                list_view.append(item)

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            yield Label("Ver Reglas (Archivos Cargados)")
            yield ListView()
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_list_view_selected(self, event: ListView.Selected):
        file_path_str = event.item.name
        if file_path_str:
            self.app.push_screen(FileContentScreen(Path(file_path_str)))

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen":
            self.app.pop_screen()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()


class SongSeparatorItem(ListItem):
    """Un separador para mostrar el nombre de la canción en la lista de partes."""
    def __init__(self, song_name: str):
        super().__init__(disabled=True) # Hacemos que no sea seleccionable
        self.song_name = song_name

    def compose(self) -> ComposeResult:
        yield Static(self.song_name, classes="song-separator-title")

class PartListItem(ListItem):
    """Un widget para mostrar una parte de la canción en una lista."""

    def __init__(self, part_data: dict, part_index: int, song_index: int):
        super().__init__()
        self.part_data = part_data
        self.part_index = part_index
        self.song_index = song_index # <-- Guardamos el índice de la canción

    def _format_pattern(self, pattern) -> str:
        """Convierte el repeat_pattern en un string legible y visual."""
        
        # --- Casos Simples (no son listas) ---
        if pattern is None or pattern is False: return "Play Once"
        if pattern is True: return "Loop"
        if isinstance(pattern, str):
            return pattern.replace("_", " ").title()

        # --- Caso Complejo: Lista de Acciones ---
        if isinstance(pattern, list):
            formatted_parts = []
            for step in pattern:
                if step is True:
                    formatted_parts.append("✔")
                elif step is False:
                    formatted_parts.append("✘")
                elif isinstance(step, str):
                    # Mapeo de strings a símbolos
                    symbol_map = {"repeat": "⟳", "next": "→", "prev": "←"}
                    formatted_parts.append(symbol_map.get(step, "?"))
                elif isinstance(step, dict):
                    if "jump_to_part" in step:
                        formatted_parts.append(f"→P:{step['jump_to_part'] + 1}")
                    elif "jump_to_cue" in step:
                        formatted_parts.append(f"→C:{step['jump_to_cue']}")
                    elif "random_part" in step:
                        formatted_parts.append("?")
                    else:
                        formatted_parts.append("{…}")
                else:
                    formatted_parts.append("?")
            
            return f"[{' | '.join(formatted_parts)}]"

        # --- Fallback para otros tipos (como diccionarios no en lista) ---
        if isinstance(pattern, dict):
            if "jump_to_part" in pattern: return f"Jump to Part {pattern['jump_to_part'] + 1}"
            if "jump_to_cue" in pattern: return f"Jump to Cue {pattern['jump_to_cue']}"
            if "random_part" in pattern: return "Random Part"

        return str(pattern)


    def compose(self) -> ComposeResult:
        # ... (la lógica de estilo no cambia) ...
        style_dict = self.app.miditema._resolve_color_style(self.part_data.get('color'), self.app.miditema.TITLE_COLOR_PALETTE, 'default')
        self.styles.background = style_dict['bg']
        self.styles.color = style_dict['fg']

        with Horizontal():
            yield Static(f"{self.part_index + 1:02d}", classes="part-list-index")
            yield Static(self.part_data.get('name', 'N/A'), classes="part-list-name")
            yield Static(f"{self.part_data.get('bars', 0)} bars", classes="part-list-bars")
            yield Static(self._format_pattern(self.part_data.get('repeat_pattern')), classes="part-list-pattern")


class SongPartsScreen(ModalScreen):
    """Muestra las partes de la canción actual o de toda la playlist."""

    def on_mount(self) -> None:
        """Puebla la lista con las partes."""
        list_view = self.query_one(ListView)
        miditema = self.app.miditema

        if miditema.playlist_state.is_active:
            # MODO PLAYLIST: Iterar sobre todas las canciones
            for song_idx, song_element in enumerate(miditema.playlist_state.playlist_elements):
                song_name = song_element.get("song_name", Path(song_element.get("filepath", "N/A")).stem)
                list_view.append(SongSeparatorItem(f"[{song_idx + 1}] {song_name}"))
                
                parts = miditema._get_parts_from_playlist_element(song_element)
                for part_idx, part_data in enumerate(parts):
                    list_view.append(PartListItem(part_data, part_idx, song_idx))
        else:
            # MODO CANCIÓN ÚNICA: Comportamiento original
            parts = miditema.song_state.parts
            if not parts:
                list_view.append(ListItem(Label("No hay canción cargada o no tiene partes.")))
                return
            
            list_view.append(SongSeparatorItem(miditema.song_state.song_name))
            for i, part in enumerate(parts):
                list_view.append(PartListItem(part, i, 0)) # song_index es 0

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            # El título ahora es más genérico
            yield Label("Setlist")
            yield ListView()
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_list_view_selected(self, event: ListView.Selected):
        if isinstance(event.item, PartListItem):
            miditema = self.app.miditema
            miditema.navigate_silent_to(event.item.song_index, event.item.part_index)
            miditema.set_feedback_message(f"Ir a parte: {event.item.part_data.get('name')}")
            self.app.pop_screen()

    # ... (on_button_pressed y on_key no cambian) ...
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen": self.app.pop_screen()
    def on_key(self, event: Key) -> None:
        if event.key == "escape": self.app.pop_screen()


class SessionScreen(ModalScreen):
    """Clips: lanzamiento de partes del setlist en vivo."""

    def __init__(self):
        super().__init__()
        self._viewed_song_index: int | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="session-screen-container"):
            yield Static("", id="session-title", classes="menu-title")
            with VerticalScroll(id="session-scroll"):
                yield Static(id="session-grid")
            yield Static("", id="session-footer")

    def on_mount(self) -> None:
        miditema = self.app.miditema
        if miditema.playlist_state.is_active:
            self._viewed_song_index = miditema.playlist_state.current_song_index
        self._refresh_timer = self.set_interval(0.15, self._refresh)
        self._refresh()

    def _viewed_parts_and_name(self, miditema) -> tuple[list, str, int]:
        """Devuelve (parts, song_name, song_idx) de la canción que se está viendo."""
        if not miditema.playlist_state.is_active:
            return miditema.song_state.parts, miditema.song_state.song_name or "Sin canción", 0

        songs = miditema.playlist_state.playlist_elements
        idx = self._viewed_song_index if self._viewed_song_index is not None else miditema.playlist_state.current_song_index
        idx = max(0, min(idx, len(songs) - 1))
        song_el = songs[idx]
        name = song_el.get("song_name", Path(song_el.get("filepath", "")).stem)
        parts = miditema.song_state.parts if idx == miditema.playlist_state.current_song_index else miditema._get_parts_from_playlist_element(song_el)
        return parts, name, idx

    def _refresh(self) -> None:
        miditema = self.app.miditema
        title_w = self.query_one("#session-title", Static)
        grid_w = self.query_one("#session-grid", Static)
        footer_w = self.query_one("#session-footer", Static)

        parts, song_name, song_idx = self._viewed_parts_and_name(miditema)
        current_song_idx = miditema.playlist_state.current_song_index if miditema.playlist_state.is_active else 0
        is_current_song = (song_idx == current_song_idx)

        song_name_esc = song_name.replace('[', '\\[').replace(']', '\\]')
        sess_badge = " [on purple] CLIPS ON [/]" if miditema.session_mode else " [dim] CLIPS OFF [/]"
        quant_str = miditema.quantize_mode.replace("_", " ").upper()

        nav_str = ""
        if miditema.playlist_state.is_active:
            total = len(miditema.playlist_state.playlist_elements)
            nav_str = f" [dim]{song_idx + 1}/{total}[/]"
            if not is_current_song:
                nav_str += " [yellow]≠ activa[/]"

        title_w.update(f"Clips — {song_name_esc}{nav_str}{sess_badge}  [dim]Q: {quant_str}[/]")

        if not parts:
            grid_w.update("[dim]No hay partes cargadas.[/]")
        else:
            current_part_idx = miditema.song_state.current_part_index if is_current_song else -1
            pending_idx = self._resolve_pending_idx(miditema, parts, song_idx)

            cells = []
            for idx, part in enumerate(parts):
                if idx >= len(_SESSION_KEYS):
                    break
                key = _SESSION_KEYS[idx]
                name = part.get("name", "N/A").replace('[', '\\[').replace(']', '\\]')
                bars = part.get("bars", 0)
                style_dict = miditema._resolve_color_style(part.get("color"), miditema.TITLE_COLOR_PALETTE, "default")
                bg = style_dict.get("bg", "#222222")
                fg = style_dict.get("fg", "white")

                if idx == current_part_idx:
                    text = f" {key} ▶ {name[:18]:<18} {bars:3d}b "
                    cells.append(f"[bold {fg} on {bg}]{text}[/]")
                elif idx == pending_idx:
                    tinted = _tint_header(bg, 0.55)
                    text = f" {key} ◉ {name[:18]:<18} {bars:3d}b "
                    cells.append(f"[{fg} on {tinted}]{text}[/]")
                else:
                    # Inactiva: el nombre se muestra en el color vivo de la parte
                    # sobre fondo casi negro, para que el color se vea aunque
                    # esté detenido (antes iba en gris fijo #777777).
                    fg_vivid = miditema._resolve_color_style(
                        part.get("color"), miditema.FG_COLOR_PALETTE, "default")
                    tinted = _tint_header(bg, 0.15)
                    text = f" {key}   {name[:18]:<18} {bars:3d}b "
                    cells.append(f"[{fg_vivid} on {tinted}]{text}[/]")

            lines = []
            for i in range(0, len(cells), 2):
                if i + 1 < len(cells):
                    lines.append(f"{cells[i]}  {cells[i + 1]}")
                else:
                    lines.append(cells[i])
            grid_w.update("\n".join(lines))

        nav_hint = "  AvPág/RePág: canción" if miditema.playlist_state.is_active else ""
        footer_w.update(f"[dim]Teclas 1-9 / a-z: lanzar parte   ↑↓: scroll   Bksp: Clips Mode{nav_hint}   ESC: cerrar[/]")

    @staticmethod
    def _resolve_pending_idx(miditema, parts: list, viewed_song_idx: int) -> int:
        pa = miditema.pending_action
        if not pa:
            return -1
        target = pa.get("target")
        if pa.get("target_type") == "global_part":
            if pa.get("target_song") == viewed_song_idx:
                tp = pa.get("target_part", -1)
                return tp if 0 <= tp < len(parts) else -1
            return -1
        current_song_idx = miditema.playlist_state.current_song_index if miditema.playlist_state.is_active else 0
        if viewed_song_idx != current_song_idx:
            return -1
        if isinstance(target, int) and 0 <= target < len(parts):
            return target
        if isinstance(target, dict) and target.get("type") == "relative":
            cur = miditema.song_state.current_part_index
            val = target.get("value", 1)
            return max(0, min(len(parts) - 1, cur + val))
        return -1

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()
            return
        if event.key == "backspace":
            self.app.miditema.toggle_session_mode()
            event.stop()
            return

        miditema = self.app.miditema

        scroll = self.query_one("#session-scroll", VerticalScroll)
        if event.key == "up":
            scroll.scroll_up()
            event.stop()
            return
        if event.key == "down":
            scroll.scroll_down()
            event.stop()
            return
        if event.key == "home":
            scroll.scroll_home()
            event.stop()
            return
        if event.key == "end":
            scroll.scroll_end()
            event.stop()
            return

        if event.key in ("pagedown", "pageup"):
            if miditema.playlist_state.is_active:
                songs = miditema.playlist_state.playlist_elements
                current = self._viewed_song_index if self._viewed_song_index is not None else miditema.playlist_state.current_song_index
                if event.key == "pagedown":
                    self._viewed_song_index = min(current + 1, len(songs) - 1)
                else:
                    self._viewed_song_index = max(current - 1, 0)
            else:
                # Sin playlist: AvPág/RePág hacen scroll de página en la rejilla.
                scroll.scroll_page_down() if event.key == "pagedown" else scroll.scroll_page_up()
            event.stop()
            return

        parts, _, song_idx = self._viewed_parts_and_name(miditema)
        if not parts:
            return
        idx = _SESSION_KEYS.find(event.key)
        if 0 <= idx < len(parts):
            part_name = parts[idx].get("name", "?")
            miditema.navigate_silent_to(song_idx, idx)
            miditema.set_feedback_message(f"Clips: → {part_name}")
            event.stop()


class MenuScreen(Screen):
    """Pantalla de menú principal a pantalla completa."""

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-screen-container"):
            yield Static("Menú Principal", classes="menu-title")
            yield ListView(
                ListItem(Label("Seleccionar Entrada de Clock..."), id="menu-device"),
                ListItem(Label("Abrir Canción/Playlist..."), id="menu-open"),
                ListItem(Label("Setlist..."), id="menu-song-parts"),
                ListItem(Label("Live..."), id="menu-live"),
                ListItem(Label("Ver Reglas..."), id="menu-rules"),
                ListItem(Label("Monitor MIDI/OSC  [M]"), id="menu-monitor"),
                ListItem(Label("Editor html"), id="menu-editor"),
                ListItem(Label("Ver Controles"), id="menu-controls"),
                ListItem(Label("Acerca de MIDItema"), id="menu-about"),
                id="menu-list"
            )
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")


    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Maneja la selección de un ítem del menú."""
        self.app.pop_screen()  # Cerrar el menú primero
        if event.item.id == "menu-open":
            self.app.push_screen(FileSelectScreen())
        elif event.item.id == "menu-device":
            self.app.push_screen(DeviceSelectScreen())
        elif event.item.id == "menu-song-parts":
            self.app.push_screen(SongPartsScreen())
        elif event.item.id == "menu-live":
            self.app.live_view_mode = 1
        elif event.item.id == "menu-rules":
            self.app.push_screen(RulesListScreen())
        elif event.item.id == "menu-controls":
            self.app.action_view_controls()
        elif event.item.id == "menu-monitor":
            self.app.push_screen(MonitorScreen())
        elif event.item.id == "menu-editor":
            editor_path = Path(__file__).parent / "editor" / "index.html"
            webbrowser.open(editor_path.as_uri())
        elif event.item.id == "menu-about":
            self.app.push_screen(AboutScreen())

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen":
            self.app.pop_screen()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()




class FileSelectScreen(ModalScreen):
    """
    Pantalla modal que permite navegar por el directorio de canciones y
    seleccionar un archivo de canción o playlist.
    """
    def _populate_list_view(self) -> None:
        """Limpia y vuelve a poblar la ListView con el contenido del directorio actual."""
        list_view = self.query_one(ListView)
        list_view.clear()

        # Mostrar ruta actual de forma amigable
        display_path = "/"
        if self.current_path != self.base_path:
            display_path = f"/{self.current_path.relative_to(self.base_path)}/"
        self.query_one("#file-path-label", Static).update(f"Dir: {display_path}")

        # Añadir opción para subir de nivel si no estamos en la raíz
        if self.current_path != self.base_path:
            up_item = ListItem(Label("../"), name="..")
            list_view.append(up_item)

        # Listar directorios y archivos
        directories = []
        files = []
        try:
            for path in sorted(self.current_path.iterdir(), key=lambda p: p.name.lower()):
                if path.is_dir():
                    dir_item = ListItem(Label(f"{path.name}/"), name=path.name)
                    directories.append(dir_item)
                elif path.suffix in (".json", ".json5"):
                    file_item = ListItem(Label(path.name), name=path.name)
                    files.append(file_item)
        except OSError as e:
            self.app.miditema.set_feedback_message(f"[!] Error al leer directorio: {e}")
            self.pop_screen()

        # Añadir directorios y luego archivos a la lista
        for item in directories + files:
            list_view.append(item)

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            yield Label("Abrir Archivo")
            yield Static(id="file-path-label")
            yield ListView() # Se poblará en on_mount
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_mount(self) -> None:
        """Puebla la lista de archivos al montar la pantalla."""
        # --- Lógica de inicialización movida aquí ---
        self.base_path = self.app.miditema.SONGS_DIR.resolve()
        self.current_path = self.base_path
        # --- Fin de la lógica de inicialización ---
        self._populate_list_view()

    def on_list_view_selected(self, event: ListView.Selected):
        item_name = event.item.name
        selected_path = self.current_path / item_name

        if item_name == "..":
            # Navegar al directorio padre
            self.current_path = self.current_path.parent
            self._populate_list_view()
        elif selected_path.is_dir():
            # Navegar al subdirectorio
            self.current_path = selected_path
            self._populate_list_view()
        elif selected_path.is_file():
            # Cargar el archivo seleccionado
            relative_path = selected_path.relative_to(self.base_path)
            self.app.miditema.load_file_by_name(str(relative_path))
            self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen":
            self.app.pop_screen()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()

class DeviceSelectScreen(ModalScreen):
    """Pantalla para seleccionar un dispositivo MIDI de clock."""
    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            yield Label("Seleccionar Entrada de Clock")
            ports = self.app.miditema.mido.get_input_names()
            with VerticalScroll():
                yield ListView(*[ListItem(Label(port), name=port) for port in ports])
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected):
        port_name = event.item.name
        self.app.miditema.reconfigure_clock_port(port_name)
        self.dismiss(port_name)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen":
            self.dismiss(None)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)

class ControlsScreen(Screen):
    """Muestra una ayuda exhaustiva con los controles de teclado a pantalla completa."""

    def __init__(self, miditema=None):
        super().__init__()
        self.miditema = miditema

    def _create_control_row(self, key: str, description: str) -> Horizontal:
        """Crea una fila de control con formato."""
        return Horizontal(
            Static(f"`{key}`", classes="control-key"),
            Static(description, classes="control-description"),
            classes="control-row",
        )
    
    def _get_cues_info(self) -> str:
        """Obtiene información sobre los cues definidos en la playlist."""
        if not self.miditema or not self.miditema.playlist_state.is_active:
            return "No hay playlist activa."
        
        # Importar la función necesaria del módulo miditema
        import miditema
        
        cues_found = []
        for s_idx, element in enumerate(self.miditema.playlist_state.playlist_elements):
            song_name = element.get("song_name", f"Canción {s_idx + 1}")
            parts = miditema._get_parts_from_playlist_element(element)
            
            for p_idx, part in enumerate(parts):
                cue = part.get("cue")
                if cue is not None:
                    part_name = part.get("name", f"Parte {p_idx + 1}")
                    cues_found.append(f"F{cue}: {song_name} → {part_name}")
        
        if not cues_found:
            return "No hay cues definidos en la playlist.\nPuedes agregar 'cue': N en cualquier parte del JSON."
        
        return "\n".join(cues_found)

    def compose(self) -> ComposeResult:
        with Vertical(id="info-screen-container"):
            with VerticalScroll(id="controls-content"):
                # Sección de Cues al inicio
                yield Static("Cues Disponibles", classes="controls-header-text")
                yield Static("", id="cues-info-content", classes="cues-info")

                yield Static("Reproducción", classes="controls-header-text")
                yield self._create_control_row("Enter", "Play / Stop: Inicia o detiene la reproducción.")
                yield self._create_control_row("Espacio", "Continue / Stop: Reanuda o detiene la reproducción.")
                yield self._create_control_row("o", "Silent: Activa/desactiva el envío de outputs.")
                yield self._create_control_row("Ctrl+C", "Salir inmediatamente de la aplicación.")

                yield Static("Navegación", classes="controls-header-text")
                yield self._create_control_row("→ / ←", "Parte Siguiente / Anterior.")
                yield self._create_control_row("Ctrl+→ / Ctrl+←", "Parte Siguiente / Anterior (estado colapsado).")
                yield self._create_control_row("PgDn / PgUp", "Canción Siguiente / Anterior.")
                yield self._create_control_row("Home / End", "Primera / Última Canción.")
                yield self._create_control_row(". o ,", "Ir a Parte... (activa modo de entrada).")

                yield Static("Saltos Rápidos (0-3)", classes="controls-header-text")
                yield self._create_control_row("0", "Siguiente parte al siguiente compás.")
                yield self._create_control_row("1", "Siguiente parte en 4 compases.")
                yield self._create_control_row("2", "Siguiente parte en 8 compases.")
                yield self._create_control_row("3", "Siguiente parte en 16 compases.")

                yield Static("Cuantización Global (4-9)", classes="controls-header-text")
                yield self._create_control_row("4", "Fijar cuantización global a 4 compases.")
                yield self._create_control_row("5", "Fijar cuantización global a 8 compases.")
                yield self._create_control_row("6", "Fijar cuantización global a 16 compases.")
                yield self._create_control_row("7", "Fijar cuantización global al siguiente compás.")
                yield self._create_control_row("8", "Fijar cuantización global al final de parte.")
                yield self._create_control_row("9", "Fijar cuantización global a instantáneo.")

                yield Static("Cues (F1-F12)", classes="controls-header-text")
                yield self._create_control_row("F1-F12", "Saltar al cue correspondiente si está definido.")

                yield Static("Acciones y Modos", classes="controls-header-text")
                yield self._create_control_row("↓", "Cancelar Acción / Reiniciar Setlist.")
                yield self._create_control_row("↑", "Activar/Desactivar Loop de Parte.")
                yield self._create_control_row("m", "Alternar Modo (Loop / Song).")
                yield self._create_control_row("l", "Vista Live (cicla Normal → Full → Compact).")
                yield self._create_control_row("Ctrl+↑/↓", "Scroll de la Vista Live (al estar detenido).")
                yield self._create_control_row("q", "Salir de la aplicación.")
                yield self._create_control_row("r", "Recargar archivo actual.")
                yield self._create_control_row("Ctrl+P", "Panic: detiene todas las notas MIDI activas.")

                yield Static("Vistas", classes="controls-header-text")
                yield self._create_control_row("v", "Abrir Setlist.")
                yield self._create_control_row("g", "Abrir Clips/Session.")
                yield self._create_control_row("h", "Ver Controles.")
                yield self._create_control_row("M", "Monitor MIDI/OSC.")
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_mount(self) -> None:
        """Actualiza la información de cues cuando se monta la pantalla."""
        cues_info = self._get_cues_info()
        cues_widget = self.query_one("#cues-info-content", Static)
        cues_widget.update(cues_info)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen":
            self.app.pop_screen()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()


class AboutScreen(Screen):
    """Muestra información sobre la aplicación."""
    def compose(self) -> ComposeResult:
        with Vertical(id="info-screen-container"):
            with VerticalScroll(classes="info-screen-content"):
                yield Static("MIDItema v1.0", classes="about-title")
                yield Static("A terminal-based, live performance song arranger and bar counter.", classes="about-subtitle")
                yield Static("---", classes="about-separator")
                yield Static("MIDItema acts as a MIDI clock slave, stepping through song structures\nand broadcasting state changes via MIDI and OSC, giving you powerful,\nquantized control over your song's flow.", classes="about-body")
                yield Static("Created with [dim]Python & Textual[/]", classes="about-footer")
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen":
            self.app.pop_screen()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()



class MonitorScreen(Screen):
    """Pantalla de monitor MIDI/OSC en tiempo real (últimos 200 eventos)."""

    def compose(self) -> ComposeResult:
        with Vertical(id="info-screen-container"):
            yield Static("Monitor MIDI / OSC", classes="menu-title")
            with VerticalScroll(classes="info-screen-content"):
                yield Static(id="monitor-content")
            with Center(classes="info-screen-footer"):
                yield Button("Limpiar", id="monitor-clear", classes="subtle-button")
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_mount(self) -> None:
        self._refresh_timer = self.set_interval(0.5, self._refresh_log)
        self._refresh_log()

    def _refresh_log(self) -> None:
        log = list(self.app.miditema.midi_osc_event_log)
        content = self.query_one("#monitor-content", Static)
        if not log:
            content.update("[dim]Sin eventos. Los triggers MIDI/OSC aparecen aquí.[/]")
            return
        lines = []
        for ev in reversed(log):
            proto_color = "cyan" if ev["proto"] == "MIDI" else "yellow"
            lines.append(
                f"[dim]{ev['time']}[/] [{proto_color}]{ev['proto']}[/] "
                f"[bold]{html.escape(ev['device'])}[/] {html.escape(ev['payload'])}"
            )
        content.update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-screen":
            self.app.pop_screen()
        elif event.button.id == "monitor-clear":
            self.app.miditema.midi_osc_event_log.clear()
            self._refresh_log()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.app.pop_screen()


def _part_counter(miditema, part_info) -> str:
    """Devuelve '[N/M]' donde N es la posición local de la parte y M el total de partes de su canción."""
    total = sum(1 for p in miditema.global_parts_manager.global_parts if p.song_index == part_info.song_index)
    return f"[{part_info.part_index + 1}/{total}]"


# --- App Principal ---
class MiditemaApp(App):
    CSS_PATH = "tui.css"
    COMMAND_PALETTE = False
    BINDINGS = [
        # --- Grupo Principal de Botones (Ordenado por Teclas de Función) ---
        Binding("enter", "start_stop", "Play/Stop", show=True, priority=True),
        Binding("space", "continue_stop", "Continue/Stop", show=True, priority=True),
        Binding("o", "toggle_outputs", "Silent", show=True, priority=True),
        Binding("up", "toggle_part_loop", "Loop", show=True, priority=True),
        Binding("down", "cancel_or_reset", "Cancel", show=True, priority=True),
        Binding("m", "toggle_mode", "Mode", show=True, priority=True),
        Binding("v", "view_song_parts", "Setlist", show=True, priority=True),
        Binding("g", "view_session", "Clips", show=True, priority=True),
        Binding("l", "toggle_live_view", "Live", show=True, priority=True),
        Binding("h", "view_controls", "Help", show=True, priority=True),
        Binding("4", "quant_4", "Q.4", show=True, priority=True),
        Binding("5", "quant_8", "Q.8", show=True, priority=True),
        # --- Grupo Secundario (Alineado a la derecha) ---
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+c", "force_quit", "Quit", show=False),
        Binding("ctrl+p", "panic", "Panic", show=False, priority=True),
        Binding("r", "reload_file", "Reload", show=False),

        # --- Otros Atajos Ocultos ---
        Binding("right", "part_next", "Parte Siguiente", show=False),
        Binding("left", "part_prev", "Parte Anterior", show=False),
        Binding("ctrl+right", "part_next_collapsed", "Parte Siguiente (Estado)", show=False),
        Binding("ctrl+left", "part_prev_collapsed", "Parte Anterior (Estado)", show=False),
        Binding("pageup", "song_prev", "Canción Anterior", show=False),
        Binding("pagedown", "song_next", "Canción Siguiente", show=False),
        Binding("home", "song_first", "Primera Canción", show=False),
        Binding("end", "song_last", "Última Canción", show=False),
    ]

    # --- Atributos Reactivos ---
    # Estos atributos almacenarán una copia del estado de miditema.
    # Cuando cambien, Textual llamará automáticamente a sus métodos 'watch_'.
    
    # Estado del Clock
    clock_status = var("STOPPED")
    clock_source_name = var("")
    bpm = var(0.0)
    
    # Estado del Archivo/Setlist
    loaded_filename = var("")
    playlist_state = var({})
    
    # Estado de la Canción y Parte
    song_state = var({})
    
    # Estado de las Acciones y Modos
    pending_action = var(None)
    quantize_mode = var("next_bar")
    part_loop_active = var(False)
    repeat_override_active = var(False)
    
    # Estado de la UI
    feedback_message = var(("", 0)) # (mensaje, tiempo_expiracion)
    feedback_sticky = var(False)
    feedback_level = var("info")
    beat_flash_end_time = var(0.0)
    device_health = var(())  # tuple para forzar reactividad
    
    # Estado local de la UI (no necesita ser reactivo de la misma manera)
    goto_input_active = var(False)
    goto_input_buffer = var("")
    plusminus_input_active = var(False)
    plusminus_input_sign = var(1)   # +1 o -1

    outputs_enabled = var(True)
    file_changed_on_disk = var(False)
    session_mode = var(False)
    live_view_mode = var(0)   # 0=normal, 1=live full, 2=live compact

    _time_update_timer: Timer | None = None
    _feedback_timer: Timer | None = None

    def __init__(self, miditema_module, **kwargs):
        super().__init__(**kwargs)
        self.miditema = miditema_module
        self._live_scroll_offset = 0   # scroll manual de la Live View (Ctrl+↑/↓)

    def action_open_file(self) -> None:
        self.push_screen(FileSelectScreen())

    def action_select_device(self) -> None:
        self.push_screen(DeviceSelectScreen())

    def action_view_controls(self) -> None:
        self.push_screen(ControlsScreen(self.miditema))

    def action_about(self) -> None:
        self.push_screen(AboutScreen())

    def action_open_menu(self) -> None:
        """Abre la pantalla del menú principal."""
        self.push_screen(MenuScreen())

    def action_view_song_parts(self) -> None:
        """Abre la pantalla de partes del setlist."""
        self.push_screen(SongPartsScreen())

    def action_view_session(self) -> None:
        """Abre el modo Session para lanzar partes en vivo."""
        self.push_screen(SessionScreen())

    def on_click(self, event: Click) -> None:
        """Maneja los clics en widgets, como el título para abrir el menú."""
        if event.widget.id == "header-left":
            self.action_open_menu()
        elif event.widget.id == "header-center":
            self.action_start_stop()

    # --- Acciones (sin cambios) ---
    def _set_global_quantize(self, mode: str):
        self.miditema.quantize_mode = mode
        self.miditema.set_feedback_message(f"Cuantización Global: {mode.upper()}")

    def action_quant_4(self) -> None:
        self._set_global_quantize("next_4")

    def action_quant_8(self) -> None:
        self._set_global_quantize("next_8")

    def action_quit(self) -> None:
        self.exit()
    
    def action_force_quit(self) -> None:
        """Salida forzada sin confirmación para Ctrl+C"""
        if self.miditema.clock_state.status == "PLAYING":
            self.miditema.enqueue_transport("stop")
        self.exit(return_code=0)

    def action_panic(self) -> None:
        self.miditema.panic()

    def action_start_stop(self) -> None:
        if self.miditema.clock_state.status == "PLAYING":
            self.miditema.enqueue_transport("stop")
        else:
            self.miditema.enqueue_transport("start")

    def action_continue_stop(self) -> None:
        if self.miditema.clock_state.status == "PLAYING":
            self.miditema.enqueue_transport("stop")
        else:
            self.miditema.enqueue_transport("continue")

    def action_toggle_outputs(self) -> None:
        self.miditema.toggle_outputs()

    def action_toggle_mode(self) -> None:
        self.miditema.repeat_override_active = not self.miditema.repeat_override_active
        self.miditema.user_mode_override = self.miditema.repeat_override_active
        mode_str = "Song Mode" if self.miditema.repeat_override_active else "Loop Mode"
        self.miditema.set_feedback_message(f"Modo cambiado a: {mode_str}")

    def _set_relative_jump(self, value: int):
        self.miditema.cancel_part_loop()
        if self.miditema.clock_state.status == "STOPPED":
            direction = "+1" if value > 0 else "-1"
            current_idx = self.miditema.song_state.current_part_index
            next_idx, next_pass = self.miditema.find_next_part_index_manual(direction, current_idx, self.miditema.song_state.pass_count)
            if next_idx is not None:
                self.miditema.song_state.pass_count = next_pass
                self.miditema.setup_part(next_idx, fire_instant_trigger=False)
                self.miditema.pending_action = {"target": next_idx, "quantize": self.miditema.quantize_mode}
                self.miditema.initial_outputs_sent = False
                part_name = self.miditema.song_state.parts[next_idx].get("name", "N/A")
                self.miditema.set_feedback_message(f"Parte seleccionada: {part_name}")
            else:
                if self.miditema.playlist_state.is_active:
                    adj = self.miditema.playlist_state.current_song_index + (1 if value > 0 else -1)
                    if 0 <= adj < len(self.miditema.playlist_state.playlist_elements):
                        if value < 0:
                            target_part = self.miditema.find_last_playable_part_of_song(adj)
                            if target_part is not None:
                                self.miditema.pending_action = {
                                    "target_type": "global_part",
                                    "target_song": adj,
                                    "target_part": target_part,
                                    "quantize": self.miditema.quantize_mode,
                                }
                                self.miditema.execute_global_part_jump(silent=True)
                            else:
                                self.miditema.pending_action = {"target_type": "song", "target": adj, "quantize": self.miditema.quantize_mode}
                                self.miditema.execute_song_jump(silent=True)
                        else:
                            self.miditema.pending_action = {"target_type": "song", "target": adj, "quantize": self.miditema.quantize_mode}
                            self.miditema.execute_song_jump(silent=True)
                    else:
                        self.miditema.set_feedback_message("No hay más partes en esta dirección.")
                else:
                    self.miditema.set_feedback_message("No hay más partes en esta dirección.")
        else:
            if (self.miditema.pending_action and
                    isinstance(self.miditema.pending_action.get("target"), dict) and
                    self.miditema.pending_action["target"].get("type") == "relative"):
                self.miditema.pending_action["target"]["value"] += value
            else:
                target = {"type": "relative", "value": value}
                self.miditema.pending_action = {"target": target, "quantize": self.miditema.quantize_mode}
            self.miditema.set_feedback_message(f"Salto relativo: {self.miditema.pending_action['target']['value']:+}")

    def action_part_next(self) -> None:
        self._set_relative_jump(1)

    def action_part_prev(self) -> None:
        self._set_relative_jump(-1)

    def _set_collapsed_jump(self, value: int) -> None:
        """Ctrl+Arrow: jump to adjacent part sending a collapsed state-reconstruction packet."""
        gpm = self.miditema.global_parts_manager
        if not gpm.is_initialized:
            gpm.build_global_parts_list()

        current_song_idx = self.miditema.playlist_state.current_song_index if self.miditema.playlist_state.is_active else 0
        current_part_idx = self.miditema.song_state.current_part_index

        current_global_idx = -1
        for i, part_info in enumerate(gpm.global_parts):
            if part_info.song_index == current_song_idx and part_info.part_index == current_part_idx:
                current_global_idx = i
                break

        step = 1 if value > 0 else -1
        target_global_idx = current_global_idx + step
        while 0 <= target_global_idx < len(gpm.global_parts) and gpm.global_parts[target_global_idx].bars <= 0:
            target_global_idx += step
        if not (0 <= target_global_idx < len(gpm.global_parts)):
            self.miditema.set_feedback_message("No hay más partes en esta dirección.")
            return

        target = gpm.global_parts[target_global_idx]
        collapsed = self.miditema.build_collapsed_outputs(target_global_idx)

        self.miditema.cancel_part_loop()

        if self.miditema.clock_state.status == "STOPPED":
            self.miditema.pending_collapsed_outputs = collapsed
            if self.miditema.playlist_state.is_active:
                self.miditema.pending_action = {
                    "target_type": "global_part",
                    "target_song": target.song_index,
                    "target_part": target.part_index,
                    "quantize": self.miditema.quantize_mode,
                }
                self.miditema.execute_global_part_jump(silent=True)
            else:
                self.miditema.setup_part(target.part_index, fire_instant_trigger=False)
                self.miditema.pending_action = {
                    "target": target.part_index,
                    "quantize": self.miditema.quantize_mode,
                }
                self.miditema.initial_outputs_sent = False
            self.miditema.set_feedback_message(f"[Ctrl] {target.name}")
        else:
            if self.miditema.playlist_state.is_active:
                self.miditema.pending_action = {
                    "target_type": "global_part",
                    "target_song": target.song_index,
                    "target_part": target.part_index,
                    "quantize": self.miditema.quantize_mode,
                    "collapsed_outputs": collapsed,
                }
            else:
                self.miditema.pending_action = {
                    "target": target.part_index,
                    "quantize": self.miditema.quantize_mode,
                    "collapsed_outputs": collapsed,
                }
            self.miditema.set_feedback_message(f"[Ctrl] Salto: {target.name}")

    def action_part_next_collapsed(self) -> None:
        self._set_collapsed_jump(1)

    def action_part_prev_collapsed(self) -> None:
        self._set_collapsed_jump(-1)

    def action_toggle_part_loop(self) -> None:
        if self.miditema.part_loop_active and self.miditema.song_state.current_part_index == self.miditema.part_loop_index:
            self.miditema.cancel_part_loop()
        elif self.miditema.clock_state.status == "PLAYING" and self.miditema.song_state.current_part_index != -1:
            self.miditema.activate_part_loop()
            part_name = self.miditema.song_state.parts[self.miditema.part_loop_index].get('name', 'N/A')
            self.miditema.set_feedback_message(f"Loop activado para parte: {part_name}")
        else:
            self.miditema.set_feedback_message("No se puede activar el bucle (reproducción detenida).")

    def action_cancel_or_reset(self) -> None:
        if self.miditema.clock_state.status == "STOPPED":
            self.miditema.reset_song_state_on_stop()
            if self.miditema.playlist_state.is_active:
                self.miditema.load_song_from_playlist(0)
            self.miditema.set_feedback_message("Setlist reiniciado.")
        else:
            if self.miditema.pending_action:
                self.miditema.pending_action = None
                self.miditema.set_feedback_message("Acción pendiente cancelada.")
            else:
                self.miditema.cancel_part_loop()

    def _trigger_song_jump(self, target):
        if not self.miditema.playlist_state.is_active:
            self.miditema.set_feedback_message("Navegación de canción deshabilitada (no hay playlist).")
            return
        action = {"target_type": "song", "target": target, "quantize": self.miditema.quantize_mode}
        self.miditema.trigger_song_jump(action)

    def action_song_next(self) -> None:
        self.miditema.set_feedback_message("Playlist: Siguiente Canción.")
        self._trigger_song_jump({"type": "relative", "value": 1})

    def action_song_prev(self) -> None:
        self.miditema.set_feedback_message("Playlist: Canción Anterior.")
        self._trigger_song_jump({"type": "relative", "value": -1})

    def action_song_first(self) -> None:
        self.miditema.set_feedback_message("Playlist: Primera Canción.")
        self._trigger_song_jump(0)

    def action_song_last(self) -> None:
        last_index = len(self.miditema.playlist_state.playlist_elements) - 1
        self.miditema.set_feedback_message("Playlist: Última Canción.")
        self._trigger_song_jump(last_index)

    def action_reload_file(self) -> None:
        """Recarga el archivo actual desde disco sin reiniciar la app."""
        filename = self.miditema.loaded_filename
        if not filename:
            self.miditema.set_feedback_message("[!] No hay archivo cargado.", level="warning")
            return
        if self.miditema.clock_state.status == "PLAYING":
            self.miditema.set_feedback_message("[!] Detén la reproducción antes de recargar.", level="warning")
            return
        self.miditema.load_file_by_name(filename)

    def action_open_monitor(self) -> None:
        self.push_screen(MonitorScreen())

    def _do_plusminus_jump(self, steps: int) -> None:
        miditema = self.miditema
        gpm = miditema.global_parts_manager
        if not gpm.is_initialized:
            gpm.build_global_parts_list()

        current_song_idx = miditema.playlist_state.current_song_index if miditema.playlist_state.is_active else 0
        current_part_idx = miditema.song_state.current_part_index

        current_global_idx = -1
        for i, gp in enumerate(gpm.global_parts):
            if gp.song_index == current_song_idx and gp.part_index == current_part_idx:
                current_global_idx = i
                break

        miditema.cancel_part_loop()

        if steps == 0:
            # Retrigger: recola la parte activa con la cuantización actual
            if current_part_idx < 0:
                miditema.set_feedback_message("No hay parte activa.")
                return
            if miditema.playlist_state.is_active:
                miditema.pending_action = {
                    "target_type": "global_part",
                    "target_song": current_song_idx,
                    "target_part": current_part_idx,
                    "quantize": miditema.quantize_mode,
                }
            else:
                miditema.pending_action = {
                    "target": current_part_idx,
                    "quantize": miditema.quantize_mode,
                }
            part_name = html.escape(miditema.song_state.parts[current_part_idx].get("name", "?") if miditema.song_state.parts else "?")
            miditema.set_feedback_message(f"[±0] Retrigger: {part_name}")
            return

        # Saltar N partes en la dirección dada, saltando partes con 0 compases
        step = 1 if steps > 0 else -1
        target_global_idx = current_global_idx
        for _ in range(abs(steps)):
            next_idx = target_global_idx + step
            while 0 <= next_idx < len(gpm.global_parts) and gpm.global_parts[next_idx].bars <= 0:
                next_idx += step
            if not (0 <= next_idx < len(gpm.global_parts)):
                miditema.set_feedback_message("No hay más partes en esta dirección.")
                return
            target_global_idx = next_idx

        target = gpm.global_parts[target_global_idx]
        collapsed = miditema.build_collapsed_outputs(target_global_idx)
        sign_char = "+" if steps > 0 else "-"

        if miditema.clock_state.status == "STOPPED":
            miditema.pending_collapsed_outputs = collapsed
            if miditema.playlist_state.is_active:
                miditema.pending_action = {
                    "target_type": "global_part",
                    "target_song": target.song_index,
                    "target_part": target.part_index,
                    "quantize": miditema.quantize_mode,
                }
                miditema.execute_global_part_jump(silent=True)
            else:
                miditema.setup_part(target.part_index, fire_instant_trigger=False)
                miditema.pending_action = {
                    "target": target.part_index,
                    "quantize": miditema.quantize_mode,
                }
                miditema.initial_outputs_sent = False
            miditema.set_feedback_message(f"[{sign_char}{abs(steps)}] {html.escape(target.name)}")
        else:
            if miditema.playlist_state.is_active:
                miditema.pending_action = {
                    "target_type": "global_part",
                    "target_song": target.song_index,
                    "target_part": target.part_index,
                    "quantize": miditema.quantize_mode,
                    "collapsed_outputs": collapsed,
                }
            else:
                miditema.pending_action = {
                    "target": target.part_index,
                    "quantize": miditema.quantize_mode,
                    "collapsed_outputs": collapsed,
                }
            miditema.set_feedback_message(f"[{sign_char}{abs(steps)}] {html.escape(target.name)}")

    def action_toggle_live_view(self) -> None:
        self.live_view_mode = (self.live_view_mode + 1) % 3
        self._live_scroll_offset = 0

    def watch_live_view_mode(self, new_mode: int) -> None:
        try:
            self.query_one("#app-grid").display = (new_mode == 0)
            self.query_one("#live-view-container").display = (new_mode != 0)
        except Exception:
            pass

    def on_key(self, event: Key) -> None:
        """Maneja todas las pulsaciones de teclas."""
        if event.key == "ctrl+c":
            self.action_force_quit()
            event.stop()
            return

        # Descartar feedback sticky con Esc
        if event.key == "escape" and self.miditema.feedback_sticky:
            self.miditema.set_feedback_message("")
            return

        # --- Scroll manual de la Live View (solo dentro de la vista 'l') ---
        if self.live_view_mode > 0 and event.key in ("ctrl+up", "ctrl+down"):
            self._live_scroll_offset = max(0, self._live_scroll_offset + (-1 if event.key == "ctrl+up" else 1))
            self._update_live_view()
            event.stop()
            return

        miditema = self.miditema

        # --- Modo +/- (navegación relativa global) ---
        if event.character in ("+", "-") and not self.goto_input_active:
            self.plusminus_input_sign = 1 if event.character == "+" else -1
            self.plusminus_input_active = True
            return

        if self.plusminus_input_active:
            self.plusminus_input_active = False
            if event.key == "escape":
                miditema.set_feedback_message("Acción cancelada.")
                return
            if event.character and event.character.isdigit():
                self._do_plusminus_jump(self.plusminus_input_sign * int(event.character))
                return
            # Cualquier otra tecla: cancelar silenciosamente y procesar la tecla con normalidad

        # --- Modo "Ir a Parte" ---
        if self.goto_input_active:
            if event.key == "enter":
                if self.goto_input_buffer.isdigit():
                    part_num = int(self.goto_input_buffer)
                    if 1 <= part_num <= len(miditema.song_state.parts):
                        miditema.pending_action = {"target": part_num - 1, "quantize": miditema.quantize_mode}
                        miditema.set_feedback_message(f"Ir a parte {part_num}.")
                    else:
                        miditema.set_feedback_message(f"[!] Error: parte {part_num} no existe.")
                else:
                    miditema.set_feedback_message("[!] Error: entrada inválida.")
                self.goto_input_active = False
                self.goto_input_buffer = ""
            elif event.key == "escape":
                self.goto_input_active = False
                self.goto_input_buffer = ""
                miditema.set_feedback_message("Acción cancelada.")
            elif event.key == "backspace":
                self.goto_input_buffer = self.goto_input_buffer[:-1]
            elif event.character and event.character.isdigit():
                self.goto_input_buffer += event.character
            return # No procesar más teclas en este modo

        # --- Teclas de Acción Normal ---
        if event.key in (".", ","):
            self.goto_input_active = True
            self.goto_input_buffer = ""
        elif '0' <= event.key <= '9':
            miditema.cancel_part_loop()
            if '0' <= event.key <= '3':
                quant_map = {"0": "next_bar", "1": "next_4", "2": "next_8", "3": "next_16"}
                quant = quant_map[event.key]
                target = {"type": "relative", "value": 1}
                miditema.pending_action = {"target": target, "quantize": quant}
                miditema.set_feedback_message(f"Siguiente parte (Quant: {quant.upper()}).")
            else:
                quant_map = {"4": "next_4", "5": "next_8", "6": "next_16", "7": "next_bar", "8": "end_of_part", "9": "instant"}
                miditema.quantize_mode = quant_map[event.key]
                miditema.set_feedback_message(f"Cuantización Global: {miditema.quantize_mode.upper()}.")
        elif event.key.startswith("f"):
            try:
                key_num = int(event.key[1:])
                if 1 <= key_num <= 12:
                    miditema.cancel_part_loop()
                    miditema.trigger_cue_jump(key_num)
            except ValueError:
                pass
        elif event.key in ("M", "shift+m"):
            self.action_open_monitor()

    def compose(self) -> ComposeResult:
        yield CustomHeader(id="header")
        with Vertical(id="app-grid"):
            yield SongTitle("...", id="song-title")
            yield PartInfo(id="part-info-container")
            yield Counters(id="counters-container")
            with Center(): yield NextPart("...", id="next-part")
            with Vertical(id="sequencer-container"):
                with Center(): yield StepSequencer(id="sequencer")
            yield MiniMap(id="mini-map")
            yield SetProgress(id="set-progress")
        with Vertical(id="live-view-container"):
            yield LiveInfoBar(id="live-info-bar")
            with Vertical(id="live-sequencer-container"):
                yield LiveSequencer(id="live-sequencer")
        yield Feedback("...", id="feedback")
        yield ActionStatus("...", id="action-status")
        yield Footer(show_command_palette=False)


    # --- NUEVO MÉTODO: Sondeo de Estado ---

    def _poll_miditema_state(self) -> None:
        """
        Este método se ejecuta en un intervalo. Lee el estado de miditema
        y lo asigna a los atributos reactivos. Textual se encargará del resto.
        """
        miditema = self.miditema
        
        self.clock_status = miditema.clock_state.status
        self.clock_source_name = miditema.clock_state.source_name
        self.bpm = miditema.clock_state.bpm
        self.loaded_filename = miditema.loaded_filename
        

        if self.playlist_state != miditema.playlist_state:
             self.playlist_state = copy(miditema.playlist_state)
        if self.song_state != miditema.song_state:
             self.song_state = copy(miditema.song_state)
        
        self.pending_action = miditema.pending_action
        self.quantize_mode = miditema.quantize_mode
        self.part_loop_active = miditema.part_loop_active
        self.repeat_override_active = miditema.repeat_override_active
        self.outputs_enabled = miditema.outputs_enabled
        self.session_mode = miditema.session_mode
        
        if self.feedback_message != (miditema.ui_feedback_message, miditema.feedback_expiry_time):
            self.feedback_message = (miditema.ui_feedback_message, miditema.feedback_expiry_time)
        self.feedback_sticky = miditema.feedback_sticky
        self.feedback_level = miditema.feedback_level

        # Device health: build snapshot tuple for change detection
        health_snapshot = []
        for info in miditema.port_registry.iter_ports():
            if info.direction != "out":
                continue
            try:
                closed = info.port.closed
            except Exception:
                closed = True
            health_snapshot.append((info.alias, closed))
        new_health = tuple(health_snapshot)
        if self.device_health != new_health:
            self.device_health = new_health

        self.beat_flash_end_time = miditema.beat_flash_end_time

        miditema.check_file_watch()
        if self.file_changed_on_disk != miditema.file_changed_on_disk:
            self.file_changed_on_disk = miditema.file_changed_on_disk

        self._update_header()
        self._update_mini_map()
        self._update_set_progress()
        if self.live_view_mode > 0:
            self._update_live_view()

    def _update_mini_map(self) -> None:
        self.query_one(MiniMap).update_content(self.miditema)

    def _update_set_progress(self) -> None:
        self.query_one(SetProgress).update_content(self.miditema)

    def _update_header(self) -> None:
        """Actualiza todos los componentes de la cabecera."""
        header_left = self.query_one("#header-left", Static)
        header_center = self.query_one("#header-center", Static)
        header_right = self.query_one("#header-right", Static)
        miditema = self.miditema
        now = time.time()

        filename_str = f"[{self.loaded_filename}]" if self.loaded_filename else ""
        header_left.update(f"  MIDItema {filename_str}")

        # Pulso de beat
        pulse = "[bold bright_white]●[/]" if now < self.beat_flash_end_time else "[#444444]●[/]"

        # LEDs de actividad por device de salida (parpadean 200ms; color por tipo)
        _LED_COLORS = {"pc": "bright_blue", "cc": "yellow", "note": "green", "osc": "magenta", "midi": "white"}
        chips = ""
        for info in miditema.port_registry.iter_ports():
            if info.direction != "out":
                continue
            try:
                port_ok = not info.port.closed
            except Exception:
                port_ok = False
            raw = miditema.device_last_send_time.get(info.alias, (0, ""))
            last_send, msg_cat = raw if isinstance(raw, tuple) else (raw, "")
            if port_ok and now - last_send < 0.2:
                color = _LED_COLORS.get(msg_cat, "white")
            elif port_ok:
                color = "#555555"
            else:
                color = "red"
            chips += f" [{color}]■[/]{info.alias}"
        for alias in miditema.osc_outputs:
            raw = miditema.device_last_send_time.get(alias, (0, ""))
            last_send, _ = raw if isinstance(raw, tuple) else (raw, "")
            color = _LED_COLORS["osc"] if now - last_send < 0.2 else "#555555"
            chips += f" [{color}]◆[/]{alias}"

        # Dot de salud del clock input (sin cambios)
        clock_port = miditema.port_registry.get_input("clock")
        if clock_port:
            try:
                clk_ok = not clock_port.closed
            except Exception:
                clk_ok = False
            clk_color = "green" if clk_ok else "red"
            chips = f" [{clk_color}]●[/]clk" + chips

        header_right.update(f"{pulse} {self.bpm:.0f} BPM{chips}  ")

        status = self.clock_status
        source = self.clock_source_name
        if status == "PLAYING":
            header_center.update(f"[on green] ► PLAYING ({source}) [/]")
        elif status == "STOPPED":
            header_center.update(f"[on red] ■ STOPPED [/]")
        else:
            header_center.update(f"[on #333333] {status} [/]")

        # Tinte de fondo del header según el color de la parte activa
        part_index = miditema.song_state.current_part_index
        header_bg = "#111111"
        if part_index != -1 and miditema.song_state.parts:
            part_color = miditema.song_state.parts[part_index].get('color')
            if part_color:
                style_dict = miditema._resolve_color_style(part_color, miditema.TITLE_COLOR_PALETTE, 'default')
                header_bg = _tint_header(style_dict.get('bg', '#111111'))
        self.query_one("#header", CustomHeader).styles.background = header_bg

    def _update_time_counters(self) -> None:
        """Actualiza solo los contadores de tiempo."""
        self.query_one(Counters).update_content(self.miditema)
        self.query_one(SetProgress).update_content(self.miditema)

    def watch_device_health(self) -> None:
        self._update_header()

    def watch_clock_status(self, new_status: str) -> None:
        self._update_header()
        if new_status == "PLAYING":
            if self._time_update_timer is None:
                self._time_update_timer = self.set_interval(1, self._update_time_counters)
        else:
            if self._time_update_timer is not None:
                self._time_update_timer.stop()
                self._time_update_timer = None
            # Forzar una última actualización al parar para que muestre el tiempo final.
            self._update_time_counters()

    def watch_bpm(self) -> None:
        self._update_header()

    def watch_loaded_filename(self) -> None:
        self._update_header()
        # Cuando se carga un archivo, todo lo demás cambia también.
        self.query_one(SongTitle).update_content(self.miditema)
        self.query_one(PartInfo).update_content(self.miditema)
        self.query_one(Counters).update_content(self.miditema)

    def watch_playlist_state(self) -> None:
        self.query_one(SongTitle).update_content(self.miditema)
        self.query_one(Counters).update_content(self.miditema)
        self.watch_pending_action() # La acción puede depender del playlist

    def watch_song_state(self) -> None:
        # La lógica de StepSequencer y Countdown ahora vive aquí.
        self.query_one(SongTitle).update_content(self.miditema)
        self.query_one(PartInfo).update_content(self.miditema)
        self.query_one(Counters).update_content(self.miditema)

        # Lógica para Countdown
        self._update_countdown()

        # Lógica para StepSequencer
        self._update_step_sequencer()

        self._update_next_part()

    def _update_action_status(self):
        self.query_one(ActionStatus).update_content(
            self.miditema, self.goto_input_active, self.goto_input_buffer,
            self.plusminus_input_active, self.plusminus_input_sign,
        )

    def watch_pending_action(self) -> None:
        self._update_action_status()
        self._update_next_part()
    
    def watch_quantize_mode(self) -> None:
        self._update_action_status()

    def watch_part_loop_active(self) -> None:
        self.query_one(PartInfo).update_content(self.miditema)
        self._update_action_status()
        self._update_next_part()

    def watch_repeat_override_active(self) -> None:
        self._update_action_status()

    def _clear_feedback(self) -> None:
        """Borra el mensaje de feedback."""
        self.query_one(Feedback).update("")

    def watch_feedback_message(self, new_feedback: tuple) -> None:
        """Muestra un mensaje de feedback con nivel y soporte sticky."""
        message, expiry_time = new_feedback

        if self._feedback_timer:
            self._feedback_timer.stop()

        if not message:
            self._clear_feedback()
            return

        level = self.miditema.feedback_level
        if level == "error":
            styled = f"[on red] ✖ {message} [/]"
        elif level == "warning":
            styled = f"[on dark_orange] ⚠ {message} [/]"
        else:
            styled = message

        sticky = self.miditema.feedback_sticky
        if sticky:
            self.query_one(Feedback).update(styled + "  [dim](Esc para cerrar)[/]")
        elif time.time() < expiry_time:
            self.query_one(Feedback).update(styled)
            self._feedback_timer = self.set_timer(expiry_time - time.time(), self._clear_feedback)
        else:
            self._clear_feedback()
            
    def watch_beat_flash_end_time(self, end_time: float) -> None:
        counters_row = self.query_one("#counters-container")
        counters_row.styles.background = "#333333"
        self.set_timer(0.1, self._end_beat_flash)


    def watch_goto_input_active(self) -> None:
        self._update_action_status()

    def watch_goto_input_buffer(self) -> None:
        self._update_action_status()

    def watch_plusminus_input_active(self) -> None:
        self._update_action_status()

    def watch_plusminus_input_sign(self) -> None:
        self._update_action_status()

    def watch_outputs_enabled(self) -> None:
        self._update_action_status()

    def watch_session_mode(self) -> None:
        self._update_action_status()

    def action_toggle_session_mode(self) -> None:
        self.miditema.toggle_session_mode()

    def watch_file_changed_on_disk(self, changed: bool) -> None:
        if changed:
            self.miditema.set_feedback_message(
                "⚠ Archivo modificado en disco — pulsa R para recargar",
                duration=30, level="warning"
            )

    def _end_beat_flash(self) -> None:
        counters_row = self.query_one("#counters-container")
        counters_row.styles.background = "#111111"
        
    def _update_countdown(self) -> None:
        miditema = self.miditema
        bar_text, beat_text, style = "-0", "0", "white"
        if miditema.clock_state.status == "PLAYING" and miditema.song_state.remaining_beats_in_part > 0:
            sig_num = miditema.song_state.time_signature_numerator
            rem_beats = miditema.song_state.remaining_beats_in_part
            endpoint_bar = miditema.get_dynamic_endpoint()
            total_beats_in_part = miditema.song_state.parts[miditema.song_state.current_part_index].get("bars", 0) * sig_num
            beats_into_part = total_beats_in_part - rem_beats
            current_bar_index = beats_into_part // sig_num
            remaining_bars_to_endpoint = endpoint_bar - current_bar_index

            display_beat = (rem_beats - 1) % sig_num + 1
            display_bar = -(remaining_bars_to_endpoint - 1)

            bar_text = f"{display_bar}"
            if remaining_bars_to_endpoint == 1: bar_text = "-0"
            beat_text = f"{display_beat}"

            if remaining_bars_to_endpoint == 1: style = "bold red"
            elif remaining_bars_to_endpoint <= 4: style = "bold yellow"

        countdown_str = f"[{style}]{bar_text}[#888888].[/]{beat_text}[/]"
        self.query_one("#counter-bars .value", Static).update(countdown_str)
        
    def _update_next_part(self) -> None:
        miditema = self.miditema
        raw_text, style = "", "grey"

        next_part_info = miditema.global_parts_manager.get_next_part_info()
        current_part_info = miditema.global_parts_manager.get_current_global_part_info()

        if miditema.part_loop_active:
            self.query_one(NextPart).update("[bold red]>> Loop Part[/]")
            return
        elif (miditema.clock_state.status == "PLAYING" and
              current_part_info and
              current_part_info.part_data.get("repeat_pattern") == "repeat"):
            part_color_name = miditema._resolve_color_style(current_part_info.color, miditema.FG_COLOR_PALETTE, 'default')
            self.query_one(NextPart).update(f"[bold {part_color_name}]>> Repeat: {html.escape(current_part_info.name)}[/]")
            return
        elif next_part_info:
            color_name = miditema._resolve_color_style(next_part_info.color, miditema.FG_COLOR_PALETTE, 'default')
            style = f"bold {color_name}"
            counter = _part_counter(miditema, next_part_info)
            if current_part_info and next_part_info.song_index != current_part_info.song_index:
                raw_text = f">> {{{html.escape(next_part_info.song_name)}}} {counter} {html.escape(next_part_info.name)} ({next_part_info.bars})"
            else:
                raw_text = f">> {counter} {html.escape(next_part_info.name)} ({next_part_info.bars})"
        else:
            if not miditema.playlist_state.playlist_elements:
                raw_text = "Carga una canción o setlist"
            elif miditema.playlist_state.is_active and miditema.clock_state.status != "PLAYING":
                if miditema.initial_outputs_sent:
                    style = "bold yellow"
                    raw_text = "Outputs enviados - Espera clock externo para iniciar"
                else:
                    raw_text = "Esperando clock... Enter para enviar valores de inicio"
            else:
                raw_text = ">> End of Setlist" if miditema.playlist_state.is_active else ">> End of Song"
            self.query_one(NextPart).update(f"[{style}]{raw_text}[/]")
            return

        segments = [f"[{style}]{raw_text}[/]"]
        queue = miditema.global_parts_manager.get_next_parts_queue(3)
        for part_info in queue[1:3]:
            fg = miditema._resolve_color_style(part_info.color, miditema.FG_COLOR_PALETTE, "default")
            song_prefix = ""
            if current_part_info and part_info.song_index != current_part_info.song_index:
                song_prefix = f"{{{html.escape(part_info.song_name)}}} "
            counter = _part_counter(miditema, part_info)
            segments.append(f"[dim {fg}]{song_prefix}{counter} {html.escape(part_info.name)} ({part_info.bars})[/]")

        self.query_one(NextPart).update("   [dim]>>[/]   ".join(segments))


    def _update_step_sequencer(self) -> None:
        miditema = self.miditema
        sequencer_text = ""
        FULL_BLOCK = "█"
        BARS_PER_ROW = 8
        COMPACT_MODE_THRESHOLD = 32

        if miditema.song_state.current_part_index != -1:
            part = miditema.song_state.parts[miditema.song_state.current_part_index]
            total_bars = part.get("bars", 0)
            compact_mode = total_bars > COMPACT_MODE_THRESHOLD

            if total_bars > 0:
                sig_num = miditema.song_state.time_signature_numerator
                consumed_beats = (total_bars * sig_num) - miditema.song_state.remaining_beats_in_part
                consumed_bars = consumed_beats // sig_num
                current_beat_in_bar = (consumed_beats % sig_num) + 1 if miditema.clock_state.status == "PLAYING" else 0
                endpoint_bar = miditema.get_dynamic_endpoint() if miditema.pending_action else total_bars

                part_color_name = part.get('color')
                part_style_color = miditema._resolve_color_style(part_color_name, miditema.FG_COLOR_PALETTE, 'default')

                all_bars = []
                for i in range(total_bars):
                    block_style_color = part_style_color
                    if i < consumed_bars or (miditema.pending_action and i >= endpoint_bar):
                        block_style_color = "#222222"

                    if i == consumed_bars and miditema.clock_state.status == "PLAYING":
                        progress_style_color = "#555555"
                        intended_progress_color_name = None
                        remaining_bars_to_endpoint = endpoint_bar - i
                        if remaining_bars_to_endpoint == 1: intended_progress_color_name = 'red'
                        elif remaining_bars_to_endpoint <= 4: intended_progress_color_name = 'yellow'
                        if part_color_name == intended_progress_color_name:
                            progress_style_color = "white"
                        elif intended_progress_color_name:
                            progress_style_color = miditema.FG_COLOR_PALETTE.get(intended_progress_color_name, "#555555")
                        bar_line = "".join(
                            f"[{progress_style_color if beat <= current_beat_in_bar else block_style_color}]{FULL_BLOCK}[/]"
                            for beat in range(1, sig_num + 1)
                        )
                    else:
                        bar_line = f"[{block_style_color}]{FULL_BLOCK * sig_num}[/]"

                    all_bars.append(bar_line)

                lines_per_row = 1 if compact_mode else 3
                total_rows = (total_bars + BARS_PER_ROW - 1) // BARS_PER_ROW

                # Autoscroll: determine which rows to render
                try:
                    container_h = self.query_one("#sequencer-container").size.height
                except Exception:
                    container_h = 0
                visible_rows = max(1, container_h // lines_per_row) if container_h > 0 else total_rows

                if total_rows <= visible_rows or miditema.clock_state.status != "PLAYING":
                    start_row = 0
                else:
                    active_row = min(consumed_bars // BARS_PER_ROW, total_rows - 1)
                    # 2 visible: active at top; 3+: active at second position
                    offset = 0 if visible_rows <= 2 else 1
                    start_row = max(0, min(active_row - offset, total_rows - visible_rows))

                end_row = min(start_row + visible_rows, total_rows)
                for row_idx in range(start_row, end_row):
                    row_of_bars = "  ".join(all_bars[row_idx * BARS_PER_ROW:(row_idx + 1) * BARS_PER_ROW])
                    if compact_mode:
                        sequencer_text += row_of_bars + "\n"
                    else:
                        sequencer_text += row_of_bars + "\n" + row_of_bars + "\n\n"

                hidden_below = total_rows - end_row
                if hidden_below > 0:
                    sequencer_text += f"[dim]+{hidden_below}[/]"

        self.query_one(StepSequencer).update(sequencer_text)

    def _update_live_view(self) -> None:
        miditema = self.miditema
        BARS_PER_ROW = 8
        FULL_BLOCK = "█"

        self.query_one(LiveInfoBar).update_content(miditema)

        gpm = miditema.global_parts_manager
        if not gpm.is_initialized:
            gpm.build_global_parts_list()
        global_parts = gpm.global_parts
        if not global_parts:
            self.query_one(LiveSequencer).update("[dim]No hay partes cargadas.[/]")
            return

        live_rows = _build_live_rows(global_parts)

        is_playing = miditema.clock_state.status == "PLAYING"
        current_song_idx = miditema.playlist_state.current_song_index if miditema.playlist_state.is_active else 0
        current_part_idx = miditema.song_state.current_part_index
        sig_num = miditema.song_state.time_signature_numerator or 4

        # Índice en global_parts de la parte activa
        current_gp_idx = -1
        if current_part_idx >= 0:
            for i, gp in enumerate(global_parts):
                if gp.song_index == current_song_idx and gp.part_index == current_part_idx:
                    current_gp_idx = i
                    break

        # Compases consumidos en la parte activa
        consumed_bars = 0
        current_beat_in_bar = 0
        total_part_bars_active = 0
        if current_part_idx >= 0 and miditema.song_state.parts:
            total_part_bars_active = miditema.song_state.parts[current_part_idx].get("bars", 0)
            total_beats = total_part_bars_active * sig_num
            consumed_beats = total_beats - miditema.song_state.remaining_beats_in_part
            consumed_bars = consumed_beats // sig_num
            if is_playing:
                current_beat_in_bar = (consumed_beats % sig_num) + 1

        # Parte objetivo para resaltar la primera caja
        next_highlight_gp_idx = -1
        pa = miditema.pending_action
        if pa and pa.get("target_type") == "global_part":
            ts, tp = pa.get("target_song"), pa.get("target_part")
            if ts is not None and tp is not None:
                for i, gp in enumerate(global_parts):
                    if gp.song_index == ts and gp.part_index == tp:
                        next_highlight_gp_idx = i
                        break
        elif current_gp_idx >= 0:
            next_info = gpm.get_next_part_info()
            if next_info:
                for i, gp in enumerate(global_parts):
                    if gp.song_index == next_info.song_index and gp.part_index == next_info.part_index:
                        next_highlight_gp_idx = i
                        break

        compact = (self.live_view_mode == 2)
        lines_per_row = 1 if compact else 3
        total_rows = len(live_rows)

        try:
            container_h = self.query_one("#live-sequencer-container").size.height
        except Exception:
            container_h = 0
        visible_count = max(1, container_h // lines_per_row) if container_h > 0 else total_rows

        # Fila activa (chunk que contiene el compás actual)
        active_row_idx = max(0, current_gp_idx) if current_gp_idx >= 0 else 0
        if current_gp_idx >= 0:
            for i, row in enumerate(live_rows):
                if row.global_part_idx == current_gp_idx:
                    chunk_end = row.bar_offset + BARS_PER_ROW
                    if row.bar_offset <= consumed_bars < chunk_end:
                        active_row_idx = i
                        break
                    # última fila de la parte activa como fallback
                    if i + 1 >= len(live_rows) or live_rows[i + 1].global_part_idx != current_gp_idx:
                        active_row_idx = i

        # Scroll: autoscroll siguiendo el playhead al reproducir; manual (Ctrl+↑/↓) al estar detenido.
        max_offset = max(0, total_rows - visible_count)
        if total_rows <= visible_count:
            start_row = 0
            self._live_scroll_offset = 0
        elif not is_playing:
            self._live_scroll_offset = max(0, min(self._live_scroll_offset, max_offset))
            start_row = self._live_scroll_offset
        else:
            offset = 0 if visible_count <= 2 else 1
            start_row = max(0, min(active_row_idx - offset, max_offset))
            self._live_scroll_offset = start_row  # sincronizar para cuando se pare
        end_row = min(start_row + visible_count, total_rows)

        # Etiquetas visuales: ▶ para la activa, +N para futuras (N = posición ordinal desde activa)
        row_label: dict[int, str] = {}
        seen_future_keys: set = set()
        future_n = 1
        for row_idx in range(start_row, end_row):
            row = live_rows[row_idx]
            pk = (row.part_info.song_index, row.part_info.part_index)
            if row.global_part_idx < current_gp_idx:
                row_label[row_idx] = ""
            elif row.global_part_idx == current_gp_idx:
                row_label[row_idx] = "▶" if row.is_first_chunk else ""
            else:
                if pk not in seen_future_keys and future_n <= 9:
                    seen_future_keys.add(pk)
                    row_label[row_idx] = f"+{future_n}" if row.is_first_chunk else ""
                    if row.is_first_chunk:
                        future_n += 1
                else:
                    row_label[row_idx] = ""
        # Sin parte activa: numerar desde +1 todas las partes visibles
        if current_gp_idx == -1:
            seen_future_keys.clear()
            future_n = 1
            for row_idx in range(start_row, end_row):
                row = live_rows[row_idx]
                pk = (row.part_info.song_index, row.part_info.part_index)
                if pk not in seen_future_keys and future_n <= 9:
                    seen_future_keys.add(pk)
                    row_label[row_idx] = f"+{future_n}" if row.is_first_chunk else ""
                    if row.is_first_chunk:
                        future_n += 1
                else:
                    row_label[row_idx] = ""

        # Parpadeo BPM-sincronizado para el primer compás del target
        bpm = miditema.clock_state.bpm
        half_beat_sec = 30.0 / bpm if bpm > 0 else 0.5
        blink_tick = int(time.time() / half_beat_sec) % 2

        # Renderizar filas
        bar_area_w = sig_num * BARS_PER_ROW + 2 * (BARS_PER_ROW - 1)
        cols = _collect_output_columns(global_parts)
        col_w = max(5, max((len(_col_label(d, c)) for d, c in cols), default=5))
        text_lines = []
        if cols:
            header_indent = " " * (3 + bar_area_w + 2)
            header_str = " ".join(_col_label(d, c).ljust(col_w) for d, c in cols)
            text_lines.append(f"[dim]{header_indent}{header_str}[/]")
        for row_idx in range(start_row, end_row):
            row = live_rows[row_idx]
            pi = row.part_info

            if row.is_first_chunk and row_idx > start_row:
                if live_rows[row_idx - 1].part_info.song_index != pi.song_index:
                    sep_line = f"[dim]   {'╌' * bar_area_w}  {html.escape(pi.song_name)}[/]"
                    text_lines.append(sep_line)
                    if not compact:
                        text_lines.append("")

            total_part_bars = pi.bars
            chunk_start = row.bar_offset
            chunk_bars = min(BARS_PER_ROW, total_part_bars - chunk_start)

            part_style = miditema._resolve_color_style(pi.color, miditema.FG_COLOR_PALETTE, 'default')
            # Color de las cajas "gastadas" (pasadas/consumidas): gris al reproducir,
            # pero versión atenuada del color de la parte al estar detenido, para que
            # se siga viendo el color del arreglo.
            spent_color = "#222222" if is_playing else _tint_header(part_style, 0.4)

            is_highlight_row = (
                row.global_part_idx == next_highlight_gp_idx
                and row.bar_offset == 0
                and row.global_part_idx != current_gp_idx
            )

            bar_blocks = []
            for b in range(BARS_PER_ROW):
                if b >= chunk_bars:
                    bar_blocks.append(" " * sig_num)
                    continue

                global_bar = chunk_start + b

                if current_gp_idx == -1 or row.global_part_idx > current_gp_idx:
                    # Parte futura (o sin parte activa)
                    if is_highlight_row and b == 0:
                        hi_color = "blue" if (pi.color or "").lower() == "white" else "white"
                        bar_color = hi_color if blink_tick == 0 else part_style
                        bar_blocks.append(f"[{bar_color}]{FULL_BLOCK * sig_num}[/]")
                    else:
                        bar_blocks.append(f"[{part_style}]{FULL_BLOCK * sig_num}[/]")

                elif row.global_part_idx < current_gp_idx:
                    # Parte pasada
                    bar_blocks.append(f"[{spent_color}]{FULL_BLOCK * sig_num}[/]")

                else:
                    # Parte activa
                    if global_bar < consumed_bars:
                        bar_blocks.append(f"[{spent_color}]{FULL_BLOCK * sig_num}[/]")
                    elif global_bar == consumed_bars and is_playing:
                        # Animación beat a beat
                        endpoint_bar = miditema.get_dynamic_endpoint() if pa else total_part_bars_active
                        rem_to_end = endpoint_bar - global_bar
                        prog_color = "#555555"
                        intended = None
                        if rem_to_end == 1:
                            intended = 'red'
                        elif rem_to_end <= 4:
                            intended = 'yellow'
                        if pi.color == intended:
                            prog_color = "white"
                        elif intended:
                            prog_color = miditema.FG_COLOR_PALETTE.get(intended, "#555555")
                        beats_markup = "".join(
                            f"[{prog_color if beat <= current_beat_in_bar else part_style}]{FULL_BLOCK}[/]"
                            for beat in range(1, sig_num + 1)
                        )
                        bar_blocks.append(beats_markup)
                    else:
                        bar_blocks.append(f"[{part_style}]{FULL_BLOCK * sig_num}[/]")

            label = row_label.get(row_idx, "")
            is_active_row = (row.global_part_idx == current_gp_idx)  # usado en midi_hint
            if label == "▶":
                prefix = "▶  "
            elif label:
                prefix = f"{label} "   # "+N " = 3 chars
            else:
                prefix = "   "
            row_content = "  ".join(bar_blocks)

            midi_hint = ""
            if row.is_first_chunk and cols:
                is_emphasis = (is_active_row or row.global_part_idx == next_highlight_gp_idx)
                hint_style = "bold" if is_emphasis else "dim"
                cells = " ".join(_matrix_cell(pi.output, d, c, col_w) for d, c in cols)
                midi_hint = f"  [{hint_style}]{cells}[/]"

            main_line = prefix + row_content + midi_hint

            if compact:
                text_lines.append(main_line)
            else:
                text_lines.append(main_line)
                text_lines.append("   " + row_content)
                text_lines.append("")

        self.query_one(LiveSequencer).update("\n".join(text_lines))

    def on_mount(self) -> None:
        """Configura el intervalo de actualización y comprueba el clock inicial."""
        # Si falta el clock, se pide al usuario que seleccione uno. Y ya está.
        if not self.miditema.port_registry.get_input("clock") and not self.miditema._bus_clock_alias:
            self.push_screen(DeviceSelectScreen())

        # El sondeo de estado se inicia siempre.
        self.set_interval(1 / 20, self._poll_miditema_state)
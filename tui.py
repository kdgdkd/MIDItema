# Archivo: tui.py

import html
import time
import json
from pathlib import Path
from copy import copy

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
        yield Counter("Song/Set", id="counter-song-set")
        yield Counter("Part/Song", id="counter-part")
        yield Counter("Bar", id="counter-bar")

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
        
        song_set_val = f"{miditema.playlist_state.current_song_index + 1:02d}/{len(miditema.playlist_state.playlist_elements):02d}" if miditema.playlist_state.is_active else "--/--"
        self.query_one("#counter-song-set .value").update(song_set_val)
        
        part_val = f"{miditema.song_state.current_part_index + 1:02d}/{len(miditema.song_state.parts):02d}" if miditema.song_state.parts else "--/--"
        self.query_one("#counter-part .value").update(part_val)

        bar_val = "--/--"
        if miditema.song_state.current_part_index != -1:
            part = miditema.song_state.parts[miditema.song_state.current_part_index]
            total_bars, current_bar = part.get("bars", 0), miditema.song_state.current_bar_in_part
            display_bar = current_bar + 1 if miditema.clock_state.status == "PLAYING" and current_bar < total_bars else 0
            bar_val = f"{display_bar:02d}/{total_bars:02d}"
        self.query_one("#counter-bar .value").update(bar_val)
        

class ActionStatus(Static):
    def update_content(self, miditema, goto_input_active, goto_input_buffer):
        """Muestra el estado de la acción o el modo de entrada de texto."""
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
        
        # Status indicators for outputs and silent mode
        output_status = ""
        if not miditema.outputs_enabled:
            output_status += "[on red] OUT OFF [/]"
        if miditema.silent_mode:
            output_status += "[on orange] SILENT [/]"

        status_separator = " | " if output_status else ""

        self.update(f"{mode_style} | [bold]Quant:[/] [yellow]{quant_str}[/] | [bold]Action:[/] [cyan]{action_str}[/]{status_separator}{output_status}")

class Feedback(Static):
    def update_content(self, miditema):
        if time.time() < miditema.feedback_expiry_time:
            self.update(miditema.ui_feedback_message)
        else:
            self.update("")

class Countdown(Static): pass
class StepSequencer(Static): pass
class NextPart(Static): pass
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
            yield Label("Partes del Setlist")
            yield ListView()
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_list_view_selected(self, event: ListView.Selected):
        if isinstance(event.item, PartListItem):
            miditema = self.app.miditema
            
            # Crear una acción de salto global
            miditema.pending_action = {
                "target_type": "global_part",
                "target_song": event.item.song_index,
                "target_part": event.item.part_index,
                "quantize": miditema.quantize_mode
            }
            
            miditema.set_feedback_message(f"Ir a parte: {event.item.part_data.get('name')}")
            self.app.pop_screen()

    # ... (on_button_pressed y on_key no cambian) ...
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "close-screen": self.app.pop_screen()
    def on_key(self, event: Key) -> None:
        if event.key == "escape": self.app.pop_screen()

class MenuScreen(Screen):
    """Pantalla de menú principal a pantalla completa."""

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-screen-container"):
            yield Static("Menú Principal", classes="menu-title")
            yield ListView(
                ListItem(Label("Seleccionar Entrada de Clock..."), id="menu-device"),
                ListItem(Label("Abrir Canción/Playlist..."), id="menu-open"),
                ListItem(Label("Ver Partes del Setlist..."), id="menu-song-parts"),
                ListItem(Label("Ver Reglas..."), id="menu-rules"),
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
        elif event.item.id == "menu-rules":
            self.app.push_screen(RulesListScreen())
        elif event.item.id == "menu-controls":
            self.app.action_view_controls()
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
            yield ListView(*[ListItem(Label(port)) for port in ports])
            with Center(classes="info-screen-footer"):
                yield Button("Cerrar (ESC)", id="close-screen", classes="subtle-button")

    def on_list_view_selected(self, event: ListView.Selected):
        port_name = event.item.children[0].renderable
        self.app.miditema.reconfigure_clock_port(str(port_name))
        self.dismiss(str(port_name))

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
                yield self._create_control_row("o", "Outputs: Activa/desactiva el envío de outputs.")
                yield self._create_control_row("Ctrl+C", "Salir inmediatamente de la aplicación.")

                yield Static("Navegación", classes="controls-header-text")
                yield self._create_control_row("→ / ←", "Parte Siguiente / Anterior.")
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
                yield self._create_control_row("q", "Salir de la aplicación.")
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



# --- App Principal ---
class MiditemaApp(App):
    CSS_PATH = "tui.css"
    COMMAND_PALETTE = False
    BINDINGS = [
        # --- Grupo Principal de Botones (Ordenado por Teclas de Función) ---
        Binding("enter", "start_stop", "Play/Stop", show=True, priority=True),
        Binding("o", "toggle_outputs", "Outputs", show=True, priority=True),
        Binding("s", "toggle_silent_mode", "Silent", show=True, priority=True),
        Binding("up", "toggle_part_loop", "Loop", show=True, priority=True),
        Binding("down", "cancel_or_reset", "Cancel", show=True, priority=True),
        Binding("m", "toggle_mode", "Mode", show=True, priority=True),
        Binding("v", "view_song_parts", "Parts", show=True, priority=True),
        Binding("h", "view_controls", "Help", show=True, priority=True),
        Binding("4", "quant_4", "Q.4", show=True, priority=True),
        Binding("5", "quant_8", "Q.8", show=True, priority=True),
        # --- Grupo Secundario (Alineado a la derecha) ---
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+c", "force_quit", "Quit", show=False),

        # --- Atajos de Teclado Originales (Ahora Ocultos) ---
        # Mantenemos los atajos originales para que sigan funcionando, pero sin ser visibles.
        Binding("enter", "start_stop", "Play/Stop", show=False),
        Binding("space", "continue_stop", "Continue", show=False),
        Binding("up", "toggle_part_loop", "Loop Part", show=False),
        Binding("m", "toggle_mode", "Modo Song/Loop", show=False),
        Binding("down", "cancel_or_reset", "Cancelar/Reiniciar", show=False),
        
        # --- Otros Atajos Ocultos ---
        Binding("right", "part_next", "Parte Siguiente", show=False),
        Binding("left", "part_prev", "Parte Anterior", show=False),
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
    beat_flash_end_time = var(0.0)
    
    # Estado local de la UI (no necesita ser reactivo de la misma manera)
    goto_input_active = var(False)
    goto_input_buffer = var("")

    # Estados de output y modo silencioso
    outputs_enabled = var(True)
    silent_mode = var(False)

    _time_update_timer: Timer | None = None
    _feedback_timer: Timer | None = None

    def __init__(self, miditema_module, **kwargs):
        super().__init__(**kwargs)
        self.miditema = miditema_module
        # El estado local de goto_input se gestionará por separado
        # self.goto_input_active = False
        # self.goto_input_buffer = ""

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
        # Enviar señal de stop si está reproduciéndose
        if self.miditema.clock_state.status == "PLAYING":
            self.miditema.handle_stop()
        # Usar exit sin confirmación
        self.exit(return_code=0)
    
    def on_key(self, event) -> None:
        """Interceptar Ctrl+C para salida directa"""
        if event.key == "ctrl+c":
            self.action_force_quit()
            event.stop()
            return
        return super().on_key(event)

    def action_start_stop(self) -> None:
        if self.miditema.clock_state.status == "PLAYING":
            self.miditema.handle_stop()
        else:
            self.miditema.handle_start()

    def action_continue_stop(self) -> None:
        if self.miditema.clock_state.status == "PLAYING":
            self.miditema.handle_stop()
        else:
            self.miditema.handle_continue()

    def action_toggle_outputs(self) -> None:
        self.miditema.toggle_outputs()

    def action_toggle_silent_mode(self) -> None:
        self.miditema.toggle_silent_mode()

    def action_toggle_mode(self) -> None:
        self.miditema.repeat_override_active = not self.miditema.repeat_override_active
        mode_str = "Song Mode" if self.miditema.repeat_override_active else "Loop Mode"
        self.miditema.set_feedback_message(f"Modo cambiado a: {mode_str}")

    def _set_relative_jump(self, value: int):
        self.miditema.cancel_part_loop()
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

    def action_toggle_part_loop(self) -> None:
        if self.miditema.part_loop_active and self.miditema.song_state.current_part_index == self.miditema.part_loop_index:
            self.miditema.cancel_part_loop()
        elif self.miditema.clock_state.status == "PLAYING" and self.miditema.song_state.current_part_index != -1:
            self.miditema.part_loop_active = True
            self.miditema.part_loop_index = self.miditema.song_state.current_part_index
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
        self._trigger_song_jump({"type": "relative", "value": 1})
        self.miditema.set_feedback_message("Playlist: Siguiente Canción.")

    def action_song_prev(self) -> None:
        self._trigger_song_jump({"type": "relative", "value": -1})
        self.miditema.set_feedback_message("Playlist: Canción Anterior.")

    def action_song_first(self) -> None:
        self._trigger_song_jump(0)
        self.miditema.set_feedback_message("Playlist: Primera Canción.")

    def action_song_last(self) -> None:
        last_index = len(self.miditema.playlist_state.playlist_elements) - 1
        self._trigger_song_jump(last_index)
        self.miditema.set_feedback_message("Playlist: Última Canción.")

    def on_key(self, event: Key) -> None:
        """Maneja todas las pulsaciones de teclas."""
        miditema = self.miditema

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

    def compose(self) -> ComposeResult:
        yield CustomHeader(id="header")
        with Vertical(id="app-grid"):
            yield SongTitle("...", id="song-title")
            yield PartInfo(id="part-info-container")
            yield Counters(id="counters-container")
            with Center(id="countdown-row"): 
                yield Countdown("[-0.0]", id="countdown")
            with Center(): yield NextPart("...", id="next-part")
            # Contenedor con scroll para el secuenciador
            with VerticalScroll(id="sequencer-container"):
                with Center(): yield StepSequencer(id="sequencer")

            # Widgets de estado, ahora fuera del contenedor con scroll
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
        self.silent_mode = miditema.silent_mode
        
        # Solo actualiza si el mensaje o el tiempo de expiración cambian
        if self.feedback_message != (miditema.ui_feedback_message, miditema.feedback_expiry_time):
            self.feedback_message = (miditema.ui_feedback_message, miditema.feedback_expiry_time)
            
        self.beat_flash_end_time = miditema.beat_flash_end_time



    def _update_header(self) -> None:
        """Actualiza todos los componentes de la cabecera."""
        header_left = self.query_one("#header-left", Static)
        header_center = self.query_one("#header-center", Static)
        header_right = self.query_one("#header-right", Static)

        filename_str = f"[{self.loaded_filename}]" if self.loaded_filename else ""
        header_left.update(f"  MIDItema {filename_str}")
        
        header_right.update(f"{self.bpm:.0f} BPM  ")

        status = self.clock_status
        source = self.clock_source_name
        if status == "PLAYING":
            header_center.update(f"[on green] ► PLAYING ({source}) [/]")
        elif status == "STOPPED":
            header_center.update(f"[on red] ■ STOPPED [/]")
        else:
            header_center.update(f"[on #333333] {status} [/]")

    def _update_time_counters(self) -> None:
        """Actualiza solo los contadores de tiempo."""
        self.query_one(Counters).update_content(self.miditema)

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

    def _update_action_status(self):
        self.query_one(ActionStatus).update_content(self.miditema, self.goto_input_active, self.goto_input_buffer)

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
        """Muestra un mensaje de feedback y programa su desaparición."""
        message, expiry_time = new_feedback
        
        # Si hay un timer antiguo, lo cancelamos para que no borre el nuevo mensaje.
        if self._feedback_timer:
            self._feedback_timer.stop()

        # Si el mensaje no está vacío y no ha expirado, lo mostramos.
        if message and time.time() < expiry_time:
            self.query_one(Feedback).update(message)
            duration = expiry_time - time.time()
            # Programamos un nuevo timer para borrar este mensaje.
            self._feedback_timer = self.set_timer(duration, self._clear_feedback)
        else:
            # Si el mensaje está vacío o ya expiró, simplemente lo borramos.
            self._clear_feedback()
            
    def watch_beat_flash_end_time(self, end_time: float) -> None:
        # Inicia el flash y programa su finalización.
        countdown_row = self.query_one("#countdown-row")
        countdown_row.styles.background = "#333333"
        self.set_timer(0.1, self._end_beat_flash)
    
    def watch_goto_input_active(self) -> None:
        self._update_action_status()
        
    def watch_goto_input_buffer(self) -> None:
        self._update_action_status()

    def watch_outputs_enabled(self) -> None:
        self._update_action_status()

    def watch_silent_mode(self) -> None:
        self._update_action_status()

    def _end_beat_flash(self) -> None:
        """Revierte el color de fondo de la fila del countdown."""
        countdown_row = self.query_one("#countdown-row")
        countdown_row.styles.background = "#111111"
        
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
        self.query_one(Countdown).update(countdown_str)
        
    def _update_next_part(self) -> None:
        miditema = self.miditema
        raw_text, style = "", "grey"

        # Use the global parts manager to get the next part info
        next_part_info = miditema.global_parts_manager.get_next_part_info()
        current_part_info = miditema.global_parts_manager.get_current_global_part_info()

        # Handle special cases first
        if miditema.part_loop_active:
            style, raw_text = "bold red", ">> Loop Part"
        elif (miditema.clock_state.status == "PLAYING" and 
              current_part_info and 
              current_part_info.part_data.get("repeat_pattern") == "repeat"):
            part_color_name = miditema._resolve_color_style(current_part_info.color, miditema.FG_COLOR_PALETTE, 'default')
            style = f"bold {part_color_name}"
            raw_text = f">> Repeat: {html.escape(current_part_info.name)}"
        elif next_part_info:
            # Display the next part using global parts manager
            color_name = miditema._resolve_color_style(next_part_info.color, miditema.FG_COLOR_PALETTE, 'default')
            style = f"bold {color_name}"
            
            # Check if next part is in a different song
            if (current_part_info and 
                next_part_info.song_index != current_part_info.song_index):
                raw_text = f">> Next Song: {html.escape(next_part_info.song_name)} [{html.escape(next_part_info.name)} ({next_part_info.bars})]"
            else:
                raw_text = f">> {html.escape(next_part_info.name)} ({next_part_info.bars})"
        else:
            # No next part found - check different states
            if not miditema.playlist_state.playlist_elements:
                # No playlist loaded
                raw_text = "Carga una canción o setlist"
            elif miditema.playlist_state.is_active and miditema.clock_state.status != "PLAYING":
                # Playlist loaded but clock not started
                raw_text = "Esperando clock... Enter para enviar valores de inicio"
            else:
                # End of song/setlist
                raw_text = ">> End of Setlist" if miditema.playlist_state.is_active else ">> End of Song"

        self.query_one(NextPart).update(f"[{style}]{raw_text}[/]")


    def _update_step_sequencer(self) -> None:
        miditema = self.miditema
        sequencer_text = ""
        TOP_BLOCK = "█"
        BOTTOM_BLOCK = "█"
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
                    bar_index_0based = i
                    block_style_color = part_style_color
                    if bar_index_0based < consumed_bars or (miditema.pending_action and bar_index_0based >= endpoint_bar):
                        block_style_color = "#222222"
                    
                    bar_line = ""
                    if bar_index_0based == consumed_bars and miditema.clock_state.status == "PLAYING":
                        progress_style_color = "#555555"
                        intended_progress_color_name = None
                        remaining_bars_to_endpoint = endpoint_bar - bar_index_0based
                        if remaining_bars_to_endpoint == 1: intended_progress_color_name = 'red'
                        elif remaining_bars_to_endpoint <= 4: intended_progress_color_name = 'yellow'
                        
                        if part_color_name == intended_progress_color_name:
                            progress_style_color = "white"
                        elif intended_progress_color_name:
                            progress_style_color = miditema.FG_COLOR_PALETTE.get(intended_progress_color_name, "#555555")

                        for beat in range(1, sig_num + 1):
                            style = progress_style_color if beat <= current_beat_in_bar else block_style_color
                            bar_line += f"[{style}]{FULL_BLOCK}[/]"
                    else:
                        bar_line = f"[{block_style_color}]{FULL_BLOCK * sig_num}[/]"
                    
                    all_bars.append(bar_line)

                for row_start in range(0, len(all_bars), BARS_PER_ROW):
                    row_of_bars = "  ".join(all_bars[row_start:row_start + BARS_PER_ROW])
                    if compact_mode:
                        sequencer_text += row_of_bars + "\n"
                    else:
                        top_line = row_of_bars.replace(FULL_BLOCK, TOP_BLOCK)
                        bottom_line = row_of_bars.replace(FULL_BLOCK, BOTTOM_BLOCK)
                        sequencer_text += top_line + "\n" + bottom_line + "\n\n"
        
        self.query_one(StepSequencer).update(sequencer_text)

    def on_mount(self) -> None:
        """Configura el intervalo de actualización y comprueba el clock inicial."""
        # Si falta el clock, se pide al usuario que seleccione uno. Y ya está.
        if not self.miditema.midi_inputs.get("clock"):
            self.push_screen(DeviceSelectScreen())

        # El sondeo de estado se inicia siempre.
        self.set_interval(1 / 20, self._poll_miditema_state)
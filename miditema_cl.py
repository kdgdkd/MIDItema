import mido
import time
import json
import argparse
import traceback
import signal
from pathlib import Path
import sys
import threading
import math
import html
import json5
import random
from pythonosc import udp_client
from pythonosc import osc_message_builder
from schema_validator import MIDItemaValidator, ValidationError

try:
    # Unix-like (Linux, macOS)
    import tty
    import termios
    import select
    def get_char_non_blocking():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(sys.stdin.fileno())
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return None
except ImportError:
    # Windows
    import msvcrt
    def get_char_non_blocking():
        if msvcrt.kbhit():
            try:
                return msvcrt.getch().decode('utf-8')
            except UnicodeDecodeError:
                return None # Ignorar teclas no estándar
        return None
    
from textual.color import Color
import tui_cl as tui


# --- Global Configuration ---
SONGS_DIR_NAME = "temas"
SONGS_DIR = Path(f"./{SONGS_DIR_NAME}")
CONF_FILE_NAME = "miditema.conf.json"
SHUTDOWN_FLAG = False
MIDI_PPQN = 24  # MIDI Clock Standard, no configurable


# --- Color Palette Definitions ---
# Styles for part titles (background color)
TITLE_COLOR_PALETTE = {
    'default': {'bg': '#222222', 'fg': 'white'},
    'red': {'bg': 'darkred', 'fg': 'white'},
    'green': {'bg': 'darkgreen', 'fg': 'white'},
    'yellow': {'bg': 'yellow', 'fg': 'black'},
    'blue': {'bg': 'blue', 'fg': 'white'},
    'magenta': {'bg': 'magenta', 'fg': 'white'},
    'cyan': {'bg': 'cyan', 'fg': 'black'},
    'orange': {'bg': '#ff7e00', 'fg': 'white'},
    'ruby_pink': {'bg': '#e30052', 'fg': 'white'},
    'indigo_blue': {'bg': '#5564eb', 'fg': 'white'},
    'purple': {'bg': '#800040', 'fg': 'white'},
    'forest_green': {'bg': '#3d642d', 'fg': 'white'},
    'ivory': {'bg': '#ffffbf', 'fg': 'black'},
    # --- Variantes Eléctricas/Neón ---
    'bright_red': {'bg': '#FF004D', 'fg': 'white'},
    'neon_green': {'bg': '#39FF14', 'fg': 'black'},
    'electric_blue': {'bg': '#0099FF', 'fg': 'white'},
    'bright_yellow': {'bg': '#FFFF00', 'fg': 'black'},
    'hot_pink': {'bg': '#FF1493', 'fg': 'white'},
    'electric_cyan': {'bg': '#08E8DE', 'fg': 'black'},
    'electric_orange': {'bg': '#FF3300', 'fg': 'white'},
    # --- Escala de Grises / Monocromo ---
    'dark_gray': {'bg': '#404040', 'fg': '#DDDDDD'},
    'mid_gray': {'bg': '#888888', 'fg': 'black'},
    'light_gray': {'bg': '#CCCCCC', 'fg': 'black'},
    'white': {'bg': '#FFFFFF', 'fg': 'black'},
}
# Styles for foreground elements (text, sequencer blocks)
FG_COLOR_PALETTE = {
    'default': "cyan",
    'red': "red",
    'green': "green",
    'yellow': "yellow",
    'blue': "blue",
    'magenta': "magenta",
    'cyan': "cyan",
    'orange': "#ff7e00",
    'ruby_pink': "#e30052",
    'indigo_blue': "#5564eb",
    'purple': "#800040",
    'forest_green': "#3d642d",
    'ivory': "#cccca0",
    # --- Variantes Eléctricas/Neón ---
    'bright_red': "#FF004D",
    'neon_green': "#39FF14",
    'electric_blue': "#0099FF",
    'bright_yellow': "#FFFF00",
    'hot_pink': "#FF1493",
    'electric_cyan': "#08E8DE",
    'electric_orange': "#FF3300",
    # --- Escala de Grises / Monocromo ---
    'dark_gray': "#888888",
    'mid_gray': "#B0B0B0",
    'light_gray': "#D8D8D8",
    'white': "white",
}

def _resolve_color_style(color_value: str, palette: dict, default_key: str = 'default'):
    """
    Resuelve un valor de color para obtener un estilo, adaptándose al tipo de paleta.
    - Si la paleta contiene diccionarios (ej: TITLE_COLOR_PALETTE), devuelve un dict.
    - Si la paleta contiene strings (ej: FG_COLOR_PALETTE), devuelve un str.
    """
    default_style = palette.get(default_key)
        
    # --- Lógica para paletas de strings (como FG_COLOR_PALETTE) ---
    if isinstance(default_style, str):
        # Prioridad 1: El color es una clave en la paleta
        if color_value and color_value in palette:
            return palette[color_value]
        # Prioridad 2: El color es un valor hexadecimal directo
        elif isinstance(color_value, str) and color_value.startswith('#'):
            return color_value
        # Fallback: Usar el color por defecto
        else:
            return default_style

    # --- Lógica para paletas de diccionarios (como TITLE_COLOR_PALETTE) ---
    style = {}
    # Prioridad 1: El color es una clave en la paleta
    if color_value and color_value in palette:
        style = palette[color_value].copy()
    # Prioridad 2: El color es un valor hexadecimal directo
    elif isinstance(color_value, str) and color_value.startswith('#'):
        style['bg'] = color_value
    # Fallback: Usar el color por defecto
    else:
        style = default_style.copy() if default_style else {}

    # Si el estilo resultante no tiene un color de texto ('fg') definido, lo calculamos.
    if 'fg' not in style or not style['fg']:
        try:
            # Usamos un color de fondo por defecto si no está definido para el cálculo
            bg_for_calc = style.get('bg', '#000000')
            parsed_color = Color.parse(bg_for_calc)
            # get_luminance_rgb() no existe, usamos get_luminance()
            luminance = parsed_color.get_luminance()
            style['fg'] = 'black' if luminance > 0.5 else 'white'
        except Exception:
            # Fallback en caso de error de parseo o si no hay default
            style['fg'] = default_style.get('fg', 'white') if default_style else 'white'

    return style


# Control Change (CC) Numbers
CC_MAIN_CONTROL = 0         # CC principal para la mayoría de las acciones
CC_GLOBAL_PART_JUMP = 1     # CC para saltar a una parte global de la playlist
CC_CUE_JUMP = 2             # CC para saltar a un cue específico

# Note Numbers for Navigation
NOTE_PREV_PART = 124
NOTE_NEXT_PART = 125
NOTE_PREV_SONG = 126
NOTE_NEXT_SONG = 127

# Values for CC_MAIN_CONTROL
CC0_VAL_QUANT_INSTANT = 0   # Salto rápido: Cuantización instantánea
CC0_VAL_QUANT_BAR = 1       # Salto rápido: Cuantización al siguiente compás
CC0_VAL_QUANT_8 = 2         # Salto rápido: Cuantización al siguiente bloque de 8
CC0_VAL_QUANT_16 = 3        # Salto rápido: Cuantización al siguiente bloque de 16

CC0_VAL_SET_QUANT_4 = 4
CC0_VAL_SET_QUANT_8 = 5
CC0_VAL_SET_QUANT_16 = 6
CC0_VAL_SET_QUANT_BAR = 7
CC0_VAL_SET_QUANT_END = 8
CC0_VAL_SET_QUANT_INSTANT = 9

CC0_VAL_PART_PREV = 10
CC0_VAL_PART_NEXT = 11
CC0_VAL_SONG_PREV = 12
CC0_VAL_SONG_NEXT = 13
CC0_VAL_SONG_FIRST = 14
CC0_VAL_SONG_LAST = 15
CC0_VAL_PART_LOOP_TOGGLE = 16
CC0_VAL_PART_RESTART = 17
CC0_VAL_ACTION_CANCEL = 18
CC0_VAL_MODE_TOGGLE = 19
CC0_VAL_SONG_RESTART = 20


# --- State Classes ---

class ClockState:
    """Almacena el estado del reloj MIDI entrante."""
    def __init__(self):
        self.status = "STOPPED"
        self.bpm = 0.0
        self.source_name = "Ninguna"
        self.source_id = None
        self.tick_times = [] # Para promediar el BPM
        self.last_tick_time = 0
        self.start_time = 0
        self.paused_set_elapsed_time = 0

class SongState:
    """Almacena el estado de la canción y la secuencia."""
    def __init__(self):
        self.song_name = "Sin canción cargada"
        self.song_name = "Elige canción/setlist en el menú"
        self.song_color = None
        self.parts = []
        self.current_part_index = -1
        self.remaining_beats_in_part = 0
        self.pass_count = 0
        self.midi_clock_tick_counter = 0
        self.current_bar_in_part = 0 
        self.start_time = 0
        self.paused_song_elapsed_time = 0
        # Valores derivados de la canción
        self.time_signature_numerator = 4
        self.ticks_per_song_beat = MIDI_PPQN

class PlaylistState:
    """Almacena el estado de la playlist."""
    def __init__(self):
        self.is_active = False
        self.playlist_name = "Sin Playlist"
        self.playlist_elements = [] # Puede contener rutas o datos de canción
        self.current_song_index = -1
        self.beats = 2

class GlobalPartInfo:
    """Información de una parte en el contexto global de la playlist."""
    def __init__(self, song_index, part_index, part_data, song_name=None, song_color=None):
        self.song_index = song_index
        self.part_index = part_index
        self.part_data = part_data
        self.song_name = song_name or "Unknown"
        self.song_color = song_color
        
    @property
    def global_part_index(self):
        """Returns the global index of this part across all songs."""
        return _get_global_part_index(self.song_index, self.part_index)
        
    @property
    def name(self):
        return self.part_data.get("name", "N/A")
        
    @property
    def bars(self):
        return self.part_data.get("bars", 0)
        
    @property
    def color(self):
        return self.part_data.get("color")
        
    @property
    def notes(self):
        return self.part_data.get("notes")
        
    @property
    def cue(self):
        return self.part_data.get("cue")
        
    @property
    def output(self):
        return self.part_data.get("output", [])

class GlobalPartsManager:
    """Manages a global list of all parts across all songs in the playlist."""
    def __init__(self):
        self.global_parts = []  # List of GlobalPartInfo objects
        self.is_initialized = False
        
    def build_global_parts_list(self):
        """Builds the global parts list from the current playlist."""
        self.global_parts.clear()
        
        if not playlist_state.is_active:
            # Single song mode
            for part_idx, part_data in enumerate(song_state.parts):
                part_info = GlobalPartInfo(0, part_idx, part_data, song_state.song_name, song_state.song_color)
                self.global_parts.append(part_info)
        else:
            # Playlist mode
            for song_idx, song_element in enumerate(playlist_state.playlist_elements):
                song_parts = _get_parts_from_playlist_element(song_element)
                song_name = song_element.get("song_name", Path(song_element.get("filepath", "N/A")).stem)
                song_color = song_element.get("color")
                
                for part_idx, part_data in enumerate(song_parts):
                    part_info = GlobalPartInfo(song_idx, part_idx, part_data, song_name, song_color)
                    self.global_parts.append(part_info)
        
        self.is_initialized = True
        
    def get_current_global_part_info(self):
        """Gets the GlobalPartInfo for the current part."""
        if not self.is_initialized:
            self.build_global_parts_list()
            
        current_song_idx = playlist_state.current_song_index if playlist_state.is_active else 0
        current_part_idx = song_state.current_part_index
        
        for part_info in self.global_parts:
            if part_info.song_index == current_song_idx and part_info.part_index == current_part_idx:
                return part_info
        return None
        
    def get_next_part_info(self):
        """Dynamically calculates and returns the next part that will be played."""
        if not self.is_initialized:
            self.build_global_parts_list()
            
        # Use the existing prediction logic to determine the next part
        action_to_predict = None
        
        # 1. Check for pending user actions (highest priority)
        if pending_action:
            action_to_predict = pending_action
        # 2. Check for part loop mode
        elif part_loop_active and song_state.current_part_index == part_loop_index:
            # Next part is the same (looping)
            return self.get_current_global_part_info()
        # 3. Check current part's repeat pattern
        elif song_state.current_part_index != -1:
            current_part = song_state.parts[song_state.current_part_index]
            if current_part.get("repeat_pattern") == "repeat":
                # Next part is the same (repeating)
                return self.get_current_global_part_info()
            else:
                # Default behavior: advance to next part
                action_to_predict = {"target_type": "part", "target": {"type": "relative", "value": 1}}
        
        # If we have an action to predict, use it
        if action_to_predict:
            dest_song_idx, dest_part_idx = predict_jump_destination(action_to_predict)
            if dest_song_idx is not None and dest_part_idx is not None:
                for part_info in self.global_parts:
                    if part_info.song_index == dest_song_idx and part_info.part_index == dest_part_idx:
                        return part_info
        
        return None

# --- Global State Instances ---
config = {}
clock_state = ClockState()
song_state = SongState()
playlist_state = PlaylistState()
global_parts_manager = GlobalPartsManager()
pending_action = None
repeat_override_active = False
part_loop_active = False
part_loop_index = -1
quantize_mode = "next_8" 
goto_input_active = False
goto_input_buffer = ""
app_ui_instance = None
initial_outputs_sent = False
outputs_enabled = True
part_change_advanced = 0
beat_flash_end_time = 0
ui_feedback_message = ""
feedback_expiry_time = 0
loaded_filename = ""
_last_used_device = None
midi_inputs = {}
midi_outputs = {}
osc_outputs = {}

# --- Helper Functions ---


def _is_part_active_in_loop(part: dict, loop_pass: int) -> bool:
    """
    Determina si una parte debe sonar en una pasada de bucle específica.
    El loop_pass es 1-based (la primera repetición es el paso 1).
    """
    pattern = part.get("repeat_pattern")
    
    if pattern is True or pattern == "repeat":
        return True
    if pattern is False or pattern is None:
        return False
    
    if isinstance(pattern, list) and pattern:
        # El patrón se repite. Usamos el módulo para ciclar.
        # loop_pass es 1-based, lo convertimos a 0-based para el índice.
        index = (loop_pass - 1) % len(pattern)
        return pattern[index]

    # Si el patrón es un string (como "repeat", "next_song") o un dict,
    # no se considera parte del bucle de repetición estándar.
    # Su lógica se maneja por separado como una acción especial.
    return False


def signal_handler(sig, frame):
    global SHUTDOWN_FLAG
    SHUTDOWN_FLAG = True
    if app_ui_instance:
        app_ui_instance.exit(result="shutdown")

def find_port_by_substring(ports, sub):
    if not ports or not sub: return None
    for name in ports:
        if sub.lower() in name.lower(): return name
    return None


def setup_devices(config):
    """
    Lee la sección 'devices' de la config, abre todos los puertos y los almacena
    en los diccionarios globales midi_inputs, midi_outputs y osc_outputs.
    """
    global midi_inputs, midi_outputs, osc_outputs

    devices = config.get("devices", {})
    if not devices:
        print("[!] No se encontró la sección 'devices' en el archivo de configuración.")
        return

    # --- Configurar Entradas MIDI ---
    midi_in_aliases = devices.get("midi_in", {})
    available_in_ports = mido.get_input_names()
    
    # Puerto de Clock (obligatorio)
    clock_alias = midi_in_aliases.get("clock")
    if clock_alias:
        port_name = find_port_by_substring(available_in_ports, clock_alias)
        if port_name:
            try:
                midi_inputs["clock"] = mido.open_input(port_name)
                clock_state.source_name = port_name
                print(f"[*] Puerto de Clock 'clock' abierto en '{port_name}'.")
            except Exception as e:
                print(f"[!] Error abriendo puerto de Clock '{port_name}': {e}")
        else:
            print(f"[!] No se encontró el puerto de Clock con alias '{clock_alias}'.")


    # Puerto de Control (opcional, ahora llamado 'midi_in')
    control_alias = midi_in_aliases.get("midi_in")
    if control_alias:
        # Reutilizar el puerto de clock si los alias son idénticos
        if control_alias == clock_alias and "clock" in midi_inputs:
             midi_inputs["midi_in"] = midi_inputs["clock"]
             print("[*] Puerto de Control 'midi_in' asignado al mismo puerto que 'clock'.")
        else:
            port_name = find_port_by_substring(available_in_ports, control_alias)
            if port_name:
                try:
                    midi_inputs["midi_in"] = mido.open_input(port_name)
                    print(f"[*] Puerto de Control 'midi_in' abierto en '{port_name}'.")
                except Exception as e:
                    print(f"[!] Error abriendo puerto de Control '{port_name}': {e}")
            else:
                 print(f"[!] No se encontró el puerto de Control con alias '{control_alias}'.")

    # --- Configurar Salidas MIDI ---
    midi_out_aliases = devices.get("midi_out", {})
    available_out_ports = mido.get_output_names()
    for alias, port_substring in midi_out_aliases.items():
        port_name = find_port_by_substring(available_out_ports, port_substring)
        if port_name:
            try:
                midi_outputs[alias] = mido.open_output(port_name)
                print(f"[*] Puerto de Salida MIDI '{alias}' abierto en '{port_name}'.")
            except Exception as e:
                print(f"[!] Error abriendo puerto de salida '{alias}' en '{port_name}': {e}")
        else:
            print(f"[!] No se encontró el puerto de salida MIDI con alias '{alias}' (buscando '{port_substring}').")

    # --- Configurar Salidas OSC ---
    osc_out_aliases = devices.get("osc_out", {})
    _debug_log(f"OSC out aliases found: {osc_out_aliases}")
    for alias, connection_details in osc_out_aliases.items():
        ip = connection_details.get("ip")
        port = connection_details.get("port")
        _debug_log(f"Setting up OSC device '{alias}' -> {ip}:{port}")
        if ip and port:
            try:
                osc_outputs[alias] = udp_client.SimpleUDPClient(ip, port)
                print(f"[*] Destino de Salida OSC '{alias}' configurado para {ip}:{port}.")
            except Exception as e:
                print(f"[!] Error configurando destino OSC '{alias}' para {ip}:{port}: {e}")
        else:
            print(f"[!] Configuración OSC para '{alias}' incompleta (falta 'ip' o 'port').")
    
    _debug_log(f"Final osc_outputs dictionary: {list(osc_outputs.keys())}")


# --- Core Logic ---

def _resolve_value(value, context):
    """
    Resuelve un valor. Si es un string que coincide con una clave del contexto,
    devuelve el valor del contexto. Si no, devuelve el valor original.
    """
    if isinstance(value, str) and value in context:
        return context[value]
    return value

# Control de debug logging - se configurará basado en --debug
DEBUG_LOGGING_ENABLED = False

def _debug_log(message):
    """Write debug message to file."""
    if not DEBUG_LOGGING_ENABLED:
        return
    with open("miditema_debug.log", "a", encoding="utf-8") as f:
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        f.write(f"[{timestamp}] {message}\n")
        f.flush()

def init_debug_log():
    """Initialize debug log file."""
    if not DEBUG_LOGGING_ENABLED:
        return
    with open("miditema_debug.log", "w", encoding="utf-8") as f:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"=== MIDItema Debug Log Started at {timestamp} ===\n")

def _process_trigger_action(action, context):
    """
    Procesa una única acción de trigger, resolviendo sus valores y enviando
    el mensaje MIDI u OSC correspondiente. Incluye lógica de inferencia de tipo.
    """


    global _last_used_device

    # DEBUG: Write to file
    _debug_log(f"Processing trigger action: {action}")
    _debug_log(f"Context: {context}")

    device_name = action.get("device")

    if device_name:
        # Si se especifica un dispositivo, lo usamos y lo guardamos como el último usado.
        _last_used_device = device_name
    else:
        # Si no se especifica, heredamos el último que se usó.
        if _last_used_device:
            device_name = _last_used_device
        else:
            # No hay dispositivo en la acción y nunca se ha definido uno. No se puede procesar.
            return

    if device_name in midi_outputs:
        port = midi_outputs[device_name]
        try:
            # Hacemos una copia para no modificar el diccionario original
            msg_params = action.copy()

            # Lógica de inferencia si 'type' no está definido
            if "type" not in msg_params:
                if "note" in msg_params:
                    msg_params["type"] = "note_on"
                    if "velocity" not in msg_params:
                        msg_params["velocity"] = 127 # Valor por defecto
                elif "control" in msg_params:
                    msg_params["type"] = "control_change"
                    if "value" not in msg_params:
                        msg_params["value"] = 127 # Valor por defecto
                elif "program" in msg_params:
                    msg_params["type"] = "program_change"
                elif "song" in msg_params:
                    msg_params["type"] = "song_select"
                else:
                    return # No se puede inferir el tipo, se ignora la acción

            # Resolver parámetros comunes usando el contexto
            for param in ["channel", "note", "velocity", "control", "value", "program", "song"]:
                if param in msg_params:
                    msg_params[param] = _resolve_value(msg_params[param], context)

            # Lógica de valores implícitos (se mantiene)
            if msg_params["type"] == "program_change" and "program" not in msg_params:
                msg_params["program"] = context.get("part_index", 0)
            elif msg_params["type"] == "song_select" and "song" not in msg_params:
                msg_params["song"] = context.get("song_index", 0)
            
            # Filtrar parámetros nulos y construir el mensaje
            final_params = {k: v for k, v in msg_params.items() if v is not None and k != 'device'}
            msg = mido.Message(**final_params)
            port.send(msg)

        except Exception as e:
            set_feedback_message(f"Error MIDI Trigger ({device_name}): {e}")

    elif device_name in osc_outputs:
        # La lógica OSC no necesita inferencia y se mantiene igual
        client = osc_outputs[device_name]
        _debug_log(f"Sending OSC message to device '{device_name}'")
        try:
            address = _resolve_value(action.get("address"), context)
            if not address: 
                _debug_log(f"No address found in action")
                return

            builder = osc_message_builder.OscMessageBuilder(address=address)
            raw_args = action.get("args", [])
            resolved_args = []
            for arg in raw_args:
                resolved_arg = _resolve_value(arg, context)
                resolved_args.append(resolved_arg)
                builder.add_arg(resolved_arg)
            
            msg = builder.build()
            _debug_log(f"Sending OSC: {address} with args: {resolved_args}")
            client.send(msg)
            _debug_log(f"OSC message sent successfully")

        except Exception as e:
            _debug_log(f"OSC Error: {e}")
            set_feedback_message(f"Error OSC Trigger ({device_name}): {e}")
    else:
        _debug_log(f"Device '{device_name}' not found in MIDI or OSC outputs")
        _debug_log(f"Available MIDI devices: {list(midi_outputs.keys())}")
        _debug_log(f"Available OSC devices: {list(osc_outputs.keys())}")
            
def fire_triggers(event_name, context, is_delayed_check=False, remaining_beats=0, force_instant=False):
    """
    Busca y ejecuta todos los triggers asociados a un evento, tanto globales como locales.
    """
    _debug_log(f"fire_triggers called: event={event_name}, delayed={is_delayed_check}, beats={remaining_beats}, instant={force_instant}")
    _debug_log(f"Context: {context}")
    _debug_log(f"Config has triggers: {'triggers' in config}")
    if "triggers" in config:
        _debug_log(f"Available trigger events: {list(config['triggers'].keys())}")
        _debug_log(f"Looking for event '{event_name}': {event_name in config['triggers']}")
    
    # 1. Procesar triggers globales (comportamiento original)
    if "triggers" in config and event_name in config["triggers"]:
        global_actions = config["triggers"][event_name]
        _debug_log(f"Found {len(global_actions)} actions for event '{event_name}'")
        for i, action in enumerate(global_actions):
            # ... (la lógica de delay se mantiene igual)
            delay_in_beats = 0
            if "bar" in action: 
                delay_in_beats = action["bar"] * song_state.time_signature_numerator
            elif "beats" in action: 
                delay_in_beats = action["beats"]
            elif event_name in ["part_change", "song_change"] and is_delayed_check and playlist_state.is_active:
                # Usar beats del setlist para cambios de parte/canción si no hay delay específico
                delay_in_beats = playlist_state.beats

            should_fire = False
            if force_instant: should_fire = True
            elif is_delayed_check:
                if delay_in_beats > 0 and delay_in_beats == remaining_beats: should_fire = True
            else:
                if delay_in_beats == 0: should_fire = True
            
            _debug_log(f"Action {i}: delay={delay_in_beats}, should_fire={should_fire}, force_instant={force_instant}, is_delayed_check={is_delayed_check}")
            
            if should_fire:
                _debug_log(f"Firing action {i}")
                _process_trigger_action(action, context)
            else:
                _debug_log(f"Skipping action {i}")
                
        _debug_log(f"Finished processing global actions for '{event_name}'")

    # 2. Procesar triggers locales de la parte (nueva funcionalidad)
    # CORRECCIÓN: Los triggers locales también deben respetar el adelanto configurado
    if event_name == "part_change":
        current_part_index = context.get("part_index")
        if current_part_index is not None and 0 <= current_part_index < len(song_state.parts):
            part_data = song_state.parts[current_part_index]
            local_actions = part_data.get("output", []) # Esperamos una lista
            
            # Asegurarse de que siempre sea una lista para un procesamiento uniforme
            if isinstance(local_actions, dict):
                local_actions = [local_actions]

            if isinstance(local_actions, list):
                # Calcular el delay para triggers locales (igual que globales)
                delay_in_beats = playlist_state.beats if playlist_state.is_active else 0
                
                should_fire_local = False
                if force_instant: 
                    should_fire_local = True
                elif is_delayed_check:
                    if delay_in_beats > 0 and delay_in_beats == remaining_beats: 
                        should_fire_local = True
                else:
                    if delay_in_beats == 0: 
                        should_fire_local = True
                
                if should_fire_local and not context.get("skip_outputs", False) and outputs_enabled:
                    for action in local_actions:
                        _process_trigger_action(action, context)


def load_config(conf_filename: str):
    """Carga la configuración del alias del dispositivo desde el archivo .conf."""
    conf_path = Path(conf_filename)
    if not conf_path.is_file():
        # No mostrar error si es el archivo por defecto el que no existe
        if conf_filename != CONF_FILE_NAME:
            print(f"[!] El archivo de configuración '{conf_filename}' no fue encontrado.")
        return {} # Devuelve un diccionario vacío si no existe
    try:
        with conf_path.open('r', encoding='utf-8') as f:
            config = json5.load(f)
        print(f"[*] Archivo de configuración '{conf_filename}' cargado.")
        return config
    except Exception as e:
        print(f"[!] Error cargando el archivo de configuración '{conf_filename}': {e}")
        return {}


def normalize_repeat_pattern(pattern):
    """Convierte strings 'true'/'false' a booleanos en repeat_pattern."""
    if pattern == "true":
        return True
    elif pattern == "false":
        return False
    return pattern

def load_song_file(filepath: Path = None, data: dict = None):
    """
    Carga y valida una canción, actualizando el SongState.
    Puede cargar desde un diccionario (data) o desde un archivo (filepath).
    """
    global song_state
    
    song_data = None
    if data:
        # Priorizar los datos si se proporcionan directamente
        song_data = data
        # Validar datos proporcionados
        errors = MIDItemaValidator.validate_data(data)
        if errors:
            error_msg = "Errores de validación:\n" + "\n".join(str(e) for e in errors[:3])
            if len(errors) > 3:
                error_msg += f"\n... y {len(errors) - 3} errores más"
            set_feedback_message(f"[!] {error_msg}")
            return False
    elif filepath:
        # Si no hay datos, leer desde el archivo
        is_valid, errors, song_data = MIDItemaValidator.validate_file(filepath)
        if not is_valid:
            error_msg = "Errores en el archivo:\n" + "\n".join(str(e) for e in errors[:3])
            if len(errors) > 3:
                error_msg += f"\n... y {len(errors) - 3} errores más"
            print(f"[!] {error_msg}")
            set_feedback_message(f"[!] Error validando '{filepath.name}'")
            return False
    else:
        print("Error: Se debe proporcionar 'filepath' o 'data' para cargar la canción.")
        return False

    if not song_data:
        return False

    song_state = SongState() # Resetear estado al cargar nueva canción
    song_state.song_name = song_data.get("song_name", filepath.stem if filepath else "Canción Incrustada")
    song_state.song_color = song_data.get("color") # <-- AÑADIR ESTA LÍNEA
    song_state.parts = song_data.get("parts", [])

    for part in song_state.parts:
        if "repeat_pattern" in part:
            part["repeat_pattern"] = normalize_repeat_pattern(part["repeat_pattern"])
   
    if not song_state.parts or not isinstance(song_state.parts, list):
        print(f"Error: La canción '{song_state.song_name}' no tiene una lista de 'parts' válida.")
        return False

    # Interpretar Time Signature
    try:
        sig = song_data.get("time_signature", "4/4").split('/')
        song_state.time_signature_numerator = int(sig[0])
    except (ValueError, IndexError):
        song_state.time_signature_numerator = 4

    # Interpretar Time Division
    division = song_data.get("time_division", "1/4")
    division_map = {"1/4": 24, "1/8": 12, "1/16": 6}
    song_state.ticks_per_song_beat = division_map.get(division, MIDI_PPQN)

    # Rebuild global parts list when song is loaded
    global_parts_manager.build_global_parts_list()
    
    # print(f"[*] Canción '{song_state.song_name}' cargada. ({len(song_state.parts)} partes)")
    return True


def load_song_from_playlist(song_index: int):
    """Carga una canción específica de la playlist activa y envía notificaciones."""
    global ui_feedback_message
    if not playlist_state.is_active:
        set_feedback_message("[!] No hay playlist activa.")
        handle_song_end()
        return False

    if not (0 <= song_index < len(playlist_state.playlist_elements)):
        set_feedback_message(f"[!] Índice de canción {song_index} fuera de rango.")
        handle_song_end()
        return False
    
    playlist_state.current_song_index = song_index
    element = playlist_state.playlist_elements[song_index]
    
    song_data_to_load = None
    song_name_for_osc = "N/A"

    if "filepath" in element:
        song_path = SONGS_DIR / element["filepath"]
        song_name_for_osc = song_path.stem
        if not song_path.is_file():
            error_msg = f"Archivo '{element['filepath']}' no encontrado en {SONGS_DIR}"
            print(f"[!] {error_msg}")
            set_feedback_message(f"[!] {error_msg}")
            # Intentar cargar la siguiente canción solo si no es la carga inicial
            if song_index < len(playlist_state.playlist_elements) - 1:
                print(f"[*] Intentando cargar la siguiente canción...")
                return load_song_from_playlist(song_index + 1)
            return False
        
        try:
            with song_path.open('r', encoding='utf-8') as f:
                song_data_to_load = json5.load(f)
            # Sobrescribir el nombre si está definido dentro del archivo
            if "song_name" in song_data_to_load:
                song_name_for_osc = song_data_to_load["song_name"]
        except Exception as e:
            error_msg = f"Error al parsear '{element['filepath']}': {e}"
            print(f"[!] {error_msg}")
            set_feedback_message(f"[!] Error en archivo JSON")
            return False
            
    elif "parts" in element:
        # Esto mantiene la compatibilidad con canciones incrustadas en la playlist
        song_data_to_load = element
        song_name_for_osc = song_data_to_load.get("song_name", "Canción Incrustada")
    else:
        error_msg = f"Elemento de playlist en índice {song_index} no tiene 'filepath' ni 'parts'"
        print(f"[!] {error_msg}")
        set_feedback_message(f"[!] Elemento de playlist inválido")
        return False

    context = {
        "song_index": song_index,
        "song_name": song_name_for_osc,
        "song_color": song_data_to_load.get("color")
    }
    fire_triggers("song_change", context)

    # Ahora, cargar la canción en el estado global usando los datos recién leídos.
    if not load_song_file(data=song_data_to_load):
        # El error específico ya se mostró en load_song_file
        print(f"[!] No se pudo cargar la canción desde el elemento {song_index} de la playlist")
        
        return False

    return True

def reset_song_state_on_stop():
    """Resetea el estado de la secuencia cuando el reloj se detiene."""
    # print("DEBUG: reset_song_state_on_stop -> Reseteando contadores de canción")
    global _last_used_device
    _last_used_device = None 
    song_state.current_part_index = -1
    song_state.remaining_beats_in_part = 0
    song_state.start_time = 0
    song_state.paused_song_elapsed_time = 0
    song_state.pass_count = 0
    song_state.midi_clock_tick_counter = 0
    song_state.current_bar_in_part = 0
    clock_state.tick_times = []
    clock_state.bpm = 0.0


def process_song_tick():
    """Llamado en cada "beat" de la canción (definido por time_division)."""
    global beat_flash_end_time
    if clock_state.status != "PLAYING" or song_state.current_part_index == -1:
        return

    # --- 1. Calcular estado y beats restantes ---
    sig_num = song_state.time_signature_numerator
    current_part = song_state.parts[song_state.current_part_index]
    total_beats_in_part = current_part.get("bars", 0) * sig_num
    
    # Beats que ya han transcurrido en la parte ANTES de este tick.
    beats_elapsed_in_part = total_beats_in_part - song_state.remaining_beats_in_part
    
    # El compás final relevante (puede ser el final de la parte o un punto de salto cuantizado)
    endpoint_bar = get_dynamic_endpoint()
    endpoint_beat_absolute = endpoint_bar * sig_num
    
    # Beats restantes HASTA el evento, contado desde el inicio de este tick.
    # Si quedan 4 beats, este valor será 4, 3, 2, 1 en los ticks sucesivos.
    remaining_beats_to_event = endpoint_beat_absolute - beats_elapsed_in_part

    # --- 2. Lógica de Triggers por adelantado (part_change, song_change) ---
    next_part_info = global_parts_manager.get_next_part_info()
    current_part_info = global_parts_manager.get_current_global_part_info()

    if next_part_info:
        # Check if this is a cross-song transition
        is_cross_song_jump = (current_part_info and 
                            next_part_info.song_index != current_part_info.song_index)
        
        # Build context for the next part
        context = {
            "song_index": next_part_info.song_index,
            "song_name": next_part_info.song_name,
            "song_color": next_part_info.song_color,
            "part_index": next_part_info.part_index,
            "part_name": next_part_info.name,
            "part_bars": next_part_info.bars,
            "part_color": next_part_info.color,
            "part_notes": next_part_info.notes,
            "part_cue": next_part_info.cue,
            "part_index_in_setlist": next_part_info.global_part_index
        }
        
        # Fire song_change trigger if transitioning to a different song
        if is_cross_song_jump:
            fire_triggers("song_change", context, is_delayed_check=True, remaining_beats=remaining_beats_to_event)
        
        # Always fire part_change trigger for the next part
        fire_triggers("part_change", context, is_delayed_check=True, remaining_beats=remaining_beats_to_event)


    # --- 3. Ejecutar Salto Pendiente ---
    jump_executed = check_and_execute_pending_action()
    if jump_executed:
        return

    # --- 4. Avanzar el Estado de la Canción ---
    song_state.remaining_beats_in_part -= 1
    beats_elapsed_in_part += 1 # Actualizar el contador local para el resto de la función

    # --- 5. Disparar Triggers Cíclicos, de Cuenta Atrás y Actualizar UI ---
    if beats_elapsed_in_part > 0 and beats_elapsed_in_part % sig_num == 0:
        song_state.current_bar_in_part = beats_elapsed_in_part // sig_num
        
        bar_context = {
            "completed_bar": song_state.current_bar_in_part, "current_song_name": song_state.song_name,
            "current_part_name": current_part.get("name"), "current_part_index": song_state.current_part_index
        }
        for action in config.get("triggers", {}).get("bar_triggers", []):
            bar_interval = action.get("each_bar")
            if bar_interval and song_state.current_bar_in_part > 0 and song_state.current_bar_in_part % bar_interval == 0:
                action_context = bar_context.copy()
                action_context["block_number"] = song_state.current_bar_in_part // bar_interval
                _process_trigger_action(action, action_context)
        
        if song_state.remaining_beats_in_part > 0:
            beat_flash_end_time = time.time() + 0.1

    # Disparar countdown_triggers en cada beat
    countdown_context = {
        "remaining_beats": remaining_beats_to_event, "remaining_bars": math.ceil(remaining_beats_to_event / sig_num),
        "current_song_name": song_state.song_name, "current_part_name": current_part.get("name"),
        "current_part_index": song_state.current_part_index
    }
    for action in config.get("triggers", {}).get("countdown_triggers", []):
        beat_interval = action.get("each_beat")
        # La condición es más clara: si los beats restantes están dentro del intervalo deseado
        if beat_interval and 0 < remaining_beats_to_event <= beat_interval:
             _process_trigger_action(action, countdown_context)

    # --- 6. Comprobar Fin de Parte ---
    if song_state.remaining_beats_in_part <= 0:
        start_next_part()

# --- Dynamic Part-Jumping Logic ---

def _find_next_valid_part_index(parts: list, direction: str, start_index: int, start_pass_count: int, repeat_override: bool):
    """
    Encuentra el índice y el pass_count de la siguiente parte válida.
    (Réplica de la lógica original)
    """
    if not parts:
        return None, None

    step = 1 if direction == "+1" else -1
    
    temp_index = start_index
    temp_pass_count = start_pass_count
    for _ in range(len(parts) * 2): # Bucle de seguridad
        temp_index += step

        # Lógica de bucle y actualización de pass_count
        if temp_index >= len(parts):
            if repeat_override: return None, None
            temp_index = 0
            temp_pass_count += 1
        elif temp_index < 0:
            if repeat_override: return None, None
            temp_index = len(parts) - 1
            temp_pass_count = max(0, temp_pass_count - 1) 

        part = parts[temp_index]
        if part.get("bars", 0) > 0:
            # En el pase inicial (pass_count 0) o en Song Mode, cualquier parte con compases es válida
            if temp_pass_count == 0 or repeat_override:
                return temp_index, temp_pass_count
            
            # En fase de bucle (pass_count > 0) y Loop Mode
            else:
                pattern = part.get("repeat_pattern")
                if pattern is True or pattern == "repeat":
                    return temp_index, temp_pass_count
                if isinstance(pattern, list) and pattern:
                    # temp_pass_count es 1-based para el primer bucle
                    if pattern[(temp_pass_count - 1) % len(pattern)]:
                        return temp_index, temp_pass_count

    return None, None

def _get_parts_from_playlist_element(element):
    """
    Devuelve la lista de partes de un elemento de la playlist, leyéndola del disco si es necesario.
    """
    # Prioridad 1: La canción está completamente incrustada en la playlist
    if "parts" in element and isinstance(element["parts"], list):
        return element["parts"]
    
    # Prioridad 2: El elemento es una referencia a un archivo
    if "filepath" in element:
        try:
            # Usar la variable global SONGS_DIR que se actualiza al cargar un directorio
            song_path = SONGS_DIR / element["filepath"]
            if song_path.is_file():
                with song_path.open('r', encoding='utf-8') as f:
                    data = json5.load(f)
                    return data.get("parts", [])
        except Exception:
            # Si hay cualquier error de lectura, devolver una lista vacía
            return []
            
    # Fallback si el elemento no es válido
    return []

def predict_jump_destination(action: dict):
    """
    Analiza una acción pendiente y devuelve el destino final como (índice_canción, índice_parte).
    Devuelve (None, None) si el destino es inválido o no se encuentra.
    """
    target_type = action.get("target_type")
    target = action.get("target")

    # Caso 1: Salto global o de cue (destino explícito)
    if target_type in ["global_part", "cue_jump"]:
        return action.get("target_song"), action.get("target_part")

    # Caso 2: Salto de canción
    if target_type == "song":
        dest_song_idx = playlist_state.current_song_index
        if isinstance(target, int): dest_song_idx = target
        elif isinstance(target, dict): dest_song_idx += target.get("value", 0)
        
        if not (0 <= dest_song_idx < len(playlist_state.playlist_elements)): return None, None
        
        dest_song_parts = _get_parts_from_playlist_element(playlist_state.playlist_elements[dest_song_idx])
        dest_part_idx, _ = _find_next_valid_part_index(dest_song_parts, "+1", -1, 0, repeat_override_active)
        
        return (dest_song_idx, dest_part_idx) if dest_part_idx is not None else (None, None)

    # Caso 3: Salto de parte (puede cruzar canciones)
    sim_song_idx = playlist_state.current_song_index
    sim_part_idx = song_state.current_part_index
    sim_pass_count = song_state.pass_count

    if isinstance(target, dict) and target.get("type") == "relative":
        steps = target.get("value", 0)
        direction = "+1" if steps > 0 else "-1"
        for _ in range(abs(steps)):
            # Determinar de dónde obtener la lista de partes para la simulación
            current_sim_parts = []
            if playlist_state.is_active:
                # Modo Playlist: obtener partes del elemento de la playlist
                if not (0 <= sim_song_idx < len(playlist_state.playlist_elements)):
                    return None, None # Salida segura si el índice de canción es inválido
                current_sim_parts = _get_parts_from_playlist_element(playlist_state.playlist_elements[sim_song_idx])
            else:
                # Modo Canción Única: usar las partes de la canción actual
                current_sim_parts = song_state.parts

            next_part_idx, next_pass_count = _find_next_valid_part_index(current_sim_parts, direction, sim_part_idx, sim_pass_count, repeat_override_active)
            
            if next_part_idx is not None:
                sim_part_idx, sim_pass_count = next_part_idx, next_pass_count
            elif playlist_state.is_active: # Cruzar límite de canción
                sim_song_idx += 1 if direction == "+1" else -1
                if not (0 <= sim_song_idx < len(playlist_state.playlist_elements)): return None, None
                
                new_sim_parts = _get_parts_from_playlist_element(playlist_state.playlist_elements[sim_song_idx])
                start_idx = -1 if direction == "+1" else len(new_sim_parts)
                sim_part_idx, sim_pass_count = _find_next_valid_part_index(new_sim_parts, direction, start_idx, 0, repeat_override_active)
                if sim_part_idx is None: return None, None
            else:
                return None, None # Fin de la línea sin playlist

    elif target == "restart": sim_part_idx = song_state.current_part_index
    elif isinstance(target, int): sim_part_idx = target

    return sim_song_idx, sim_part_idx


def find_next_valid_part_index(direction: str, start_index: int, start_pass_count: int):
    """Encuentra el índice y el pass_count de la siguiente parte válida usando el estado global."""
    return _find_next_valid_part_index(
        song_state.parts, direction, start_index, start_pass_count, repeat_override_active
    )


def resolve_global_part_index(global_index: int):
    """
    Convierte un índice de parte global (a través de toda la playlist)
    en un par (índice_de_canción, índice_de_parte_local).
    """
    if not playlist_state.is_active:
        return None, None

    cumulative_parts = 0
    for song_idx, element in enumerate(playlist_state.playlist_elements):
        parts_in_song = _get_parts_from_playlist_element(element)
        num_parts = len(parts_in_song)
        
        if global_index < cumulative_parts + num_parts:
            local_part_index = global_index - cumulative_parts
            return song_idx, local_part_index
        
        cumulative_parts += num_parts
        
    return None, None # Índice fuera de rango


def execute_global_part_jump():
    """
    Ejecuta un salto a una parte específica en una canción específica de la playlist.
    """
    global pending_action
    if not pending_action:
        return

    target_song_idx = pending_action.get("target_song")
    target_part_idx = pending_action.get("target_part")

    if target_song_idx is None or target_part_idx is None:
        pending_action = None
        return

    if load_song_from_playlist(target_song_idx):
        reset_song_state_on_stop()
        song_state.pass_count = 0 # Un salto directo resetea el ciclo de pases
        setup_part(target_part_idx)

        if clock_state.status == "PLAYING":
            process_song_tick()
    
    pending_action = None


def halve_quantization(current_quantize: str) -> str:
    """
    Reduce la cuantización a un nivel más rápido según una jerarquía fija.
    Devuelve el siguiente nivel de cuantización.
    """
    hierarchy = ["next_32", "next_16", "next_8", "next_4", "next_bar"]
    try:
        # Encontrar el índice del modo actual en la jerarquía
        current_index = hierarchy.index(current_quantize)
        # Si no es el último (el más rápido), devolver el siguiente
        if current_index < len(hierarchy) - 1:
            return hierarchy[current_index + 1]
    except ValueError:
        # Si el modo actual no está en la jerarquía (ej. "instant", "end_of_part"),
        # se devuelve el más rápido por defecto.
        return "next_bar"
    
    # Si ya está en el modo más rápido, no cambia
    return "next_bar"






def execute_part_jump ():
    """Ejecuta el salto de PARTE modificando el estado de la canción."""
    global pending_action
    if not pending_action:
        return

    target = pending_action.get("target")
    final_index = song_state.current_part_index
    final_pass_count = song_state.pass_count
    
    # Guardar la dirección original del salto para la lógica de fin de canción
    original_direction = 0
    if isinstance(target, dict) and target.get("type") == "relative":
        original_direction = target.get("value", 0)

    if isinstance(target, dict) and target.get("type") == "relative":
        steps = target.get("value", 0)
        if steps == 0:
            pending_action = None
            return

        direction = "+1" if steps > 0 else "-1"
        for _ in range(abs(steps)):
            if final_index is not None:
                final_index, final_pass_count = find_next_valid_part_index(direction, final_index, final_pass_count)
        
    elif target == "restart":
        pass # El índice y el pass_count no cambian
    elif isinstance(target, int):
        if 0 <= target < len(song_state.parts):
            final_index = target
            final_pass_count = 0 
        else:
            pending_action = None
            return
    
    # Si el salto resulta en un índice inválido, gestionar el cambio de canción
    if final_index is None:
        # Si el salto fue hacia atrás y hay una playlist, saltar a la canción anterior
        if original_direction < 0 and playlist_state.is_active:
            # Crear y ejecutar una acción de salto de canción
            song_jump_action = {"target_type": "song", "target": {"type": "relative", "value": -1}}
            pending_action = song_jump_action
            execute_song_jump()
            return # execute_song_jump ya limpia la acción, así que salimos
        else:
            # Comportamiento original: fin de la canción (o salto adelante a la siguiente)
            handle_song_end()
    else:
        # Aplicar el estado y configurar la parte de destino
        song_state.pass_count = final_pass_count
        setup_part(final_index)
    
    pending_action = None
  

def execute_song_jump():
    """Ejecuta el salto de CANCIÓN, iniciando en el punto correcto según la dirección."""
    global pending_action, ui_feedback_message
    if not pending_action or not playlist_state.is_active:
        pending_action = None
        return

    target = pending_action.get("target")
    current_index = playlist_state.current_song_index
    final_index = current_index

    is_relative_backwards_jump = (isinstance(target, dict) and 
                                target.get("type") == "relative" and 
                                target.get("value", 0) < 0)

    if target == "restart":
        final_index = current_index
    elif isinstance(target, dict) and target.get("type") == "relative":
        steps = target.get("value", 0)
        final_index = current_index + steps
    elif isinstance(target, int):
        final_index = target

    pending_action = None

    if not (0 <= final_index < len(playlist_state.playlist_elements)):
        set_feedback_message(f"Salto a canción {final_index + 1} inválido (fuera de rango).")
        return

    if load_song_from_playlist(final_index):
        reset_song_state_on_stop()
        
        if is_relative_backwards_jump:
            start_search_index = len(song_state.parts)
            target_part_index, target_pass_count = find_next_valid_part_index(
                "-1", start_search_index, 0
            )
            if target_part_index is not None:
                song_state.pass_count = target_pass_count
                setup_part(target_part_index, fire_instant_trigger=False)
            else:
                handle_song_end()
        else:
            start_next_part()
            
        if clock_state.status == "PLAYING":
            process_song_tick()
    else:
        set_feedback_message(f"Salto a canción {final_index + 1} inválido (error de carga).")


def execute_pending_action():
    """Inspecciona la acción pendiente y decide si es un salto de parte o de canción."""
    if not pending_action:
        return

    # Los Cues ahora se tratan como saltos de parte globales.
    if pending_action.get("target_type") in ["global_part", "cue_jump"]:
        execute_global_part_jump()
    elif pending_action.get("target_type") == "song":
        execute_song_jump()
    else:
        execute_part_jump()


def check_and_execute_pending_action():
    """
    Verifica si se cumplen las condiciones de cuantización para ejecutar una acción
    o para enviar un mensaje de cambio de parte por adelantado.
    Devuelve True si se ejecutó una acción de salto, False en caso contrario.
    """
    if not pending_action or clock_state.status != "PLAYING":
        return False


    quantize = pending_action.get("dynamic_quantize") or pending_action.get("quantize")
    sig_num = song_state.time_signature_numerator
    is_last_beat_of_bar = (song_state.remaining_beats_in_part % sig_num == 1)

    should_jump = False
    if quantize == "instant": should_jump = True
    elif quantize == "end_of_part" and song_state.remaining_beats_in_part == 1: should_jump = True
    elif quantize == "next_bar" and is_last_beat_of_bar: should_jump = True
    else:
        if is_last_beat_of_bar:
            total_beats_in_part = song_state.parts[song_state.current_part_index].get("bars", 0) * sig_num
            beats_into_part = total_beats_in_part - song_state.remaining_beats_in_part
            current_bar = beats_into_part // sig_num
            if quantize == "next_4" and (current_bar + 1) % 4 == 0: should_jump = True
            elif quantize == "next_8" and (current_bar + 1) % 8 == 0: should_jump = True
            elif quantize == "next_16" and (current_bar + 1) % 16 == 0: should_jump = True
            elif quantize == "next_32" and (current_bar + 1) % 32 == 0: should_jump = True

    if should_jump:
        execute_pending_action()
        return True

    return False

def start_next_part():
    """
    Determina qué parte reproducir a continuación, dando prioridad a las acciones del usuario.
    """
    global part_loop_active, part_loop_index, repeat_override_active

    # --- INICIO DEL CAMBIO ---
    # PRIORIDAD MÁXIMA: Si hay una acción pendiente, ejecutarla y salir.
    # Esto asegura que un salto programado por el usuario siempre anule
    # el comportamiento por defecto de la parte (como "repeat").
    if pending_action:
        execute_pending_action()
        return
    # --- FIN DEL CAMBIO ---

    if part_loop_active and song_state.current_part_index == part_loop_index:
        setup_part(song_state.current_part_index)
        return

    action_to_execute = "next"
    if song_state.current_part_index != -1:
        current_part = song_state.parts[song_state.current_part_index]
        pattern = current_part.get("repeat_pattern")
        if isinstance(pattern, list) and pattern:
            action_to_execute = pattern[song_state.pass_count % len(pattern)]
        elif isinstance(pattern, str):
            action_to_execute = pattern

    action = action_to_execute
    if action == "song_mode":
        repeat_override_active = True
        set_feedback_message("Repeat Pattern: Song Mode activado.")
        action = "next"
    elif action == "loop_mode":
        repeat_override_active = False
        set_feedback_message("Repeat Pattern: Loop Mode activado.")
        action = "next"

    if not repeat_override_active:
        if isinstance(action, dict):
            song_state.pass_count = 0
            if "jump_to_part" in action:
                target_idx = action["jump_to_part"]
                if 0 <= target_idx < len(song_state.parts): setup_part(target_idx); return
            elif "jump_to_cue" in action:
                cue_num = action["jump_to_cue"]
                for i, part in enumerate(song_state.parts):
                    if part.get("cue") == cue_num: setup_part(i); return
            elif "random_part" in action:
                choices = action["random_part"]
                if choices and isinstance(choices, list):
                    target_idx = random.choice(choices)
                    if 0 <= target_idx < len(song_state.parts): setup_part(target_idx); return
            action = "next"

        if action == "repeat": setup_part(song_state.current_part_index); return
        elif action == "prev":
            next_index, next_pass_count = find_next_valid_part_index("-1", song_state.current_part_index, song_state.pass_count)
            if next_index is not None: song_state.pass_count = next_pass_count; setup_part(next_index)
            else: handle_song_end()
            return
        elif action == "first_part":
            song_state.pass_count = 0
            next_index, _ = find_next_valid_part_index("+1", -1, 0)
            if next_index is not None: setup_part(next_index)
            else: handle_song_end()
            return
        elif action == "last_part":
            song_state.pass_count = 0
            next_index, _ = find_next_valid_part_index("-1", len(song_state.parts), 0)
            if next_index is not None: setup_part(next_index)
            else: handle_song_end()
            return
        elif action == "loop_part":
            part_loop_active = True; part_loop_index = song_state.current_part_index
            set_feedback_message(f"Repeat Pattern: Loop Part activado."); setup_part(part_loop_index); return

    if playlist_state.is_active:
        if action == "next_song": handle_song_end(); return
        elif action == "prev_song":
            prev_idx = playlist_state.current_song_index - 1
            if prev_idx >= 0 and load_song_from_playlist(prev_idx): start_next_part()
            return
        elif action == "first_song":
            if load_song_from_playlist(0): start_next_part()
            return
        elif action == "last_song":
            last_idx = len(playlist_state.playlist_elements) - 1
            if last_idx >= 0 and load_song_from_playlist(last_idx): start_next_part()
            return

    next_index, next_pass_count = find_next_valid_part_index("+1", song_state.current_part_index, song_state.pass_count)
    if next_index is None:
        handle_song_end()
    else:
        song_state.pass_count = next_pass_count
        setup_part(next_index)

def setup_part(part_index, fire_instant_trigger=True):
    """
    Configura una parte y dispara incondicionalmente sus triggers asociados.
    """
    if not (0 <= part_index < len(song_state.parts)):
        return # Salida segura si el índice no es válido

    song_state.current_part_index = part_index
    part = song_state.parts[part_index]
    song_state.remaining_beats_in_part = part.get("bars", 0) * song_state.time_signature_numerator
    song_state.current_bar_in_part = 0

    if part_index == 0:
        song_state.start_time = time.time()

    if fire_instant_trigger:
        global initial_outputs_sent, part_loop_active
        # No enviar outputs si:
        # 1. Ya se enviaron los iniciales para la primera parte, O
        # 2. Está activo el loop de parte (para evitar reenvío en cada repetición)
        skip_outputs = ((initial_outputs_sent and part_index == 0 and 
                        playlist_state.current_song_index == 0) or
                       part_loop_active)
        
        context = {
            "song_index": playlist_state.current_song_index,
            "song_name": song_state.song_name,
            "song_color": song_state.song_color,
            "part_index": part_index,
            "part_name": part.get("name"),
            "part_bars": part.get("bars"),
            "part_color": part.get("color"),
            "part_notes": part.get("notes"),
            "part_cue": part.get("cue"),
            "part_index_in_setlist": _get_global_part_index(playlist_state.current_song_index, part_index),
            "skip_outputs": skip_outputs
        }
        fire_triggers("part_change", context, force_instant=True)

    if song_state.remaining_beats_in_part <= 0:
        start_next_part()


def _send_initial_outputs():
    """Envía los outputs de la primera parte para inicialización."""
    if not song_state.parts or not playlist_state.is_active or not outputs_enabled:
        return
    
    # Obtener la primera parte de la primera canción
    first_part = song_state.parts[0]
    local_actions = first_part.get("output", [])
    
    # Asegurar que sea una lista
    if isinstance(local_actions, dict):
        local_actions = [local_actions]
    
    if isinstance(local_actions, list) and local_actions:
        context = {
            "song_index": 0,
            "song_name": song_state.song_name,
            "song_color": song_state.song_color,
            "part_index": 0,
            "part_name": first_part.get("name"),
            "part_bars": first_part.get("bars"),
            "part_color": first_part.get("color"),
            "part_notes": first_part.get("notes"),
            "part_cue": first_part.get("cue"),
            "part_index_in_setlist": 0
        }
        
        for action in local_actions:
            _process_trigger_action(action, context)
        
        set_feedback_message("Outputs iniciales enviados")


def handle_start(is_passive_start=False):
    """Lógica para procesar un comando START."""
    global clock_state, initial_outputs_sent
    if clock_state.status == "PLAYING": return

    # Si no está reproduciendo, enviar outputs iniciales inmediatamente
    if clock_state.status == "STOPPED" and not initial_outputs_sent:
        _send_initial_outputs()
        initial_outputs_sent = True
        return

    # Disparar el evento de inicio de transporte y el nuevo evento de inicio inicial
    if not is_passive_start:
        if "transport_out" in midi_outputs:
            try:
                midi_outputs["transport_out"].send(mido.Message('start'))
            except Exception as e:
                set_feedback_message(f"Error transport_out: {e}")
        fire_triggers("playback_start", {})
        fire_triggers("playback_initial_start", {}) 

    clock_state.status = "PLAYING"
    clock_state.start_time = time.time()
    clock_state.paused_set_elapsed_time = 0
    reset_song_state_on_stop()
    start_next_part()
  

    # El trigger de la primera parte ahora es manejado por setup_part.
    if playlist_state.is_active and playlist_state.playlist_elements:
        first_song_element = playlist_state.playlist_elements[0]
        context = {
            "song_index": 0,
            "song_name": first_song_element.get("song_name", Path(first_song_element.get("filepath", "N/A")).stem),
            "song_color": first_song_element.get("color")
        }
        fire_triggers("song_change", context, force_instant=True)

    # CORRECCIÓN: Eliminar la llamada inmediata a process_song_tick()
    # Esto causaba que el primer beat se perdiera porque decrementaba
    # remaining_beats_in_part antes de que el usuario viera el estado inicial
    # if song_state.current_part_index != -1:
    #     process_song_tick()

def handle_stop():
    """Lógica para procesar un comando STOP."""
    global clock_state, song_state, initial_outputs_sent
    if clock_state.status == "STOPPED": return # Evitar múltiples paradas
    
    # Resetear flag de outputs iniciales al parar
    initial_outputs_sent = False

    # Envío implícito de transporte si está configurado
    if "transport_out" in midi_outputs:
        try:
            midi_outputs["transport_out"].send(mido.Message('stop'))
        except Exception as e:
            set_feedback_message(f"Error transport_out: {e}")
    fire_triggers("playback_stop", {})
    if clock_state.status == "PLAYING":
        current_time = time.time()
        if clock_state.start_time > 0:
            clock_state.paused_set_elapsed_time += current_time - clock_state.start_time
        if song_state.start_time > 0:
            song_state.paused_song_elapsed_time += current_time - song_state.start_time
    
    clock_state.status = "STOPPED"

def handle_continue():
    """Lógica para procesar un comando CONTINUE."""
    global clock_state, song_state
    if clock_state.status == "PLAYING": return # Evitar múltiples inicios

    # Envío implícito de transporte si está configurado
    if "transport_out" in midi_outputs:
        try:
            midi_outputs["transport_out"].send(mido.Message('continue'))
        except Exception as e:
            set_feedback_message(f"Error transport_out: {e}")
    fire_triggers("playback_continue", {})
    clock_state.status = "PLAYING"
    current_time = time.time()
    clock_state.start_time = current_time
    if song_state.current_part_index != -1:
        song_state.start_time = current_time

def midi_input_listener():
    """El hilo principal que escucha los mensajes MIDI y actualiza el estado."""
    global clock_state, song_state
    
    # Obtener los puertos del diccionario
    main_port = midi_inputs.get("clock")
    control_port = midi_inputs.get("midi_in")
    # Un puerto es compartido si el puerto de control se ha asignado al de entrada.
    is_shared_port = control_port is not None and control_port is main_port

    if main_port:
        time.sleep(0.05) # Pequeña pausa para asegurar que el puerto está listo
        while main_port.poll() is not None:
            pass # Consumir y descartar todos los mensajes pendientes

    while not SHUTDOWN_FLAG:
        if not main_port:
            time.sleep(0.1)
            continue

        msg = main_port.poll()
        if not msg:
            time.sleep(0.001)
            continue

        # --- Lógica de Clock ---

        if msg.type == 'start':
            handle_start()
        elif msg.type == 'stop':
            handle_stop()
        elif msg.type == 'continue':
            handle_continue()
        elif msg.type == 'clock':
            if clock_state.status == "STOPPED":
                handle_start(is_passive_start=True)
                set_feedback_message("Clock detectado. Iniciando secuencia...")
            # --- Cálculo de BPM ---
            current_time = time.perf_counter()
            if clock_state.last_tick_time > 0:
                delta = current_time - clock_state.last_tick_time
                if delta > 0:
                    clock_state.tick_times.append(delta)
                    if len(clock_state.tick_times) > 96:
                        clock_state.tick_times.pop(0)
                    avg_delta = sum(clock_state.tick_times) / len(clock_state.tick_times)
                    clock_state.bpm = (60.0 / MIDI_PPQN) / avg_delta
            clock_state.last_tick_time = current_time

            # --- Avance de la Canción ---
            if clock_state.status == "PLAYING":
                song_state.midi_clock_tick_counter += 1
                if song_state.midi_clock_tick_counter >= song_state.ticks_per_song_beat:
                    song_state.midi_clock_tick_counter = 0
                    process_song_tick()
        
        # --- Lógica de Control (si el puerto es compartido) ---
        elif is_shared_port:
            process_control_message(msg)



def trigger_song_jump(action_dict):
    """
    Crea una acción pendiente si el reloj está en PLAYING,
    o ejecuta el salto de canción inmediatamente si está detenido.
    """
    global pending_action
    if clock_state.status == "PLAYING":
        pending_action = action_dict
    else:
        # Si no estamos reproduciendo, el salto es inmediato
        # Creamos una acción temporal para que execute_song_jump la consuma
        pending_action = action_dict
        execute_song_jump()


def toggle_outputs():
    """Activa/desactiva el envío de outputs."""
    global outputs_enabled
    outputs_enabled = not outputs_enabled
    status = "activado" if outputs_enabled else "desactivado"
    set_feedback_message(f"Envío de outputs {status}")


def cancel_part_loop():
    """Desactiva el modo de bucle de parte si está activo."""
    global part_loop_active, part_loop_index, ui_feedback_message
    if part_loop_active:
        part_loop_active = False
        part_loop_index = -1
        set_feedback_message("Part loop cancelled.")


def trigger_cue_jump(cue_num: int):
    """
    Gestiona la lógica para disparar un salto a un Cue, incluyendo la
    cuantización dinámica. La búsqueda del cue es global a toda la playlist.
    """
    global pending_action, ui_feedback_message

    if not playlist_state.is_active:
        set_feedback_message(f"Cues ignorados (no hay playlist activa).")
        return

    # --- LÓGICA DE BÚSQUEDA GLOBAL ---
    target_song_idx = None
    target_part_idx = None
    part_name = "N/A"

    for s_idx, element in enumerate(playlist_state.playlist_elements):
        parts = _get_parts_from_playlist_element(element)
        for p_idx, part in enumerate(parts):
            if part.get("cue") == cue_num:
                target_song_idx = s_idx
                target_part_idx = p_idx
                part_name = part.get("name", "N/A")
                break # Salir del bucle de partes
        if target_song_idx is not None:
            break # Salir del bucle de canciones
    
    if target_song_idx is None:
        set_feedback_message(f"Cue {cue_num} no encontrado en la playlist.")
        return

    # Comprobar si ya hay una acción pendiente para este mismo cue
    if (pending_action and 
        pending_action.get("target_type") == "cue_jump" and
        pending_action.get("cue_num") == cue_num):
        
        # Acelerar la cuantización existente
        new_quantize = halve_quantization(pending_action["dynamic_quantize"])
        pending_action["dynamic_quantize"] = new_quantize
        set_feedback_message(f"Cue {cue_num} ({part_name}) acelerado a {new_quantize.upper()}.")

    else:
        # Crear una nueva acción de salto a cue
        pending_action = {
            "target_type": "cue_jump",
            "target_song": target_song_idx,
            "target_part": target_part_idx,
            "cue_num": cue_num,
            "dynamic_quantize": quantize_mode # Empezar con la cuantización global
        }
        set_feedback_message(f"Ir a Cue {cue_num}: {part_name}")


def process_control_message(msg):
    """Procesa un único mensaje de control MIDI (PC, CC, Note, Song Select)."""
    global pending_action, quantize_mode, ui_feedback_message, repeat_override_active, part_loop_active, part_loop_index
    
    if msg.type == 'program_change':
        if clock_state.status == "PLAYING":
            pending_action = {"target": msg.program, "quantize": quantize_mode}
            set_feedback_message(f"PC Recibido: Ir a parte {msg.program + 1}.")
        else:
            set_feedback_message("PC ignorado (reproducción detenida).")

    elif msg.type == 'song_select':
        if playlist_state.is_active:
            action = {"target_type": "song", "target": msg.song, "quantize": quantize_mode}
            trigger_song_jump(action)
            set_feedback_message(f"Song Select: Ir a canción {msg.song + 1}.")
        else:
            set_feedback_message("Song Select ignorado (no hay playlist activa).")

    elif msg.type == 'note_on':
        if msg.note in [NOTE_PREV_PART, NOTE_NEXT_PART]: # Saltos de PARTE
            if clock_state.status == "PLAYING":
                value = 1 if msg.note == NOTE_NEXT_PART else -1
                target = {"type": "relative", "value": value}
                pending_action = {"target": target, "quantize": quantize_mode}
                set_feedback_message(f"Note Recibido: {'Siguiente' if value == 1 else 'Anterior'} Parte.")
            else:
                set_feedback_message("Note On (Part Jump) ignorado (reproducción detenida).")
        
        elif msg.note in [NOTE_PREV_SONG, NOTE_NEXT_SONG]: # Saltos de CANCIÓN
            if not playlist_state.is_active:
                set_feedback_message("Note On (Song Jump) ignorado (no hay playlist activa).")
                return
            value = 1 if msg.note == NOTE_NEXT_SONG else -1
            target = {"type": "relative", "value": value}
            action = {"target_type": "song", "target": target, "quantize": quantize_mode}
            trigger_song_jump(action)
            set_feedback_message(f"Note Recibido: {'Siguiente' if value == 1 else 'Anterior'} Canción.")

    elif msg.type == 'control_change' and msg.control == CC_GLOBAL_PART_JUMP:
        if not playlist_state.is_active:
            set_feedback_message(f"CC#{CC_GLOBAL_PART_JUMP} ignorado (no hay playlist activa).")
            return

        target_song_idx, target_part_idx = resolve_global_part_index(msg.value)

        if target_song_idx is not None:
            pending_action = {
                "target_type": "global_part",
                "target_song": target_song_idx,
                "target_part": target_part_idx,
                "quantize": quantize_mode
            }
            set_feedback_message(f"CC#{CC_GLOBAL_PART_JUMP} IN: Ir a parte global {msg.value + 1}.")
        else:
            set_feedback_message(f"CC#{CC_GLOBAL_PART_JUMP} Error: Parte global {msg.value + 1} no existe.")

    elif msg.type == 'control_change' and msg.control == CC_CUE_JUMP:
        trigger_cue_jump(msg.value)

    elif msg.type == 'control_change' and msg.control == CC_MAIN_CONTROL:
        val = msg.value
        # Saltos rápidos (cuantización fija)
        if CC0_VAL_QUANT_INSTANT <= val <= CC0_VAL_QUANT_16:
            quant_map = {
                CC0_VAL_QUANT_INSTANT: "instant", 
                CC0_VAL_QUANT_BAR: "next_bar", 
                CC0_VAL_QUANT_8: "next_8", 
                CC0_VAL_QUANT_16: "next_16"
            }
            quant = quant_map.get(val, "next_bar")
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quant}
            set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Salto rápido (Quant: {quant.upper()}).")
        # Selección de modo de cuantización global
        elif val in [CC0_VAL_SET_QUANT_4, CC0_VAL_SET_QUANT_8, CC0_VAL_SET_QUANT_16, CC0_VAL_SET_QUANT_BAR, CC0_VAL_SET_QUANT_END, CC0_VAL_SET_QUANT_INSTANT]:
            quant_map = {
                CC0_VAL_SET_QUANT_4: "next_4", 
                CC0_VAL_SET_QUANT_8: "next_8", 
                CC0_VAL_SET_QUANT_16: "next_16", 
                CC0_VAL_SET_QUANT_BAR: "next_bar", 
                CC0_VAL_SET_QUANT_END: "end_of_part",
                CC0_VAL_SET_QUANT_INSTANT: "instant"
            }
            quantize_mode = quant_map[val]
            set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Modo global -> {quantize_mode.upper()}.")
        # Navegación de PARTE (cuantización global)
        elif val == CC0_VAL_PART_PREV: # Saltar Parte Anterior
            target = {"type": "relative", "value": -1}
            pending_action = {"target": target, "quantize": quantize_mode}
            set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Saltar Parte Anterior.")
        elif val == CC0_VAL_PART_NEXT: # Saltar Parte Siguiente
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quantize_mode}
            set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Saltar Parte Siguiente.")
        elif CC0_VAL_SONG_PREV <= val <= CC0_VAL_SONG_RESTART:
            playlist_actions = [
                CC0_VAL_SONG_PREV, CC0_VAL_SONG_NEXT, CC0_VAL_SONG_FIRST, 
                CC0_VAL_SONG_LAST, CC0_VAL_SONG_RESTART
            ]
            if val in playlist_actions and not playlist_state.is_active:
                set_feedback_message(f"CC#{CC_MAIN_CONTROL}({val}) ignorado (no hay playlist activa).")
                return
            
            action = {}
            if val == CC0_VAL_SONG_PREV: # Canción Anterior
                target = {"type": "relative", "value": -1}
                action = {"target_type": "song", "target": target, "quantize": quantize_mode}
                set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Canción Anterior.")
            elif val == CC0_VAL_SONG_NEXT: # Siguiente Canción
                target = {"type": "relative", "value": 1}
                action = {"target_type": "song", "target": target, "quantize": quantize_mode}
                set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Siguiente Canción.")
            elif val == CC0_VAL_SONG_FIRST: # Ir a Primera Canción
                action = {"target_type": "song", "target": 0, "quantize": quantize_mode}
                set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Ir a Primera Canción.")
            elif val == CC0_VAL_SONG_LAST: # Ir a Última Canción
                last_song_index = len(playlist_state.playlist_elements) - 1
                action = {"target_type": "song", "target": last_song_index, "quantize": quantize_mode}
                set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Ir a Última Canción.")
            
            elif val == CC0_VAL_PART_LOOP_TOGGLE: # Toggle Part Loop
                if part_loop_active and song_state.current_part_index == part_loop_index:
                    cancel_part_loop()
                elif clock_state.status == "PLAYING" and song_state.current_part_index != -1:
                    part_loop_active = True
                    part_loop_index = song_state.current_part_index
                    part_name = song_state.parts[part_loop_index].get('name', 'N/A')
                    set_feedback_message(f"Loop activado para parte: {part_name}")
                else:
                    set_feedback_message("No se puede activar el bucle (reproducción detenida).")
            
            elif val == CC0_VAL_PART_RESTART: # Reiniciar Parte
                if clock_state.status == "PLAYING":
                    pending_action = {"target": "restart", "quantize": quantize_mode}
                    set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Reiniciar Parte.")
                else:
                    set_feedback_message(f"CC#{CC_MAIN_CONTROL}({val}) ignorado (reproducción detenida).")
            elif val == CC0_VAL_ACTION_CANCEL: # Cancelar Acción
                if pending_action:
                    pending_action = None
                    set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Acción cancelada.")
            elif val == CC0_VAL_MODE_TOGGLE: # Toggle Mode
                repeat_override_active = not repeat_override_active
                mode_str = "Song Mode" if repeat_override_active else "Loop Mode"
                set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: {mode_str}")
            
            elif val == CC0_VAL_SONG_RESTART: # Reiniciar Canción
                action = {"target_type": "song", "target": "restart", "quantize": quantize_mode}
                set_feedback_message(f"CC#{CC_MAIN_CONTROL} IN: Reiniciar Canción.")

            if action:
                trigger_song_jump(action)
                return


def _get_global_part_index(target_song_idx, local_part_idx):
    """
    Convierte un par (índice_de_canción, índice_de_parte_local) en un
    índice de parte global a través de toda la playlist.
    """
    if not playlist_state.is_active:
        return local_part_idx

    cumulative_parts = 0
    for i in range(target_song_idx):
        element = playlist_state.playlist_elements[i]
        parts_in_song = _get_parts_from_playlist_element(element)
        cumulative_parts += len(parts_in_song)

    return cumulative_parts + local_part_idx


def midi_control_listener():
    """El hilo que escucha los mensajes MIDI de control (en un puerto dedicado)."""
    control_port = midi_inputs.get("midi_in")
    while not SHUTDOWN_FLAG:
        if not control_port:
            time.sleep(0.1)
            continue

        msg = control_port.poll()

        if not msg:
            time.sleep(0.001)
            continue
        
        process_control_message(msg)

def handle_song_end():
    """
    Gestiona el final de la secuencia de una canción.
    Si hay una playlist, intenta cargar la siguiente canción.
    Si no, o si es el final de la playlist, finaliza la reproducción.
    """
    global ui_feedback_message

    if playlist_state.is_active:
        next_song_index = playlist_state.current_song_index + 1
        if next_song_index < len(playlist_state.playlist_elements):
            next_song_element = playlist_state.playlist_elements[next_song_index]
            next_song_name = "Siguiente Canción"
            if "filepath" in next_song_element:
                next_song_name = Path(next_song_element["filepath"]).stem
            elif "song_name" in next_song_element:
                next_song_name = next_song_element["song_name"]
            
            set_feedback_message(f"Iniciando '{next_song_name}'...")

            if load_song_from_playlist(next_song_index):
                start_next_part()
            else:
                clock_state.status = "FINISHED"
                reset_song_state_on_stop()
                set_feedback_message("Error al cargar la siguiente canción. Reproducción detenida.")
        else:
            total_parts = 0
            for element in playlist_state.playlist_elements:
                total_parts += len(_get_parts_from_playlist_element(element))
            
            context = {
                "playlist_name": playlist_state.playlist_name,
                "playlist_song_count": len(playlist_state.playlist_elements),
                "playlist_part_count": total_parts
            }
            fire_triggers("setlist_end", context)
            clock_state.status = "FINISHED"
            reset_song_state_on_stop()
            set_feedback_message(f"Playlist '{playlist_state.playlist_name}' finalizada.")
    else:
        # No hay playlist, comportamiento normal
        clock_state.status = "FINISHED"
        reset_song_state_on_stop()
        set_feedback_message(f"Canción '{song_state.song_name}' finalizada.")

def set_feedback_message(message: str, duration: int = 5):
    """Establece un mensaje de feedback y su tiempo de expiración."""
    global ui_feedback_message, feedback_expiry_time
    ui_feedback_message = message
    feedback_expiry_time = time.time() + duration

def get_dynamic_endpoint():
    """
    Calcula el compás final relevante, ya sea el final de la parte
    o el punto de ejecución de una acción pendiente.
    Devuelve el número del compás final (1-based).
    """
    if not pending_action or clock_state.status != "PLAYING" or song_state.current_part_index == -1:
        if song_state.current_part_index != -1:
            return song_state.parts[song_state.current_part_index].get("bars", 0)
        return 0

    current_part = song_state.parts[song_state.current_part_index]
    total_bars_in_part = current_part.get("bars", 0)

    target = pending_action.get("target")
    if isinstance(target, dict) and target.get("type") == "relative" and target.get("value") == 0:
        return total_bars_in_part
    
    sig_num = song_state.time_signature_numerator
    beats_into_part = (total_bars_in_part * sig_num) - song_state.remaining_beats_in_part
    current_bar_index = beats_into_part // sig_num

    quantize = pending_action.get("dynamic_quantize") or pending_action.get("quantize")
    
    if quantize in ["instant", "next_bar", "end_of_part"]:
        if quantize == "end_of_part":
            return total_bars_in_part
        return current_bar_index + 1
    
    quantize_map = {"next_4": 4, "next_8": 8, "next_16": 16, "next_32": 32}
    if quantize in quantize_map:
        boundary = quantize_map[quantize]
        target_bar = ((current_bar_index // boundary) + 1) * boundary
        return target_bar
    
    return total_bars_in_part


def load_file_by_name(filename: str):
    """Carga un archivo de canción o playlist por su nombre."""
    global loaded_filename, playlist_state, repeat_override_active, song_state, config

    filepath = SONGS_DIR / filename
    if not filepath.is_file():
        set_feedback_message(f"Error: no se encontró el archivo '{filename}'")
        return

    # Validar antes de cargar
    is_valid, errors, data = MIDItemaValidator.validate_file(filepath)
    if not is_valid:
        error_details = "\n".join(str(e) for e in errors[:5])
        set_feedback_message(f"[!] Archivo inválido: {errors[0]}")
        print(f"[!] Errores de validación en '{filename}':\n{error_details}")
        return
    # Resetear estado antes de cargar
    reset_song_state_on_stop()
    playlist_state = PlaylistState()


    if "songs" in data and isinstance(data["songs"], list):
        playlist_state.is_active = True
        playlist_state.playlist_name = data.get("playlist_name", filepath.stem)
        playlist_state.playlist_elements = data["songs"]
        set_feedback_message(f"Playlist '{playlist_state.playlist_name}' cargada.")
        
        playlist_mode = data.get("mode", "loop")
        repeat_override_active = playlist_mode.lower() == "song"
        
        load_song_from_playlist(0)
    else:
        playlist_state.is_active = False
        load_song_file(data=data)
    
    loaded_filename = filepath.stem

def reconfigure_clock_port(port_name: str):
    """Cierra el puerto de clock actual y abre uno nuevo."""
    global midi_inputs, clock_state
    
    # Detener la reproducción para evitar problemas
    if clock_state.status != "STOPPED":
        handle_stop()

    if "clock" in midi_inputs and midi_inputs["clock"]:
        try:
            midi_inputs["clock"].close()
        except Exception:
            pass # Ignorar errores al cerrar

    try:
        midi_inputs["clock"] = mido.open_input(port_name)
        clock_state.source_name = port_name
        set_feedback_message(f"Clock reconfigurado a: '{port_name}'")
    except Exception as e:
        set_feedback_message(f"Error abriendo '{port_name}': {e}")
        midi_inputs["clock"] = None
        clock_state.source_name = "Ninguna"


# --- Main Application ---
def main():
    global app_ui_instance, quantize_mode, repeat_override_active, loaded_filename, config, midi_inputs, SONGS_DIR, SHUTDOWN_FLAG

    init_debug_log()
    initial_data = None
    initial_load_success = True
    print("MIDItema\n")
    # El help text ahora es más genérico para reflejar la carga de directorios y playlists
    parser = argparse.ArgumentParser(prog="miditema", description="Contador de compases esclavo de MIDI Clock.")
    parser.add_argument("song_file", nargs='?', default=None, help="Nombre del archivo de canción, playlist o directorio.")
    parser.add_argument("--quant", type=str, default=None, help="Fija la cuantización por defecto. Valores: bar, 4, 8, 16, 32, instant.")
    parser.add_argument("--conf", type=str, default=None, help="Especifica un archivo de configuración alternativo.")
    parser.add_argument("--debug", action="store_true", help="Activa logging de debug y modo consola de depuración.")
    parser.add_argument("--no-output", action="store_true", help="Inicia con el envío de outputs desactivado.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--song-mode", action="store_true", help="Inicia en 'Song Mode', ignorando los patrones de repetición.")
    mode_group.add_argument("--loop-mode", action="store_true", help="Inicia en 'Loop Mode', respetando los patrones de repetición.")
    args = parser.parse_args()

    # Configurar debug logging basado en --debug
    global DEBUG_LOGGING_ENABLED, outputs_enabled
    DEBUG_LOGGING_ENABLED = args.debug
    
    # Configurar estado inicial de outputs
    if args.no_output:
        outputs_enabled = False
        print("[*] Outputs desactivados desde inicio.")

    if args.quant:
        quant_map = {"bar": "next_bar", "4": "next_4", "8": "next_8", "16": "next_16", "32": "next_32", "instant": "instant"}
        user_mode = quant_map.get(args.quant, args.quant)
        if user_mode in quant_map.values():
            quantize_mode = user_mode
            print(f"[*] Default quantization {quantize_mode.upper()}")
        else:
            print(f"[!] Invalid quantization '{args.quant}'. Using default '{quantize_mode}'.")

    config_file_to_load = args.conf if args.conf else CONF_FILE_NAME
    config = load_config(config_file_to_load)
    # Añadimos la ruta al propio diccionario de configuración. Es más robusto.
    config['_source_file'] = config_file_to_load
    setup_devices(config)


    if args.song_file:
        is_dir_mode = args.song_file.endswith(('/', '\\')) or Path(args.song_file).is_dir()
        user_path = Path(args.song_file)

        if is_dir_mode:
            if not user_path.is_dir():
                print(f"[!] Error: El directorio '{user_path}' no existe.")
                return
            
            print(f"[*] Directorio '{user_path.name}' detectado. Cargando como playlist...")
            SONGS_DIR = user_path # La base para buscar archivos es ahora este directorio
            json_files = sorted(list(SONGS_DIR.glob("*.json")) + list(SONGS_DIR.glob("*.json5")))
            if not json_files:
                print(f"[!] Error: El directorio '{user_path.name}' no contiene archivos .json o .json5.")
                return

            # Lógica de carga de directorio restaurada (simple y directa)
            playlist_elements = [{"filepath": f.name} for f in json_files]
            initial_data = {"playlist_name": user_path.name, "songs": playlist_elements}
            loaded_filename = user_path.name
        else:
            # Modo archivo: buscar en el directorio por defecto 'temas/'
            filename = user_path.name if user_path.name.lower().endswith((".json", ".json5")) else f"{user_path.name}.json"
            selected_file_path = SONGS_DIR / filename
            if not selected_file_path.is_file():
                print(f"[!] El archivo '{filename}' no se encontró en la carpeta '{SONGS_DIR_NAME}'.")
                # Si no se encuentra, activamos la lógica del selector interactivo
                args.song_file = None
            else:
                try:
                    with selected_file_path.open('r', encoding='utf-8') as f:
                        initial_data = json5.load(f)
                    loaded_filename = selected_file_path.stem
                except Exception as e:
                    print(f"Error al leer el archivo '{selected_file_path.name}': {e}")
                    return

    if initial_data:
        # Procesar devices del archivo si existen
        if "devices" in initial_data:
            merged_config = config.copy()
            # Merge profundo para devices
            if "devices" in merged_config and "devices" in initial_data:
                for device_type, aliases in initial_data["devices"].items():
                    if device_type not in merged_config["devices"]:
                        merged_config["devices"][device_type] = {}
                    merged_config["devices"][device_type].update(aliases)
            else:
                merged_config["devices"] = initial_data["devices"]
        if "songs" in initial_data and isinstance(initial_data["songs"], list):
            playlist_state.is_active = True
            playlist_state.playlist_elements = initial_data["songs"]
            playlist_state.playlist_name = initial_data.get("playlist_name", loaded_filename or "Sin nombre")
            # Leer beats o bars del setlist, convertir bars a beats si es necesario
            if "beats" in initial_data:
                playlist_state.beats = initial_data["beats"]
            elif "bars" in initial_data:
                # Convertir bars a beats usando time_signature por defecto (4/4)
                playlist_state.beats = initial_data["bars"] * 4
            else:
                playlist_state.beats = 2  # Default
            
            print(f"[*] Playlist '{playlist_state.playlist_name}' cargada con {len(playlist_state.playlist_elements)} canciones.")
            
            # Rebuild global parts list when playlist is loaded
            global_parts_manager.build_global_parts_list()
            
            playlist_mode = initial_data.get("mode", "loop")
            repeat_override_active = playlist_mode.lower() == "song"
            if args.song_mode: repeat_override_active = True
            elif args.loop_mode: repeat_override_active = False
            
            mode_str = "SONG MODE" if repeat_override_active else "LOOP MODE"
            print(f"[*] Inicio en {mode_str}.")

            if not load_song_from_playlist(0):
                print("[!] Error: No se pudo cargar la primera canción de la playlist.")
                print("[*] La TUI se abrirá de todos modos. Puedes cargar otro archivo desde el menú.")
                initial_load_success = False
        else:
            if not load_song_file(data=initial_data):
                print("[!] Error: No se pudo cargar la canción.")
                print("[*] La TUI se abrirá de todos modos. Puedes cargar otro archivo desde el menú.")
                initial_load_success = False
            if args.song_mode: repeat_override_active = True
            elif args.loop_mode: repeat_override_active = False

    listener_thread = threading.Thread(target=midi_input_listener, daemon=True)
    listener_thread.start()
    control_listener_thread = None
    if "midi_in" in midi_inputs and midi_inputs["midi_in"] is not midi_inputs.get("clock"):
        control_listener_thread = threading.Thread(target=midi_control_listener, daemon=True)
        control_listener_thread.start()

    signal.signal(signal.SIGINT, signal_handler)
   
    if args.debug:
        print("\n--- MODO DEPURACIÓN ACTIVO ---")
        print("El motor está corriendo. Presiona 'Tab' para lanzar la TUI, Ctrl+C para salir.")
        
        def print_debug_status():
            """Imprime una línea de estado simple para la depuración en consola."""
            status = clock_state.status
            bpm = clock_state.bpm
            part_name = "N/A"
            part_idx = song_state.current_part_index
            
            if 0 <= part_idx < len(song_state.parts):
                part_name = song_state.parts[part_idx].get('name', 'N/A')

            action_str = "None"
            if pending_action:
                action_str = str(pending_action.get('target', 'N/A'))

            print(
                f"Status: {status} | BPM: {bpm:.1f} | Part: {part_name} ({part_idx+1}) | Pending: {action_str}      ",
                end='\r'
            )
            sys.stdout.flush()

        try:
            while not SHUTDOWN_FLAG:
                char = get_char_non_blocking()
                if char == '\t': # Tecla Tab
                    print("\nLanzando TUI...")
                    break 
                print_debug_status()
                time.sleep(0.1)
        except KeyboardInterrupt:
            SHUTDOWN_FLAG = True

    if not SHUTDOWN_FLAG:
        app_ui_instance = tui.MiditemaApp(miditema_module=sys.modules[__name__])
        # Mostrar mensaje de error en la TUI si hubo problemas
        if not initial_load_success:
            set_feedback_message("[!] Error en carga inicial. Usa el menú para abrir un archivo.", duration=10)
       
        app_ui_instance.run()

    SHUTDOWN_FLAG = True
    print("\nCerrando...")
    unique_ports = {id(p): p for p in midi_inputs.values()}.values()
    for port in unique_ports:
        if port and not port.closed: port.close()
    for port in midi_outputs.values():
        if port and not port.closed: port.close()

    if listener_thread.is_alive(): listener_thread.join(timeout=0.2)
    if control_listener_thread and control_listener_thread.is_alive(): control_listener_thread.join(timeout=0.2)
    print("Detenido.")


if __name__ == "__main__":
    main()

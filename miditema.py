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
from pythonosc import udp_client
from pythonosc import osc_message_builder


# --- UI Imports ---
from prompt_toolkit import Application, HTML
from prompt_toolkit.layout.containers import HSplit, Window, VSplit, WindowAlign
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition

# --- Global Configuration ---
SONGS_DIR_NAME = "temas"
SONGS_DIR = Path(f"./{SONGS_DIR_NAME}")
CONF_FILE_NAME = "miditema.conf.json"
SHUTDOWN_FLAG = False
MIDI_PPQN = 24  # MIDI Clock Standard, no configurable


# --- Color Palette Definitions ---
# Styles for part titles (background color)
TITLE_COLOR_PALETTE = {
    'default': "bg='#222222' fg='ansiwhite'",
    'red':     "bg='ansired' fg='ansiwhite'",
    'green':   "bg='ansigreen' fg='ansiwhite'",
    'yellow':  "bg='ansiyellow' fg='ansiblack'",
    'blue':    "bg='ansiblue' fg='ansiwhite'",
    'magenta': "bg='ansimagenta' fg='ansiwhite'",
    'cyan':    "bg='ansicyan' fg='ansiblack'",
}
# Styles for foreground elements (text, sequencer blocks)
FG_COLOR_PALETTE = {
    'default': "fg='ansicyan' bold='true'",
    'red':     "fg='ansired' bold='true'",
    'green':   "fg='ansigreen' bold='true'",
    'yellow':  "fg='ansiyellow' bold='true'",
    'blue':    "fg='ansiblue' bold='true'",
    'magenta': "fg='ansimagenta' bold='true'",
    'cyan':    "fg='ansicyan' bold='true'",
}

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

class SongState:
    """Almacena el estado de la canción y la secuencia."""
    def __init__(self):
        self.song_name = "Nada"
        self.song_color = None
        self.parts = []
        self.current_part_index = -1
        self.remaining_beats_in_part = 0
        self.pass_count = 0
        self.midi_clock_tick_counter = 0
        self.current_bar_in_part = 0 
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

# --- Global State Instances ---
clock_state = ClockState()
song_state = SongState()
playlist_state = PlaylistState()
pending_action = None
repeat_override_active = False
quantize_mode = "next_8" # Modo de cuantización por defecto
goto_input_active = False
goto_input_buffer = ""
app_ui_instance = None
midi_input_port = None
midi_control_port = None
midi_output_ports = []
pc_output_port = None
pc_channel = 0 
beat_flash_end_time = 0
osc_client = None
osc_address = None
osc_config = {}
ui_feedback_message = ""

# --- Helper Functions ---
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

# --- Core Logic ---

def load_config():
    """Carga la configuración del alias del dispositivo desde el archivo .conf."""
    conf_path = Path(f"./{CONF_FILE_NAME}")
    if not conf_path.is_file():
        return {} # Devuelve un diccionario vacío si no existe
    try:
        with conf_path.open('r', encoding='utf-8') as f:
            config = json5.load(f)
        print(f"[*] Archivo de configuración '{CONF_FILE_NAME}' cargado.")
        return config
    except Exception:
        return {}


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
    elif filepath:
        # Si no hay datos, leer desde el archivo
        try:
            with filepath.open('r', encoding='utf-8') as f:
                song_data = json5.load(f)
        except Exception as e:
            print(f"Error: No se pudo leer o parsear el archivo '{filepath.name}': {e}")
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

    # print(f"[*] Canción '{song_state.song_name}' cargada. ({len(song_state.parts)} partes)")
    return True


def load_song_from_playlist(song_index: int):
    """Carga una canción específica de la playlist activa y envía notificaciones."""
    global ui_feedback_message
    if not playlist_state.is_active or not (0 <= song_index < len(playlist_state.playlist_elements)):
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
            ui_feedback_message = f"[!] Error: Archivo '{element['filepath']}' no encontrado."
            # Intentar cargar la siguiente canción de forma segura
            # NOTA: Esto podría causar un bucle si todos los archivos faltan.
            # Por ahora, es un comportamiento aceptable para la recuperación de errores.
            return load_song_from_playlist(song_index + 1)
        
        try:
            with song_path.open('r', encoding='utf-8') as f:
                song_data_to_load = json5.load(f)
            # Sobrescribir el nombre si está definido dentro del archivo
            if "song_name" in song_data_to_load:
                song_name_for_osc = song_data_to_load["song_name"]
        except Exception as e:
            ui_feedback_message = f"[!] Error al leer '{element['filepath']}': {e}"
            return False
            
    elif "parts" in element:
        song_data_to_load = element
        song_name_for_osc = song_data_to_load.get("song_name", "Canción Incrustada")
    else:
        ui_feedback_message = f"[!] Error: Elemento de playlist en índice {song_index} es inválido."
        return False


    # Enviar notificaciones ANTES de la carga completa en el estado global.
    send_midi_song_select(song_index)
    send_osc_song_change(song_index, song_name_for_osc)

    # Ahora, cargar la canción en el estado global
    if not load_song_file(data=song_data_to_load):
        return False

    return True


def reset_song_state_on_stop():
    """Resetea el estado de la secuencia cuando el reloj se detiene."""
    # print("DEBUG: reset_song_state_on_stop -> Reseteando contadores de canción")
    song_state.current_part_index = -1
    song_state.remaining_beats_in_part = 0
    song_state.pass_count = 0
    song_state.midi_clock_tick_counter = 0
    song_state.current_bar_in_part = 0
    clock_state.tick_times = []
    clock_state.bpm = 0.0

def setup_part(part_index):
    """Configura una parte específica para la reproducción y envía mensajes."""
    if not (0 <= part_index < len(song_state.parts)):
        return # Salida segura si el índice no es válido

    song_state.current_part_index = part_index
    part = song_state.parts[part_index]
    song_state.remaining_beats_in_part = part.get("bars", 0) * song_state.time_signature_numerator
    song_state.current_bar_in_part = 0
    
    send_osc_part_change(song_state.song_name, song_state.current_part_index, part)
    send_midi_program_change(part_index) 

    # Si una parte válida tiene 0 compases, la saltamos para evitar bucles infinitos
    if song_state.remaining_beats_in_part <= 0:
        start_next_part()



def start_next_part():
    """La lógica principal para determinar qué parte de la canción reproducir a continuación."""
    # Encuentra el siguiente índice válido partiendo del estado actual
    next_index, next_pass_count = find_next_valid_part_index(
        "+1", song_state.current_part_index, song_state.pass_count
    )
    
    if next_index is None:
        # No hay más partes válidas para reproducir
        handle_song_end()
    else:
        # Aplicar el nuevo estado de pase y configurar la parte
        song_state.pass_count = next_pass_count
        setup_part(next_index)


def process_song_tick():
    """Llamado en cada "beat" de la canción (definido por time_division)."""
    global beat_flash_end_time
    if clock_state.status != "PLAYING":
        return
    
    # Comprobar si hay un salto pendiente y si se debe ejecutar ahora
    jump_executed = check_and_execute_pending_action()

    # Si NO se ejecutó un salto, proceder con la cuenta atrás normal.
    if not jump_executed:
        song_state.remaining_beats_in_part -= 1
    
        # Lógica de fin de compás
        sig_num = song_state.time_signature_numerator
        # Evitar error si la parte no tiene 'bars' (aunque setup_part ya lo filtra)
        current_part = song_state.parts[song_state.current_part_index]
        total_beats_in_part = current_part.get("bars", 0) * sig_num
        beats_into_part = total_beats_in_part - song_state.remaining_beats_in_part

        # Comprobar si se ha completado un compás
        if beats_into_part > 0 and beats_into_part % sig_num == 0:
            # Actualizar el contador de compases completados
            song_state.current_bar_in_part = beats_into_part // sig_num
            
            # Llamar a la función que enviará los mensajes OSC
            send_osc_bar_triggers(song_state.current_bar_in_part)
            
            # Activar flash visual en el primer beat del siguiente compás
            if song_state.remaining_beats_in_part > 0:
                beat_flash_end_time = time.time() + 0.1

        # Comprobar si la parte ha terminado
        if song_state.remaining_beats_in_part <= 0:
            start_next_part()
# ----------------------------------------------------

# --- Dynamic Part-Jumping Logic ---

def find_next_valid_part_index(direction: str, start_index: int, start_pass_count: int):
    """Encuentra el índice y el pass_count de la siguiente parte válida."""
    if not song_state.parts:
        return None, None

    # --- Lógica para MODO CANCIÓN (Lineal) ---
    if repeat_override_active:
        step = 1 if direction == "+1" else -1
        next_index = start_index + step
        
        # Comprobar si el nuevo índice está dentro de los límites de la canción actual
        if 0 <= next_index < len(song_state.parts):
            # Si la parte existe, es válida en Song Mode (siempre que tenga compases)
            if song_state.parts[next_index].get("bars", 0) > 0:
                # El pass_count no cambia en modo lineal
                return next_index, start_pass_count
        
        # Si el índice está fuera de los límites, la canción ha terminado
        return None, None

    # --- Lógica para MODO LOOP (Normal) ---
    temp_index = start_index
    temp_pass_count = start_pass_count
    step = 1 if direction == "+1" else -1

    for _ in range(len(song_state.parts) * 2): # Bucle de seguridad
        temp_index += step

        if temp_index >= len(song_state.parts):
            temp_index = 0
            temp_pass_count += 1
        elif temp_index < 0:
            temp_index = len(song_state.parts) - 1
            temp_pass_count = max(0, temp_pass_count - 1)

        part = song_state.parts[temp_index]
        play_this_part = False
        
        pattern = part.get("repeat_pattern")
        if pattern is None or pattern is True:
            play_this_part = True
        elif pattern is False:
            if temp_pass_count == 0: play_this_part = True
        elif isinstance(pattern, list) and pattern:
            if pattern[temp_pass_count % len(pattern)]: play_this_part = True

        if play_this_part and part.get("bars", 0) > 0:
            return temp_index, temp_pass_count

    return None, None


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
    
    # Determinar si fue un salto relativo hacia atrás
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

    # Asegurarse de que el índice esté dentro de los límites de la playlist
    if not (0 <= final_index < len(playlist_state.playlist_elements)):
        ui_feedback_message = f"Salto a canción {final_index + 1} inválido (fuera de rango)."
        pending_action = None
        return

    if load_song_from_playlist(final_index):
        reset_song_state_on_stop()
        
        # Empezar por el final SÓLO si fue un salto relativo hacia atrás
        if is_relative_backwards_jump:
            start_search_index = len(song_state.parts)
            target_part_index, target_pass_count = find_next_valid_part_index(
                "-1", start_search_index, 0
            )
            if target_part_index is not None:
                song_state.pass_count = target_pass_count
                setup_part(target_part_index)
            else:
                handle_song_end() # La canción no tiene partes válidas
        else:
            # Para todos los demás casos (Inicio, Fin, PgDn, restart), empezar por el principio
            start_next_part()
    else:
        ui_feedback_message = f"Salto a canción {final_index + 1} inválido (error de carga)."

    pending_action = None

def execute_pending_action():
    """Inspecciona la acción pendiente y decide si es un salto de parte o de canción."""
    if not pending_action:
        return

    if pending_action.get("target_type") == "global_part":
        execute_global_part_jump()
    elif pending_action.get("target_type") == "song":
        execute_song_jump()
    else:
        execute_part_jump()



def check_and_execute_pending_action():
    """
    Verifica si se cumplen las condiciones de cuantización para ejecutar una acción.
    Devuelve True si se ejecutó una acción, False en caso contrario.
    """
    if not pending_action or clock_state.status != "PLAYING":
        return False

    # Usa la cuantización dinámica si es un salto de cue, si no, la normal.
    quantize = pending_action.get("dynamic_quantize") or pending_action.get("quantize")
    
    
    # Contexto musical actual
    sig_num = song_state.time_signature_numerator
    total_beats_in_part = song_state.parts[song_state.current_part_index].get("bars", 0) * sig_num
    beats_into_part = total_beats_in_part - song_state.remaining_beats_in_part
    current_bar = beats_into_part // sig_num
    is_last_beat_of_bar = (song_state.remaining_beats_in_part % sig_num == 1)

    should_jump = False
    if quantize == "instant":
        should_jump = True
    # --- AÑADIR ESTE NUEVO ELIF ---
    elif quantize == "end_of_part":
        # Se ejecuta justo en el último beat de la parte
        if song_state.remaining_beats_in_part == 1:
            should_jump = True
    # -----------------------------
    elif quantize == "next_bar" and is_last_beat_of_bar:
        should_jump = True
    elif quantize == "next_4" and is_last_beat_of_bar and (current_bar + 1) % 4 == 0:
        should_jump = True
    elif quantize == "next_8" and is_last_beat_of_bar and (current_bar + 1) % 8 == 0:
        should_jump = True
    elif quantize == "next_16" and is_last_beat_of_bar and (current_bar + 1) % 16 == 0:
        should_jump = True
    elif quantize == "next_32" and is_last_beat_of_bar and (current_bar + 1) % 32 == 0:
        should_jump = True

    if should_jump:
        execute_pending_action()
        return True

    return False


def midi_input_listener():
    """El hilo principal que escucha los mensajes MIDI y actualiza el estado."""
    global midi_input_port, clock_state, song_state
    
    # Un puerto es compartido si el puerto de control se ha asignado al de entrada.
    is_shared_port = midi_control_port is not None and midi_control_port is midi_input_port

    while not SHUTDOWN_FLAG:
        if not midi_input_port:
            time.sleep(0.1)
            continue

        msg = midi_input_port.poll()
        if not msg:
            time.sleep(0.001)
            continue

        # --- Lógica de Clock ---
        if msg.type == 'start':
            # print("DEBUG: midi_input_listener (start) -> cambiando estado a PLAYING")
            clock_state.status = "PLAYING"
            clock_state.start_time = time.time()
            reset_song_state_on_stop()
            start_next_part()
        elif msg.type == 'stop':
            # print("DEBUG: midi_input_listener (stop) -> cambiando estado a STOPPED")    
            clock_state.status = "STOPPED"
            clock_state.start_time = 0
            reset_song_state_on_stop()
        elif msg.type == 'continue':
            # print("DEBUG: midi_input_listener (continue) -> cambiando estado a PLAYING")
            clock_state.status = "PLAYING"
        elif msg.type == 'clock':
            if clock_state.status == "STOPPED":
                # print("DEBUG: midi_input_listener (clock) -> cambiando estado a PLAYING")
                clock_state.status = "PLAYING"
                print("Info: Clock detectado. Sincronizando estado a PLAYING.")
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



def trigger_cue_jump(cue_num: int):
    """
    Gestiona la lógica para disparar un salto a un Cue, incluyendo la
    cuantización dinámica si se dispara repetidamente.
    """
    global pending_action, ui_feedback_message

    target_part_index = None
    for index, part in enumerate(song_state.parts):
        if part.get("cue") == cue_num:
            target_part_index = index
            break
    
    if target_part_index is None:
        ui_feedback_message = f"Cue {cue_num} no encontrado en esta canción."
        return

    part_name = song_state.parts[target_part_index].get("name", "N/A")

    # Comprobar si ya hay una acción pendiente para este mismo cue
    if (pending_action and 
        pending_action.get("target_type") == "cue_jump" and
        pending_action.get("cue_num") == cue_num):
        
        # Acelerar la cuantización existente
        new_quantize = halve_quantization(pending_action["dynamic_quantize"])
        pending_action["dynamic_quantize"] = new_quantize
        ui_feedback_message = f"Cue {cue_num} ({part_name}) acelerado a {new_quantize.upper()}."

    else:
        # Crear una nueva acción de salto a cue
        pending_action = {
            "target_type": "cue_jump",
            "target": target_part_index,
            "cue_num": cue_num,
            "dynamic_quantize": quantize_mode # Empezar con la cuantización global
        }
        ui_feedback_message = f"Ir a Cue {cue_num}: {part_name}"



def process_control_message(msg):
    """Procesa un único mensaje de control MIDI (PC, CC, Note, Song Select)."""
    global pending_action, quantize_mode, ui_feedback_message, repeat_override_active
    
    if msg.type == 'program_change':
        # Los saltos de parte siempre son cuantizados y solo tienen sentido si se está reproduciendo
        if clock_state.status == "PLAYING":
            pending_action = {"target": msg.program, "quantize": quantize_mode}
            ui_feedback_message = f"PC Recibido: Ir a parte {msg.program + 1}."
        else:
            ui_feedback_message = "PC ignorado (reproducción detenida)."

    elif msg.type == 'song_select':
        if playlist_state.is_active:
            action = {"target_type": "song", "target": msg.song, "quantize": quantize_mode}
            trigger_song_jump(action)
            ui_feedback_message = f"Song Select: Ir a canción {msg.song + 1}."
        else:
            ui_feedback_message = "Song Select ignorado (no hay playlist activa)."

    elif msg.type == 'note_on':
        if msg.note in [124, 125]: # Saltos de PARTE
            if clock_state.status == "PLAYING":
                value = 1 if msg.note == 125 else -1
                target = {"type": "relative", "value": value}
                pending_action = {"target": target, "quantize": quantize_mode}
                ui_feedback_message = f"Note Recibido: {'Siguiente' if value == 1 else 'Anterior'} Parte."
            else:
                ui_feedback_message = "Note On (Part Jump) ignorado (reproducción detenida)."
        
        elif msg.note in [126, 127]: # Saltos de CANCIÓN
            if not playlist_state.is_active:
                ui_feedback_message = "Note On (Song Jump) ignorado (no hay playlist activa)."
                return
            value = 1 if msg.note == 127 else -1
            target = {"type": "relative", "value": value}
            action = {"target_type": "song", "target": target, "quantize": quantize_mode}
            trigger_song_jump(action)
            ui_feedback_message = f"Note Recibido: {'Siguiente' if value == 1 else 'Anterior'} Canción."

    elif msg.type == 'control_change' and msg.control == 1:
        if not playlist_state.is_active:
            ui_feedback_message = "CC#1 ignorado (no hay playlist activa)."
            return

        target_song_idx, target_part_idx = resolve_global_part_index(msg.value)

        if target_song_idx is not None:
            pending_action = {
                "target_type": "global_part",
                "target_song": target_song_idx,
                "target_part": target_part_idx,
                "quantize": quantize_mode
            }
            ui_feedback_message = f"CC#1 Recibido: Ir a parte global {msg.value + 1}."
        else:
            ui_feedback_message = f"CC#1 Error: Parte global {msg.value + 1} no existe."

    elif msg.type == 'control_change' and msg.control == 2:
        trigger_cue_jump(msg.value)

    elif msg.type == 'control_change' and msg.control == 0:
        val = msg.value
        # Saltos rápidos (cuantización fija)
        if 0 <= val <= 3:
            quant_map = {0: "instant", 1: "next_bar", 2: "next_8", 3: "next_16"}
            quant = quant_map.get(val, "next_bar")
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quant}
            ui_feedback_message = f"CC#0 Recibido: Salto rápido (Quant: {quant.upper()})."
        # Selección de modo de cuantización global
        elif val in [4, 5, 6, 7, 8, 9]:
            quant_map = {4: "next_4", 5: "next_8", 6: "next_16", 7: "next_bar", 8: "end_of_part", 9: "instant"}
            quantize_mode = quant_map[val]
            ui_feedback_message = f"CC#0 Recibido: Modo global -> {quantize_mode.upper()}."
        # Navegación de PARTE (cuantización global)
        elif val == 10: # Saltar Parte Anterior
            target = {"type": "relative", "value": -1}
            pending_action = {"target": target, "quantize": quantize_mode}
            ui_feedback_message = "CC#0 Recibido: Saltar Parte Anterior."
        elif val == 11: # Saltar Parte Siguiente
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quantize_mode}
            ui_feedback_message = "CC#0 Recibido: Saltar Parte Siguiente."
        elif 12 <= val <= 19:
            if val in [12, 13, 14, 15, 16] and not playlist_state.is_active:
                ui_feedback_message = f"CC#0({val}) ignorado (no hay playlist activa)."
                return
            
            action = {}
            if val == 12: # Canción Anterior
                target = {"type": "relative", "value": -1}
                action = {"target_type": "song", "target": target, "quantize": quantize_mode}
                ui_feedback_message = "CC#0 Recibido: Canción Anterior."
            elif val == 13: # Siguiente Canción
                target = {"type": "relative", "value": 1}
                action = {"target_type": "song", "target": target, "quantize": quantize_mode}
                ui_feedback_message = "CC#0 Recibido: Siguiente Canción."
            elif val == 14: # Ir a Primera Canción
                action = {"target_type": "song", "target": 0, "quantize": quantize_mode}
                ui_feedback_message = "CC#0 Recibido: Ir a Primera Canción."
            elif val == 15: # Ir a Última Canción
                last_song_index = len(playlist_state.playlist_elements) - 1
                action = {"target_type": "song", "target": last_song_index, "quantize": quantize_mode}
                ui_feedback_message = "CC#0 Recibido: Ir a Última Canción."
            elif val == 16: # Reiniciar Canción
                action = {"target_type": "song", "target": "restart", "quantize": quantize_mode}
                ui_feedback_message = "CC#0 Recibido: Reiniciar Canción."

            if action:
                trigger_song_jump(action)
                return

            if val == 17: # Reiniciar Parte
                if clock_state.status == "PLAYING":
                    pending_action = {"target": "restart", "quantize": quantize_mode}
                    ui_feedback_message = "CC#0 Recibido: Reiniciar Parte."
                else:
                    ui_feedback_message = "CC#0(17) ignorado (reproducción detenida)."
            elif val == 18: # Cancelar Acción
                if pending_action:
                    pending_action = None
                    ui_feedback_message = "CC#0 Recibido: Acción cancelada."
            elif val == 19: # Toggle Mode
                repeat_override_active = not repeat_override_active
                mode_str = "Song Mode" if repeat_override_active else "Loop Mode"
                ui_feedback_message = f"CC#0 Recibido: Modo cambiado a {mode_str}"


def midi_control_listener():
    """El hilo que escucha los mensajes MIDI de control (en un puerto dedicado)."""
    while not SHUTDOWN_FLAG:
        if not midi_control_port:
            time.sleep(0.1)
            continue

        msg = midi_control_port.poll()
        if not msg:
            time.sleep(0.001)
            continue
        
        process_control_message(msg)


def send_midi_command(command: str):
    """Envía un comando MIDI a todos los puertos de salida."""
    global ui_feedback_message
    # print(f"DEBUG: handle_song_end -> cambiando estado a FINISHED")
    if not midi_output_ports:
        ui_feedback_message = "[!] No hay puerto de control remoto configurado."
        return
    try:
        msg = mido.Message(command)
        for port in midi_output_ports:
            port.send(msg)
            ui_feedback_message = f"[!] '{command}' sent to '{port.name}'."
    except Exception as e:
        ui_feedback_message = f"Error sending MIDI: {e}"


def send_midi_program_change(part_index: int):
    """Envía un mensaje de Program Change si el puerto está configurado."""
    if not pc_output_port:
        return
    try:
        # El índice de la parte se usa directamente como el número del program change
        msg = mido.Message('program_change', channel=pc_channel, program=part_index)
        pc_output_port.send(msg)
    except Exception as e:
        global ui_feedback_message
        ui_feedback_message = f"Error enviando PC: {e}"

def send_midi_song_select(song_index: int):
    """Envía un mensaje de Song Select si el puerto de PC está configurado."""
    if not pc_output_port:
        return
    try:
        msg = mido.Message('song_select', song=song_index)
        pc_output_port.send(msg)
    except Exception as e:
        global ui_feedback_message
        ui_feedback_message = f"Error enviando Song Select: {e}"

def send_osc_song_end():
    """Construye y envía un mensaje OSC cuando la canción termina."""
    if not osc_client or not osc_config:
        return
    
    address = osc_config.get("address_song_end")
    if not address:
        return # No se envía nada si la dirección no está configurada

    try:
        builder = osc_message_builder.OscMessageBuilder(address=address)
        builder.add_arg(song_state.song_name, 's')
        msg = builder.build()
        osc_client.send(msg)
    except Exception as e:
        global ui_feedback_message
        ui_feedback_message = f"Error enviando OSC de fin: {e}"


def handle_song_end():
    """
    Gestiona el final de la secuencia de una canción.
    Si hay una playlist, intenta cargar la siguiente canción.
    Si no, finaliza la reproducción.
    """
    global ui_feedback_message

    # Primero, enviar notificación de que la canción actual ha terminado
    send_osc_song_end()

    if playlist_state.is_active:
        next_song_index = playlist_state.current_song_index + 1
        if next_song_index < len(playlist_state.playlist_elements):
            # --- LÓGICA DE MENSAJE MODIFICADA ---
            # Obtener el nombre de la siguiente canción para el mensaje
            next_song_element = playlist_state.playlist_elements[next_song_index]
            next_song_name = "Siguiente Canción"
            if "filepath" in next_song_element:
                next_song_name = Path(next_song_element["filepath"]).stem
            elif "song_name" in next_song_element:
                next_song_name = next_song_element["song_name"]
            
            ui_feedback_message = f"Iniciando '{next_song_name}'..."



            if load_song_from_playlist(next_song_index):
                # Si la carga fue exitosa, iniciar la nueva canción
                start_next_part()
            else:
                # La carga falló, así que detenemos todo
                clock_state.status = "FINISHED"
                send_midi_command('stop')
                reset_song_state_on_stop()
                ui_feedback_message = "Error al cargar la siguiente canción. Reproducción detenida."
        else:
            # Era la última canción de la playlist
            clock_state.status = "FINISHED"
            send_midi_command('stop')
            reset_song_state_on_stop()
            ui_feedback_message = f"Playlist '{playlist_state.playlist_name}' finalizada."
    else:
        # No hay playlist, comportamiento normal
        clock_state.status = "FINISHED"
        send_midi_command('stop')
        reset_song_state_on_stop()
        ui_feedback_message = f"Canción '{song_state.song_name}' finalizada."


def send_osc_part_change(song_name: str, part_index: int, part: dict):
    """Construye y envía un mensaje OSC cuando cambia una parte."""
    if not osc_client:
        return

    try:
        # Construir el mensaje con los argumentos: (string) name, (int) bars, (int) index
        builder = osc_message_builder.OscMessageBuilder(address=osc_address)
        builder.add_arg(song_name, 's')
        builder.add_arg(part.get("name", "N/A"), 's')
        builder.add_arg(part.get("bars", 0), 'i')
        builder.add_arg(part_index, 'i')
        msg = builder.build()
        
        osc_client.send(msg)
    except Exception as e:
        # Actualizar el feedback de la UI si hay un error OSC
        global ui_feedback_message
        ui_feedback_message = f"Error sending OSC: {e}"

def send_osc_song_change(song_index: int, song_name: str):
    """Construye y envía un mensaje OSC cuando cambia una canción."""
    if not osc_client or not osc_config:
        return
    
    address = osc_config.get("address_song_change")
    if not address:
        return # No se envía nada si la dirección no está configurada

    try:
        builder = osc_message_builder.OscMessageBuilder(address=address)
        builder.add_arg(song_name, 's')
        builder.add_arg(song_index, 'i')
        msg = builder.build()
        osc_client.send(msg)
    except Exception as e:
        global ui_feedback_message
        ui_feedback_message = f"Error enviando OSC de cambio de canción: {e}"

def send_osc_bar_triggers(completed_bar_number: int):
    """Comprueba y envía mensajes OSC para los contadores de compases/bloques."""
    if not osc_client or not osc_config:
        return

    bar_triggers = osc_config.get("bar_triggers", [])
    if not bar_triggers:
        return

    for trigger in bar_triggers:
        block_size = trigger.get("block_size")
        address = trigger.get("address")

        if not block_size or not address or block_size <= 0:
            continue # Ignorar triggers mal configurados

        if completed_bar_number % block_size == 0:
            try:
                # Calcular el número de bloque (ej. compás 8 con block_size 4 es el bloque 2)
                block_number = completed_bar_number // block_size
                
                builder = osc_message_builder.OscMessageBuilder(address=address)
                builder.add_arg(completed_bar_number, 'i') # Compás actual en la parte
                builder.add_arg(block_number, 'i')         # Número de bloque
                msg = builder.build()
                osc_client.send(msg)
            except Exception as e:
                global ui_feedback_message
                ui_feedback_message = f"Error enviando OSC trigger: {e}"


def get_feedback_text():
    """Muestra el último mensaje de feedback en la UI."""
    return HTML(f"<style fg='#888888'>{ui_feedback_message}</style>")


def get_action_status_text():
    """Muestra el modo de cuantización, la acción pendiente y el estado de repetición."""
    global ui_feedback_message
    quant_str = quantize_mode.replace("_", " ").upper()
    
    action_str = "Ø"
    if pending_action:
        quant = (pending_action.get("dynamic_quantize") or pending_action.get("quantize", "")).replace("_", " ").upper()
        
        # --- Lógica para determinar el texto de la acción pendiente ---

        # 1. Salto de Cue
        if pending_action.get("target_type") == "cue_jump":
            target_index = pending_action.get("target")
            part_name = song_state.parts[target_index].get("name", "N/A")
            action_str = f"Go to: {part_name} ({quant})"

        # 2. Salto a Parte Global
        elif pending_action.get("target_type") == "global_part":
            song_idx = pending_action.get("target_song")
            part_idx = pending_action.get("target_part")
            song_element = playlist_state.playlist_elements[song_idx]
            parts = _get_parts_from_playlist_element(song_element)
            
            song_name = song_element.get("song_name", Path(song_element.get("filepath", "N/A")).stem)
            part_name = parts[part_idx].get("name", "N/A") if part_idx < len(parts) else "N/A"
            
            action_str = f"Go to Global Part: {html.escape(song_name)} - {html.escape(part_name)} ({quant})"

        # 3. Salto de Canción
        elif pending_action.get("target_type") == "song":
            target = pending_action.get("target")
            target_song_idx = playlist_state.current_song_index
            
            if isinstance(target, int):
                target_song_idx = target
            elif isinstance(target, dict) and target.get("type") == "relative":
                target_song_idx += target.get("value", 0)
            
            if 0 <= target_song_idx < len(playlist_state.playlist_elements):
                element = playlist_state.playlist_elements[target_song_idx]
                song_name = element.get("song_name", Path(element.get("filepath", "N/A")).stem)
                action_str = f"Go to Song: {html.escape(song_name)} ({quant})"
            else:
                action_str = "Jump to End of Setlist"

        # 4. Salto de Parte (Normal)
        else:
            target = pending_action.get("target")
            part_name = ""
            if isinstance(target, dict) and target.get("type") == "relative":
                value = target.get("value", 0)
                if value != 0:
                    direction = "+1" if value > 0 else "-1"
                    final_index, _ = find_next_valid_part_index(direction, song_state.current_part_index, song_state.pass_count)
                    if final_index is None:
                        part_name = "End"
                    else:
                        part_name = song_state.parts[final_index].get('name', 'N/A')
                    prefix = "Jump to" if value > 0 else "Jump back to"
                    action_str = f"{prefix} ({value:+}): {part_name} ({quant})"
                else:
                    action_str = "Cancelled"

            elif target == "restart":
                part_name = song_state.parts[song_state.current_part_index].get('name', 'N/A')
                action_str = f"Restart: {part_name} ({quant})"
            elif isinstance(target, int):
                if 0 <= target < len(song_state.parts):
                    part_name = song_state.parts[target].get('name', 'N/A')
                action_str = f"Go to: {part_name} ({quant})"
    
    if goto_input_active:
        ui_feedback_message = ""
        return HTML(f"<style bg='ansiyellow' fg='ansiblack'>Ir a Parte: {goto_input_buffer}_</style>")

    quant_part = f"<b>Quant:</b> <style bg='#333333'>[{quant_str}]</style>"
    action_part = f"<b>Pending Action:</b> <style bg='#333333'>[{html.escape(action_str)}]</style>"
    
    repeat_part = ""
    if repeat_override_active:
        repeat_part = " | <style fg='ansigreen' bold='true'>Song Mode</style>"
    else:
        repeat_part = " | <style fg='ansiblue' bold='true'>Loop Mode</style>"

    return HTML(f"{quant_part} | {action_part}{repeat_part}")

def get_key_legend_text():
    """Muestra la leyenda de los controles de teclado."""
    line1 = "<b>[←→:</b> Part Nav] <b>[↑:</b> Restart Part] <b>[↓:</b> Cancel] <b>[PgUp/PgDn:</b> Song Nav]"
    line2 = "<b>[r:</b> Mode] <b>[.:</b> Goto] <b>[0-3:</b> Q-Jump] <b>[4-9:</b> Set Quant]"
    return HTML(f"<style fg='#666666'>{line1}\n{line2}</style>")

# --- UI Functions ---
def get_part_name_text():
    """Genera el bloque de encabezado completo."""
    
    # --- Línea 1: Estado ---
    app_name = "miditema".ljust(14)
    status = clock_state.status.ljust(10)
    elapsed_str = "--:--"
    if clock_state.start_time > 0 and clock_state.status != "FINISHED":
        elapsed_seconds = time.time() - clock_state.start_time
        minutes, seconds = divmod(int(elapsed_seconds), 60)
        elapsed_str = f"{minutes:02d}:{seconds:02d}"
    bpm = f"{clock_state.bpm:.0f} BPM".ljust(12)
    source = f"Clock: {clock_state.source_name}"
    status_text = f"{app_name} | {status} | {elapsed_str} | {bpm} | {source}"
    status_line = f"<style fg='ansiwhite'>{status_text.center(80)}</style>"

    # --- Línea 2: Título de la Canción ---
    song_color_name = song_state.song_color
    song_style_str = TITLE_COLOR_PALETTE.get(song_color_name, "bg='#aaaaaa' fg='ansiblack'")
    safe_song_name = html.escape(song_state.song_name)
    centered_song_name = safe_song_name.center(80)
    final_title_str = centered_song_name

    if playlist_state.is_active:
        current = playlist_state.current_song_index + 1
        total = len(playlist_state.playlist_elements)
        playlist_prefix = f"[{current}/{total}] "
        # Convertir a lista de caracteres para poder modificarla
        title_chars = list(centered_song_name)
        # Sobrescribir los primeros caracteres con el prefijo
        for i in range(len(playlist_prefix)):
            if i < len(title_chars):
                title_chars[i] = playlist_prefix[i]
        
        final_title_str = "".join(title_chars)

    song_title_line = f"<style {song_style_str} bold='true'>{final_title_str}</style>"


    part_info_str = "---".center(80)
    part_to_display = None
    part_style_str = TITLE_COLOR_PALETTE['default']
    
    # Determinar qué parte mostrar (la actual o la primera como preview)
    part_index_to_show = song_state.current_part_index
    if part_index_to_show == -1 and song_state.parts:
        part_index_to_show = 0
        
    if part_index_to_show != -1:
        part_to_display = song_state.parts[part_index_to_show]
        
        name = part_to_display.get('name', '---')
        bars = part_to_display.get('bars', 0)
        total_parts = len(song_state.parts)
        
        safe_part_name = html.escape(name)
        centered_part_name = safe_part_name.center(80)
        
        final_part_title_str = centered_part_name
        
        # 2. Crear el prefijo y sobrescribirlo al principio
        part_prefix = f"[{part_index_to_show + 1}/{total_parts}] {bars} "
        
        title_chars = list(centered_part_name)
        for i in range(len(part_prefix)):
            if i < len(title_chars):
                title_chars[i] = part_prefix[i]
        
        final_part_title_str = "".join(title_chars)
        
        color_name = part_to_display.get('color')
        part_style_str = TITLE_COLOR_PALETTE.get(color_name, TITLE_COLOR_PALETTE['default'])
        part_info_str = final_part_title_str

    part_name_line = f"<style {part_style_str} bold='true'>{part_info_str}</style>"

    # --- Líneas 4 y 5: Nueva tabla de información ---
    col_width = 12
    header_song = "Song".center(col_width)
    header_part = "Part".center(col_width)
    header_bar = "Bar".center(col_width)
    table_header = f"{header_song}|{header_part}|{header_bar}"
    
    song_index_str = "--/--"
    if playlist_state.is_active:
        song_index_str = f"{playlist_state.current_song_index + 1:02d}/{len(playlist_state.playlist_elements):02d}"
    
    part_index_str = "--/--"
    if song_state.parts:
        part_index_str = f"{song_state.current_part_index + 1:02d}/{len(song_state.parts):02d}"

    bar_str = "--/--"
    if song_state.current_part_index != -1:
        part = song_state.parts[song_state.current_part_index]
        total_bars = part.get("bars", 0)
        current_bar = song_state.current_bar_in_part
        display_bar = 0
        if clock_state.status == "PLAYING" and current_bar < total_bars:
            display_bar = current_bar + 1
        bar_str = f"{display_bar:02d}/{total_bars:02d}"

    value_song = song_index_str.center(col_width)
    value_part = part_index_str.center(col_width)
    value_bar = bar_str.center(col_width)
    table_values = f"{value_song}|{value_part}|{value_bar}"

    table_line_1 = f"<style fg='ansiwhite'>{table_header.center(80)}</style>"
    table_line_2 = f"<style fg='ansiwhite' bold='true'>{table_values.center(80)}</style>"


    return HTML(
        f"{status_line}\n"
        f"{song_title_line}\n"
        f"{part_name_line}\n"
        f"{table_line_1}\n"
        f"{table_line_2}"
    )


def get_dynamic_endpoint():
    """
    Calcula el compás final relevante, ya sea el final de la parte
    o el punto de ejecución de una acción pendiente.
    Devuelve el número del compás final (1-based).
    """
    if not pending_action or clock_state.status != "PLAYING" or song_state.current_part_index == -1:
        # Si no hay acción o no estamos en una parte válida, el final es el final real.
        if song_state.current_part_index != -1:
            return song_state.parts[song_state.current_part_index].get("bars", 0)
        return 0

    current_part = song_state.parts[song_state.current_part_index]
    total_bars_in_part = current_part.get("bars", 0)

    # Calcular la posición actual
    sig_num = song_state.time_signature_numerator
    beats_into_part = (total_bars_in_part * sig_num) - song_state.remaining_beats_in_part
    current_bar_index = beats_into_part // sig_num # 0-based

    # --- LÍNEA MODIFICADA ---
    # Busca la cuantización dinámica primero, si no, la normal.
    quantize = pending_action.get("dynamic_quantize") or pending_action.get("quantize")
    
    if quantize in ["instant", "next_bar", "end_of_part"]:
        # Para estos modos, el salto es inminente o al final.
        # "end_of_part" visualmente se comporta como el final de la parte.
        if quantize == "end_of_part":
            return total_bars_in_part
        return current_bar_index + 1
    
    quantize_map = {"next_4": 4, "next_8": 8, "next_16": 16, "next_32": 32}
    if quantize in quantize_map:
        boundary = quantize_map[quantize]
        # Calcula el próximo múltiplo de 'boundary' desde el compás actual
        target_bar = ((current_bar_index // boundary) + 1) * boundary
        return target_bar
    
    return total_bars_in_part # Fallback


def get_countdown_text():
    """Genera la cuenta atrás de compases con un fondo de ancho completo."""
    bar_text = "-0"
    beat_text = "0"
    style = "bg='#222222' fg='ansiwhite'"

    if clock_state.status == "PLAYING" and song_state.remaining_beats_in_part > 0:
        sig_num = song_state.time_signature_numerator
        rem_beats = song_state.remaining_beats_in_part
        
        endpoint_bar = get_dynamic_endpoint()
        
        total_beats_in_part = song_state.parts[song_state.current_part_index].get("bars", 0) * sig_num
        beats_into_part = total_beats_in_part - rem_beats
        current_bar_index = beats_into_part // sig_num
        
        remaining_bars_to_endpoint = endpoint_bar - current_bar_index
        
        display_beat = (rem_beats - 1) % sig_num + 1
        display_bar = -(remaining_bars_to_endpoint - 1)
        
        bar_text = f"{display_bar}"
        if remaining_bars_to_endpoint == 1: bar_text = "-0"
        beat_text = f"{display_beat}"

        if remaining_bars_to_endpoint == 1:
            style = "bg='#222222' fg='ansired' bold='true'"
        elif remaining_bars_to_endpoint <= 4:
            style = "bg='#222222' fg='ansiyellow' bold='true'"
    
    if time.time() < beat_flash_end_time:
        style = "bg='#cccccc' fg='ansiblack' bold='true'"

    countdown_str = f"{bar_text}<style fg='#888888'>.</style>{beat_text}"
     
    # Calcular padding izquierdo y derecho manualmente
    visible_len = len(bar_text) + 1 + len(beat_text)
    padding_left_len = (80 - visible_len) // 2
    padding_right_len = 80 - visible_len - padding_left_len
    
    padding_left = " " * padding_left_len
    padding_right = " " * padding_right_len
    
    # Construir la línea completa y aplicar el estilo
    full_line = f"{padding_left}{countdown_str}{padding_right}"
    
    return HTML(f"<style {style}>{full_line}</style>")



def _get_parts_from_playlist_element(element):
    """Devuelve la lista de partes de un elemento de la playlist, leyéndola si es necesario."""
    if "parts" in element:
        return element["parts"]
    if "filepath" in element:
        try:
            with (SONGS_DIR / element["filepath"]).open('r', encoding='utf-8') as f:
                data = json5.load(f)
                return data.get("parts", [])
        except Exception:
            return []
    return []


def get_next_part_text():
    """
    Muestra el destino de la acción pendiente (incluso a través de canciones), 
    o el siguiente paso natural si no hay acción.
    """
    global song_state
    if clock_state.status != "PLAYING":
        return ""

    raw_text = ""
    style_str = "fg='#888888'"

    if pending_action:
        target = pending_action.get("target")
        
        if pending_action.get("target_type") == "song":
            # --- PREDECIR SALTO DE CANCIÓN ---
            target_song_idx = playlist_state.current_song_index
            if isinstance(target, int):
                target_song_idx = target
            elif isinstance(target, dict) and target.get("type") == "relative":
                target_song_idx += target.get("value", 0)
            
            if 0 <= target_song_idx < len(playlist_state.playlist_elements):
                element = playlist_state.playlist_elements[target_song_idx]
                song_name = element.get("song_name", Path(element.get("filepath", "N/A")).stem)
                raw_text = f">> Próxima Canción: {html.escape(song_name)}"
                style_str = "fg='ansiyellow' bold='true'"
            else:
                raw_text = ">> Fin del Setlist"

        else: # --- PREDECIR SALTO DE PARTE (CON SIMULACIÓN COMPLEJA) ---
            final_part_data = None
            
            # Inicializar variables de simulación aquí para evitar UnboundLocalError
            sim_song_idx = playlist_state.current_song_index
            sim_part_idx = song_state.current_part_index
            sim_pass_count = song_state.pass_count

            if isinstance(target, dict) and target.get("type") == "relative":
                value = target.get("value", 0)
                if value != 0:
                    direction = "+1" if value > 0 else "-1"
                    for _ in range(abs(value)):
                        temp_song_state = SongState()
                        temp_song_state.parts = _get_parts_from_playlist_element(playlist_state.playlist_elements[sim_song_idx])
                        
                        original_song_state = song_state
                        song_state = temp_song_state
                        next_part_idx, next_pass_count = find_next_valid_part_index(direction, sim_part_idx, sim_pass_count)
                        song_state = original_song_state

                        if next_part_idx is not None:
                            sim_part_idx = next_part_idx
                            sim_pass_count = next_pass_count
                        else:
                            sim_song_idx += 1 if direction == "+1" else -1
                            if 0 <= sim_song_idx < len(playlist_state.playlist_elements):
                                next_song_parts = _get_parts_from_playlist_element(playlist_state.playlist_elements[sim_song_idx])
                                sim_part_idx = -1 if direction == "+1" else len(next_song_parts)
                                sim_pass_count = 0
                            else:
                                sim_song_idx = -1
                                break
                    
                    if sim_song_idx != -1:
                        final_parts = _get_parts_from_playlist_element(playlist_state.playlist_elements[sim_song_idx])
                        if sim_part_idx == -1 or sim_part_idx >= len(final_parts):
                            temp_song_state.parts = final_parts
                            original_song_state = song_state
                            song_state = temp_song_state
                            sim_part_idx, _ = find_next_valid_part_index(direction, sim_part_idx, sim_pass_count)
                            song_state = original_song_state
                        
                        if sim_part_idx is not None and 0 <= sim_part_idx < len(final_parts):
                            final_part_data = final_parts[sim_part_idx]

            elif target == "restart":
                final_part_data = song_state.parts[song_state.current_part_index]
            elif isinstance(target, int) and 0 <= target < len(song_state.parts):
                final_part_data = song_state.parts[target]

            if final_part_data:
                name = final_part_data.get('name', 'N/A')
                bars = final_part_data.get('bars', 0)
                raw_text = f">> {html.escape(name)} ({bars})"
                color_name = final_part_data.get('color', 'default')
                style_str = FG_COLOR_PALETTE.get(color_name, FG_COLOR_PALETTE['default'])
            else:
                raw_text = ">> Fin"

                
    if not raw_text:
        next_part_index, _ = find_next_valid_part_index("+1", song_state.current_part_index, song_state.pass_count)

        if next_part_index is not None:
            part = song_state.parts[next_part_index]
            name = part.get('name', 'N/A')
            bars = part.get('bars', 0)
            raw_text = f">> {html.escape(name)} ({bars})"
            color_name = part.get('color', 'default')
            style_str = FG_COLOR_PALETTE.get(color_name, FG_COLOR_PALETTE['default'])
        
        elif playlist_state.is_active:
            next_song_index = playlist_state.current_song_index + 1
            if next_song_index < len(playlist_state.playlist_elements):
                next_song_element = playlist_state.playlist_elements[next_song_index]
                song_name = next_song_element.get("song_name", Path(next_song_element.get("filepath", "N/A")).stem)
                raw_text = f">> Próxima Canción: {html.escape(song_name)}"
                style_str = "fg='ansiyellow' bold='true'"
            else:
                raw_text = ">> Fin del Setlist"
        else:
            raw_text = ">> Fin de la Canción"

    centered_text = raw_text.center(80)
    return HTML(f"<style {style_str}>{centered_text}</style>")


def get_step_sequencer_text():
    """Genera la representación visual de los compases con detección de conflicto de color."""
    FIXED_SEQUENCER_HEIGHT = 18

    if song_state.current_part_index == -1:
        return HTML("\n" * FIXED_SEQUENCER_HEIGHT)

    part = song_state.parts[song_state.current_part_index]
    total_bars = part.get("bars", 0)
    if total_bars == 0:
        return HTML("\n" * FIXED_SEQUENCER_HEIGHT)

    COMPACT_MODE_THRESHOLD = 32
    compact_mode = total_bars > COMPACT_MODE_THRESHOLD

    sig_num = song_state.time_signature_numerator
    consumed_beats = (total_bars * sig_num) - song_state.remaining_beats_in_part
    consumed_bars = consumed_beats // sig_num
    
    current_beat_in_bar = 0
    if clock_state.status == "PLAYING":
        beats_into_current_bar = consumed_beats % sig_num
        current_beat_in_bar = beats_into_current_bar + 1

    endpoint_bar = get_dynamic_endpoint() if pending_action else total_bars
    part_color_name = part.get('color')
    part_style = FG_COLOR_PALETTE.get(part_color_name, "fg='#888888'")

    output_lines = []
    content_width = 8 * 6
    padding = " " * ((80 - content_width) // 2)

    for row_start in range(0, total_bars, 8):
        line_content = ""
        is_active_row = (row_start <= consumed_bars < row_start + 8)

        for i in range(row_start, min(row_start + 8, total_bars)):
            bar_index_0based = i
            
            block_style = part_style
            if bar_index_0based < consumed_bars or (pending_action and bar_index_0based >= endpoint_bar):
                block_style = "fg='#222222'"

            block = ""
            if bar_index_0based == consumed_bars and clock_state.status == "PLAYING":
                # --- Lógica de Detección de Conflicto de Color ---
                progress_style = "fg='#555555'" # Progreso por defecto: gris claro
                intended_progress_color_name = None

                remaining_bars_to_endpoint = endpoint_bar - bar_index_0based
                if remaining_bars_to_endpoint == 1:
                    intended_progress_color_name = 'red'
                elif remaining_bars_to_endpoint <= 4:
                    intended_progress_color_name = 'yellow'

                # Comprobar si el color de la parte y el del progreso chocan
                if part_color_name == intended_progress_color_name:
                    progress_style = "fg='#cccccc' bold='true'" # Fallback: gris oscuro
                elif intended_progress_color_name is not None:
                    progress_style = FG_COLOR_PALETTE[intended_progress_color_name]
                # ----------------------------------------------------

                for beat in range(1, sig_num + 1):
                    if beat <= current_beat_in_bar:
                        block += f"<style {progress_style}>█</style>"
                    else:
                        block += f"<style {block_style}>█</style>"
                block += "  "
            else:
                block = f"<style {block_style}>████  </style>"

            line_content += block
        
        # Lógica de renderizado de fila
        output_lines.append(padding + line_content)
        
        if is_active_row or not compact_mode:
            output_lines.append(padding + line_content)

        if row_start + 8 < total_bars:
            output_lines.append("")
    
    # Lógica de Altura Fija
    if len(output_lines) > FIXED_SEQUENCER_HEIGHT:
        output_lines = output_lines[:FIXED_SEQUENCER_HEIGHT]
    else:
        while len(output_lines) < FIXED_SEQUENCER_HEIGHT:
            output_lines.append("")
            
    return HTML("\n".join(output_lines))


def get_status_line_text():
    app_name = "miditema".ljust(14)
    status = clock_state.status.ljust(10)
    
    elapsed_str = "--:--"
    if clock_state.start_time > 0 and clock_state.status != "FINISHED":
        elapsed_seconds = time.time() - clock_state.start_time
        minutes, seconds = divmod(int(elapsed_seconds), 60)
        elapsed_str = f"{minutes:02d}:{seconds:02d}"
    
    bpm = f"{clock_state.bpm:.0f} BPM".ljust(12)
    source = f"Clock: {clock_state.source_name}"

    return HTML(f"{app_name} | {status} | {elapsed_str} | {bpm} | {source}")

# --- UI Interactive Selectors ---
def interactive_selector(items, prompt_title):
    """Implementación de un selector interactivo genérico."""
    if not items: return None
    
    current_selection_index = 0
    kb = KeyBindings()

    @kb.add('c-c', eager=True)
    @kb.add('q', eager=True)
    def _(event): event.app.exit(result=None)

    @kb.add('up', eager=True)
    def _(event):
        nonlocal current_selection_index
        current_selection_index = (current_selection_index - 1 + len(items)) % len(items)

    @kb.add('down', eager=True)
    def _(event):
        nonlocal current_selection_index
        current_selection_index = (current_selection_index + 1) % len(items)

    @kb.add('enter', eager=True)
    def _(event):
        event.app.exit(result=items[current_selection_index])

    def get_text_for_ui():
        # Corregido: Construir una lista de strings y unirlos al final.
        text_parts = [f"<b>{prompt_title}</b>\n(↑↓: navegar, Enter: confirmar, q: salir)\n\n"]
        for i, item_name in enumerate(items):
            if i == current_selection_index:
                # Añadir la línea como una cadena de texto formateada
                text_parts.append(f"<style bg='ansiblue' fg='ansiwhite'>> {item_name}</style>\n")
            else:
                text_parts.append(f"  {item_name}\n")
        # Devolver un único objeto HTML que contiene todo el texto.
        return HTML("".join(text_parts))

    control = FormattedTextControl(text=get_text_for_ui, focusable=True, key_bindings=kb)
    selector_app = Application(layout=Layout(HSplit([Window(content=control)])), full_screen=False)
    
    return selector_app.run()

# --- Main Application ---
def main():
    global app_ui_instance, midi_input_port, midi_output_ports, osc_client, osc_address, quantize_mode, pc_output_port, pc_channel, midi_control_port, repeat_override_active

    print("MIDItema\n")
    parser = argparse.ArgumentParser(prog="miditema", description="Contador de compases esclavo de MIDI Clock.")
    parser.add_argument("song_file", nargs='?', default=None, help=f"Nombre del archivo de canción (sin .json) en ./{SONGS_DIR_NAME}/.")
    parser.add_argument("--quant", type=str, default=None, help="Fija la cuantización por defecto. Valores: bar, 4, 8, 16, 32, instant.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--song-mode", action="store_true", help="Inicia en 'Song Mode', ignorando los patrones de repetición.")
    mode_group.add_argument("--loop-mode", action="store_true", help="Inicia en 'Loop Mode', respetando los patrones de repetición.")
    args = parser.parse_args()

    # Procesar argumento de cuantización
    if args.quant:
        quant_map = {"bar": "next_bar", "4": "next_4", "8": "next_8", "16": "next_16", "32": "next_32", "instant": "instant"}
        valid_modes = set(quant_map.values())
        user_mode = quant_map.get(args.quant, args.quant)
        if user_mode in valid_modes:
            quantize_mode = user_mode
            print(f"[*] Modo de cuantización por defecto fijado a: {quantize_mode.upper()}")
        else:
            print(f"[!] Modo de cuantización '{args.quant}' no válido. Usando por defecto '{quantize_mode}'.")

    config = load_config()
    # --- Configuración de Entrada de Clock ---
    clock_source_name = config.get("clock_source")
    selected_port_name = None
    available_ports = mido.get_input_names()

    if not available_ports:
        print("[!] Error: No se encontraron puertos de entrada MIDI.")
        return

    if clock_source_name:
        selected_port_name = find_port_by_substring(available_ports, clock_source_name)
        if selected_port_name:
            print(f"[*] Fuente de clock '{selected_port_name}' encontrada desde la configuración.")
        else:
            print(f"[!] La fuente de clock '{clock_source_name}' de la config no fue encontrada.")

    if not selected_port_name:
        selected_port_name = interactive_selector(available_ports, "Selecciona la fuente de MIDI Clock")
        if not selected_port_name:
            print("[!] No se seleccionó ninguna fuente. Saliendo.")
            return
            
    # Abrir puerto de clock principal
    try:
        midi_input_port = mido.open_input(selected_port_name)
        clock_state.source_name = selected_port_name
        print(f"[*] Escuchando MIDI Clock en '{selected_port_name}'...")
    except Exception as e:
        print(f"[!] Error abriendo el puerto MIDI '{selected_port_name}': {e}")
        return

    # --- Configuración de Salidas y Control ---
    # ... (El código de transport_out y osc_configuration no cambia) ...
    transport_out_name = config.get("transport_out")
    if transport_out_name:
        output_port_name = find_port_by_substring(mido.get_output_names(), transport_out_name)
        if output_port_name:
            try:
                port = mido.open_output(output_port_name)
                midi_output_ports.append(port)
                print(f"[*] Puerto de salida '{output_port_name}' abierto para control de transporte.")
            except Exception as e:
                print(f"[!] No se pudo abrir el puerto de transporte '{output_port_name}': {e}")
        else:
            print(f"[!] El puerto de transporte '{transport_out_name}' no fue encontrado.")

    midi_config = config.get("midi_configuration")
    if midi_config:
        pc_device_name = midi_config.get("device_out")
        pc_channel_config = midi_config.get("channel_out", 1)

        if pc_device_name:
            pc_port_name = find_port_by_substring(mido.get_output_names(), pc_device_name)
            if pc_port_name:
                try:
                    pc_output_port = mido.open_output(pc_port_name)
                    pc_channel = max(0, min(15, pc_channel_config - 1))
                    print(f"[*] Puerto de salida '{pc_port_name}' abierto para Program Change en el canal {pc_channel + 1}.")
                except Exception as e:
                    print(f"[!] No se pudo abrir el puerto para Program Change '{pc_port_name}': {e}")
            else:
                print(f"[!] El dispositivo de Program Change '{pc_device_name}' no fue encontrado.")

        control_device_key = midi_config.get("device_in") or midi_config.get("midi_in")
        if control_device_key:
            control_port_name = find_port_by_substring(mido.get_input_names(), control_device_key)
            if control_port_name:
                if control_port_name == selected_port_name:
                    print("[*] El puerto de control es el mismo que el de clock. Usando modo compartido.")
                    midi_control_port = midi_input_port
                else:
                    try:
                        midi_control_port = mido.open_input(control_port_name)
                        print(f"[*] Puerto de entrada '{control_port_name}' abierto para control MIDI (dedicado).")
                    except Exception as e:
                        print(f"[!] No se pudo abrir el puerto de control '{control_port_name}': {e}")
            else:
                print(f"[!] El dispositivo de control '{control_device_key}' no fue encontrado.")

    osc_config = config.get("osc_configuration", {}).get("send", {})
    if osc_config:
        ip = osc_config.get("ip", "127.0.0.1")
        port = osc_config.get("port")
        osc_address = osc_config.get("address")
        
        # Guardamos la configuración completa para usarla en otras funciones
        globals()['osc_config'] = osc_config

        if port and (osc_address or osc_config.get("bar_triggers")):
            try:
                osc_client = udp_client.SimpleUDPClient(ip, port)
                print(f"[*] Cliente OSC configurado para enviar a {ip}:{port}")
                if osc_address:
                    print(f"    - Dirección de cambio de parte: '{osc_address}'")
                if osc_config.get("address_song_change"):
                    print(f"    - Dirección de cambio de canción: '{osc_config.get('address_song_change')}'")
                if osc_config.get("bar_triggers"):
                    print(f"    - Triggers de compás/bloque activados.")
            except Exception as e:
                print(f"Error configurando el cliente OSC: {e}")
        else:
            print("Advertencia: La configuración OSC está incompleta (falta 'port' y 'address' o 'bar_triggers').")


    # 2. Seleccionar Canción o Playlist
    selected_file_path = None
    if args.song_file:
        path = SONGS_DIR / f"{args.song_file}.json"
        if path.is_file():
            selected_file_path = path
        else:
            print(f"[!] El archivo '{args.song_file}' no se encontró.")
    
    if not selected_file_path:
        SONGS_DIR.mkdir(exist_ok=True)
        available_files = [f.stem for f in SONGS_DIR.glob("*.json")]
        if not available_files:
            print(f"[!] No se encontraron archivos en la carpeta './{SONGS_DIR_NAME}/'.")
            print("Crea un archivo .json de canción o playlist y vuelve a intentarlo.")
            return
        
        print()
        selected_file_name = interactive_selector(available_files, "Selecciona una canción o playlist")
        if not selected_file_name:
            print("[!] No se seleccionó ningún archivo. Saliendo.")
            return
        selected_file_path = SONGS_DIR / f"{selected_file_name}.json"

    # Cargar el archivo inicial y determinar si es una playlist o una canción
    try:
        with selected_file_path.open('r', encoding='utf-8') as f:
            initial_data = json5.load(f)
    except Exception as e:
        print(f"Error al leer el archivo inicial '{selected_file_path.name}': {e}")
        return

    if "songs" in initial_data and isinstance(initial_data["songs"], list):
        # Es una playlist
        playlist_state.is_active = True
        playlist_state.playlist_name = initial_data.get("playlist_name", selected_file_path.stem)
        playlist_state.playlist_elements = initial_data["songs"]
        print(f"[*] Playlist '{playlist_state.playlist_name}' cargada con {len(playlist_state.playlist_elements)} canciones.")
        
        # 1. Leer la configuración del archivo JSON como valor inicial
        playlist_mode = initial_data.get("mode", "loop") # Por defecto es 'loop'
        if playlist_mode.lower() == "song":
            repeat_override_active = True
        else:
            repeat_override_active = False
        
        # 2. Los argumentos de línea de comandos tienen prioridad y anulan el JSON
        if args.song_mode:
            repeat_override_active = True
            print("[*] Modo de inicio forzado a SONG MODE por argumento de línea de comandos.")
        elif args.loop_mode:
            repeat_override_active = False
            print("[*] Modo de inicio forzado a LOOP MODE por argumento de línea de comandos.")

        # Cargar la primera canción de la playlist
        if not load_song_from_playlist(0):
            print("[!] La playlist está vacía o la primera canción no es válida. Saliendo.")
            return
    else:
        # Es una canción normal. Pasamos los datos que ya hemos leído.
        if not load_song_file(filepath=selected_file_path, data=initial_data):
            return # Salir si la canción no es válida
        

    # 3. Iniciar MIDI y Lógica
    listener_thread = threading.Thread(target=midi_input_listener, daemon=True)
    listener_thread.start()

    control_listener_thread = None
    if midi_control_port and midi_control_port is not midi_input_port:
        control_listener_thread = threading.Thread(target=midi_control_listener, daemon=True)
        control_listener_thread.start()

    signal.signal(signal.SIGINT, signal_handler)
   
    # 4. Iniciar Interfaz de Usuario
    kb = KeyBindings()
    
    @Condition
    def is_playlist_active():
        return playlist_state.is_active
    
    # --- Filtros de Condición para el modo "Ir a Parte" ---
    @Condition
    def is_goto_mode():
        return goto_input_active

    # --- Acciones Globales ---
    @kb.add('q', eager=True)
    @kb.add('c-c', eager=True)
    def _(event):
        event.app.exit()

    @kb.add('enter', filter=~is_goto_mode)
    @kb.add(' ', filter=~is_goto_mode)
    def _(event):
        """Envía Start/Stop."""
        if clock_state.status == "STOPPED":
            send_midi_command('start')
        else:
            send_midi_command('stop')

    # --- Lógica de Salto (Modo Normal) ---
    @kb.add('right', filter=~is_goto_mode)
    def _(event):
        global pending_action, ui_feedback_message
        
        if (pending_action and 
            isinstance(pending_action.get("target"), dict) and 
            pending_action["target"].get("type") == "relative"):
            
            # Apilar acción existente
            pending_action["target"]["value"] += 1
        else:
            # Crear nueva acción
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quantize_mode}
        
        ui_feedback_message = "Jump forward."

    @kb.add('left', filter=~is_goto_mode)
    def _(event):
        global pending_action, ui_feedback_message

        if (pending_action and 
            isinstance(pending_action.get("target"), dict) and 
            pending_action["target"].get("type") == "relative"):
            
            # Apilar acción existente
            pending_action["target"]["value"] -= 1
        else:
            # Crear nueva acción
            target = {"type": "relative", "value": -1}
            pending_action = {"target": target, "quantize": quantize_mode}
            
        ui_feedback_message = "Jump back."

    @kb.add('up', filter=~is_goto_mode)
    def _(event):
        global pending_action, ui_feedback_message
        pending_action = {"target": "restart", "quantize": quantize_mode}
        ui_feedback_message = "Restart current part."

    @kb.add('down', filter=~is_goto_mode)
    def _(event):
        global pending_action, ui_feedback_message
        if pending_action:
            pending_action = None
            ui_feedback_message = "Pending action cancelled."

    # --- Controles Numéricos (Modo Normal) ---
    for i in "0123":
        @kb.add(i, filter=~is_goto_mode)
        def _(event):
            global pending_action, ui_feedback_message
            key = event.key_sequence[0].data
            quant_map = {"0": "next_bar", "1": "next_4", "2": "next_8", "3": "next_16"}
            quant = quant_map[key]
            
            # Corregido: Crear la acción con la nueva estructura de diccionario
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quant}
            
            ui_feedback_message = f"Next part with (Quant: {quant.upper()})."
            

    for i in "456789":
        @kb.add(i, filter=~is_goto_mode)
        def _(event):
            global quantize_mode, ui_feedback_message
            key = event.key_sequence[0].data
            quant_map = {
                "4": "next_4", 
                "5": "next_8", 
                "6": "next_16", 
                "7": "next_bar", 
                "8": "end_of_part",
                "9": "instant"
            }
            quantize_mode = quant_map[key]
            ui_feedback_message = f"Modo de cuantización global cambiado a: {quantize_mode.upper()}."

    # Atajos de Teclas de Función (F1-F12) para Cues
    for i in range(1, 13):
        @kb.add(f'f{i}', filter=~is_goto_mode)
        def _(event, key_num=i):
            trigger_cue_jump(key_num)
    # --- Activación del modo "Ir a Parte" ---
    @kb.add('.', filter=~is_goto_mode)

    # --- Activación del modo "Ir a Parte" ---
    @kb.add('.', filter=~is_goto_mode)
    @kb.add(',', filter=~is_goto_mode)
    def _(event):
        global goto_input_active, goto_input_buffer
        goto_input_active = True
        goto_input_buffer = ""

    # --- Controles en modo "Ir a Parte" ---
    @kb.add('escape', filter=is_goto_mode)
    @kb.add('down', filter=is_goto_mode)
    def _(event):
        global goto_input_active, ui_feedback_message
        goto_input_active = False
        ui_feedback_message = "Pending action cancelled."

    @kb.add('backspace', filter=is_goto_mode)
    def _(event):
        global goto_input_buffer
        goto_input_buffer = goto_input_buffer[:-1]

    # --- Captura de dígitos en modo "Ir a Parte" ---
    for i in "0123456789":
        @kb.add(i, filter=is_goto_mode)
        def _(event):
            global goto_input_buffer
            goto_input_buffer += event.data

    @kb.add('enter', filter=is_goto_mode)
    def _(event):
        global goto_input_active, goto_input_buffer, pending_action, ui_feedback_message
        if goto_input_buffer.isdigit():
            part_num = int(goto_input_buffer)
            if 1 <= part_num <= len(song_state.parts):
                pending_action = {"target": part_num - 1, "quantize": quantize_mode}
                ui_feedback_message = f"Go to part {part_num}."
            else:
                ui_feedback_message = f"[!] Error: part {part_num} does not exist."
        else:
            ui_feedback_message = "[!] Error: invalid input."
        goto_input_active = False
        goto_input_buffer = ""

    @kb.add('pageup', filter=is_playlist_active)
    def _(event):
        """Salta a la canción anterior de la playlist."""
        global ui_feedback_message
        target = {"type": "relative", "value": -1}
        action = {"target_type": "song", "target": target, "quantize": quantize_mode}
        trigger_song_jump(action)
        ui_feedback_message = "Playlist: Previous Song."

    @kb.add('pagedown', filter=is_playlist_active)
    def _(event):
        """Salta a la siguiente canción de la playlist."""
        global ui_feedback_message
        target = {"type": "relative", "value": 1}
        action = {"target_type": "song", "target": target, "quantize": quantize_mode}
        trigger_song_jump(action)
        ui_feedback_message = "Playlist: Next Song."

    @kb.add('home', filter=is_playlist_active)
    def _(event):
        """Salta a la primera canción de la playlist."""
        global ui_feedback_message
        action = {"target_type": "song", "target": 0, "quantize": quantize_mode}
        trigger_song_jump(action)
        ui_feedback_message = "Playlist: Go to First Song."

    @kb.add('end', filter=is_playlist_active)
    def _(event):
        """Salta a la última canción de la playlist."""
        global ui_feedback_message
        last_song_index = len(playlist_state.playlist_elements) - 1
        action = {"target_type": "song", "target": last_song_index, "quantize": quantize_mode}
        trigger_song_jump(action)
        ui_feedback_message = "Playlist: Go to Last Song."

    @kb.add('r', filter=~is_goto_mode)
    def _(event):
        """Activa o desactiva la anulación de los patrones de repetición."""
        global repeat_override_active, ui_feedback_message
        repeat_override_active = not repeat_override_active
        mode_str = "Song Mode" if repeat_override_active else "Loop Mode"
        ui_feedback_message = f"Modo cambiado a {mode_str}"

    
    root_container = HSplit([
        # El bloque de encabezado de 6 líneas
        Window(content=FormattedTextControl(text=get_part_name_text), height=6),
        
        # El contador de compases
        Window(content=FormattedTextControl(text=get_countdown_text)),
        Window(height=1),
        
        # El secuenciador
        Window(content=FormattedTextControl(text=get_step_sequencer_text)),
        
        # El texto de la próxima parte/canción
        Window(content=FormattedTextControl(text=get_next_part_text)),
        
        Window(content=FormattedTextControl("-" * 80), height=1),
        
        # Bloque de estado inferior
        Window(content=FormattedTextControl(text=get_action_status_text)),
        Window(content=FormattedTextControl(text=get_key_legend_text), height=2),
        Window(content=FormattedTextControl(text=get_feedback_text)),

    ], style="bg:#111111 #cccccc")


    app_ui_instance = Application(layout=Layout(root_container), key_bindings=kb, full_screen=True, refresh_interval=0.1)
    
    try:
        app_ui_instance.run()
    except Exception as e:
        traceback.print_exc()
    finally:
        SHUTDOWN_FLAG = True
        print("\nCerrando...")
        if midi_input_port:
            midi_input_port.close()
        for port in midi_output_ports:
            port.close()
        if pc_output_port: # Nueva línea
            pc_output_port.close() # Nueva línea
        if listener_thread.is_alive():
            listener_thread.join(timeout=0.2)
        if control_listener_thread and control_listener_thread.is_alive(): 
            control_listener_thread.join(timeout=0.2)
        print("Detenido.")

if __name__ == "__main__":  
    main()
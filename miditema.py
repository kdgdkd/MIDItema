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
import json5
from pythonosc import udp_client
from pythonosc import osc_message_builder


# --- UI Imports ---
from prompt_toolkit import Application, HTML
from prompt_toolkit.layout.containers import HSplit, Window, VSplit
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

    reset_song_state_on_stop()
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
        return None, None # Corregido para devolver una tupla consistente

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
        
        if repeat_override_active:
            # Si la anulación está activa, cualquier parte es válida (ignoramos el patrón)
            play_this_part = True
        else:
            # Lógica original de patrones de repetición
            pattern = part.get("repeat_pattern")
            if pattern is None or pattern is True:
                play_this_part = True
            elif pattern is False:
                if temp_pass_count == 0: play_this_part = True
            elif isinstance(pattern, list) and pattern:
                if pattern[temp_pass_count % len(pattern)]: play_this_part = True

        # La condición final es que la parte sea reproducible Y tenga compases
        if play_this_part and part.get("bars", 0) > 0:
            return temp_index, temp_pass_count

    return None, None # Si no se encuentra, devuelve None


def execute_part_jump ():
    """Ejecuta el salto de PARTE modificando el estado de la canción."""
    global pending_action
    if not pending_action:
        return

    target = pending_action.get("target")
    final_index = song_state.current_part_index
    final_pass_count = song_state.pass_count

    if isinstance(target, dict) and target.get("type") == "relative":
        steps = target.get("value", 0)
        if steps == 0:
            pending_action = None
            return

        direction = "+1" if steps > 0 else "-1"
        for _ in range(abs(steps)):
            # Si en algún paso no se encuentra una parte válida, el resultado es None
            if final_index is not None:
                final_index, final_pass_count = find_next_valid_part_index(direction, final_index, final_pass_count)
        
    elif target == "restart":
        # El índice no cambia, el pass_count tampoco
        pass
    elif isinstance(target, int):
        if 0 <= target < len(song_state.parts):
            final_index = target
            final_pass_count = 0 
        else:
            pending_action = None
            return
    
    # Si el salto resulta en el final de la canción, gestionarlo
    if final_index is None:
        handle_song_end()
    else:
        # Aplicar el estado y configurar la parte de destino DIRECTAMENTE
        song_state.pass_count = final_pass_count
        setup_part(final_index)
    
    pending_action = None
  
def execute_song_jump():
    """Ejecuta el salto de CANCIÓN cargando la nueva canción de la playlist."""
    global pending_action, ui_feedback_message
    if not pending_action or not playlist_state.is_active:
        pending_action = None
        return

    target = pending_action.get("target")
    current_index = playlist_state.current_song_index
    final_index = current_index

    if target == "restart":
        # La acción es reiniciar la canción actual, el índice no cambia.
        pass
    elif isinstance(target, dict) and target.get("type") == "relative":
        steps = target.get("value", 0)
        direction = "+1" if steps > 0 else "-1"
        temp_index = current_index
        for _ in range(abs(steps)):
            if direction == "+1":
                temp_index += 1
            else:
                temp_index -= 1
        final_index = temp_index
    elif isinstance(target, int):
        final_index = target

    # Validar el índice final
    if 0 <= final_index < len(playlist_state.playlist_elements):
        if load_song_from_playlist(final_index):
            start_next_part() # Iniciar la nueva canción
    else:
        ui_feedback_message = f"Salto a canción {final_index + 1} inválido (fuera de rango)."

    pending_action = None

def execute_pending_action():
    """Inspecciona la acción pendiente y decide si es un salto de parte o de canción."""
    if not pending_action:
        return

    if pending_action.get("target_type") == "song":
        execute_song_jump()
    else:
        execute_part_jump()



def check_and_execute_pending_action():
    """
    Verifica si se cumplen las condiciones de cuantización para ejecutar un salto.
    Devuelve True si se ejecutó un salto, False en caso contrario.
    """
    if not pending_action or clock_state.status != "PLAYING":
        return

    quantize = pending_action.get("quantize")
    
    # Contexto musical actual
    sig_num = song_state.time_signature_numerator
    total_beats_in_part = song_state.parts[song_state.current_part_index].get("bars", 0) * sig_num
    beats_into_part = total_beats_in_part - song_state.remaining_beats_in_part
    current_bar = beats_into_part // sig_num
    is_last_beat_of_bar = (song_state.remaining_beats_in_part % sig_num == 1)

    should_jump = False
    if quantize == "instant":
        should_jump = True
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

def process_control_message(msg):
    """Procesa un único mensaje de control MIDI (PC, CC, Note, Song Select)."""
    global pending_action, quantize_mode, ui_feedback_message
    
    if msg.type == 'program_change':
        if 0 <= msg.program < len(song_state.parts):
            pending_action = {"target": msg.program, "quantize": quantize_mode}
            ui_feedback_message = f"PC Recibido: Ir a parte {msg.program + 1}."
        else:
            ui_feedback_message = f"PC Recibido: Parte {msg.program + 1} no existe."

    elif msg.type == 'song_select':
        if playlist_state.is_active:
            pending_action = {
                "target_type": "song",
                "target": msg.song,
                "quantize": quantize_mode
            }
            ui_feedback_message = f"Song Select: Ir a canción {msg.song + 1}."
        else:
            ui_feedback_message = "Song Select ignorado (no hay playlist activa)."

    elif msg.type == 'note_on':
        # Lógica para saltos de PARTE
        if msg.note == 125: # Siguiente Parte
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quantize_mode}
            ui_feedback_message = "Note Recibido: Siguiente Parte."
        elif msg.note == 124: # Parte Anterior
            target = {"type": "relative", "value": -1}
            pending_action = {"target": target, "quantize": quantize_mode}
            ui_feedback_message = "Note Recibido: Parte Anterior."
        
        # Lógica para saltos de CANCIÓN (Playlist)
        elif msg.note == 127: # Siguiente Canción
            if not playlist_state.is_active:
                ui_feedback_message = "Note On (Next Song) ignorado (no hay playlist activa)."
                return
            target = {"type": "relative", "value": 1}
            pending_action = {"target_type": "song", "target": target, "quantize": quantize_mode}
            ui_feedback_message = "Note Recibido: Siguiente Canción."
        elif msg.note == 126: # Canción Anterior
            if not playlist_state.is_active:
                ui_feedback_message = "Note On (Prev Song) ignorado (no hay playlist activa)."
                return
            target = {"type": "relative", "value": -1}
            pending_action = {"target_type": "song", "target": target, "quantize": quantize_mode}
            ui_feedback_message = "Note Recibido: Canción Anterior."

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
        elif val in [4, 5, 6, 7, 9]:
            quant_map = {4: "next_4", 5: "next_8", 6: "next_16", 7: "next_bar", 9: "instant"}
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
        # --- NUEVO MAPEADO DE CONTROLES ---
        elif val == 12: # Reiniciar Parte
            pending_action = {"target": "restart", "quantize": quantize_mode}
            ui_feedback_message = "CC#0 Recibido: Reiniciar Parte."
        elif val == 13: # Canción Anterior
            if not playlist_state.is_active:
                ui_feedback_message = "CC#0(13) ignorado (no hay playlist activa)."
                return
            target = {"type": "relative", "value": -1}
            pending_action = {"target_type": "song", "target": target, "quantize": quantize_mode}
            ui_feedback_message = "CC#0 Recibido: Canción Anterior."
        elif val == 14: # Siguiente Canción
            if not playlist_state.is_active:
                ui_feedback_message = "CC#0(14) ignorado (no hay playlist activa)."
                return
            target = {"type": "relative", "value": 1}
            pending_action = {"target_type": "song", "target": target, "quantize": quantize_mode}
            ui_feedback_message = "CC#0 Recibido: Siguiente Canción."
        elif val == 15: # Reiniciar Canción
            if not playlist_state.is_active:
                ui_feedback_message = "CC#0(15) ignorado (no hay playlist activa)."
                return
            pending_action = {"target_type": "song", "target": "restart", "quantize": quantize_mode}
            ui_feedback_message = "CC#0 Recibido: Reiniciar Canción."
        elif val == 16: # Cancelar Acción
            if pending_action:
                pending_action = None
                ui_feedback_message = "CC#0 Recibido: Acción cancelada."
        elif val == 17: # Activar/Desactivar anulación de repetición
            global repeat_override_active
            repeat_override_active = not repeat_override_active
            status_str = "ON" if repeat_override_active else "OFF"
            ui_feedback_message = f"CC#0 Recibido: Repeat Override -> {status_str}"

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
            # Hay una siguiente canción en la playlist
            ui_feedback_message = f"Fin de '{song_state.song_name}'. Cargando siguiente canción..."
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
        target = pending_action.get("target")
        quant = pending_action.get("quantize").replace("_", " ").upper()
        
        part_name = ""
        
        if isinstance(target, dict) and target.get("type") == "relative":
            value = target.get("value", 0)
            if value != 0:
                direction = "+1" if value > 0 else "-1"
                
                # Simular el salto completo para encontrar el nombre de la parte de destino
                final_index = song_state.current_part_index
                final_pass_count = song_state.pass_count
                for _ in range(abs(value)):
                    if final_index is not None:
                        final_index, final_pass_count = find_next_valid_part_index(direction, final_index, final_pass_count)

                # Comprobar si el salto lleva al final
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
    
    # Lógica para el modo "Ir a Parte"
    if goto_input_active:
        ui_feedback_message = "" # Limpiar otros mensajes
        return HTML(f"<style bg='ansiyellow' fg='ansiblack'>Ir a Parte: {goto_input_buffer}_</style>")

    quant_part = f"<b>Quant:</b> <style bg='#333333'>[{quant_str}]</style>"
    action_part = f"<b>Pending Action:</b> <style bg='#333333'>[{action_str}]</style>"

    repeat_part = ""
    if repeat_override_active:
        repeat_part = " | <style fg='ansired' bold='true'>Song Mode</style>"
    else:
        repeat_part = " | <style fg='#666666'>Loop Mode</style>"

    return HTML(f"{quant_part} | {action_part}{repeat_part}")

def get_key_legend_text():
    """Muestra la leyenda de los controles de teclado."""
    line1 = "<b>[←→:</b> Part Nav] <b>[↑:</b> Restart Part] <b>[↓:</b> Cancel] "
    line2 = "<b>[PgUp/PgDn:</b> Song Nav] <b>[r:</b> Toggle Mode] "
    line3 = "<b>[.:</b> Go to Part] <b>[0-9:</b> Quantize/Jump]"
    return HTML(f"<style fg='#666666'>{line1}{line2}{line3}</style>")

# --- UI Functions ---
def get_part_name_text():
    """Genera el encabezado de la aplicación con formato unificado para canción y parte."""
    
    # --- Lógica para la línea del Título de la Canción ---
    song_color_name = song_state.song_color
    song_style_str = TITLE_COLOR_PALETTE.get(song_color_name)
    
    # Si no se especifica color o no es válido, usar el estilo por defecto (gris/negro)
    if not song_style_str:
        song_style_str = "bg='#aaaaaa' fg='ansiblack'"

    playlist_prefix = ""
    if playlist_state.is_active:
        current = playlist_state.current_song_index + 1
        total = len(playlist_state.playlist_elements)
        playlist_prefix = f"[{current}/{total}] "

    full_song_title = f"miditema - {playlist_prefix}{song_state.song_name}"
    centered_song_title = full_song_title.center(80)
    song_title_line = f"<style {song_style_str} bold='true'>{centered_song_title}</style>"

    # --- Lógica para la línea del Título de la Parte (sin cambios) ---
    part_info_str = "---"
    part_to_display = None
    part_style_str = TITLE_COLOR_PALETTE['default']

    if song_state.current_part_index != -1:
        part_to_display = song_state.parts[song_state.current_part_index]
    elif song_state.parts:
        part_to_display = song_state.parts[0]

    if part_to_display:
        name = part_to_display.get('name', '---')
        bars = part_to_display.get('bars', 0)
        part_info_str = f"{name} ({bars} compases)"
        color_name = part_to_display.get('color')
        part_style_str = TITLE_COLOR_PALETTE.get(color_name, TITLE_COLOR_PALETTE['default'])
    
    centered_part_name = part_info_str.center(80)
    part_name_line = f"<style {part_style_str} bold='true'>{centered_part_name}</style>"

    return HTML(song_title_line + "\n" + part_name_line)


def get_dynamic_endpoint():
    """
    Calcula el compás final relevante, ya sea el final de la parte
    o el punto de ejecución de una acción pendiente.
    Devuelve el número del compás final (1-based).
    """
    current_part = song_state.parts[song_state.current_part_index]
    total_bars_in_part = current_part.get("bars", 0)

    if not pending_action or clock_state.status != "PLAYING":
        return total_bars_in_part

    # Calcular la posición actual
    sig_num = song_state.time_signature_numerator
    beats_into_part = (total_bars_in_part * sig_num) - song_state.remaining_beats_in_part
    current_bar_index = beats_into_part // sig_num # 0-based

    quantize = pending_action.get("quantize")
    
    if quantize in ["instant", "next_bar"]:
        return current_bar_index + 1
    
    quantize_map = {"next_4": 4, "next_8": 8, "next_16": 16}
    if quantize in quantize_map:
        boundary = quantize_map[quantize]
        # Calcula el próximo múltiplo de 'boundary' desde el compás actual
        target_bar = ((current_bar_index // boundary) + 1) * boundary
        return target_bar
    
    return total_bars_in_part # Fallback



def get_countdown_text():
    bar_text = "-0"
    beat_text = "0"
    style = "bg='#222222' fg='ansiwhite'"

    if clock_state.status == "PLAYING" and song_state.remaining_beats_in_part > 0:
        sig_num = song_state.time_signature_numerator
        rem_beats = song_state.remaining_beats_in_part
        
        endpoint_bar = get_dynamic_endpoint()
        
        # Calcular compases y beats actuales
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
    return HTML(f"<style {style}>{countdown_str}</style>")


def get_next_part_text():
    """Calcula y muestra la siguiente parte o la siguiente canción."""
    if clock_state.status != "PLAYING":
        return ""

    # Primero, buscar la siguiente parte dentro de la canción actual
    next_part_index, _ = find_next_valid_part_index("+1", song_state.current_part_index, song_state.pass_count)

    if next_part_index is not None:
        # Hay una siguiente parte en esta canción
        part = song_state.parts[next_part_index]
        name = part.get('name', 'N/A')
        bars = part.get('bars', 0)
        next_str = f" >> {name} ({bars})"
        color_name = part.get('color', 'default')
        style_str = FG_COLOR_PALETTE.get(color_name, FG_COLOR_PALETTE['default'])
        return HTML(f"<style {style_str}>{next_str}</style>")
    
    # Si no hay siguiente parte, comprobar si hay una siguiente canción en la playlist
    if playlist_state.is_active:
        next_song_index = playlist_state.current_song_index + 1
        if next_song_index < len(playlist_state.playlist_elements):
            next_song_element = playlist_state.playlist_elements[next_song_index]
            song_name = "Siguiente Canción" # Nombre por defecto
            if "filepath" in next_song_element:
                # Extraer nombre del path
                song_name = Path(next_song_element["filepath"]).stem
            elif "song_name" in next_song_element:
                song_name = next_song_element["song_name"]
            
            next_str = f" >> Próxima Canción: {song_name}"
            return HTML(f"<style fg='ansiyellow' bold='true'>{next_str}</style>")

    # Si no hay ni siguiente parte ni siguiente canción, es el final
    return HTML("<style fg='#888888'>Siguiente >> Fin</style>")

def get_bar_counter_text():
    """Muestra el contador de compases actual vs el total de la parte."""
    if song_state.current_part_index == -1 or clock_state.status == "STOPPED":
        return HTML("<style fg='#666666'>Compás: --/--</style>")

    part = song_state.parts[song_state.current_part_index]
    total_bars = part.get("bars", 0)
    current_bar = song_state.current_bar_in_part

    # El contador es 1-based para la UI, pero el estado es 0-based
    display_bar = current_bar + 1
    if clock_state.status != "PLAYING" or current_bar >= total_bars:
        display_bar = current_bar

    # Si estamos en el último beat del compás, mostramos el siguiente número
    sig_num = song_state.time_signature_numerator
    if song_state.remaining_beats_in_part % sig_num == 1 and clock_state.status == "PLAYING":
        display_bar = current_bar + 1

    # Para evitar mostrar "17/16" al final, lo limitamos
    display_bar = min(display_bar, total_bars)
    
    # Durante la reproducción, el compás actual es el que está sonando
    if clock_state.status == "PLAYING" and song_state.current_bar_in_part < total_bars:
        display_bar = song_state.current_bar_in_part + 1
    elif clock_state.status != "PLAYING":
        display_bar = 0 # Muestra 0 si está parado
    
    bar_str = f"Compás: {display_bar:02d}/{total_bars:02d}"
    return HTML(f"<style fg='#888888'>{bar_str}</style>")


def get_step_sequencer_text():
    """Genera la representación visual de los compases."""
    if song_state.current_part_index == -1:
        return ""

    part = song_state.parts[song_state.current_part_index]
    total_bars = part.get("bars", 0)
    if total_bars == 0:
        return ""

    sig_num = song_state.time_signature_numerator
    consumed_beats = (total_bars * sig_num) - song_state.remaining_beats_in_part
    consumed_bars = consumed_beats // sig_num
    
    endpoint_bar = get_dynamic_endpoint() if pending_action else total_bars

    # Obtener el color base para los bloques de esta parte
    part_color_name = part.get('color')
    # Si no hay color definido, usar un gris tenue por defecto para los bloques futuros
    part_style = FG_COLOR_PALETTE.get(part_color_name, "fg='#888888'")

    output_lines = []
    padding = " " * 10

    for row_start in range(0, total_bars, 8):
        line1 = ""
        line2 = ""
        for i in range(row_start, min(row_start + 8, total_bars)):
            bar_index_0based = i
            
            style = part_style # Por defecto, todos los bloques tienen el color de la parte
            
            if bar_index_0based < consumed_bars:
                style = "fg='#444444'" # Compás ya consumido
            elif pending_action and bar_index_0based >= endpoint_bar:
                 style = "fg='#444444'" # Compás que se saltará
            elif bar_index_0based == consumed_bars and clock_state.status == "PLAYING":
                # Estilo especial para el compás activo
                remaining_bars_to_endpoint = endpoint_bar - bar_index_0based
                if remaining_bars_to_endpoint == 1:
                    style = "fg='ansired' bold='true'"
                elif remaining_bars_to_endpoint <= 4:
                    style = "fg='ansiyellow' bold='true'"
                else:
                    style = "fg='ansiwhite' bold='true'" # Compás activo normal
            
            block = "██  "
            line1 += f"<style {style}>{block}</style>"
            line2 += f"<style {style}>{block}</style>"
        
        output_lines.append(padding + line1)
        output_lines.append(padding + line2)

        if row_start + 8 < total_bars:
            output_lines.append("")
    
    target_height = 11
    while len(output_lines) < target_height:
        output_lines.append("")
            
    return HTML("\n".join(output_lines))



def get_status_line_text():
    status = clock_state.status.ljust(10)
    bpm = f"{clock_state.bpm:.0f} BPM".ljust(12)
    source = f"Clock: {clock_state.source_name}"
    
    elapsed_str = "--:--"
    if clock_state.start_time > 0 and clock_state.status != "FINISHED":
        elapsed_seconds = time.time() - clock_state.start_time
        minutes, seconds = divmod(int(elapsed_seconds), 60)
        elapsed_str = f"{minutes:02d}:{seconds:02d}"

    return HTML(f"{status} | {elapsed_str} | {bpm} | {source}")

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
    global app_ui_instance, midi_input_port, midi_output_ports, osc_client, osc_address, quantize_mode, pc_output_port, pc_channel, midi_control_port

    print("MIDItema\n")
    parser = argparse.ArgumentParser(prog="miditema", description="Contador de compases esclavo de MIDI Clock.")
    parser.add_argument("song_file", nargs='?', default=None, help=f"Nombre del archivo de canción (sin .json) en ./{SONGS_DIR_NAME}/.")
    parser.add_argument("--quant", type=str, default=None, help="Fija la cuantización por defecto. Valores: bar, 4, 8, 16, 32, instant.")
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
            
    for i in "45679":
        @kb.add(i, filter=~is_goto_mode)
        def _(event):
            global quantize_mode, ui_feedback_message
            key = event.key_sequence[0].data
            quant_map = {
                "4": "next_4", 
                "5": "next_8", 
                "6": "next_16", 
                "7": "next_bar", 
                "9": "instant"
            }
            quantize_mode = quant_map[key]
            ui_feedback_message = f"Modo de cuantización global cambiado a: {quantize_mode.upper()}."

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
        global pending_action, ui_feedback_message
        target = {"type": "relative", "value": -1}
        pending_action = {"target_type": "song", "target": target, "quantize": quantize_mode}
        ui_feedback_message = "Playlist: Previous Song."

    @kb.add('pagedown', filter=is_playlist_active)
    def _(event):
        """Salta a la siguiente canción de la playlist."""
        global pending_action, ui_feedback_message
        target = {"type": "relative", "value": 1}
        pending_action = {"target_type": "song", "target": target, "quantize": quantize_mode}
        ui_feedback_message = "Playlist: Next Song."

    @kb.add('r', filter=~is_goto_mode)
    def _(event):
        """Activa o desactiva la anulación de los patrones de repetición."""
        global repeat_override_active, ui_feedback_message
        repeat_override_active = not repeat_override_active
        status_str = "OFF" if repeat_override_active else "ON"
        ui_feedback_message = f"Loop Mode: {status_str}"

    root_container = HSplit([
        Window(content=FormattedTextControl(text=get_part_name_text)),
        VSplit([
            Window(width=Dimension(weight=1)),
            Window(content=FormattedTextControl(text=get_countdown_text), width=40),
            Window(width=Dimension(weight=3)),
        ]),
        Window(height=1),
        Window(content=FormattedTextControl(text=get_step_sequencer_text)),
        Window(content=FormattedTextControl(text=get_next_part_text)),
        Window(content=FormattedTextControl(text=get_bar_counter_text), height=1, style="fg:#888888"),
        Window(content=FormattedTextControl("-" * 80), height=1),
        
        # --- Bloque de estado inferior (Reordenado) ---
        Window(content=FormattedTextControl(text=get_status_line_text)),
        Window(content=FormattedTextControl(text=get_action_status_text)),
        Window(content=FormattedTextControl(text=get_feedback_text)),
        Window(content=FormattedTextControl(text=get_key_legend_text), height=1),

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
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
        self.song_name = "Sin Canción"
        self.parts = []
        self.current_part_index = -1
        self.remaining_beats_in_part = 0
        self.pass_count = 0
        self.midi_clock_tick_counter = 0
        # Valores derivados de la canción
        self.time_signature_numerator = 4
        self.ticks_per_song_beat = MIDI_PPQN


# --- Global State Instances ---
clock_state = ClockState()
song_state = SongState()
pending_action = None
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
            config = json.load(f)
        print(f"[*] Archivo de configuración '{CONF_FILE_NAME}' cargado.")
        return config
    except Exception:
        return {}

def load_song_file(filepath: Path):
    """Carga y valida un archivo de canción, actualizando el SongState."""
    global song_state
    try:
        with filepath.open('r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error: No se pudo leer o parsear el archivo '{filepath.name}': {e}")
        return False

    song_state = SongState() # Resetear estado al cargar nueva canción
    song_state.song_name = data.get("song_name", filepath.stem)
    song_state.parts = data.get("parts", [])

    if not song_state.parts or not isinstance(song_state.parts, list):
        print(f"Error: La canción '{song_state.song_name}' no tiene una lista de 'parts' válida.")
        return False

    # Interpretar Time Signature
    try:
        sig = data.get("time_signature", "4/4").split('/')
        song_state.time_signature_numerator = int(sig[0])
    except (ValueError, IndexError):
        song_state.time_signature_numerator = 4

    # Interpretar Time Division
    division = data.get("time_division", "1/4")
    division_map = {"1/4": 24, "1/8": 12, "1/16": 6}
    song_state.ticks_per_song_beat = division_map.get(division, MIDI_PPQN)

    print(f"Canción '{song_state.song_name}' cargada. ({len(song_state.parts)} partes)")
    return True

def reset_song_state_on_stop():
    """Resetea el estado de la secuencia cuando el reloj se detiene."""
    song_state.current_part_index = -1
    song_state.remaining_beats_in_part = 0
    song_state.pass_count = 0
    song_state.midi_clock_tick_counter = 0
    clock_state.tick_times = []
    clock_state.bpm = 0.0

def setup_part(part_index):
    """Configura una parte específica para la reproducción y envía mensajes."""
    if not (0 <= part_index < len(song_state.parts)):
        return # Salida segura si el índice no es válido

    song_state.current_part_index = part_index
    part = song_state.parts[part_index]
    song_state.remaining_beats_in_part = part.get("bars", 0) * song_state.time_signature_numerator
    
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
    jump_executed = check_and_execute_pending_action()

    # Si NO se ejecutó un salto, proceder con la cuenta atrás normal.
    if not jump_executed:
        song_state.remaining_beats_in_part -= 1
    
        if song_state.remaining_beats_in_part > 0 and \
           song_state.remaining_beats_in_part % song_state.time_signature_numerator == 0:
            beat_flash_end_time = time.time() + 0.1 # Activar flash por 0.1 segundos

        if song_state.remaining_beats_in_part <= 0:
            start_next_part()

# --- Dynamic Part-Jumping Logic ---

def find_next_valid_part_index(direction: str, start_index: int, start_pass_count: int):
    """Encuentra el índice y el pass_count de la siguiente parte válida."""
    if not song_state.parts:
        return -1, 0

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
        pattern = part.get("repeat_pattern")
        
        play_this_part = False
        if pattern is None or pattern is True:
            play_this_part = True
        elif pattern is False:
            if temp_pass_count == 0: play_this_part = True
        elif isinstance(pattern, list) and pattern:
            if pattern[temp_pass_count % len(pattern)]: play_this_part = True

        if play_this_part and part.get("bars", 0) > 0:
            return temp_index, temp_pass_count

    return  None, None # Si no se encuentra, devuelve None


def execute_jump():
    """Ejecuta el salto modificando el estado de la canción según la acción pendiente."""
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
        execute_jump()
        return True

    return False


def midi_input_listener():
    """El hilo principal que escucha los mensajes MIDI y actualiza el estado."""
    global midi_input_port, clock_state, song_state
    
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
            clock_state.status = "PLAYING"
            clock_state.start_time = time.time()
            reset_song_state_on_stop()
            start_next_part()
        elif msg.type == 'stop':
            clock_state.status = "STOPPED"
            clock_state.start_time = 0
            reset_song_state_on_stop()
        elif msg.type == 'continue':
            clock_state.status = "PLAYING"
        elif msg.type == 'clock':
            if clock_state.status == "STOPPED":
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

            # --- Avance de la Canción (LÓGICA CORREGIDA) ---
            if clock_state.status == "PLAYING":
                song_state.midi_clock_tick_counter += 1
                if song_state.midi_clock_tick_counter >= song_state.ticks_per_song_beat:
                    song_state.midi_clock_tick_counter = 0
                    process_song_tick()
        
        # --- Lógica de Control (si el puerto es compartido) ---
        elif is_shared_port:
            process_control_message(msg)

def process_control_message(msg):
    """Procesa un único mensaje de control MIDI. Reutilizable."""
    global pending_action, quantize_mode, ui_feedback_message
    
    if msg.type == 'program_change':
        if 0 <= msg.program < len(song_state.parts):
            pending_action = {"target": msg.program, "quantize": quantize_mode}
            ui_feedback_message = f"PC Recibido: Ir a parte {msg.program + 1}."
        else:
            ui_feedback_message = f"PC Recibido: Parte {msg.program + 1} no existe."

    elif msg.type == 'control_change' and msg.control == 0:
        val = msg.value
        if 0 <= val <= 3:
            quant_map = {0: "instant", 1: "next_bar", 2: "next_8", 3: "next_16"}
            quant = quant_map[val]
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quant}
            ui_feedback_message = f"CC Recibido: Salto rápido (Quant: {quant.upper()})."
        elif val in [4, 5, 6, 7, 9]:
            quant_map = {4: "next_4", 5: "next_8", 6: "next_16", 7: "next_bar", 9: "instant"}
            quantize_mode = quant_map[val]
            ui_feedback_message = f"CC Recibido: Modo global -> {quantize_mode.upper()}."
        elif val == 10:
            target = {"type": "relative", "value": -1}
            pending_action = {"target": target, "quantize": quantize_mode}
            ui_feedback_message = "CC Recibido: Saltar Anterior."
        elif val == 11:
            target = {"type": "relative", "value": 1}
            pending_action = {"target": target, "quantize": quantize_mode}
            ui_feedback_message = "CC Recibido: Saltar Siguiente."
        elif val == 12:
            pending_action = {"target": "restart", "quantize": quantize_mode}
            ui_feedback_message = "CC Recibido: Reiniciar Parte."
        elif val == 13:
            if pending_action:
                pending_action = None
                ui_feedback_message = "CC Recibido: Acción cancelada."

def midi_control_listener():
    """El hilo que escucha los mensajes MIDI de control (PC, CC)."""
    global pending_action, quantize_mode, ui_feedback_message
    while not SHUTDOWN_FLAG:
        if not midi_control_port:
            time.sleep(0.1)
            continue

        msg = midi_control_port.poll()
        if not msg:
            time.sleep(0.001)
            continue
        
        process_control_message(msg)

        if msg.type == 'program_change':
            # Salto directo a una parte usando el número de Program Change
            if 0 <= msg.program < len(song_state.parts):
                pending_action = {"target": msg.program, "quantize": quantize_mode}
                ui_feedback_message = f"PC Recibido: Ir a parte {msg.program + 1}."
            else:
                ui_feedback_message = f"PC Recibido: Parte {msg.program + 1} no existe."

        elif msg.type == 'control_change' and msg.control == 0:
            val = msg.value
            
            # Saltos rápidos (cuantización fija)
            if 0 <= val <= 3:
                quant_map = {0: "instant", 1: "next_bar", 2: "next_8", 3: "next_16"}
                quant = quant_map[val]
                target = {"type": "relative", "value": 1}
                pending_action = {"target": target, "quantize": quant}
                ui_feedback_message = f"CC Recibido: Salto rápido (Quant: {quant.upper()})."
            
            # Selección de modo de cuantización global
            elif val in [4, 5, 6, 7, 9]:
                quant_map = {4: "next_4", 5: "next_8", 6: "next_16", 7: "next_bar", 9: "instant"}
                quantize_mode = quant_map[val]
                ui_feedback_message = f"CC Recibido: Modo global -> {quantize_mode.upper()}."

            # Navegación (cuantización global)
            elif val == 10: # Saltar Anterior
                target = {"type": "relative", "value": -1}
                pending_action = {"target": target, "quantize": quantize_mode}
                ui_feedback_message = "CC Recibido: Saltar Anterior."
            elif val == 11: # Saltar Siguiente
                target = {"type": "relative", "value": 1}
                pending_action = {"target": target, "quantize": quantize_mode}
                ui_feedback_message = "CC Recibido: Saltar Siguiente."
            elif val == 12: # Reiniciar Parte
                pending_action = {"target": "restart", "quantize": quantize_mode}
                ui_feedback_message = "CC Recibido: Reiniciar Parte."
            elif val == 13: # Cancelar Acción
                if pending_action:
                    pending_action = None
                    ui_feedback_message = "CC Recibido: Acción cancelada."



def send_midi_command(command: str):
    """Envía un comando MIDI a todos los puertos de salida."""
    global ui_feedback_message
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
    """Gestiona el final de la secuencia de la canción."""
    global ui_feedback_message
    clock_state.status = "FINISHED"
    send_osc_song_end()
    reset_song_state_on_stop() # Resetea los contadores
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


def get_feedback_text():
    """Muestra el último mensaje de feedback en la UI."""
    return HTML(f"<style fg='#888888'>{ui_feedback_message}</style>")



def get_action_status_text():
    """Muestra el modo de cuantización y la acción pendiente."""
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

    return HTML(f"<b>Quant:</b> <style bg='#333333'>[{quant_str}]</style> | <b>Pending Action:</b> <style bg='#333333'>[{action_str}]</style>")

def get_key_legend_text():
    """Muestra la leyenda de los controles de teclado."""
    line1 = "<b>[←→:</b> Nav] <b>[↑:</b> Restart Part] <b>[↓:</b> Cancel] "
    line2 = "<b>[0-3:</b> Quick Jump] <b>[4-7,9:</b> Set Quantize] "
    line3 = "<b>[.:</b> Go to Part]"
    return HTML(f"<style fg='#666666'>{line1}{line2}{line3}</style>")

# --- UI Functions ---
def get_part_name_text():
    """Genera el encabezado de la aplicación, incluyendo el nombre de la parte."""
    app_title_line = f"<style fg='#888888'>miditema - {song_state.song_name}</style>"

    part_info_str = "---"
    part_to_display = None

    if song_state.current_part_index != -1:
        part_to_display = song_state.parts[song_state.current_part_index]
    elif song_state.parts:
        part_to_display = song_state.parts[0]

    if part_to_display:
        name = part_to_display.get('name', '---')
        bars = part_to_display.get('bars', 0)
        part_info_str = f"{name} ({bars} compases)"
    
    # Centrar el nombre en un ancho fijo (ej. 80) para consistencia
    centered_name = part_info_str.center(80)
    part_name_line = f"<style bg='#222222' fg='ansiwhite' bold='true'>{centered_name}</style>"

    return HTML(app_title_line + "\n" + part_name_line)


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
    """Calcula y muestra la siguiente parte que se va a reproducir."""
    if clock_state.status != "PLAYING":
        return ""

    # Simular la búsqueda de la siguiente parte sin cambiar el estado real
    next_index, _ = find_next_valid_part_index("+1", song_state.current_part_index, song_state.pass_count)

    # Si no se encuentra una parte siguiente válida, es el final de la canción.
    if next_index is None:
        return HTML("<style fg='#888888'>Siguiente >> Fin</style>")

    # Si se encontró una parte, mostrar su información.
    part = song_state.parts[next_index]
    name = part.get('name', 'N/A')
    bars = part.get('bars', 0)
    next_part_str = f" >> {name} ({bars})"
    return HTML(f"<style fg='#888888'>{next_part_str}</style>")




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

    output_lines = []
    padding = " " * 10

    for row_start in range(0, total_bars, 8):
        line1 = ""
        line2 = ""
        for i in range(row_start, min(row_start + 8, total_bars)):
            bar_index_0based = i
            
            style = "fg='#888888'" # Estilo por defecto (compás futuro normal)
            
            if bar_index_0based < consumed_bars:
                style = "fg='#444444'" # Compás ya consumido
            elif bar_index_0based == consumed_bars and clock_state.status == "PLAYING":
                remaining_bars_to_endpoint = endpoint_bar - bar_index_0based
                if remaining_bars_to_endpoint == 1:
                    style = "fg='ansired' bold='true'"
                elif remaining_bars_to_endpoint <= 4:
                    style = "fg='ansiyellow' bold='true'"
                else:
                    style = "fg='ansicyan' bold='true'"
            elif pending_action and bar_index_0based >= endpoint_bar:
                 style = "fg='#444444'" # Compás que se saltará
            
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
    global app_ui_instance, midi_input_port, midi_output_ports, osc_client, osc_address

    print("MIDItema\n")
    parser = argparse.ArgumentParser(prog="miditema", description="Contador de compases esclavo de MIDI Clock.")
    parser.add_argument("song_file", nargs='?', default=None, help=f"Nombre del archivo de canción (sin .json) en ./{SONGS_DIR_NAME}/.")
    args = parser.parse_args()

    config = load_config()
    # --- Configuración de Entrada de Clock ---
    clock_source_name = config.get("clock_source")
    selected_port_name = None
    available_ports = mido.get_input_names()

    if not available_ports:
        print("[!] Error: No se encontraron puertos de entrada MIDI.")
        print("Asegúrate de que tus dispositivos están conectados y el backend MIDI (ej. rtmidi) está instalado.")
        return

    if clock_source_name:
        selected_port_name = find_port_by_substring(available_ports, clock_source_name)
        if selected_port_name:
            print(f"[*] Fuente de clock '{selected_port_name}' encontrada desde la configuración.")
        else:
            print(f"[!] La fuente de clock '{clock_source_name}' de la configuración no coincide con ningún puerto.")

    if not selected_port_name:
        selected_port_name = interactive_selector(available_ports, "Selecciona la fuente de MIDI Clock")
        if not selected_port_name:
            print("[!] No se seleccionó ninguna fuente. Saliendo.")
            return

    # --- Configuración de Salidas MIDI ---
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
        global pc_output_port, pc_channel, midi_control_port
        pc_device_name = midi_config.get("device_out")
        pc_channel_config = midi_config.get("channel_out", 1) # Por defecto canal 1

        if pc_device_name:
            pc_port_name = find_port_by_substring(mido.get_output_names(), pc_device_name)
            if pc_port_name:
                try:
                    pc_output_port = mido.open_output(pc_port_name)
                    # El canal del usuario es 1-16, Mido usa 0-15
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
                    print("[!] Advertencia: El puerto de control es el mismo que el de clock.")
                    midi_control_port = midi_input_port
                else:
                    try:
                        midi_control_port = mido.open_input(control_port_name)
                        print(f"[*] Puerto de entrada '{control_port_name}' abierto para control MIDI.")
                    except Exception as e:
                        print(f"[!] No se pudo abrir el puerto de control '{control_port_name}': {e}")
            else:
                print(f"[!] El dispositivo de control '{control_device_key}' no fue encontrado.")

    osc_config = config.get("osc_configuration", {}).get("send", {})
    if osc_config:
        ip = osc_config.get("ip", "127.0.0.1")
        port = osc_config.get("port")
        osc_address = osc_config.get("address")
        if port and osc_address:
            try:
                osc_client = udp_client.SimpleUDPClient(ip, port)
                print(f"[*] Cliente OSC configurado para enviar a {ip}:{port} en la dirección '{osc_address}'")
            except Exception as e:
                print(f"Error configurando el cliente OSC: {e}")
        else:
            print("Advertencia: La configuración OSC está incompleta (falta 'port' o 'address').")


    # 2. Seleccionar Canción
    selected_song_path = None
    if args.song_file:
        path = SONGS_DIR / f"{args.song_file}.json"
        if path.is_file():
            selected_song_path = path
        else:
            print(f"[!] El archivo de canción '{args.song_file}' no se encontró.")
    
    if not selected_song_path:
        SONGS_DIR.mkdir(exist_ok=True)
        available_songs = [f.stem for f in SONGS_DIR.glob("*.json")]
        if not available_songs:
            print(f"[!] No se encontraron canciones en la carpeta './{SONGS_DIR_NAME}/'.")
            print("Crea un archivo .json de canción y vuelve a intentarlo.")
            return
        
        print()
        selected_song_name = interactive_selector(available_songs, "Selecciona una canción")
        if not selected_song_name:
            print("[!] No se seleccionó ninguna canción. Saliendo.")
            return
        selected_song_path = SONGS_DIR / f"{selected_song_name}.json"

    if not load_song_file(selected_song_path):
        return # Salir si la canción no es válida

    # 3. Iniciar MIDI y Lógica
    try:
        midi_input_port = mido.open_input(selected_port_name)
        clock_state.source_name = selected_port_name
        print(f"[*] Escuchando MIDI Clock en '{selected_port_name}'...")
    except Exception as e:
        print(f"[!] Error abriendo el puerto MIDI '{selected_port_name}': {e}")
        return

    listener_thread = threading.Thread(target=midi_input_listener, daemon=True)
    listener_thread.start()

    if midi_control_port and midi_control_port is not midi_input_port:
        control_listener_thread = threading.Thread(target=midi_control_listener, daemon=True)
        control_listener_thread.start()
    else:
        # Si el puerto es el mismo, la lógica se manejará en el hilo principal de clock
        # (Esto requiere una modificación futura, por ahora separamos)
        control_listener_thread = None 

    signal.signal(signal.SIGINT, signal_handler)
   
    # 4. Iniciar Interfaz de Usuario
    kb = KeyBindings()
    
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
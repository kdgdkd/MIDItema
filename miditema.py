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
app_ui_instance = None
midi_input_port = None
midi_output_ports = []
beat_flash_end_time = 0
osc_client = None
osc_address = None
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

def start_next_part():
    """La lógica principal para determinar qué parte de la canción reproducir a continuación."""
    while True: # Bucle para saltar partes que no se deben reproducir
        song_state.current_part_index += 1

        # Si hemos pasado la última parte, envolvemos y aumentamos el contador de pasadas
        if song_state.current_part_index >= len(song_state.parts):
            song_state.current_part_index = 0
            song_state.pass_count += 1

        part = song_state.parts[song_state.current_part_index]
        pattern = part.get("repeat_pattern")

        play_this_part = False
        # Lógica de repeat_pattern
        if pattern is None or pattern is True:
            play_this_part = True
        elif pattern is False:
            if song_state.pass_count == 0:
                play_this_part = True
        elif isinstance(pattern, list) and pattern:
            pattern_index = song_state.pass_count % len(pattern)
            if pattern[pattern_index]:
                play_this_part = True

        if play_this_part:
            song_state.remaining_beats_in_part = part.get("bars", 0) * song_state.time_signature_numerator
            send_osc_part_change(song_state.song_name, song_state.current_part_index, part)
            # Si una parte válida tiene 0 compases, la saltamos para evitar bucles infinitos
            if song_state.remaining_beats_in_part > 0:
                break # Salimos del bucle while porque hemos encontrado una parte para reproducir
        
        # Si llegamos aquí, la parte actual se salta, y el bucle while continúa a la siguiente.

def process_song_tick():
    """Llamado en cada "beat" de la canción (definido por time_division)."""
    global beat_flash_end_time
    if clock_state.status != "PLAYING": return

    song_state.remaining_beats_in_part -= 1
    
    if song_state.remaining_beats_in_part > 0 and \
       song_state.remaining_beats_in_part % song_state.time_signature_numerator == 0:
        beat_flash_end_time = time.time() + 0.1 # Activar flash por 0.1 segundos

    if song_state.remaining_beats_in_part <= 0:
        start_next_part()

def midi_input_listener():
    """El hilo principal que escucha los mensajes MIDI y actualiza el estado."""
    global midi_input_port, clock_state, song_state
    
    while not SHUTDOWN_FLAG:
        if not midi_input_port:
            time.sleep(0.1)
            continue

        msg = midi_input_port.poll()
        if not msg:
            time.sleep(0.001)
            continue

        if msg.type == 'start':
            clock_state.status = "PLAYING"
            reset_song_state_on_stop()
            start_next_part()
        elif msg.type == 'stop':
            clock_state.status = "STOPPED"
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
                    if len(clock_state.tick_times) > 96: # Promediar sobre las últimas 4 negras
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

def send_midi_command(command: str):
    """Envía un comando MIDI a todos los puertos de salida."""
    global ui_feedback_message
    if not midi_output_ports:
        ui_feedback_message = "Info: No hay puerto de control remoto configurado."
        return
    try:
        msg = mido.Message(command)
        for port in midi_output_ports:
            port.send(msg)
            ui_feedback_message = f"Info: Comando '{command}' enviado a '{port.name}'."
    except Exception as e:
        ui_feedback_message = f"Error enviando MIDI: {e}"


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
        ui_feedback_message = f"Error enviando OSC: {e}"


def get_feedback_text():
    """Muestra el último mensaje de feedback en la UI."""
    # return HTML(f"<style fg='#888888'>{ui_feedback_message}</style>")


# --- UI Functions ---
def get_part_name_text():
    """Genera el encabezado de la aplicación, incluyendo el nombre de la parte."""
    app_title_line = f"<style fg='#888888'>miditema - {song_state.song_name}</style>"

    if song_state.current_part_index != -1:
        name = song_state.parts[song_state.current_part_index].get('name', '---')
    elif song_state.parts:
        name = song_state.parts[0].get('name', '---')
    else:
        name = "---"
    
    # Centrar el nombre en un ancho fijo (ej. 80) para consistencia
    centered_name = name.center(80)
    part_name_line = f"<style bg='#222222' fg='ansiwhite' bold='true'>{centered_name}</style>"

    return HTML(app_title_line + "\n" + part_name_line)



def get_countdown_text():
    # Lógica para mostrar la cuenta atrás de compases y tiempos
    bar_text = "-0"
    beat_text = "0"
    # Corregido: Fondo oscuro por defecto
    style = "bg='#222222' fg='ansiwhite'"

    if clock_state.status == "PLAYING" and song_state.remaining_beats_in_part > 0:
        sig_num = song_state.time_signature_numerator
        rem_beats = song_state.remaining_beats_in_part
        
        display_beat = (rem_beats - 1) % sig_num + 1
        
        remaining_bars = math.ceil(rem_beats / sig_num)
        display_bar = -(remaining_bars - 1)
        
        bar_text = f"{display_bar}"
        if remaining_bars == 1: bar_text = "-0"
        beat_text = f"{display_beat}"

        if remaining_bars == 1:
            style = "bg='#222222' fg='ansired' bold='true'" # Último compás en rojo
        elif remaining_bars <= 4:
            style = "bg='#222222' fg='ansiyellow' bold='true'" # Aviso en amarillo
    
    # Nuevo: El flash tiene prioridad sobre otros estilos
    if time.time() < beat_flash_end_time:
        style = "bg='#cccccc' fg='ansiblack' bold='true'"

    countdown_str = f"{bar_text}<style fg='#888888'>.</style>{beat_text}"
    return HTML(f"<style {style}>{countdown_str}</style>")


def get_next_part_text():
    """Calcula y muestra la siguiente parte que se va a reproducir."""
    if clock_state.status != "PLAYING":
        return ""

    # Simular la búsqueda de la siguiente parte sin cambiar el estado real
    temp_index = song_state.current_part_index
    temp_pass_count = song_state.pass_count

    for _ in range(len(song_state.parts) * 2): # Bucle de seguridad
        temp_index += 1
        if temp_index >= len(song_state.parts):
            temp_index = 0
            temp_pass_count += 1

        part = song_state.parts[temp_index]
        pattern = part.get("repeat_pattern")
        
        play_this_part = False
        if pattern is None or pattern is True:
            play_this_part = True
        elif pattern is False:
            if temp_pass_count == 0: play_this_part = True
        elif isinstance(pattern, list) and pattern:
            if pattern[temp_pass_count % len(pattern)]: play_this_part = True


        if play_this_part:
            name = part.get('name', 'N/A')
            bars = part.get('bars', 0)
            # Corregido: Sin prefijo y sin centrado
            next_part_str = f" >> {name} ({bars})"
            return HTML(f"<style fg='#888888'>{next_part_str}</style>")

    return HTML("<style fg='#888888'>Siguiente >> Fin</style>")



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

    output_lines = []
    padding = " " * 10 # Misma indentación que el título

    for row_start in range(0, total_bars, 8):
        line1 = ""
        line2 = ""
        for i in range(row_start, min(row_start + 8, total_bars)):
            bar_index = i + 1
            if bar_index <= consumed_bars:
                style = "fg='#444444'"
            elif bar_index == consumed_bars + 1 and clock_state.status == "PLAYING":
                remaining_bars = total_bars - consumed_bars
                if remaining_bars == 1:
                    style = "fg='ansired' bold='true'" # Último compás
                elif remaining_bars <= 4:
                    style = "fg='ansiyellow' bold='true'" # Aviso
                else:
                    style = "fg='ansicyan' bold='true'" # Normal
            else:
                style = "fg='#888888'"
            
            block = "██  "
            line1 += f"<style {style}>{block}</style>"
            line2 += f"<style {style}>{block}</style>"
        
        output_lines.append(padding + line1)
        output_lines.append(padding + line2)

        if row_start + 8 < total_bars:
            output_lines.append("")
    
    # Nuevo: Lógica para asegurar una altura mínima de 4 filas de bloques
    # 4 filas = 8 líneas de texto (2 por fila) + 3 separadores = 11 líneas
    target_height = 11
    while len(output_lines) < target_height:
        output_lines.append("")
            
    return HTML("\n".join(output_lines))



def get_status_line_text():
    status = clock_state.status.ljust(10)
    # Corregido: Formato a 0 decimales
    bpm = f"{clock_state.bpm:.0f} BPM".ljust(12)
    source = f"Fuente: {clock_state.source_name}"
    return HTML(f"{status} | {bpm} | {source}")

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
    clock_alias = config.get("clock_source_alias")
    selected_port_name = None
    available_ports = mido.get_input_names()

    if not available_ports:
        print("[!] Error: No se encontraron puertos de entrada MIDI.")
        print("Asegúrate de que tus dispositivos están conectados y el backend MIDI (ej. rtmidi) está instalado.")
        return

    if clock_alias:
        selected_port_name = find_port_by_substring(available_ports, clock_alias)
        if selected_port_name:
            print(f"[*] Fuente de clock '{selected_port_name}' encontrada desde {CONF_FILE_NAME}.")
        else:
            print(f"[!] El alias '{clock_alias}' de {CONF_FILE_NAME} no coincide con ningún puerto.")

    if not selected_port_name:
        selected_port_name = interactive_selector(available_ports, "Selecciona la fuente de MIDI Clock")
        if not selected_port_name:
            print("[!] No se seleccionó ninguna fuente. Saliendo.")
            return
            return

    remote_alias = config.get("remote_control_alias")
    if remote_alias:
        output_port_name = find_port_by_substring(mido.get_output_names(), remote_alias)
        if output_port_name:
            try:
                port = mido.open_output(output_port_name)
                midi_output_ports.append(port)
                print(f"[*] Puerto de salida '{output_port_name}' abierto para control remoto.")
            except Exception as e:
                print(f"[!] No se pudo abrir el puerto de salida '{output_port_name}': {e}")
        else:
            print(f"[!] El alias de control remoto '{remote_alias}' no fue encontrado.")

    osc_config = config.get("osc_configuration", {}).get("send")
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

    signal.signal(signal.SIGINT, signal_handler)

    # 4. Iniciar Interfaz de Usuario
    kb = KeyBindings()
    @kb.add('q', eager=True)
    @kb.add('c-c', eager=True)
    def _(event):
        event.app.exit()

    @kb.add('enter')
    @kb.add(' ')
    def _(event):
        """Envía Start/Stop."""
        if clock_state.status == "STOPPED":
            send_midi_command('start')
        else:
            send_midi_command('stop')


    root_container = HSplit([
        Window(content=FormattedTextControl(text=get_part_name_text)),
        # Corregido: Alineación al 25% con VSplit y pesos
        VSplit([
            Window(width=Dimension(weight=1)), # 25% de espacio flexible a la izquierda
            Window(content=FormattedTextControl(text=get_countdown_text), width=40),
            Window(width=Dimension(weight=3)), # 75% de espacio flexible a la derecha
        ]),
        Window(height=1),
        Window(content=FormattedTextControl(text=get_step_sequencer_text)),
        Window(content=FormattedTextControl(text=get_next_part_text)),
        Window(content=FormattedTextControl("-" * 80), height=1),
        Window(content=FormattedTextControl(text=get_status_line_text)),
        Window(content=FormattedTextControl(text=get_feedback_text)), # Nueva línea de feedback
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
        # Nuevo: Cerrar puertos de salida
        for port in midi_output_ports:
            port.close()
        if listener_thread.is_alive():
            listener_thread.join(timeout=0.2)
        print("Detenido.")

if __name__ == "__main__":  
    main()
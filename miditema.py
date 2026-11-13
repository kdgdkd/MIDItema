"""
MIDItema - Contador de compases esclavo de MIDI Clock.

Este módulo es un facade ligero sobre `session.MiditemaSession`:
- Mantiene una única instancia `_session` y reenvía los accesos vía __getattr__ / __setattr__
  para preservar la compatibilidad con `tui.py` (que accede como `miditema.song_state`,
  `miditema.handle_start()`, etc.).
- Re-exporta dataclasses y funciones puras para los tests (`from miditema import SongState`,
  `normalize_repeat_pattern`, etc.).
- Contiene la CLI (`main()`), el `signal_handler` y el arranque de logging.
"""
import argparse
import logging
import signal
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import mido
import json5

# Re-exports para tests y para tui.py
from ui_helpers import (  # noqa: F401
    TITLE_COLOR_PALETTE,
    FG_COLOR_PALETTE,
    _load_palettes,
    _resolve_color_style,
)
from session import (  # noqa: F401
    MiditemaSession,
    ClockState,
    SongState,
    PlaylistState,
    GlobalPartInfo,
    GlobalPartsManager,
    normalize_repeat_pattern,
    _find_next_valid_part_index,
    _is_part_active_in_loop,
    _resolve_value,
    SONGS_DIR_NAME,
    CONF_FILE_NAME,
    MIDI_PPQN,
)

try:
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
    import msvcrt
    def get_char_non_blocking():
        if msvcrt.kbhit():
            try:
                return msvcrt.getch().decode('utf-8')
            except UnicodeDecodeError:
                return None
        return None

import tui as tui


logger = logging.getLogger("miditema")


_session = MiditemaSession()


def setup_logging(debug: bool):
    import midicore.logging as _mc_logging
    _mc_logging.setup("miditema", log_file=Path("miditema.log"), verbose=debug)


def print_midi_backend_info():
    """Imprime información sobre el backend MIDI en uso (útil para diagnóstico en Linux)."""
    try:
        backend = mido.backend
        logger.info(f"[*] Backend MIDI: {backend.module.__name__}")
        logger.info(f"[*] API: {getattr(backend.module, 'api', 'N/A')}")
    except Exception as e:
        logger.warning(f"[!] No se pudo obtener info del backend MIDI: {e}")


def signal_handler(sig, frame):
    _session.shutdown_flag = True
    if _session.app_ui_instance:
        _session.app_ui_instance.exit(result="shutdown")


# Facade: reenvía accesos desconocidos a la sesión.
# Esto permite que tui.py acceda como `miditema.song_state`, `miditema.handle_start()`,
# `miditema.pending_action = X`, etc., sin tener que tocar la TUI.
class _ModuleFacade(types.ModuleType):
    def __getattr__(self, name):
        try:
            return getattr(_session, name)
        except AttributeError:
            raise AttributeError(f"module 'miditema' has no attribute {name!r}")

    def __setattr__(self, name, value):
        if not name.startswith('_') and hasattr(_session, name):
            setattr(_session, name, value)
        else:
            super().__setattr__(name, value)


sys.modules[__name__].__class__ = _ModuleFacade



def main():
    initial_data = None
    initial_load_success = True
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

    setup_logging(args.debug)
    print("MIDItema\n")
    print_midi_backend_info()

    if args.no_output:
        _session.outputs_enabled = False
        logger.info("[*] Outputs desactivados desde inicio.")

    if args.quant:
        quant_map = {"bar": "next_bar", "4": "next_4", "8": "next_8", "16": "next_16", "32": "next_32", "instant": "instant"}
        user_mode = quant_map.get(args.quant, args.quant)
        if user_mode in quant_map.values():
            _session.quantize_mode = user_mode
            logger.info(f"[*] Default quantization {_session.quantize_mode.upper()}")
        else:
            logger.warning(f"[!] Invalid quantization '{args.quant}'. Using default '{_session.quantize_mode}'.")

    config_file_to_load = args.conf if args.conf else CONF_FILE_NAME
    _session.config = _session.load_config(config_file_to_load)
    _session.config['_source_file'] = config_file_to_load

    if args.song_file:
        is_dir_mode = args.song_file.endswith(('/', '\\')) or Path(args.song_file).is_dir()
        user_path = Path(args.song_file)

        if is_dir_mode:
            if not user_path.is_dir():
                logger.warning(f"[!] Error: El directorio '{user_path}' no existe.")
                return

            logger.info(f"[*] Directorio '{user_path.name}' detectado. Cargando como playlist...")
            _session.SONGS_DIR = user_path
            json_files = sorted(list(_session.SONGS_DIR.glob("*.json")) + list(_session.SONGS_DIR.glob("*.json5")))
            if not json_files:
                logger.warning(f"[!] Error: El directorio '{user_path.name}' no contiene archivos .json o .json5.")
                return

            playlist_elements = [{"filepath": f.name} for f in json_files]
            initial_data = {"playlist_name": user_path.name, "songs": playlist_elements}
            _session.loaded_filename = user_path.name
        else:
            filename = user_path.name if user_path.name.lower().endswith((".json", ".json5")) else f"{user_path.name}.json"
            selected_file_path = _session.SONGS_DIR / filename
            if not selected_file_path.is_file():
                logger.warning(f"[!] El archivo '{filename}' no se encontró en la carpeta '{SONGS_DIR_NAME}'.")
                args.song_file = None
            else:
                try:
                    with selected_file_path.open('r', encoding='utf-8') as f:
                        initial_data = json5.load(f)
                    _session.loaded_filename = selected_file_path.stem
                except Exception as e:
                    logger.error(f"Error al leer el archivo '{selected_file_path.name}': {e}")
                    return

    bus_outputs_active = bool(initial_data and initial_data.get("bus_outputs", False))
    _session.bus_outputs = bus_outputs_active
    if bus_outputs_active:
        logger.info("[*] Bus outputs activado — los mensajes se enviaran via bus a midimod.")

    if initial_data and "device_alias" in initial_data:
        _merged_alias = {**_session.config.get("device_alias", {}), **initial_data["device_alias"]}
        _merged_conf = {**_session.config, "device_alias": _merged_alias}
        song_label = _session.loaded_filename if _session.loaded_filename else "archivo de cancion"
        device_errors = _session.setup_devices(_merged_conf,
                                               source_label=f"{config_file_to_load} + {song_label}",
                                               skip_outputs=bus_outputs_active)
    else:
        device_errors = _session.setup_devices(_session.config, source_label=config_file_to_load,
                                               skip_outputs=bus_outputs_active)

    if initial_data:
        if "songs" in initial_data and isinstance(initial_data["songs"], list):
            _session.playlist_state.is_active = True
            _session.playlist_state.playlist_elements = initial_data["songs"]
            _session.playlist_state.playlist_name = initial_data.get("playlist_name", _session.loaded_filename or "Sin nombre")
            if "beats" in initial_data:
                _session.playlist_state.beats = initial_data["beats"]
            elif "bars" in initial_data:
                _session.playlist_state.beats = initial_data["bars"] * 4
            else:
                _session.playlist_state.beats = 2

            logger.info(f"[*] Playlist '{_session.playlist_state.playlist_name}' cargada con {len(_session.playlist_state.playlist_elements)} canciones.")

            _session.global_parts_manager.build_global_parts_list()

            playlist_mode = initial_data.get("mode", "song")
            _session.repeat_override_active = playlist_mode.lower() == "song"
            if args.song_mode:
                _session.repeat_override_active = True
                _session.user_mode_override = True
            elif args.loop_mode:
                _session.repeat_override_active = False
                _session.user_mode_override = False

            mode_str = "SONG MODE" if _session.repeat_override_active else "LOOP MODE"
            logger.info(f"[*] Inicio en {mode_str}.")

            if not _session.load_song_from_playlist(0):
                logger.warning("[!] Error: No se pudo cargar la primera canción de la playlist.")
                logger.info("[*] La TUI se abrirá de todos modos. Puedes cargar otro archivo desde el menú.")
                initial_load_success = False
        else:
            if not _session.load_song_file(data=initial_data):
                logger.warning("[!] Error: No se pudo cargar la canción.")
                logger.info("[*] La TUI se abrirá de todos modos. Puedes cargar otro archivo desde el menú.")
                initial_load_success = False
            if args.song_mode:
                _session.repeat_override_active = True
                _session.user_mode_override = True
            elif args.loop_mode:
                _session.repeat_override_active = False
                _session.user_mode_override = False

    _session.setup_bus()
    _session.start_motor()

    if device_errors:
        logger.warning("\n" + "=" * 60)
        logger.warning("ADVERTENCIA: Se encontraron errores al inicializar dispositivos:")
        logger.warning("=" * 60)
        for error in device_errors:
            logger.warning(f"  {error}")
        logger.warning("=" * 60)
        print("\nOpciones:")
        print("  [Enter] - Continuar de todos modos")
        print("  [d] - Reiniciar en modo debug")
        print("  [q] - Salir")

        try:
            choice = input("\nElige una opción: ").strip().lower()
            if choice == 'q':
                print("Saliendo...")
                return
            elif choice == 'd':
                print("\nReiniciando en modo debug...")
                cmd = [sys.executable] + sys.argv
                if '--debug' not in cmd:
                    cmd.append('--debug')
                subprocess.run(cmd)
                return
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo...")
            return

    if not _session._bus_clock_alias:
        listener_thread = threading.Thread(target=_session.midi_input_listener, daemon=True)
        listener_thread.start()
    control_listener_threads = []
    for info in list(_session.port_registry.iter_ports()):
        if info.direction != "in" or info.alias == "clock":
            continue
        if info.alias in _session._shared_clock_aliases:
            continue  # shared port — handled inline in the clock listener
        t = threading.Thread(target=_session.midi_control_listener_for, args=(info.alias,), daemon=True)
        t.start()
        control_listener_threads.append(t)

    signal.signal(signal.SIGINT, signal_handler)

    if args.debug:
        logger.info("\n--- MODO DEPURACIÓN ACTIVO ---")
        logger.info("El motor está corriendo. Presiona 'Tab' para lanzar la TUI, Ctrl+C para salir.")

        def print_debug_status():
            status = _session.clock_state.status
            bpm = _session.clock_state.bpm
            part_name = "N/A"
            part_idx = _session.song_state.current_part_index

            if 0 <= part_idx < len(_session.song_state.parts):
                part_name = _session.song_state.parts[part_idx].get('name', 'N/A')

            action_str = "None"
            if _session.pending_action:
                action_str = str(_session.pending_action.get('target', 'N/A'))

            print(
                f"Status: {status} | BPM: {bpm:.1f} | Part: {part_name} ({part_idx+1}) | Pending: {action_str}      ",
                end='\r'
            )
            sys.stdout.flush()

        try:
            while not _session.shutdown_flag:
                char = get_char_non_blocking()
                if char == '\t':
                    logger.info("\nLanzando TUI...")
                    break
                print_debug_status()
                time.sleep(0.1)
        except KeyboardInterrupt:
            _session.shutdown_flag = True

    if not _session.shutdown_flag:
        _session.app_ui_instance = tui.MiditemaApp(miditema_module=sys.modules[__name__])
        if not initial_load_success:
            _session.set_feedback_message("[!] Error en carga inicial. Usa el menú para abrir un archivo.", duration=10)

        _session.app_ui_instance.run()

    _session.shutdown_flag = True
    logger.info("\nCerrando...")
    _session.port_registry.close_all()

    if _session.presence:
        _session.presence.stop()
    if _session.bus:
        _session.bus.stop()
    if listener_thread.is_alive():
        listener_thread.join(timeout=0.2)
    for t in control_listener_threads:
        if t.is_alive():
            t.join(timeout=0.2)
    logging.shutdown()
    print("Detenido.")


if __name__ == "__main__":
    main()

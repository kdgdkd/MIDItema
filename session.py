"""
MIDItema session: encapsula todo el estado y motor del secuenciador.

Contiene:
- Dataclasses de estado (ClockState, SongState, PlaylistState)
- GlobalPartInfo / GlobalPartsManager
- Funciones puras del sequencer (re-importadas por miditema para los tests)
- Clase MiditemaSession con todo el motor (triggers, jumps, listeners, I/O)
"""
import mido
import time
import math
import random
import queue
import threading
import logging
import json5
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from midicore.aliases import AliasMap as _AliasMap, resolve as _alias_resolve, ALIAS_TYPE_OSC
from midicore.output import parse_action_block as _parse_action_block
from midicore.transport import TransportReceiver as _TransportReceiver
from midicore.ports import find_port_by_substring, PortRegistry
from midicore.osc import OscClient
from midicore.clock import ClockListener
from midicore.config import deep_merge
from midicore import LocalBus, bus_topics, AppPresence
from midicore.protocol import (
    MIDIMOD_OSC_VERSION,
    MIDIMOD_OSC_SEQ_PLAY,
    MIDIMOD_OSC_SEQ_STOP,
    MIDIMOD_MIDI_CHANNEL,
    MIDIMOD_CC_VERSION,
    MIDIMOD_CC_SEQ_PLAY,
    MIDIMOD_CC_SEQ_STOP,
)

from schema_validator import MIDItemaValidator


logger = logging.getLogger("miditema")


# --- Constantes globales ---
SONGS_DIR_NAME = "temas"
CONF_FILE_NAME = "miditema.conf.json"
MIDI_PPQN = 24  # MIDI Clock Standard, no configurable


# --- State Dataclasses ---

@dataclass(eq=False)
class ClockState:
    """Almacena el estado del reloj MIDI entrante."""
    status: str = "STOPPED"
    bpm: float = 0.0
    source_name: str = "Ninguna"
    source_id: Any = None
    tick_times: list[float] = field(default_factory=list)
    last_tick_time: float = 0.0
    start_time: float = 0.0
    paused_set_elapsed_time: float = 0.0


@dataclass(eq=False)
class SongState:
    """Almacena el estado de la canción y la secuencia."""
    song_name: str = "Elige canción/setlist en el menú"
    song_color: Optional[str] = None
    triggers: dict = field(default_factory=dict)
    parts: list = field(default_factory=list)
    current_part_index: int = -1
    remaining_beats_in_part: int = 0
    pass_count: int = 0
    midi_clock_tick_counter: int = 0
    current_bar_in_part: int = 0
    start_time: float = 0.0
    paused_song_elapsed_time: float = 0.0
    time_signature_numerator: int = 4
    ticks_per_song_beat: int = MIDI_PPQN

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SongState):
            return False
        return (
            self.song_name == other.song_name and
            self.song_color == other.song_color and
            self.parts == other.parts and
            self.current_part_index == other.current_part_index and
            self.remaining_beats_in_part == other.remaining_beats_in_part and
            self.pass_count == other.pass_count and
            self.current_bar_in_part == other.current_bar_in_part and
            self.triggers == other.triggers and
            self.time_signature_numerator == other.time_signature_numerator
        )


@dataclass(eq=False)
class PlaylistState:
    """Almacena el estado de la playlist."""
    is_active: bool = False
    playlist_name: str = "Sin Playlist"
    triggers: dict = field(default_factory=dict)
    playlist_elements: list = field(default_factory=list)
    current_song_index: int = -1
    beats: int = 2

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PlaylistState):
            return False
        return (
            self.is_active == other.is_active and
            self.playlist_name == other.playlist_name and
            self.playlist_elements == other.playlist_elements and
            self.current_song_index == other.current_song_index and
            self.beats == other.beats and
            self.triggers == other.triggers
        )


class GlobalPartInfo:
    """Información de una parte en el contexto global de la playlist."""
    def __init__(self, session, song_index, part_index, part_data, song_name=None, song_color=None):
        self._session = session
        self.song_index = song_index
        self.part_index = part_index
        self.part_data = part_data
        self.song_name = song_name or "Unknown"
        self.song_color = song_color

    @property
    def global_part_index(self):
        return self._session._get_global_part_index(self.song_index, self.part_index)

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
    def __init__(self, session):
        self.session = session
        self.global_parts = []
        self.is_initialized = False

    def build_global_parts_list(self):
        s = self.session
        self.global_parts.clear()

        if not s.playlist_state.is_active:
            for part_idx, part_data in enumerate(s.song_state.parts):
                part_info = GlobalPartInfo(s, 0, part_idx, part_data, s.song_state.song_name, s.song_state.song_color)
                self.global_parts.append(part_info)
        else:
            for song_idx, song_element in enumerate(s.playlist_state.playlist_elements):
                song_parts = s._get_parts_from_playlist_element(song_element)
                song_name = song_element.get("song_name", Path(song_element.get("filepath", "N/A")).stem)
                song_color = song_element.get("color")

                for part_idx, part_data in enumerate(song_parts):
                    part_info = GlobalPartInfo(s, song_idx, part_idx, part_data, song_name, song_color)
                    self.global_parts.append(part_info)

        self.is_initialized = True

    def get_current_global_part_info(self):
        s = self.session
        if not self.is_initialized:
            self.build_global_parts_list()

        current_song_idx = s.playlist_state.current_song_index if s.playlist_state.is_active else 0
        current_part_idx = s.song_state.current_part_index

        for part_info in self.global_parts:
            if part_info.song_index == current_song_idx and part_info.part_index == current_part_idx:
                return part_info
        return None

    def get_next_part_info(self):
        s = self.session
        if not self.is_initialized:
            self.build_global_parts_list()

        action_to_predict = None

        if s.pending_action:
            action_to_predict = s.pending_action
        elif s.part_loop_active and s.song_state.current_part_index == s.part_loop_index:
            return self.get_current_global_part_info()
        elif s.song_state.current_part_index != -1:
            current_part = s.song_state.parts[s.song_state.current_part_index]
            if current_part.get("repeat_pattern") == "repeat":
                return self.get_current_global_part_info()
            else:
                action_to_predict = {"target_type": "part", "target": {"type": "relative", "value": 1}}

        if action_to_predict:
            dest_song_idx, dest_part_idx = s.predict_jump_destination(action_to_predict)
            if dest_song_idx is not None and dest_part_idx is not None:
                for part_info in self.global_parts:
                    if part_info.song_index == dest_song_idx and part_info.part_index == dest_part_idx:
                        return part_info

        return None

    def get_next_parts_queue(self, n: int = 3):
        s = self.session
        if not self.is_initialized:
            self.build_global_parts_list()

        current_song_idx = s.playlist_state.current_song_index if s.playlist_state.is_active else 0
        current_part_idx = s.song_state.current_part_index

        current_global_idx = -1
        for i, part_info in enumerate(self.global_parts):
            if part_info.song_index == current_song_idx and part_info.part_index == current_part_idx:
                current_global_idx = i
                break

        if current_global_idx == -1:
            return self.global_parts[:n]

        results = []
        idx = current_global_idx + 1
        while len(results) < n and idx < len(self.global_parts):
            results.append(self.global_parts[idx])
            idx += 1
        return results


# --- Funciones puras (usadas por tests y por el motor) ---

def normalize_repeat_pattern(pattern: Any) -> Any:
    """Convierte strings 'true'/'false' a booleanos en repeat_pattern."""
    if pattern == "true":
        return True
    elif pattern == "false":
        return False
    return pattern


def _is_part_active_in_loop(part: dict, loop_pass: int) -> bool:
    """Determina si una parte debe sonar en una pasada de bucle específica."""
    pattern = part.get("repeat_pattern")
    if pattern is True or pattern == "repeat":
        return True
    if pattern is False or pattern is None:
        return False
    if isinstance(pattern, list) and pattern:
        index = (loop_pass - 1) % len(pattern)
        return pattern[index]
    return False


def _find_next_valid_part_index(parts: list, direction: str, start_index: int, start_pass_count: int, repeat_override: bool) -> tuple[int, int]:
    """Encuentra el índice y el pass_count de la siguiente parte válida."""
    if not parts:
        return None, None

    step = 1 if direction == "+1" else -1

    temp_index = start_index
    temp_pass_count = start_pass_count
    for _ in range(len(parts) * 2):
        temp_index += step

        if temp_index >= len(parts):
            if repeat_override:
                return None, None
            temp_index = 0
            temp_pass_count += 1
        elif temp_index < 0:
            if repeat_override:
                return None, None
            temp_index = len(parts) - 1
            temp_pass_count = max(0, temp_pass_count - 1)

        part = parts[temp_index]
        if part.get("bars", 0) > 0:
            if temp_pass_count == 0 or repeat_override:
                return temp_index, temp_pass_count
            else:
                pattern = part.get("repeat_pattern")
                if pattern is True or pattern == "repeat":
                    return temp_index, temp_pass_count
                if isinstance(pattern, list) and pattern:
                    if pattern[(temp_pass_count - 1) % len(pattern)]:
                        return temp_index, temp_pass_count

    return None, None


def _find_next_part_index_manual(parts: list, direction: str, start_index: int, start_pass_count: int, repeat_override: bool) -> tuple[int, int]:
    """Como _find_next_valid_part_index, pero para navegación MANUAL: salta sólo partes con bars==0, ignora repeat_pattern."""
    if not parts:
        return None, None

    step = 1 if direction == "+1" else -1

    temp_index = start_index
    temp_pass_count = start_pass_count
    for _ in range(len(parts) * 2):
        temp_index += step

        if temp_index >= len(parts):
            if repeat_override:
                return None, None
            temp_index = 0
            temp_pass_count += 1
        elif temp_index < 0:
            if repeat_override:
                return None, None
            temp_index = len(parts) - 1
            temp_pass_count = max(0, temp_pass_count - 1)

        if parts[temp_index].get("bars", 0) > 0:
            return temp_index, temp_pass_count

    return None, None


def _resolve_value(value: Any, context: dict) -> Any:
    """Resuelve un valor contra el contexto del trigger."""
    if isinstance(value, str) and value in context:
        return context[value]
    return value


def _build_mido_message(action: dict, context: dict) -> Optional[mido.Message]:
    """Build a mido.Message from a trigger action dict."""
    try:
        parsed = _parse_action_block(action, suffix='_out')
    except ValueError as e:
        logger.warning(f"_build_mido_message: {e}")
        return None

    ev = parsed.event
    if ev is None:
        return None

    ch = max(0, min(15, int(_resolve_value(parsed.channel or 0, context))))
    v1 = _resolve_value(parsed.value_1, context) if parsed.value_1 is not None else None
    v2 = _resolve_value(parsed.value_2, context) if parsed.value_2 is not None else None

    if ev == "program_change" and v1 is None:
        v1 = context.get("part_index", 0)
    elif ev == "song_select" and v1 is None:
        v1 = context.get("song_index", 0)

    try:
        if ev == "note_on":
            return mido.Message("note_on", channel=ch, note=max(0, min(127, int(v1 or 0))), velocity=max(0, min(127, int(v2 or 64))))
        elif ev == "note_off":
            return mido.Message("note_off", channel=ch, note=max(0, min(127, int(v1 or 0))), velocity=max(0, min(127, int(v2 or 0))))
        elif ev == "control_change":
            return mido.Message("control_change", channel=ch, control=max(0, min(127, int(v1 or 0))), value=max(0, min(127, int(v2 or 0))))
        elif ev == "program_change":
            return mido.Message("program_change", channel=ch, program=max(0, min(127, int(v1 or 0))))
        elif ev == "pitchwheel":
            return mido.Message("pitchwheel", channel=ch, pitch=int(v1 or 0))
        elif ev == "aftertouch":
            return mido.Message("aftertouch", channel=ch, value=max(0, min(127, int(v1 or 0))))
        elif ev == "polytouch":
            return mido.Message("polytouch", channel=ch, note=max(0, min(127, int(v1 or 0))), value=max(0, min(127, int(v2 or 0))))
        elif ev == "song_select":
            return mido.Message("song_select", song=max(0, min(127, int(v1 or 0))))
        elif ev in ("start", "stop", "continue"):
            return mido.Message(ev)
        else:
            return None
    except (ValueError, TypeError) as e:
        logger.warning(f"_build_mido_message: cannot build {ev!r}: {e}")
        return None


# --- MiditemaSession ---

class MiditemaSession:
    """Estado y motor completo del secuenciador. Una instancia por proceso."""

    def __init__(self):
        # Estado de runtime
        self.config = {}
        self.clock_state = ClockState()
        self.song_state = SongState()
        self.playlist_state = PlaylistState()
        self.global_parts_manager = GlobalPartsManager(self)
        self.pending_action = None
        self.repeat_override_active = True
        self.user_mode_override: Optional[bool] = None
        self.part_loop_active = False
        self.part_loop_index = -1
        self._outputs_enabled_before_loop_part = None
        self.quantize_mode = "next_8"
        self.goto_input_active = False
        self.goto_input_buffer = ""
        self.app_ui_instance = None
        self.initial_outputs_sent = False
        self.pending_collapsed_outputs = None
        self._part_early_fired = False
        self.outputs_enabled = True
        self.beat_flash_end_time = 0
        self.ui_feedback_message = ""
        self.feedback_expiry_time = 0
        self.feedback_sticky = False
        self.feedback_level = "info"
        self.loaded_filename = ""
        self.previous_song_index = -1
        self._last_used_device = None
        self.last_triggered_song_index = -1
        self.port_registry = PortRegistry()
        self._shared_clock_aliases: set[str] = set()
        self.osc_outputs = {}
        self.midi_osc_event_log: deque = deque(maxlen=200)
        self._parts_file_cache: dict = {}
        self.device_last_send_time: dict = {}
        self._watched_file_path = None
        self._watched_file_mtime: float = 0.0
        self.file_changed_on_disk: bool = False

        self.session_mode: bool = False

        # Bus outputs — when True, output actions are published to bus
        self.bus_outputs: bool = False

        # Bus
        self.bus: Optional[LocalBus] = None
        self.presence: Optional[AppPresence] = None
        self.midimod_active_version: Optional[int] = None
        self.midimod_sequencer_states: dict = {}
        self._bus_clock_alias: Optional[str] = None

        # Motor de eventos serializado
        self._event_queue: queue.Queue = queue.Queue()
        self._motor_thread: Optional[threading.Thread] = None
        self._clock_stale: bool = False
        self._playback_start_count: int = 0

        # Mutables del proceso
        self.SONGS_DIR = Path(f"./{SONGS_DIR_NAME}")
        self.shutdown_flag = False

    # --- Setup de dispositivos ---

    def setup_devices(self, config: dict, source_label: str = CONF_FILE_NAME, skip_outputs: bool = False) -> list[str]:
        """
        Lee 'device_alias' + 'clock_in'/'transport_out' de la config y abre los puertos.

        Formato esperado::

            "device_alias": {
                "MyClock":    "USB MIDI 1",
                "MySynth":    "MicroKorg",
                "VisualsOSC": {"type": "osc", "ip": "127.0.0.1", "port": 9000}
            },
            "clock_in":      "MyClock",
            "transport_out": "MyClock"

        El formato antiguo ('devices.midi_in/midi_out/osc_out') emite un error de migración
        y rechaza la carga.
        """
        errors = []

        # Detect old format and reject with migration message
        devices_section = config.get("devices")
        if isinstance(devices_section, dict) and any(
            k in devices_section for k in ("midi_in", "midi_out", "osc_out")
        ):
            error_msg = (
                f"FORMATO OBSOLETO en '{source_label}': 'devices.midi_in/midi_out/osc_out' "
                f"ya no está soportado. Migrar a 'device_alias' plano + 'clock_in'/'transport_out'. "
                f"Ver MIGRATION.md."
            )
            logger.error(f"[!!!] {error_msg}")
            errors.append(error_msg)
            return errors

        device_alias = config.get("device_alias", {})
        if not isinstance(device_alias, dict) or not device_alias:
            return errors

        try:
            alias_map = _AliasMap(device_alias)
        except ValueError as e:
            error_msg = f"device_alias inválido en '{source_label}': {e}"
            logger.error(f"[!!!] {error_msg}")
            errors.append(error_msg)
            return errors

        logger.info(f"\n--- Configurando dispositivos desde: {source_label} ---")

        try:
            available_in_ports = mido.get_input_names()
            available_out_ports = mido.get_output_names()
        except Exception as e:
            error_msg = f"Error al obtener puertos MIDI: {e}"
            logger.warning(f"[!] {error_msg}")
            errors.append(error_msg)
            return errors

        clock_in_alias = config.get("clock_in")
        transport_out_alias = config.get("transport_out")
        control_rules = config.get("control") if isinstance(config.get("control"), list) else []
        control_in_aliases = {
            rule.get("device_in") for rule in control_rules
            if isinstance(rule, dict) and rule.get("device_in")
        }

        # Aliases used only as inputs (skip when opening outputs)
        input_only_aliases = set()
        if clock_in_alias:
            input_only_aliases.add(clock_in_alias)
        input_only_aliases.update(control_in_aliases)
        # transport_out needs an output port even if it's also the clock device
        if transport_out_alias:
            input_only_aliases.discard(transport_out_alias)

        # 1. Open clock_in as MIDI input (or mark as bus source if port not found)
        if clock_in_alias:
            if clock_in_alias not in device_alias:
                error_msg = (
                    f"Clock '{clock_in_alias}': alias no encontrado en 'device_alias'. "
                    f"¿Nombre incorrecto? Se tratará como fuente de bus."
                )
                logger.warning(f"[!] {error_msg}")
                errors.append(error_msg)
                self._bus_clock_alias = clock_in_alias
            else:
                port_spec = device_alias[clock_in_alias]
                if not isinstance(port_spec, str):
                    # Bus-type or non-MIDI alias — subscribe via bus
                    self._bus_clock_alias = clock_in_alias
                    logger.info(f"[*] Clock ('{clock_in_alias}'): alias tipo bus, se usará fuente de bus")
                else:
                    port_name = find_port_by_substring(available_in_ports, port_spec)
                    if port_name:
                        try:
                            self.port_registry.open_input("clock", port_name)
                            self.clock_state.source_name = port_name
                            logger.info(f"[*] Clock ('{clock_in_alias}'): '{port_spec}' → '{port_name}'")
                        except Exception as e:
                            error_msg = f"Clock '{clock_in_alias}': Error al abrir '{port_name}' - {e}"
                            logger.warning(f"[!] {error_msg}")
                            errors.append(error_msg)
                            self._bus_clock_alias = clock_in_alias
                            logger.info(
                                f"[*] Clock: fallback a fuente de bus ('{clock_in_alias}') "
                                f"— puerto físico no disponible (puede ser exclusivo en Windows)"
                            )
                    else:
                        # Port not reachable — use bus instead (midimod fans it out)
                        self._bus_clock_alias = clock_in_alias
                        logger.info(f"[*] Clock ('{clock_in_alias}'): '{port_spec}' no encontrado, se usará fuente de bus")

        # 2. Open control device_in ports as MIDI inputs
        for alias in sorted(control_in_aliases):
            if alias == clock_in_alias:
                # Share the clock port for control too
                if self.port_registry.get_input("clock") is not None:
                    self._shared_clock_aliases.add(alias)
                continue
            if self.port_registry.get_input(alias) is not None:
                continue
            if alias not in device_alias:
                error_msg = f"control device_in '{alias}': alias no encontrado en 'device_alias'"
                logger.warning(f"[!] {error_msg}")
                errors.append(error_msg)
                continue
            port_spec = device_alias[alias]
            if not isinstance(port_spec, str):
                error_msg = f"control device_in '{alias}': debe ser alias MIDI (string)"
                logger.warning(f"[!] {error_msg}")
                errors.append(error_msg)
                continue
            port_name = find_port_by_substring(available_in_ports, port_spec)
            if port_name:
                try:
                    self.port_registry.open_input(alias, port_name)
                    logger.info(f"[*] Control In ('{alias}'): '{port_spec}' → '{port_name}'")
                except Exception as e:
                    error_msg = f"Control In '{alias}': Error al abrir '{port_name}' - {e}"
                    logger.warning(f"[!] {error_msg}")
                    errors.append(error_msg)
            else:
                error_msg = f"Control In '{alias}': Puerto no encontrado (buscando '{port_spec}')"
                logger.warning(f"[!] {error_msg}")
                errors.append(error_msg)

        # 3. Open MIDI outputs and OSC clients
        for alias in alias_map:
            resolved_a = _alias_resolve(alias, alias_map)
            if resolved_a.type == ALIAS_TYPE_OSC:
                ip = resolved_a.value.get("ip")
                port_num = resolved_a.value.get("port")
                if ip and port_num:
                    try:
                        self.osc_outputs[alias] = OscClient.get(ip, port_num)
                        logger.info(f"[*] OSC Out '{alias}': configurado para {ip}:{port_num}")
                    except Exception as e:
                        error_msg = f"OSC Out '{alias}' ({ip}:{port_num}): {e}"
                        logger.warning(f"[!] {error_msg}")
                        errors.append(error_msg)
                else:
                    error_msg = f"OSC Out '{alias}': falta 'ip' o 'port'"
                    logger.warning(f"[!] {error_msg}")
                    errors.append(error_msg)
                continue
            if not isinstance(resolved_a.value, str):
                # array, bus, virtual — not applicable in miditema output setup
                continue
            port_spec = resolved_a.value
            if alias in input_only_aliases:
                continue
            if skip_outputs:
                continue
            port_name = find_port_by_substring(available_out_ports, port_spec)
            if port_name:
                try:
                    self.port_registry.open_output(alias, port_name)
                    logger.info(f"[*] MIDI Out '{alias}': '{port_spec}' → '{port_name}'")
                except Exception as e:
                    error_msg = f"MIDI Out '{alias}' ('{port_spec}'): Error al abrir '{port_name}' - {e}"
                    logger.warning(f"[!] {error_msg}")
                    errors.append(error_msg)
            else:
                error_msg = f"MIDI Out '{alias}' ('{port_spec}'): Puerto no encontrado"
                logger.warning(f"[!] {error_msg}")
                errors.append(error_msg)

        if errors:
            logger.warning(f"\n[!] {len(errors)} error(es) encontrado(s) en {source_label}")

        return errors

    # --- Procesamiento de triggers ---

    def _process_trigger_action(self, action: dict, context: dict) -> None:
        """Procesa una única acción de trigger (MIDI u OSC)."""
        logger.debug(f"Processing trigger action: {action}")
        logger.debug(f"Context: {context}")

        # midimod protocol shortcuts
        if "midimod_version" in action:
            version = int(_resolve_value(action["midimod_version"], context))
            device = action.get("device", "midimod")
            if device in self.osc_outputs:
                return self._process_trigger_action(
                    {"device": device, "address": MIDIMOD_OSC_VERSION, "args": [version]}, context
                )
            if self.port_registry.get_output(device) is not None:
                return self._process_trigger_action(
                    {"device": device, "cc": MIDIMOD_CC_VERSION,
                     "channel": MIDIMOD_MIDI_CHANNEL, "value": version},
                    context,
                )
            msg = f"midimod_version: alias '{device}' no encontrado como OSC ni MIDI output"
            logger.warning(f"[!] {msg}")
            self.set_feedback_message(f"[!] {msg}")
            return

        if "midimod_trigger" in action:
            seq_id = str(_resolve_value(action["midimod_trigger"], context))
            stop = action.get("stop", False)
            device = action.get("device", "midimod")
            if device in self.osc_outputs:
                template = MIDIMOD_OSC_SEQ_STOP if stop else MIDIMOD_OSC_SEQ_PLAY
                return self._process_trigger_action(
                    {"device": device, "address": template.format(seq_id=seq_id), "args": []}, context
                )
            if self.port_registry.get_output(device) is not None:
                cc = MIDIMOD_CC_SEQ_STOP if stop else MIDIMOD_CC_SEQ_PLAY
                return self._process_trigger_action(
                    {"device": device, "cc": cc,
                     "channel": MIDIMOD_MIDI_CHANNEL, "value": int(seq_id) if seq_id.isdigit() else 1},
                    context,
                )
            msg = f"midimod_trigger: alias '{device}' no encontrado como OSC ni MIDI output"
            logger.warning(f"[!] {msg}")
            self.set_feedback_message(f"[!] {msg}")
            return

        device_name = action.get("device")

        if device_name:
            self._last_used_device = device_name
        else:
            if self._last_used_device:
                device_name = self._last_used_device
            else:
                device_name = "MIDItema"

        if self.bus_outputs and self.bus:
            try:
                parsed = _parse_action_block(action, suffix='_out')
            except ValueError as e:
                logger.warning(f"bus_outputs payload: {e}")
                return
            ev = parsed.event or "program_change"
            ch = max(0, min(15, int(_resolve_value(parsed.channel or 0, context))))
            v1 = _resolve_value(parsed.value_1, context) if parsed.value_1 is not None else None
            v2 = _resolve_value(parsed.value_2, context) if parsed.value_2 is not None else None
            if ev == "program_change" and v1 is None:
                v1 = context.get("part_index", 0)
            elif ev == "song_select" and v1 is None:
                v1 = context.get("song_index", 0)
            payload = {"device": device_name, "channel": ch, "msg_type": ev}
            if ev == "program_change":
                payload["program"] = max(0, min(127, int(v1 or 0)))
            elif ev == "control_change":
                payload["control"] = max(0, min(127, int(v1 or 0)))
                payload["value"] = max(0, min(127, int(v2 or 0)))
            elif ev in ("note_on", "note_off"):
                payload["note"] = max(0, min(127, int(v1 or 0)))
                payload["velocity"] = max(0, min(127, int(v2 or (64 if ev == "note_on" else 0))))
            elif ev == "song_select":
                payload["song"] = max(0, min(127, int(v1 or 0)))
            elif ev == "pitchwheel":
                payload["pitch"] = int(v1 or 0)
            elif ev == "aftertouch":
                payload["pressure"] = max(0, min(127, int(v1 or 0)))
            self.bus.publish(bus_topics.MIDITEMA_OUTPUT, payload)
            _cat = ("pc" if ev == "program_change" else
                    "cc" if ev == "control_change" else
                    "note" if ev in ("note_on", "note_off") else "midi")
            self.device_last_send_time[device_name] = (time.time(), _cat)
            self.midi_osc_event_log.append({
                'time': time.strftime('%H:%M:%S'),
                'device': device_name,
                'proto': 'BUS',
                'payload': str(payload),
            })
            return

        if self.port_registry.get_output(device_name) is not None and "address" not in action:
            port = self.port_registry.get_output(device_name)
            try:
                if port.closed:
                    error_msg = f"Puerto MIDI '{device_name}' está cerrado"
                    logger.debug(error_msg)
                    self.set_feedback_message(f"[!] {error_msg}")
                    return

                msg = _build_mido_message(action, context)
                if msg is None:
                    return
                logger.debug(f"Sending MIDI to '{device_name}': {msg}")
                port.send(msg)
                _mt = msg.type
                _cat = "pc" if _mt == "program_change" else "cc" if _mt == "control_change" else "note" if "note" in _mt else "midi"
                self.device_last_send_time[device_name] = (time.time(), _cat)
                self.midi_osc_event_log.append({
                    'time': time.strftime('%H:%M:%S'),
                    'device': device_name,
                    'proto': 'MIDI',
                    'payload': str(msg),
                })

            except Exception as e:
                error_msg = f"Error MIDI Trigger ({device_name}): {e}"
                logger.debug(error_msg)
                logger.debug(f"Action was: {action}")
                self.set_feedback_message(error_msg)

        elif device_name in self.osc_outputs:
            client = self.osc_outputs[device_name]
            logger.debug(f"Sending OSC message to device '{device_name}'")
            try:
                address = _resolve_value(action.get("address"), context)
                if not address:
                    logger.debug(f"No address found in action")
                    return

                raw_args = action.get("args", [])
                resolved_args = [_resolve_value(arg, context) for arg in raw_args]
                logger.debug(f"Sending OSC: {address} with args: {resolved_args}")
                client.send(address, *resolved_args)
                logger.debug(f"OSC message sent successfully")
                self.device_last_send_time[device_name] = (time.time(), "osc")
                self.midi_osc_event_log.append({
                    'time': time.strftime('%H:%M:%S'),
                    'device': device_name,
                    'proto': 'OSC',
                    'payload': f"{address} {resolved_args}",
                })

            except Exception as e:
                logger.debug(f"OSC Error: {e}")
                self.set_feedback_message(f"Error OSC Trigger ({device_name}): {e}")
        else:
            logger.debug(f"Device '{device_name}' not found in MIDI or OSC outputs")
            logger.debug(f"Available MIDI devices: {[info.alias for info in self.port_registry.iter_ports() if info.direction == 'out']}")
            logger.debug(f"Available OSC devices: {list(self.osc_outputs.keys())}")

            if self.outputs_enabled:
                self.set_feedback_message(f"[!] Error: Dispositivo '{device_name}' no conectado/encontrado.")

    _CANONICAL_TRIGGER_EVENTS = frozenset([
        "song_change", "part_change",
        "playback_start", "playback_initial_start", "playback_stop", "playback_continue",
        "setlist_end", "bar_triggers", "countdown_triggers"
    ])

    def fire_triggers(self, event_name: str, context: dict, is_delayed_check: bool = False, remaining_beats: int = 0, force_instant: bool = False) -> None:
        """Busca y ejecuta todos los triggers asociados a un evento, fusionando Global, Playlist y Song."""
        if event_name not in self._CANONICAL_TRIGGER_EVENTS:
            logger.warning(f"fire_triggers: evento desconocido '{event_name}'")
        logger.debug(f"fire_triggers called: event={event_name}, delayed={is_delayed_check}, beats={remaining_beats}")

        trigger_sources = []
        if "triggers" in self.config:
            trigger_sources.append(self.config["triggers"])
        if self.playlist_state.is_active and self.playlist_state.triggers:
            trigger_sources.append(self.playlist_state.triggers)
        if self.song_state.triggers:
            trigger_sources.append(self.song_state.triggers)

        for source in trigger_sources:
            if event_name in source:
                actions = source[event_name]
                for i, action in enumerate(actions):
                    delay_in_beats = 0
                    if "bar" in action:
                        delay_in_beats = action["bar"] * self.song_state.time_signature_numerator
                    elif "beats" in action:
                        delay_in_beats = action["beats"]
                    elif event_name in ["part_change", "song_change"] and is_delayed_check and self.playlist_state.is_active:
                        delay_in_beats = self.playlist_state.beats

                    if is_delayed_check:
                        should_fire = delay_in_beats > 0 and delay_in_beats == remaining_beats
                    elif force_instant:
                        should_fire = delay_in_beats == 0 or not self.playlist_state.is_active
                    else:
                        should_fire = delay_in_beats == 0

                    logger.debug(f"Action {i}: delay={delay_in_beats}, should_fire={should_fire}, force_instant={force_instant}, is_delayed_check={is_delayed_check}")

                    if should_fire and self.outputs_enabled and not context.get("skip_outputs", False):
                        logger.debug(f"Firing action {i}")
                        self._process_trigger_action(action, context)
                    else:
                        logger.debug(f"Skipping action {i}")

            logger.debug(f"Finished processing actions for '{event_name}'")

        if event_name == "part_change":
            if "part_output" in context:
                local_actions = context["part_output"] or []
            else:
                current_part_index = context.get("part_index")
                local_actions = []
                if current_part_index is not None and 0 <= current_part_index < len(self.song_state.parts):
                    local_actions = self.song_state.parts[current_part_index].get("output", [])

            if isinstance(local_actions, dict):
                local_actions = [local_actions]

            if isinstance(local_actions, list):
                if not context.get("skip_outputs", False) and self.outputs_enabled:
                    for action in local_actions:
                        if "bar" in action:
                            delay_in_beats = action["bar"] * self.song_state.time_signature_numerator
                        elif "beats" in action:
                            delay_in_beats = action["beats"]
                        else:
                            delay_in_beats = self.playlist_state.beats if self.playlist_state.is_active else 0

                        if is_delayed_check:
                            should_fire_local = delay_in_beats > 0 and delay_in_beats == remaining_beats
                        elif force_instant:
                            early_ran = self._part_early_fired
                            should_fire_local = delay_in_beats == 0 or not early_ran
                        else:
                            should_fire_local = delay_in_beats == 0

                        if should_fire_local:
                            self._process_trigger_action(action, context)
                            if is_delayed_check:
                                self._part_early_fired = True

    # --- Bus ---

    def setup_bus(self) -> None:
        """Start the LocalBus and subscribe to midimod events for TUI display."""
        bus_port = int(self.config.get("bus_port", 5555))
        self.bus = LocalBus(port=bus_port)
        self.bus.start()
        self.presence = AppPresence(self.bus, "miditema")
        self.presence.start()

        def on_version_change(topic: str, payload: dict) -> None:
            self.midimod_active_version = payload.get("version")

        def on_sequencer_state(topic: str, payload: dict) -> None:
            seq_id = payload.get("seq_id")
            playing = payload.get("playing", False)
            if seq_id is not None:
                self.midimod_sequencer_states[seq_id] = playing

        self.bus.subscribe(bus_topics.MIDIMOD_VERSION_CHANGE, on_version_change)
        self.bus.subscribe(f"{bus_topics.MIDIMOD_SEQUENCER_STATE}.*", on_sequencer_state)

        if self._bus_clock_alias:
            _src = self._bus_clock_alias

            def on_clock_tick(topic: str, payload: dict) -> None:
                if payload.get("source") != _src:
                    return
                self._event_queue.put({
                    "type": "tick",
                    "bpm": payload.get("bpm", 0.0),
                    "ts": time.time(),
                })

            def on_clock_transport(topic: str, payload: dict) -> None:
                if payload.get("source") != _src:
                    return
                t = payload.get("type")
                if t in ("start", "stop", "continue"):
                    self._event_queue.put({"type": t, "passive": False})

            self.bus.subscribe(bus_topics.CLOCK_TICK, on_clock_tick)
            self.bus.subscribe(bus_topics.CLOCK_TRANSPORT, on_clock_transport)
            logger.info(f"[*] Clock del bus suscrito (fuente: '{_src}')")

        self.bus.publish(bus_topics.MIDITEMA_TRANSPORT, {"state": "stop"}, retain=True)
        logger.debug("LocalBus started in miditema")

    # --- Motor de eventos ---

    def start_motor(self) -> None:
        """Arranca el hilo-motor que serializa toda la mutación de estado de la sesión."""
        self._motor_thread = threading.Thread(
            target=self._motor_loop, daemon=True, name="session-motor"
        )
        self._motor_thread.start()

    def _motor_loop(self) -> None:
        """Hilo único que procesa todos los eventos de clock, transport y control."""
        while not self.shutdown_flag:
            try:
                event = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                if (
                    self.clock_state.status == "PLAYING"
                    and self.clock_state.last_tick_time > 0
                ):
                    threshold = self.config.get("clock_stall_threshold_ms", 500) / 1000.0
                    if time.time() - self.clock_state.last_tick_time > threshold:
                        if not self._clock_stale:
                            self._clock_stale = True
                            self.set_feedback_message(
                                "⚠ CLOCK LOST — sin tick. Comprueba el cable o midimod.",
                                duration=10, level="error",
                            )
                continue
            t = event.get("type")
            try:
                if t == "tick":
                    self.clock_state.bpm = event.get("bpm", 0.0)
                    self.clock_state.last_tick_time = event.get("ts", time.time())
                    if self._clock_stale:
                        self._clock_stale = False
                        self.set_feedback_message("Clock recuperado.", duration=3)
                    if self.clock_state.status == "STOPPED":
                        self.handle_start(is_passive_start=True)
                    elif self.clock_state.status == "PLAYING":
                        self.song_state.midi_clock_tick_counter += 1
                        if self.song_state.midi_clock_tick_counter >= self.song_state.ticks_per_song_beat:
                            self.song_state.midi_clock_tick_counter = 0
                            self.process_song_tick()
                elif t == "start":
                    self.handle_start(is_passive_start=event.get("passive", False))
                elif t == "stop":
                    self.handle_stop()
                elif t == "continue":
                    self.handle_continue()
                elif t == "control":
                    self.process_control_message(event["msg"], event.get("alias", ""))
            except Exception as e:
                logger.error("Motor loop error processing %r: %s", t, e, exc_info=True)

    def enqueue_transport(self, t: str, passive: bool = False) -> None:
        """Encola un evento de transport (start/stop/continue) para el hilo-motor."""
        self._event_queue.put({"type": t, "passive": passive})

    def _assert_motor_thread(self, method: str) -> None:
        if self._motor_thread is not None and self._motor_thread.is_alive():
            cur = threading.current_thread().name
            if cur != "session-motor":
                logger.error(
                    "BUG: %s llamado fuera del hilo-motor (thread: %r)", method, cur
                )

    # --- Carga de configs y canciones ---

    def load_config(self, conf_filename: str) -> dict:
        """Carga la configuración del alias del dispositivo desde el archivo .conf."""
        # Load optional root midi.conf.json (one directory above the app)
        base: dict = {}
        root_conf = Path(__file__).resolve().parent.parent / "midi.conf.json"
        if root_conf.is_file():
            try:
                with root_conf.open('r', encoding='utf-8') as f:
                    base = json5.load(f)
                logger.info(f"[*] Config raíz '{root_conf.name}' cargada desde '{root_conf.parent}'.")
            except Exception as e:
                logger.warning(f"[!] Error cargando config raíz '{root_conf}': {e}")

        conf_path = Path(conf_filename)
        if not conf_path.is_file():
            if conf_filename != CONF_FILE_NAME:
                logger.warning(f"[!] El archivo de configuración '{conf_filename}' no fue encontrado.")
            return base
        try:
            with conf_path.open('r', encoding='utf-8') as f:
                cfg = json5.load(f)
            logger.info(f"[*] Archivo de configuración '{conf_filename}' cargado.")
            return deep_merge(base, cfg)
        except Exception as e:
            logger.warning(f"[!] Error cargando el archivo de configuración '{conf_filename}': {e}")
            return base

    def load_song_file(self, filepath: Optional[Path] = None, data: Optional[dict] = None) -> bool:
        """Carga y valida una canción, actualizando el SongState."""
        self._last_used_device = None

        song_data = None
        if data:
            song_data = data
            errors = MIDItemaValidator.validate_data(data)
            if errors:
                error_msg = "Errores de validación:\n" + "\n".join(str(e) for e in errors[:3])
                if len(errors) > 3:
                    error_msg += f"\n... y {len(errors) - 3} errores más"
                self.set_feedback_message(f"[!] {error_msg}")
                return False
        elif filepath:
            is_valid, errors, song_data = MIDItemaValidator.validate_file(filepath)
            if not is_valid:
                error_msg = "Errores en el archivo:\n" + "\n".join(str(e) for e in errors[:3])
                if len(errors) > 3:
                    error_msg += f"\n... y {len(errors) - 3} errores más"
                logger.warning(f"[!] {error_msg}")
                self.set_feedback_message(f"[!] Error validando '{filepath.name}'")
                return False
        else:
            logger.warning("Error: Se debe proporcionar 'filepath' o 'data' para cargar la canción.")
            return False

        if not song_data:
            return False

        self.song_state = SongState()
        self.song_state.song_name = song_data.get("song_name", filepath.stem if filepath else "Canción Incrustada")
        self.song_state.song_color = song_data.get("color")
        self.song_state.triggers = song_data.get("triggers", {})
        self.song_state.parts = song_data.get("parts", [])

        for part in self.song_state.parts:
            if "repeat_pattern" in part:
                part["repeat_pattern"] = normalize_repeat_pattern(part["repeat_pattern"])

        if not self.song_state.parts or not isinstance(self.song_state.parts, list):
            logger.warning(f"Error: La canción '{self.song_state.song_name}' no tiene una lista de 'parts' válida.")
            return False

        try:
            sig = song_data.get("time_signature", "4/4").split('/')
            self.song_state.time_signature_numerator = int(sig[0])
        except (ValueError, IndexError):
            self.song_state.time_signature_numerator = 4

        division = song_data.get("time_division", "1/4")
        division_map = {"1/4": 24, "1/8": 12, "1/16": 6}
        self.song_state.ticks_per_song_beat = division_map.get(division, MIDI_PPQN)

        self.global_parts_manager.build_global_parts_list()

        return True

    def load_song_from_playlist(self, song_index: int, fire_triggers: bool = True) -> bool:
        """Carga una canción específica de la playlist activa y envía notificaciones."""
        if not self.playlist_state.is_active:
            self.set_feedback_message("[!] No hay playlist activa.")
            self.handle_song_end()
            return False

        if not (0 <= song_index < len(self.playlist_state.playlist_elements)):
            self.set_feedback_message(f"[!] Índice de canción {song_index} fuera de rango.")
            self.handle_song_end()
            return False

        self.playlist_state.current_song_index = song_index
        element = self.playlist_state.playlist_elements[song_index]

        song_data_to_load = None
        song_name_for_osc = "N/A"

        if "filepath" in element:
            song_path = self.SONGS_DIR / element["filepath"]
            song_name_for_osc = song_path.stem
            if not song_path.is_file():
                error_msg = f"Archivo '{element['filepath']}' no encontrado en {self.SONGS_DIR}"
                logger.warning(f"[!] {error_msg}")
                self.set_feedback_message(f"[!] {error_msg}")
                if song_index < len(self.playlist_state.playlist_elements) - 1:
                    logger.info(f"[*] Intentando cargar la siguiente canción...")
                    return self.load_song_from_playlist(song_index + 1)
                return False

            try:
                with song_path.open('r', encoding='utf-8') as f:
                    song_data_to_load = json5.load(f)
                if "song_name" in song_data_to_load:
                    song_name_for_osc = song_data_to_load["song_name"]
            except Exception as e:
                error_msg = f"Error al parsear '{element['filepath']}': {e}"
                logger.warning(f"[!] {error_msg}")
                self.set_feedback_message(f"[!] Error en archivo JSON")
                return False

        elif "parts" in element:
            song_data_to_load = element
            song_name_for_osc = song_data_to_load.get("song_name", "Canción Incrustada")
        else:
            error_msg = f"Elemento de playlist en índice {song_index} no tiene 'filepath' ni 'parts'"
            logger.warning(f"[!] {error_msg}")
            self.set_feedback_message(f"[!] Elemento de playlist inválido")
            return False

        context = {
            "song_index": song_index,
            "song_name": song_name_for_osc,
            "song_color": song_data_to_load.get("color"),
            "part_index": 0
        }
        if fire_triggers and self.last_triggered_song_index != song_index:
            self.fire_triggers("song_change", context)
            self.last_triggered_song_index = song_index
            if self.bus:
                self.bus.publish(bus_topics.MIDITEMA_SONG_CHANGE, {
                    "song_index": song_index,
                    "song_name": song_name_for_osc,
                }, retain=True)

        if not self.load_song_file(data=song_data_to_load):
            logger.warning(f"[!] No se pudo cargar la canción desde el elemento {song_index} de la playlist")
            return False

        return True

    def _reset_song_state_only(self) -> None:
        """Resetea el estado de la canción sin tocar el clock_state. Usar en jumps durante PLAYING."""
        self._last_used_device = None
        self.previous_song_index = -1
        self.last_triggered_song_index = -1
        self.song_state.current_part_index = -1
        self.song_state.remaining_beats_in_part = 0
        self.song_state.start_time = 0
        self.song_state.paused_song_elapsed_time = 0
        self.song_state.pass_count = 0
        self.song_state.midi_clock_tick_counter = 0
        self.song_state.current_bar_in_part = 0

    def reset_song_state_on_stop(self) -> None:
        """Resetea el estado de la secuencia cuando el reloj se detiene (STOP/FINISHED/carga).
        Incluye clock_state — no llamar durante PLAYING. Para jumps en PLAYING usar _reset_song_state_only."""
        self._reset_song_state_only()
        self.clock_state.tick_times = []
        self.clock_state.bpm = 0.0

    # --- Tick principal ---

    def process_song_tick(self):
        """Llamado en cada "beat" de la canción (definido por time_division)."""
        self._assert_motor_thread("process_song_tick")
        if self.clock_state.status != "PLAYING" or self.song_state.current_part_index == -1:
            return

        sig_num = self.song_state.time_signature_numerator
        current_part = self.song_state.parts[self.song_state.current_part_index]
        total_beats_in_part = current_part.get("bars", 0) * sig_num

        beats_elapsed_in_part = total_beats_in_part - self.song_state.remaining_beats_in_part

        endpoint_bar = self.get_dynamic_endpoint()
        endpoint_beat_absolute = endpoint_bar * sig_num

        remaining_beats_to_event = endpoint_beat_absolute - beats_elapsed_in_part

        next_part_info = self.global_parts_manager.get_next_part_info()
        current_part_info = self.global_parts_manager.get_current_global_part_info()

        if next_part_info:
            is_cross_song_jump = (current_part_info and
                                  next_part_info.song_index != current_part_info.song_index)

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
                "part_index_in_setlist": next_part_info.global_part_index,
                "part_output": next_part_info.output,
            }

            if is_cross_song_jump:
                self.last_triggered_song_index = next_part_info.song_index
                self.fire_triggers("song_change", context, is_delayed_check=True, remaining_beats=remaining_beats_to_event)

            self.fire_triggers("part_change", context, is_delayed_check=True, remaining_beats=remaining_beats_to_event)

        jump_executed = self.check_and_execute_pending_action()
        if jump_executed:
            return

        self.song_state.remaining_beats_in_part -= 1
        beats_elapsed_in_part += 1

        trigger_sources = []
        if "triggers" in self.config:
            trigger_sources.append(self.config["triggers"])
        if self.playlist_state.is_active and self.playlist_state.triggers:
            trigger_sources.append(self.playlist_state.triggers)
        if self.song_state.triggers:
            trigger_sources.append(self.song_state.triggers)

        if beats_elapsed_in_part > 0 and beats_elapsed_in_part % sig_num == 0:
            self.song_state.current_bar_in_part = beats_elapsed_in_part // sig_num

            bar_context = {
                "completed_bar": self.song_state.current_bar_in_part,
                "current_song_name": self.song_state.song_name,
                "current_part_name": current_part.get("name"),
                "current_part_index": self.song_state.current_part_index
            }

            for source in trigger_sources:
                for action in source.get("bar_triggers", []):
                    bar_interval = action.get("each_bar")
                    if bar_interval and self.song_state.current_bar_in_part > 0 and self.song_state.current_bar_in_part % bar_interval == 0 and self.outputs_enabled:
                        action_context = bar_context.copy()
                        action_context["block_number"] = self.song_state.current_bar_in_part // bar_interval
                        self._process_trigger_action(action, action_context)

            if self.bus:
                self.bus.publish(bus_topics.MIDITEMA_BAR, {
                    "song_index": self.playlist_state.current_song_index if self.playlist_state.is_active else 0,
                    "part_index": self.song_state.current_part_index,
                    "bar": self.song_state.current_bar_in_part,
                    "total_bars": current_part.get("bars", 0),
                })

            if self.song_state.remaining_beats_in_part > 0:
                self.beat_flash_end_time = time.time() + 0.1

        countdown_context = {
            "remaining_beats": remaining_beats_to_event,
            "remaining_bars": math.ceil(remaining_beats_to_event / sig_num),
            "current_song_name": self.song_state.song_name,
            "current_part_name": current_part.get("name"),
            "current_part_index": self.song_state.current_part_index
        }

        for source in trigger_sources:
            for action in source.get("countdown_triggers", []):
                beat_interval = action.get("each_beat")
                if beat_interval and 0 < remaining_beats_to_event <= beat_interval and self.outputs_enabled:
                    self._process_trigger_action(action, countdown_context)

        if self.song_state.remaining_beats_in_part <= 0:
            self.start_next_part()

    # --- Predicción y resolución de saltos ---

    def _get_parts_from_playlist_element(self, element):
        """Devuelve la lista de partes de un elemento de la playlist, leyéndola del disco si es necesario."""
        if "parts" in element and isinstance(element["parts"], list):
            return element["parts"]

        if "filepath" in element:
            cache_key = element["filepath"]
            if cache_key in self._parts_file_cache:
                return self._parts_file_cache[cache_key]
            try:
                song_path = self.SONGS_DIR / element["filepath"]
                if song_path.is_file():
                    with song_path.open('r', encoding='utf-8') as f:
                        data = json5.load(f)
                    parts = data.get("parts", [])
                    self._parts_file_cache[cache_key] = parts
                    return parts
            except Exception:
                return []

        return []

    def predict_jump_destination(self, action: dict) -> tuple[Optional[int], Optional[int]]:
        """Analiza una acción pendiente y devuelve el destino final como (índice_canción, índice_parte)."""
        target_type = action.get("target_type")
        target = action.get("target")

        if target_type in ["global_part", "cue_jump"]:
            return action.get("target_song"), action.get("target_part")

        if target_type == "song":
            dest_song_idx = self.playlist_state.current_song_index
            if isinstance(target, int):
                dest_song_idx = target
            elif isinstance(target, dict):
                dest_song_idx += target.get("value", 0)

            if not (0 <= dest_song_idx < len(self.playlist_state.playlist_elements)):
                return None, None

            dest_song_parts = self._get_parts_from_playlist_element(self.playlist_state.playlist_elements[dest_song_idx])
            dest_part_idx, _ = _find_next_valid_part_index(dest_song_parts, "+1", -1, 0, self.repeat_override_active)

            return (dest_song_idx, dest_part_idx) if dest_part_idx is not None else (None, None)

        sim_song_idx = self.playlist_state.current_song_index
        sim_part_idx = self.song_state.current_part_index
        sim_pass_count = self.song_state.pass_count

        if isinstance(target, dict) and target.get("type") == "relative":
            steps = target.get("value", 0)
            direction = "+1" if steps > 0 else "-1"
            for _ in range(abs(steps)):
                current_sim_parts = []
                if self.playlist_state.is_active:
                    if not (0 <= sim_song_idx < len(self.playlist_state.playlist_elements)):
                        return None, None
                    current_sim_parts = self._get_parts_from_playlist_element(self.playlist_state.playlist_elements[sim_song_idx])
                else:
                    current_sim_parts = self.song_state.parts

                next_part_idx, next_pass_count = _find_next_valid_part_index(current_sim_parts, direction, sim_part_idx, sim_pass_count, self.repeat_override_active)

                if next_part_idx is not None:
                    sim_part_idx, sim_pass_count = next_part_idx, next_pass_count
                elif self.playlist_state.is_active:
                    sim_song_idx += 1 if direction == "+1" else -1
                    if not (0 <= sim_song_idx < len(self.playlist_state.playlist_elements)):
                        return None, None

                    new_sim_parts = self._get_parts_from_playlist_element(self.playlist_state.playlist_elements[sim_song_idx])
                    start_idx = -1 if direction == "+1" else len(new_sim_parts)
                    sim_part_idx, sim_pass_count = _find_next_valid_part_index(new_sim_parts, direction, start_idx, 0, self.repeat_override_active)
                    if sim_part_idx is None:
                        return None, None
                else:
                    return None, None

        elif target == "restart":
            sim_part_idx = self.song_state.current_part_index
        elif isinstance(target, int):
            sim_part_idx = target

        return sim_song_idx, sim_part_idx

    def find_next_valid_part_index(self, direction: str, start_index: int, start_pass_count: int) -> tuple[int, int]:
        """Encuentra el índice y el pass_count de la siguiente parte válida usando el estado global."""
        return _find_next_valid_part_index(
            self.song_state.parts, direction, start_index, start_pass_count, self.repeat_override_active
        )

    def find_next_part_index_manual(self, direction: str, start_index: int, start_pass_count: int) -> tuple[int, int]:
        """Navegación manual (flechas / Ctrl+flechas): salta sólo partes con bars==0, ignora repeat_pattern."""
        return _find_next_part_index_manual(
            self.song_state.parts, direction, start_index, start_pass_count, self.repeat_override_active
        )

    def find_last_playable_part_of_song(self, song_idx: int):
        """Devuelve el índice de la última parte con bars>0 de la canción dada en la playlist, o None."""
        if not self.playlist_state.is_active:
            return None
        if not (0 <= song_idx < len(self.playlist_state.playlist_elements)):
            return None
        parts = self._get_parts_from_playlist_element(self.playlist_state.playlist_elements[song_idx])
        for i in range(len(parts) - 1, -1, -1):
            if parts[i].get("bars", 0) > 0:
                return i
        return None

    def resolve_global_part_index(self, global_index: int):
        """Convierte un índice de parte global en un par (índice_de_canción, índice_de_parte_local)."""
        if not self.playlist_state.is_active:
            return None, None

        cumulative_parts = 0
        for song_idx, element in enumerate(self.playlist_state.playlist_elements):
            parts_in_song = self._get_parts_from_playlist_element(element)
            num_parts = len(parts_in_song)

            if global_index < cumulative_parts + num_parts:
                local_part_index = global_index - cumulative_parts
                return song_idx, local_part_index

            cumulative_parts += num_parts

        return None, None

    def execute_global_part_jump(self, silent: bool = False):
        """Ejecuta un salto a una parte específica en una canción específica de la playlist."""
        if not self.pending_action:
            return

        collapsed_outputs = self.pending_action.get("collapsed_outputs")
        target_song_idx = self.pending_action.get("target_song")
        target_part_idx = self.pending_action.get("target_part")

        if target_song_idx is None or target_part_idx is None:
            self.pending_action = None
            return

        if silent:
            ok = True
            if self.playlist_state.is_active:
                ok = self.load_song_from_playlist(target_song_idx, fire_triggers=False)
            if ok:
                self.reset_song_state_on_stop()
                self.song_state.pass_count = 0
                self.setup_part(target_part_idx, fire_instant_trigger=False)
                self.initial_outputs_sent = False
                self.pending_action = {
                    "target_type": "global_part",
                    "target_song": target_song_idx,
                    "target_part": target_part_idx,
                    "quantize": self.quantize_mode,
                }
            return

        if self.load_song_from_playlist(target_song_idx):
            if self.clock_state.status == "PLAYING":
                self._reset_song_state_only()
            else:
                self.reset_song_state_on_stop()
            self.song_state.pass_count = 0
            self.setup_part(target_part_idx, collapsed_outputs=collapsed_outputs)

            if self.clock_state.status == "PLAYING":
                self.process_song_tick()

        self.pending_action = None

    def navigate_silent_to(self, song_idx: int, part_idx: int) -> None:
        """Arms a global_part jump and, if not playing, executes it silently."""
        self.pending_action = {
            "target_type": "global_part",
            "target_song": song_idx,
            "target_part": part_idx,
            "quantize": self.quantize_mode,
        }
        if self.clock_state.status != "PLAYING":
            self.execute_global_part_jump(silent=True)

    @staticmethod
    def halve_quantization(current_quantize: str) -> str:
        """Reduce la cuantización a un nivel más inmediato."""
        if current_quantize == "instant":
            return "instant"
        hierarchy = ["end_of_part", "next_bar", "next_4", "next_8", "next_16", "next_32"]
        try:
            current_index = hierarchy.index(current_quantize)
            if current_index < len(hierarchy) - 1:
                return hierarchy[current_index + 1]
            return "instant"
        except ValueError:
            return "next_bar"

    def execute_part_jump(self):
        """Ejecuta el salto de PARTE modificando el estado de la canción."""
        if not self.pending_action:
            return

        collapsed_outputs = self.pending_action.get("collapsed_outputs")
        target = self.pending_action.get("target")
        final_index = self.song_state.current_part_index
        final_pass_count = self.song_state.pass_count

        original_direction = 0
        if isinstance(target, dict) and target.get("type") == "relative":
            original_direction = target.get("value", 0)

        if isinstance(target, dict) and target.get("type") == "relative":
            steps = target.get("value", 0)
            if steps == 0:
                self.pending_action = None
                return

            direction = "+1" if steps > 0 else "-1"
            for _ in range(abs(steps)):
                if final_index is not None:
                    final_index, final_pass_count = self.find_next_valid_part_index(direction, final_index, final_pass_count)

        elif target == "restart":
            pass
        elif isinstance(target, int):
            if 0 <= target < len(self.song_state.parts):
                final_index = target
                final_pass_count = 0
            else:
                self.pending_action = None
                return

        if final_index is None:
            if original_direction < 0 and self.playlist_state.is_active:
                prev_song_idx = self.playlist_state.current_song_index - 1
                target_part = self.find_last_playable_part_of_song(prev_song_idx)
                if target_part is not None:
                    self.pending_action = {
                        "target_type": "global_part",
                        "target_song": prev_song_idx,
                        "target_part": target_part,
                        "quantize": self.quantize_mode,
                    }
                    self.execute_global_part_jump()
                else:
                    song_jump_action = {"target_type": "song", "target": {"type": "relative", "value": -1}, "quantize": self.quantize_mode}
                    self.pending_action = song_jump_action
                    self.execute_song_jump()
                return
            else:
                self.handle_song_end()
        else:
            self.song_state.pass_count = final_pass_count
            self.setup_part(final_index, collapsed_outputs=collapsed_outputs)

        self.pending_action = None

    def execute_song_jump(self, silent: bool = False):
        """Ejecuta el salto de CANCIÓN, iniciando en el punto correcto según la dirección."""
        if not self.pending_action or not self.playlist_state.is_active:
            self.pending_action = None
            return

        target = self.pending_action.get("target")
        current_index = self.playlist_state.current_song_index
        final_index = current_index

        if target == "restart":
            final_index = current_index
        elif isinstance(target, dict) and target.get("type") == "relative":
            steps = target.get("value", 0)
            final_index = current_index + steps
        elif isinstance(target, int):
            final_index = target

        self.pending_action = None

        if not (0 <= final_index < len(self.playlist_state.playlist_elements)):
            self.set_feedback_message(f"Salto a canción {final_index + 1} inválido (fuera de rango).")
            return

        if self.load_song_from_playlist(final_index, fire_triggers=not silent):
            if self.clock_state.status == "PLAYING":
                self._reset_song_state_only()
            else:
                self.reset_song_state_on_stop()
            if silent:
                self._navigate_first_part_stopped()
            else:
                self.start_next_part()
                if self.clock_state.status == "PLAYING":
                    self.process_song_tick()
        else:
            self.set_feedback_message(f"Salto a canción {final_index + 1} inválido (error de carga).")

    def execute_pending_action(self):
        """Inspecciona la acción pendiente y decide si es un salto de parte o de canción."""
        if not self.pending_action:
            return

        if self.pending_action.get("target_type") in ["global_part", "cue_jump"]:
            self.execute_global_part_jump()
        elif self.pending_action.get("target_type") == "song":
            self.execute_song_jump()
        else:
            self.execute_part_jump()

    def check_and_execute_pending_action(self):
        """Verifica si se cumplen las condiciones de cuantización para ejecutar una acción."""
        if not self.pending_action or self.clock_state.status != "PLAYING":
            return False

        quantize = self.pending_action.get("dynamic_quantize") or self.pending_action.get("quantize")
        sig_num = self.song_state.time_signature_numerator
        is_last_beat_of_bar = (self.song_state.remaining_beats_in_part % sig_num == 1)

        should_jump = False
        if quantize == "instant":
            should_jump = True
        elif quantize == "end_of_part" and self.song_state.remaining_beats_in_part == 1:
            should_jump = True
        elif quantize == "next_bar" and is_last_beat_of_bar:
            should_jump = True
        else:
            if is_last_beat_of_bar:
                total_beats_in_part = self.song_state.parts[self.song_state.current_part_index].get("bars", 0) * sig_num
                beats_into_part = total_beats_in_part - self.song_state.remaining_beats_in_part
                current_bar = beats_into_part // sig_num
                if quantize == "next_4" and (current_bar + 1) % 4 == 0:
                    should_jump = True
                elif quantize == "next_8" and (current_bar + 1) % 8 == 0:
                    should_jump = True
                elif quantize == "next_16" and (current_bar + 1) % 16 == 0:
                    should_jump = True
                elif quantize == "next_32" and (current_bar + 1) % 32 == 0:
                    should_jump = True

        if should_jump:
            self.execute_pending_action()
            return True

        return False

    def start_next_part(self):
        """Determina qué parte reproducir a continuación de forma iterativa."""
        max_iterations = 2 * max(len(self.song_state.parts), 1) + max(len(self.playlist_state.playlist_elements), 1) + 4
        iteration_count = 0
        while True:
            iteration_count += 1
            if iteration_count > max_iterations:
                self.set_feedback_message("[!] Error: bucle infinito en start_next_part. Deteniendo.")
                self.handle_song_end()
                return
            if self.pending_action:
                self.execute_pending_action()
                if self.song_state.remaining_beats_in_part <= 0:
                    continue
                return

            if self.session_mode and self.song_state.current_part_index != -1 and not self.part_loop_active:
                self.setup_part(self.song_state.current_part_index)
                if self.song_state.remaining_beats_in_part <= 0:
                    continue
                return

            if self.part_loop_active and self.song_state.current_part_index == self.part_loop_index:
                self.setup_part(self.song_state.current_part_index)
                if self.song_state.remaining_beats_in_part <= 0:
                    continue
                return

            action_to_execute = "next"
            if self.song_state.current_part_index != -1:
                current_part = self.song_state.parts[self.song_state.current_part_index]
                pattern = current_part.get("repeat_pattern")
                if isinstance(pattern, list) and pattern:
                    action_to_execute = pattern[self.song_state.pass_count % len(pattern)]
                elif isinstance(pattern, str):
                    action_to_execute = pattern

            action = action_to_execute
            if action == "song_mode":
                self.repeat_override_active = True
                self.set_feedback_message("Repeat Pattern: Song Mode activado.")
                action = "next"
            elif action == "loop_mode":
                self.repeat_override_active = False
                self.set_feedback_message("Repeat Pattern: Loop Mode activado.")
                action = "next"

            target_found = False

            if not self.repeat_override_active:
                if isinstance(action, dict):
                    self.song_state.pass_count = 0
                    if "jump_to_part" in action:
                        target_idx = action["jump_to_part"]
                        if 0 <= target_idx < len(self.song_state.parts):
                            self.setup_part(target_idx)
                            target_found = True
                    elif "jump_to_cue" in action:
                        cue_num = action["jump_to_cue"]
                        for i, part in enumerate(self.song_state.parts):
                            if part.get("cue") == cue_num:
                                self.setup_part(i)
                                target_found = True
                                break
                    elif "random_part" in action:
                        choices = action["random_part"]
                        if choices and isinstance(choices, list):
                            target_idx = random.choice(choices)
                            if 0 <= target_idx < len(self.song_state.parts):
                                self.setup_part(target_idx)
                                target_found = True
                    if not target_found:
                        action = "next"

                if not target_found:
                    if action == "repeat":
                        self.setup_part(self.song_state.current_part_index)
                        target_found = True
                    elif action == "prev":
                        next_index, next_pass_count = self.find_next_valid_part_index("-1", self.song_state.current_part_index, self.song_state.pass_count)
                        if next_index is not None:
                            self.song_state.pass_count = next_pass_count
                            self.setup_part(next_index)
                        else:
                            self.handle_song_end()
                        return
                    elif action == "first_part":
                        self.song_state.pass_count = 0
                        next_index, _ = self.find_next_valid_part_index("+1", -1, 0)
                        if next_index is not None:
                            self.setup_part(next_index)
                        else:
                            self.handle_song_end()
                        return
                    elif action == "last_part":
                        self.song_state.pass_count = 0
                        next_index, _ = self.find_next_valid_part_index("-1", len(self.song_state.parts), 0)
                        if next_index is not None:
                            self.setup_part(next_index)
                        else:
                            self.handle_song_end()
                        return
                    elif action == "loop_part":
                        self.activate_part_loop()
                        self.set_feedback_message(f"Repeat Pattern: Loop Part activado.")
                        self.setup_part(self.part_loop_index)
                        target_found = True

            if target_found:
                if self.song_state.remaining_beats_in_part <= 0:
                    continue
                return

            if self.playlist_state.is_active:
                if action == "next_song":
                    self.handle_song_end()
                    return
                elif action == "prev_song":
                    prev_idx = self.playlist_state.current_song_index - 1
                    if prev_idx >= 0 and self.load_song_from_playlist(prev_idx):
                        continue
                    return
                elif action == "first_song":
                    if self.load_song_from_playlist(0):
                        continue
                    return
                elif action == "last_song":
                    last_idx = len(self.playlist_state.playlist_elements) - 1
                    if last_idx >= 0 and self.load_song_from_playlist(last_idx):
                        continue
                    return

            next_index, next_pass_count = self.find_next_valid_part_index("+1", self.song_state.current_part_index, self.song_state.pass_count)
            if next_index is None:
                self.handle_song_end()
                return
            else:
                self.song_state.pass_count = next_pass_count
                self.setup_part(next_index)
                if self.song_state.remaining_beats_in_part <= 0:
                    continue
                return

    def build_collapsed_outputs(self, target_global_idx: int) -> list:
        """Collect and collapse output actions from global parts 0..target_global_idx.

        For each (device, channel, type[, control/note]) key keeps the last action encountered,
        preserving its bar/beats timing offset. Values are pre-resolved against per-part context
        so they remain correct when fired later against the destination part's context.
        """
        gpm = self.global_parts_manager
        if not gpm.is_initialized:
            gpm.build_global_parts_list()

        collapsed = {}  # dedup_key -> resolved action dict
        local_last_device = None

        for i, part_info in enumerate(gpm.global_parts):
            if i > target_global_idx:
                break

            context = {
                "song_index": part_info.song_index,
                "song_name": part_info.song_name,
                "song_color": part_info.song_color,
                "part_index": part_info.part_index,
                "part_name": part_info.name,
                "part_bars": part_info.bars,
                "part_color": part_info.color,
                "part_notes": part_info.notes,
                "part_cue": part_info.cue,
                "part_index_in_setlist": i,
            }

            actions = part_info.output
            if isinstance(actions, dict):
                actions = [actions]
            if not isinstance(actions, list):
                continue

            for action in actions:
                device_name = action.get("device")
                if device_name:
                    local_last_device = device_name
                else:
                    device_name = local_last_device or "MIDItema"

                resolved = {"device": device_name}

                if "bar" in action:
                    resolved["bar"] = action["bar"]
                if "beats" in action:
                    resolved["beats"] = action["beats"]

                msg_type = action.get("type")
                if not msg_type:
                    if "note" in action:
                        msg_type = "note_on"
                    elif "control" in action:
                        msg_type = "control_change"
                    elif "program" in action:
                        msg_type = "program_change"
                    elif "song" in action:
                        msg_type = "song_select"
                    elif "address" in action:
                        msg_type = "osc"
                    else:
                        continue
                resolved["type"] = msg_type

                for param in ["channel", "note", "velocity", "control", "value", "program", "song"]:
                    if param in action:
                        resolved[param] = _resolve_value(action[param], context)

                if msg_type == "osc":
                    if "address" in action:
                        resolved["address"] = _resolve_value(action["address"], context)
                    if "args" in action:
                        resolved["args"] = [_resolve_value(a, context) for a in action["args"]]

                ch = resolved.get("channel", 0)
                if msg_type == "program_change":
                    key = (device_name, ch, "program_change")
                elif msg_type == "control_change":
                    key = (device_name, ch, "control_change", resolved.get("control", 0))
                elif msg_type in ("note_on", "note_off"):
                    key = (device_name, ch, msg_type, resolved.get("note", 0))
                elif msg_type == "song_select":
                    key = (device_name, "song_select")
                elif msg_type == "osc":
                    key = (device_name, "osc", resolved.get("address", ""))
                else:
                    key = (device_name, ch, msg_type)

                collapsed[key] = resolved

        # song_select delante del resto para que llegue al sintetizador antes que los PCs
        values = list(collapsed.values())
        ss = [v for v in values if v.get("type") == "song_select"]
        rest = [v for v in values if v.get("type") != "song_select"]
        return ss + rest

    def setup_part(self, part_index, fire_instant_trigger=True, collapsed_outputs=None):
        """Configura una parte y dispara incondicionalmente sus triggers asociados."""
        if not (0 <= part_index < len(self.song_state.parts)):
            return

        self.song_state.current_part_index = part_index
        part = self.song_state.parts[part_index]
        self.song_state.remaining_beats_in_part = part.get("bars", 0) * self.song_state.time_signature_numerator
        self.song_state.current_bar_in_part = 0

        current_song_index = self.playlist_state.current_song_index if self.playlist_state.is_active else 0

        if part_index == 0 and current_song_index != self.previous_song_index:
            self.song_state.start_time = time.time()
            self.song_state.paused_song_elapsed_time = 0
            self.previous_song_index = current_song_index

        if fire_instant_trigger:
            skip_initial = self.initial_outputs_sent
            skip_outputs = skip_initial or self.part_loop_active
            if skip_initial:
                self.initial_outputs_sent = False

            context = {
                "song_index": self.playlist_state.current_song_index,
                "song_name": self.song_state.song_name,
                "song_color": self.song_state.song_color,
                "part_index": part_index,
                "part_name": part.get("name"),
                "part_bars": part.get("bars"),
                "part_color": part.get("color"),
                "part_notes": part.get("notes"),
                "part_cue": part.get("cue"),
                "part_index_in_setlist": self._get_global_part_index(self.playlist_state.current_song_index, part_index),
                "skip_outputs": skip_outputs
            }
            if collapsed_outputs is not None:
                context["part_output"] = collapsed_outputs
            self.fire_triggers("part_change", context, force_instant=True)
            self._part_early_fired = False
            if self.bus:
                self.bus.publish(bus_topics.MIDITEMA_PART_CHANGE, {
                    "song_index": context["song_index"],
                    "part_index": part_index,
                    "part_name": part.get("name"),
                    "bar": 0,
                }, retain=True)

    def _navigate_first_part_stopped(self) -> None:
        """Posiciona en la primera parte válida sin enviar MIDI (modo STOP)."""
        next_idx, next_pass = self.find_next_valid_part_index("+1", -1, 0)
        if next_idx is not None:
            self.song_state.pass_count = next_pass
            self.setup_part(next_idx, fire_instant_trigger=False)
            self.pending_action = {"target": next_idx, "quantize": self.quantize_mode}
        self.initial_outputs_sent = False

    def _send_initial_outputs(self):
        """Envía los outputs (locales y globales) de la parte seleccionada para inicialización (prime)."""
        if not self.outputs_enabled or not self.song_state.parts:
            return

        part_index = self.song_state.current_part_index
        if part_index == -1:
            part_index = 0
        if not (0 <= part_index < len(self.song_state.parts)):
            return

        part = self.song_state.parts[part_index]
        current_song_idx = self.playlist_state.current_song_index if self.playlist_state.is_active else 0

        part_output = self.pending_collapsed_outputs if self.pending_collapsed_outputs is not None else part.get("output", [])
        self.pending_collapsed_outputs = None

        context = {
            "song_index": current_song_idx,
            "song_name": self.song_state.song_name,
            "song_color": self.song_state.song_color,
            "part_index": part_index,
            "part_name": part.get("name"),
            "part_bars": part.get("bars"),
            "part_color": part.get("color"),
            "part_notes": part.get("notes"),
            "part_cue": part.get("cue"),
            "part_index_in_setlist": self._get_global_part_index(current_song_idx, part_index),
            "part_output": part_output,
        }
        self.fire_triggers("part_change", context, force_instant=True)
        self.set_feedback_message(f"Outputs enviados: {part.get('name', 'N/A')}")

    # --- Transport handlers ---

    def handle_start(self, is_passive_start=False):
        """Lógica para procesar un comando START."""
        self._assert_motor_thread("handle_start")
        if self.clock_state.status == "PLAYING":
            return

        if self.clock_state.status == "STOPPED" and not self.initial_outputs_sent:
            self._send_initial_outputs()
            self.initial_outputs_sent = True
            self.set_feedback_message("Clock detectado. Iniciando secuencia...")
            return

        if not is_passive_start:
            _transport = self.port_registry.get_output("transport_out")
            if _transport is not None:
                try:
                    _transport.send(mido.Message('start'))
                except Exception as e:
                    self.set_feedback_message(f"Error transport_out: {e}")
        self._playback_start_count += 1
        self.fire_triggers("playback_start", {})
        self.fire_triggers("playback_initial_start", {})

        self.clock_state.status = "PLAYING"
        self.clock_state.start_time = time.time()
        self.clock_state.paused_set_elapsed_time = 0
        self.reset_song_state_on_stop()
        if self.bus:
            self.bus.publish(bus_topics.MIDITEMA_TRANSPORT, {"state": "play"}, retain=True)

        if self.playlist_state.is_active and self.playlist_state.playlist_elements:
            current_idx = max(self.playlist_state.current_song_index, 0)
            song_element = self.playlist_state.playlist_elements[current_idx]
            context = {
                "song_index": current_idx,
                "song_name": song_element.get("song_name", Path(song_element.get("filepath", "N/A")).stem),
                "song_color": song_element.get("color")
            }
            self.fire_triggers("song_change", context, force_instant=True)

        self.start_next_part()

    def _send_transport_stop(self):
        """Envía MIDI stop al transport_out, dispara playback_stop y ejecuta auto-panic si está configurado."""
        _transport = self.port_registry.get_output("transport_out")
        if _transport is not None:
            try:
                _transport.send(mido.Message('stop'))
            except Exception as e:
                self.set_feedback_message(f"Error transport_out: {e}")
        self.fire_triggers("playback_stop", {})
        if self.bus:
            self.bus.publish(bus_topics.MIDITEMA_TRANSPORT, {"state": "stop"}, retain=True)
        if self.config.get("auto_panic_on_stop", True):
            # En bus mode completo (clock por bus + outputs por bus), midimod ya ejecuta
            # global_panic al recibir STOP — publicar un segundo panic via bus produce doble
            # All Notes Off en los dispositivos. El pánico manual (TUI) no pasa por aquí.
            if not (self._bus_clock_alias and self.bus_outputs):
                self.panic()

    def handle_stop(self):
        """Lógica para procesar un comando STOP."""
        self._assert_motor_thread("handle_stop")
        if self.clock_state.status == "STOPPED":
            return

        self.initial_outputs_sent = False
        self._send_transport_stop()

        if self.clock_state.status == "PLAYING":
            current_time = time.time()
            if self.clock_state.start_time > 0:
                self.clock_state.paused_set_elapsed_time += current_time - self.clock_state.start_time
            if self.song_state.start_time > 0:
                self.song_state.paused_song_elapsed_time += current_time - self.song_state.start_time

        self.clock_state.status = "STOPPED"

    def handle_continue(self):
        """Lógica para procesar un comando CONTINUE."""
        self._assert_motor_thread("handle_continue")
        if self.clock_state.status == "PLAYING":
            return

        _transport = self.port_registry.get_output("transport_out")
        if _transport is not None:
            try:
                _transport.send(mido.Message('continue'))
            except Exception as e:
                self.set_feedback_message(f"Error transport_out: {e}")
        self.fire_triggers("playback_continue", {})
        self.clock_state.status = "PLAYING"
        if self.bus:
            self.bus.publish(bus_topics.MIDITEMA_TRANSPORT, {"state": "play"}, retain=True)
        current_time = time.time()
        self.clock_state.start_time = current_time
        if self.song_state.current_part_index == -1:
            self.start_next_part()
        else:
            self.song_state.start_time = current_time

    # --- Listeners ---

    def midi_control_listener_for(self, alias: str) -> None:
        """Hilo que escucha mensajes MIDI de control en el puerto con nombre 'alias'."""
        while not self.shutdown_flag:
            port = self.port_registry.get_input(alias)
            if not port:
                time.sleep(0.1)
                continue
            try:
                msg = port.poll()
            except Exception:
                time.sleep(0.1)
                continue
            if not msg:
                time.sleep(0.001)
                continue
            self._event_queue.put({"type": "control", "msg": msg, "alias": alias})

    def midi_input_listener(self):
        """Hilo principal que escucha los mensajes MIDI y actualiza el estado."""
        main_port = self.port_registry.get_input("clock")
        if not main_port:
            logger.warning("No clock port configured; MIDI input listener exiting.")
            return

        time.sleep(0.05)
        while main_port.poll() is not None:
            pass

        shared_aliases = list(self._shared_clock_aliases)
        is_shared_port = bool(shared_aliases)

        listener = ClockListener.from_port(main_port)

        def _on_tick():
            self._event_queue.put({"type": "tick", "bpm": listener.bpm, "ts": time.time()})

        listener.on_tick = _on_tick
        if is_shared_port:
            _clock_alias = self.config.get("clock_in", "")
            def _on_other(msg, _alias=_clock_alias):
                self._event_queue.put({"type": "control", "msg": msg, "alias": _alias})
            listener.on_other = _on_other

        _transport_rx = _TransportReceiver(listener)
        _transport_rx.on_start = lambda: self._event_queue.put({"type": "start", "passive": False})
        _transport_rx.on_stop = lambda: self._event_queue.put({"type": "stop"})
        _transport_rx.on_continue = lambda: self._event_queue.put({"type": "continue"})

        listener.start()

        while not self.shutdown_flag:
            time.sleep(0.05)

        _transport_rx.stop()
        listener.stop()

    def midi_control_listener(self):
        """Compatibilidad: delega al primer puerto de control no-clock."""
        alias = next(
            (info.alias for info in self.port_registry.iter_ports()
             if info.direction == "in" and info.alias != "clock"),
            None,
        )
        if alias:
            self.midi_control_listener_for(alias)

    # --- Jumps disparados desde la UI/control ---

    def trigger_song_jump(self, action_dict):
        """Crea una acción pendiente si el reloj está en PLAYING, o ejecuta el salto inmediatamente si está detenido."""
        if self.clock_state.status == "PLAYING":
            self.pending_action = action_dict
        else:
            self.pending_action = action_dict
            self.execute_song_jump(silent=True)

    def toggle_outputs(self):
        """Activa/desactiva el envío de outputs."""
        self.outputs_enabled = not self.outputs_enabled
        status = "activado" if self.outputs_enabled else "desactivado"
        self.set_feedback_message(f"Envío de outputs {status}")

    def activate_part_loop(self):
        self._outputs_enabled_before_loop_part = self.outputs_enabled
        self.outputs_enabled = False
        self.part_loop_active = True
        self.part_loop_index = self.song_state.current_part_index

    def cancel_part_loop(self):
        if self.part_loop_active:
            self.part_loop_active = False
            self.part_loop_index = -1
            if self._outputs_enabled_before_loop_part is not None:
                self.outputs_enabled = self._outputs_enabled_before_loop_part
                self._outputs_enabled_before_loop_part = None
            self.set_feedback_message("Part loop cancelled.")

    def toggle_session_mode(self):
        """Activa o desactiva el Session Mode (las partes se repiten hasta disparo manual)."""
        self.session_mode = not self.session_mode
        if self.session_mode:
            self.set_feedback_message("Session Mode activado — las partes se repiten hasta disparo manual.")
        else:
            self.set_feedback_message("Session Mode desactivado.")

    def trigger_cue_jump(self, cue_num: int):
        """Gestiona la lógica para disparar un salto a un Cue."""
        if not self.playlist_state.is_active:
            self.set_feedback_message(f"Cues ignorados (no hay playlist activa).")
            return

        target_song_idx = None
        target_part_idx = None
        part_name = "N/A"

        for s_idx, element in enumerate(self.playlist_state.playlist_elements):
            parts = self._get_parts_from_playlist_element(element)
            for p_idx, part in enumerate(parts):
                if part.get("cue") == cue_num:
                    target_song_idx = s_idx
                    target_part_idx = p_idx
                    part_name = part.get("name", "N/A")
                    break
            if target_song_idx is not None:
                break

        if target_song_idx is None:
            self.set_feedback_message(f"Cue {cue_num} no encontrado en la playlist.")
            return

        if (self.pending_action and
                self.pending_action.get("target_type") == "cue_jump" and
                self.pending_action.get("cue_num") == cue_num):

            new_quantize = self.halve_quantization(self.pending_action["dynamic_quantize"])
            self.pending_action["dynamic_quantize"] = new_quantize
            self.set_feedback_message(f"Cue {cue_num} ({part_name}) acelerado a {new_quantize.upper()}.")

        else:
            self.pending_action = {
                "target_type": "cue_jump",
                "target_song": target_song_idx,
                "target_part": target_part_idx,
                "cue_num": cue_num,
                "dynamic_quantize": self.quantize_mode
            }
            self.set_feedback_message(f"Ir a Cue {cue_num}: {part_name}")
            if self.clock_state.status != "PLAYING":
                self.execute_global_part_jump(silent=True)

    # Valid action names for the 'control' section
    _CONTROL_ACTIONS = frozenset({
        "next_part", "prev_part", "next_song", "prev_song", "song_first", "song_last",
        "song_restart", "song_jump", "part_loop_toggle", "part_restart", "action_cancel",
        "mode_toggle", "global_part_jump", "cue_jump",
        "set_quant_4", "set_quant_8", "set_quant_16", "set_quant_bar", "set_quant_end",
        "set_quant_instant",
        "quant_jump_instant", "quant_jump_bar", "quant_jump_8", "quant_jump_16",
    })

    def _dispatch_control_action(self, action: str, arg=None, msg_value: int = 0) -> None:
        """Ejecuta una acción de control por nombre (catálogo de la sección 'control')."""
        if action == "next_part":
            target = {"type": "relative", "value": 1}
            self.pending_action = {"target": target, "quantize": self.quantize_mode}
            self.set_feedback_message("Control: Siguiente Parte.")
        elif action == "prev_part":
            target = {"type": "relative", "value": -1}
            self.pending_action = {"target": target, "quantize": self.quantize_mode}
            self.set_feedback_message("Control: Parte Anterior.")
        elif action == "next_song":
            if not self.playlist_state.is_active:
                self.set_feedback_message("Control: ignorado (no hay playlist activa).")
                return
            act = {"target_type": "song", "target": {"type": "relative", "value": 1}, "quantize": self.quantize_mode}
            self.trigger_song_jump(act)
            self.set_feedback_message("Control: Siguiente Canción.")
        elif action == "prev_song":
            if not self.playlist_state.is_active:
                self.set_feedback_message("Control: ignorado (no hay playlist activa).")
                return
            act = {"target_type": "song", "target": {"type": "relative", "value": -1}, "quantize": self.quantize_mode}
            self.trigger_song_jump(act)
            self.set_feedback_message("Control: Canción Anterior.")
        elif action == "song_first":
            if not self.playlist_state.is_active:
                self.set_feedback_message("Control: ignorado (no hay playlist activa).")
                return
            act = {"target_type": "song", "target": 0, "quantize": self.quantize_mode}
            self.trigger_song_jump(act)
            self.set_feedback_message("Control: Primera Canción.")
        elif action == "song_last":
            if not self.playlist_state.is_active:
                self.set_feedback_message("Control: ignorado (no hay playlist activa).")
                return
            last = len(self.playlist_state.playlist_elements) - 1
            act = {"target_type": "song", "target": last, "quantize": self.quantize_mode}
            self.trigger_song_jump(act)
            self.set_feedback_message("Control: Última Canción.")
        elif action == "song_restart":
            if not self.playlist_state.is_active:
                self.set_feedback_message("Control: ignorado (no hay playlist activa).")
                return
            act = {"target_type": "song", "target": "restart", "quantize": self.quantize_mode}
            self.trigger_song_jump(act)
            self.set_feedback_message("Control: Reiniciar Canción.")
        elif action == "song_jump":
            target_idx = int(arg) if arg is not None else msg_value
            if not self.playlist_state.is_active:
                self.set_feedback_message("Control: ignorado (no hay playlist activa).")
                return
            act = {"target_type": "song", "target": target_idx, "quantize": self.quantize_mode}
            self.trigger_song_jump(act)
            self.set_feedback_message(f"Control: Ir a canción {target_idx + 1}.")
        elif action == "part_loop_toggle":
            if self.part_loop_active:
                self.cancel_part_loop()
            else:
                self.activate_part_loop()
        elif action == "part_restart":
            if self.clock_state.status == "PLAYING":
                self.pending_action = {"target": "restart", "quantize": self.quantize_mode}
                self.set_feedback_message("Control: Reiniciar Parte.")
            else:
                self.set_feedback_message("Control: ignorado (reproducción detenida).")
        elif action == "action_cancel":
            if self.pending_action:
                self.pending_action = None
                self.set_feedback_message("Control: Acción cancelada.")
        elif action == "mode_toggle":
            self.repeat_override_active = not self.repeat_override_active
            self.user_mode_override = self.repeat_override_active
            mode_str = "Song Mode" if self.repeat_override_active else "Loop Mode"
            self.set_feedback_message(f"Control: {mode_str}")
        elif action == "global_part_jump":
            val = int(arg) if arg is not None else msg_value
            if not self.playlist_state.is_active:
                self.set_feedback_message("Control: ignorado (no hay playlist activa).")
                return
            target_song_idx, target_part_idx = self.resolve_global_part_index(val)
            if target_song_idx is not None:
                self.pending_action = {
                    "target_type": "global_part",
                    "target_song": target_song_idx,
                    "target_part": target_part_idx,
                    "quantize": self.quantize_mode,
                }
                self.set_feedback_message(f"Control: Ir a parte global {val + 1}.")
            else:
                self.set_feedback_message(f"Control: Parte global {val + 1} no existe.")
        elif action == "cue_jump":
            val = int(arg) if arg is not None else msg_value
            self.trigger_cue_jump(val)
        elif action in ("set_quant_4", "set_quant_8", "set_quant_16",
                        "set_quant_bar", "set_quant_end", "set_quant_instant"):
            quant_map = {
                "set_quant_4": "next_4",
                "set_quant_8": "next_8",
                "set_quant_16": "next_16",
                "set_quant_bar": "next_bar",
                "set_quant_end": "end_of_part",
                "set_quant_instant": "instant",
            }
            self.quantize_mode = quant_map[action]
            self.set_feedback_message(f"Control: cuantización → {self.quantize_mode.upper()}.")
        elif action.startswith("quant_jump_"):
            quant_map = {
                "quant_jump_instant": "instant",
                "quant_jump_bar": "next_bar",
                "quant_jump_8": "next_8",
                "quant_jump_16": "next_16",
            }
            quant = quant_map.get(action, "instant")
            target = {"type": "relative", "value": 1}
            self.pending_action = {"target": target, "quantize": quant}
            self.set_feedback_message(f"Control: Salto rápido ({quant.upper()}).")
        else:
            logger.warning(f"[!] Control: acción desconocida '{action}'")

    def process_control_message(self, msg, device_alias: str = "") -> None:
        """Procesa un único mensaje de control MIDI (PC, CC, Note, Song Select)."""
        # Implicit: program_change → jump to part by number
        if msg.type == 'program_change':
            if self.clock_state.status == "PLAYING":
                self.pending_action = {"target": msg.program, "quantize": self.quantize_mode}
                self.set_feedback_message(f"PC: Ir a parte {msg.program + 1}.")
            else:
                target_index = msg.program
                if 0 <= target_index < len(self.song_state.parts):
                    self.setup_part(target_index)
                    self.set_feedback_message(
                        f"PC: Parte {target_index + 1} "
                        f"({self.song_state.parts[target_index].get('name', '')}) pre-configurada."
                    )
                else:
                    self.set_feedback_message(f"PC: Parte {target_index + 1} no existe.")
            return

        # Implicit: song_select → jump to song by number
        if msg.type == 'song_select':
            if self.playlist_state.is_active:
                action = {"target_type": "song", "target": msg.song, "quantize": self.quantize_mode}
                self.trigger_song_jump(action)
                self.set_feedback_message(f"Song Select: Ir a canción {msg.song + 1}.")
            else:
                self.set_feedback_message("Song Select ignorado (no hay playlist activa).")
            return

        # Config-driven: match against 'control' rules
        control_rules = self.config.get("control") if isinstance(self.config.get("control"), list) else []
        if not control_rules:
            return

        for rule in control_rules:
            if not isinstance(rule, dict):
                continue

            # Filter by device_in: if rule declares a device, message must match it.
            # An empty device_alias (shared clock port, no alias passed) never matches.
            rule_device = rule.get("device_in")
            if rule_device and rule_device != device_alias:
                continue

            event_type = rule.get("event", "").lower()
            matched = False
            msg_value = 0

            if event_type == "cc" and msg.type == "control_change":
                rule_cc = rule.get("cc")
                rule_ch = rule.get("ch")
                rule_value = rule.get("value")
                if rule_cc is not None and msg.control != int(rule_cc):
                    continue
                if rule_ch is not None and msg.channel != int(rule_ch):
                    continue
                if rule_value is not None and msg.value != int(rule_value):
                    continue
                matched = True
                msg_value = msg.value

            elif event_type == "note" and msg.type == "note_on" and msg.velocity > 0:
                rule_note = rule.get("note")
                rule_ch = rule.get("ch")
                if rule_note is not None and msg.note != int(rule_note):
                    continue
                if rule_ch is not None and msg.channel != int(rule_ch):
                    continue
                matched = True
                msg_value = msg.note

            elif event_type == "note_off" and (
                msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0)
            ):
                rule_note = rule.get("note")
                rule_ch = rule.get("ch")
                if rule_note is not None and msg.note != int(rule_note):
                    continue
                if rule_ch is not None and msg.channel != int(rule_ch):
                    continue
                matched = True
                msg_value = msg.note

            if matched:
                action_name = rule.get("action")
                if action_name:
                    self._dispatch_control_action(action_name, arg=rule.get("arg"), msg_value=msg_value)
                return  # first matching rule wins

    def _get_global_part_index(self, target_song_idx, local_part_idx):
        """Convierte un par (índice_de_canción, índice_de_parte_local) en un índice de parte global."""
        if not self.playlist_state.is_active:
            return local_part_idx

        cumulative_parts = 0
        for i in range(target_song_idx):
            element = self.playlist_state.playlist_elements[i]
            parts_in_song = self._get_parts_from_playlist_element(element)
            cumulative_parts += len(parts_in_song)

        return cumulative_parts + local_part_idx

    def handle_song_end(self):
        """Gestiona el final de la secuencia de una canción."""
        if self.playlist_state.is_active:
            next_song_index = self.playlist_state.current_song_index + 1
            if next_song_index < len(self.playlist_state.playlist_elements):
                next_song_element = self.playlist_state.playlist_elements[next_song_index]
                next_song_name = "Siguiente Canción"
                if "filepath" in next_song_element:
                    next_song_name = Path(next_song_element["filepath"]).stem
                elif "song_name" in next_song_element:
                    next_song_name = next_song_element["song_name"]

                self.set_feedback_message(f"Iniciando '{next_song_name}'...")

                if self.load_song_from_playlist(next_song_index):
                    self.start_next_part()
                else:
                    self._send_transport_stop()
                    self.clock_state.status = "FINISHED"
                    self.reset_song_state_on_stop()
                    self.set_feedback_message("Error al cargar la siguiente canción. Reproducción detenida.")
            else:
                total_parts = 0
                for element in self.playlist_state.playlist_elements:
                    total_parts += len(self._get_parts_from_playlist_element(element))

                context = {
                    "playlist_name": self.playlist_state.playlist_name,
                    "playlist_song_count": len(self.playlist_state.playlist_elements),
                    "playlist_part_count": total_parts
                }
                self.fire_triggers("setlist_end", context)
                self._send_transport_stop()
                self.clock_state.status = "FINISHED"
                self.reset_song_state_on_stop()
                self.set_feedback_message(f"Playlist '{self.playlist_state.playlist_name}' finalizada.")
        else:
            self._send_transport_stop()
            self.clock_state.status = "FINISHED"
            self.reset_song_state_on_stop()
            self.set_feedback_message(f"Canción '{self.song_state.song_name}' finalizada.")

    def set_feedback_message(self, message: str, duration: int = 5, sticky: bool = False, level: str = "info"):
        """Establece un mensaje de feedback con nivel y opcionalmente sticky."""
        self.ui_feedback_message = message
        self.feedback_sticky = sticky
        self.feedback_level = level
        self.feedback_expiry_time = float('inf') if sticky else time.time() + duration

    def panic(self) -> None:
        """Envía All Notes Off, All Sound Off y Reset All Controllers a todos los MIDI outputs."""
        if self.bus_outputs and self.bus:
            for alias, value in self.config.get("device_alias", {}).items():
                if isinstance(value, str):
                    for ch in range(16):
                        self.bus.publish(bus_topics.MIDITEMA_OUTPUT, {
                            "device": alias, "channel": ch,
                            "msg_type": "control_change",
                            "control": 123, "value": 0,
                        })
            self.set_feedback_message("⚡ PANIC — All Notes Off enviado (bus)", duration=3, level="warning")
            return
        for info in self.port_registry.iter_ports():
            if info.direction != "out":
                continue
            try:
                if info.port.closed:
                    continue
                for ch in range(16):
                    info.port.send(mido.Message('control_change', channel=ch, control=123, value=0))
                    info.port.send(mido.Message('control_change', channel=ch, control=120, value=0))
                    info.port.send(mido.Message('control_change', channel=ch, control=121, value=0))
            except Exception as e:
                logger.warning(f"[!] Panic ({info.alias}): {e}")
        self.set_feedback_message("⚡ PANIC — All Notes Off enviado", duration=3, level="warning")

    def _setup_file_watch(self, filepath) -> None:
        """Registra el archivo cargado para detectar cambios en disco."""
        self._watched_file_path = filepath
        self.file_changed_on_disk = False
        try:
            self._watched_file_mtime = filepath.stat().st_mtime
        except OSError:
            self._watched_file_mtime = 0.0

    def check_file_watch(self) -> None:
        """Comprueba si el archivo vigilado ha cambiado. Llamar desde el poll de la TUI."""
        if self._watched_file_path is None or self.file_changed_on_disk:
            return
        try:
            mtime = self._watched_file_path.stat().st_mtime
            if mtime != self._watched_file_mtime:
                self.file_changed_on_disk = True
        except OSError:
            pass

    def get_dynamic_endpoint(self):
        """Calcula el compás final relevante."""
        if not self.pending_action or self.clock_state.status != "PLAYING" or self.song_state.current_part_index == -1:
            if self.song_state.current_part_index != -1:
                return self.song_state.parts[self.song_state.current_part_index].get("bars", 0)
            return 0

        current_part = self.song_state.parts[self.song_state.current_part_index]
        total_bars_in_part = current_part.get("bars", 0)

        target = self.pending_action.get("target")
        if isinstance(target, dict) and target.get("type") == "relative" and target.get("value") == 0:
            return total_bars_in_part

        sig_num = self.song_state.time_signature_numerator
        beats_into_part = (total_bars_in_part * sig_num) - self.song_state.remaining_beats_in_part
        current_bar_index = beats_into_part // sig_num

        quantize = self.pending_action.get("dynamic_quantize") or self.pending_action.get("quantize")

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

    def load_file_by_name(self, filename: str) -> None:
        """Carga un archivo de canción o playlist por su nombre."""
        self._parts_file_cache.clear()
        filepath = self.SONGS_DIR / filename
        if not filepath.is_file():
            self.set_feedback_message(f"Error: no se encontró el archivo '{filename}'")
            return

        is_valid, errors, data = MIDItemaValidator.validate_file(filepath)
        if not is_valid:
            error_details = "\n".join(str(e) for e in errors[:5])
            self.set_feedback_message(f"[!] Archivo inválido: {errors[0]}")
            logger.warning(f"[!] Errores de validación en '{filename}':\n{error_details}")
            return

        self.reset_song_state_on_stop()
        self.playlist_state = PlaylistState()

        if "songs" in data and isinstance(data["songs"], list):
            self.playlist_state.is_active = True
            self.playlist_state.playlist_name = data.get("playlist_name", filepath.stem)
            self.playlist_state.triggers = data.get("triggers", {})
            self.playlist_state.playlist_elements = data["songs"]
            self.set_feedback_message(f"Playlist '{self.playlist_state.playlist_name}' cargada.")

            playlist_mode = data.get("mode", "song")
            if self.user_mode_override is None:
                self.repeat_override_active = playlist_mode.lower() == "song"

            self.load_song_from_playlist(0)
        else:
            self.playlist_state.is_active = False
            self.load_song_file(data=data)

        self.loaded_filename = filepath.relative_to(self.SONGS_DIR).with_suffix('').as_posix()
        self._setup_file_watch(filepath)

    def reconfigure_clock_port(self, port_name: str) -> None:
        """Cierra el puerto de clock actual y abre uno nuevo."""
        if self.clock_state.status != "STOPPED":
            self.handle_stop()

        self.port_registry.close("clock")

        try:
            self.port_registry.open_input("clock", port_name)
            self.clock_state.source_name = port_name
            self.set_feedback_message(f"Clock reconfigurado a: '{port_name}'")
        except Exception as e:
            self.set_feedback_message(f"Error abriendo '{port_name}': {e}")
            self.clock_state.source_name = "Ninguna"

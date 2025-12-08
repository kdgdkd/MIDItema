import jsonschema
from jsonschema import Draft7Validator, validators
from pathlib import Path
import json5
from typing import Dict, List, Tuple, Optional

class ValidationError:
    """Representa un error de validación con contexto detallado."""
    def __init__(self, message: str, path: List[str], line_number: Optional[int] = None):
        self.message = message
        self.path = path
        self.line_number = line_number
    
    def __str__(self):
        path_str = " → ".join(self.path) if self.path else "root"
        line_info = f" (línea ~{self.line_number})" if self.line_number else ""
        return f"[{path_str}]{line_info}: {self.message}"

class MIDItemaValidator:
    """Validador de archivos JSON para MIDItema con mensajes descriptivos."""
    
    # --- DEFINICIONES REUTILIZABLES ---

    # Definición para campos que aceptan entero (0-127) o string dinámico (ej: "part_index")
    # Soluciona BUG-001: Incompatibilidad de tipos para valores dinámicos
    INT_OR_DYNAMIC_7BIT = {
        "oneOf": [
            {"type": "integer", "minimum": 0, "maximum": 127},
            {"type": "string", "minLength": 1}
        ],
        "description": "Valor MIDI (0-127) o variable dinámica (ej: 'part_index')"
    }

    # Definición para canales MIDI (0-15) o dinámicos
    INT_OR_DYNAMIC_CHANNEL = {
        "oneOf": [
            {"type": "integer", "minimum": 0, "maximum": 15},
            {"type": "string", "minLength": 1}
        ],
        "description": "Canal MIDI (0-15) o variable dinámica"
    }

    # Schema para acciones de trigger
    # Actualizado para soportar tipos flexibles en argumentos OSC y valores MIDI
    TRIGGER_ACTION_SCHEMA = {
        "type": "object",
        "properties": {
            "device": {"type": "string"},
            "type": {
                "type": "string", 
                "enum": ["note_on", "note_off", "control_change", 
                         "program_change", "song_select", "start", 
                         "stop", "continue"]
            },

            # Campos MIDI con soporte dinámico
            "channel": INT_OR_DYNAMIC_CHANNEL,
            "note": INT_OR_DYNAMIC_7BIT,
            "velocity": INT_OR_DYNAMIC_7BIT,
            "control": INT_OR_DYNAMIC_7BIT,
            "value": INT_OR_DYNAMIC_7BIT,
            "program": INT_OR_DYNAMIC_7BIT,
            "song": INT_OR_DYNAMIC_7BIT,
            
            # Campos OSC
            "address": {"type": "string"},
            "args": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "integer"},
                        {"type": "number"},
                        {"type": "boolean"}
                    ]
                },
                "description": "Argumentos para mensajes OSC (tipos mixtos permitidos)"
            },
            
            # Timing (estos deben ser enteros para el cálculo matemático interno)
            "bar": {"type": "integer", "minimum": 0},
            "beats": {"type": "integer", "minimum": 0}
        }
    }

    # Schema para una parte individual
    PART_SCHEMA = {
        "type": "object",
        "required": ["name", "bars"],
        "properties": {
            "name": {
                "type": "string",
                "minLength": 1,
                "description": "Nombre de la parte"
            },
            "bars": {
                "type": "integer",
                "minimum": 1,
                "maximum": 999,
                "description": "Número de compases"
            },
            "color": {
                "type": "string",
                "pattern": "^(#[0-9a-fA-F]{6}|default|red|green|yellow|blue|magenta|cyan|orange|ruby_pink|indigo_blue|purple|forest_green|ivory|bright_red|neon_green|electric_blue|bright_yellow|hot_pink|electric_cyan|electric_orange|dark_gray|mid_gray|light_gray|white)$",
                "description": "Color de la parte"
            },
            "notes": {
                "type": "string",
                "description": "Notas o comentarios"
            },
            "cue": {
                "type": "integer",
                "minimum": 1,
                "maximum": 127,
                "description": "Número de cue"
            },
            "repeat_pattern": {
                "oneOf": [
                    {"type": "boolean"},
                    {"type": "string", "enum": ["true", "false", "repeat", "next", "prev", "first_part", 
                                                "last_part", "loop_part", "next_song", "prev_song", 
                                                "first_song", "last_song", "song_mode", "loop_mode"]},
              
                    {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "boolean"},
                                {"type": "string", "enum": ["repeat", "next", "prev"]},
                                {
                                    "type": "object",
                                    "properties": {
                                        "jump_to_part": {"type": "integer", "minimum": 0},
                                        "jump_to_cue": {"type": "integer", "minimum": 1},
                                        "random_part": {
                                            "type": "array",
                                            "items": {"type": "integer", "minimum": 0}
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ],
                "description": "Patrón de repetición"
            },
            "output": {
                "oneOf": [
                    {"$ref": "#/definitions/trigger_action"},
                    {
                        "type": "array",
                        "items": {"$ref": "#/definitions/trigger_action"}
                    }
                ],
                "description": "Acciones de salida MIDI/OSC"
            }
        }
    }
    
    # Schema principal para canciones
    SONG_SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "definitions": {
            "trigger_action": TRIGGER_ACTION_SCHEMA
        },
        "type": "object",
        "required": ["parts"],
        "properties": {
            "song_name": {"type": "string"},
            "color": {"type": "string"},
            "time_signature": {
                "type": "string",
                "pattern": "^\\d+/\\d+$",
                "description": "Signatura de tiempo (ej: 4/4)"
            },
            "time_division": {
                "type": "string",
                "enum": ["1/4", "1/8", "1/16"],
                "description": "División de tiempo para el contador"
            },
            "devices": {
                "type": "object",
                "description": "Definición local de dispositivos (override)"
            },
            "triggers": {
                "type": "object",
                "description": "Triggers globales de la canción"
            },
            "parts": {
                "type": "array",
                "minItems": 1,
                "items": PART_SCHEMA
            }
        }
    }
    
    # Schema para playlists
    PLAYLIST_SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["songs"],
        "properties": {
            "playlist_name": {"type": "string"},
            "mode": {
                "type": "string",
                "enum": ["loop", "song"],
                "description": "Modo de reproducción por defecto"
            },
            "devices": {"type": "object"},
            "triggers": {"type": "object"},
            "beats": {"type": "integer"}, 
            "bars": {"type": "integer"},
            "songs": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "oneOf": [
                        {
                            "type": "object",
                            "required": ["filepath"],
                            "properties": {
                                "filepath": {"type": "string"},
                                "song_name": {"type": "string"},
                                "color": {"type": "string"}
                            }
                        },
                        {
                            "allOf": [
                                {"$ref": "#/definitions/song"},
                                {
                                    "type": "object",
                                    "required": ["song_name"]
                                }
                            ]
                        }
                    ]
                }
            }
        },
        "definitions": {
            "song": SONG_SCHEMA,
            "trigger_action": TRIGGER_ACTION_SCHEMA
        }
    }
    
    @staticmethod
    def _create_validator_with_defaults(schema):
        """Crea un validador que aplica valores por defecto."""
        def extend_with_default(validator_class):
            validate_properties = validator_class.VALIDATORS["properties"]
            
            def set_defaults(validator, properties, instance, schema):
                for property, subschema in properties.items():
                    if "default" in subschema:
                        instance.setdefault(property, subschema["default"])
                
                for error in validate_properties(validator, properties, instance, schema):
                    yield error
            
            return validators.create(
                validator_class.META_SCHEMA,
                {**validator_class.VALIDATORS, "properties": set_defaults}
            )
        
        DefaultValidator = extend_with_default(Draft7Validator)
        return DefaultValidator(schema)
    
    @staticmethod
    def estimate_line_number(json_str: str, path: List[str]) -> Optional[int]:
        """Estima el número de línea aproximado de un error basándose en el path."""
        lines = json_str.split('\n')
        current_line = 1
        
        for i, line in enumerate(lines, 1):
            for element in path:
                if f'"{element}"' in line or f"'{element}'" in line:
                    current_line = i
                    break
        
        return current_line
    
    @classmethod
    def validate_data(cls, data: dict, json_str: str = "") -> List[ValidationError]:
        """
        Valida los datos y retorna una lista de errores descriptivos.
        """
        errors = []
        
        # Determinar si es playlist o canción
        is_playlist = "songs" in data and isinstance(data["songs"], list)
        schema = cls.PLAYLIST_SCHEMA if is_playlist else cls.SONG_SCHEMA
        
        validator = cls._create_validator_with_defaults(schema)
        
        for error in validator.iter_errors(data):
            # Construir el path legible
            path = []
            for element in error.absolute_path:
                if isinstance(element, int):
                    path.append(f"[{element}]")
                else:
                    path.append(str(element))
            
            # Crear mensaje descriptivo
            message = cls._format_error_message(error)
            
            # Estimar línea si tenemos el string JSON
            line_num = cls.estimate_line_number(json_str, path) if json_str else None
            
            errors.append(ValidationError(message, path, line_num))
        
        ## Validaciones adicionales personalizadas
        if is_playlist:
            errors.extend(cls._validate_playlist_custom(data))
        else:
            errors.extend(cls._validate_song_custom(data))
        
        return errors
    
    @staticmethod
    def _format_error_message(error) -> str:
        """Formatea mensajes de error para que sean más legibles."""
        if error.validator == 'required':
            return f"Falta el campo requerido '{error.validator_value[0]}'"
        elif error.validator == 'type':
            expected = error.validator_value
            actual = type(error.instance).__name__
            return f"Tipo incorrecto: se esperaba {expected}, se recibió {actual}"
        elif error.validator == 'minimum':
            return f"Valor {error.instance} es menor que el mínimo permitido ({error.validator_value})"
        elif error.validator == 'maximum':
            return f"Valor {error.instance} es mayor que el máximo permitido ({error.validator_value})"
        elif error.validator == 'minItems':
            return f"La lista debe tener al menos {error.validator_value} elementos"
        elif error.validator == 'pattern':
            return f"El valor '{error.instance}' no coincide con el formato esperado"
        elif error.validator == 'enum':
            return f"Valor '{error.instance}' no válido. Opciones: {', '.join(map(str, error.validator_value))}"
        elif error.validator == 'oneOf':
            return "El valor no coincide con ninguno de los esquemas permitidos (verificar tipos string/integer)"
        else:
            return error.message
    
    @staticmethod
    def _validate_song_custom(data: dict) -> List[ValidationError]:
        """Validaciones personalizadas para canciones."""
        errors = []
        
        # Verificar cues duplicados dentro de la canción
        if "parts" in data:
            cues = [p.get("cue") for p in data["parts"] if "cue" in p]
            duplicate_cues = set([x for x in cues if cues.count(x) > 1])
            if duplicate_cues:
                errors.append(ValidationError(
                    f"Números de cue duplicados en la misma canción: {', '.join(map(str, duplicate_cues))}",
                    ["parts"]
                ))
        
        # Verificar referencias en repeat_pattern
        if "parts" in data:
            for i, part in enumerate(data["parts"]):
                pattern = part.get("repeat_pattern")
                if isinstance(pattern, dict):
                    if "jump_to_part" in pattern:
                        target = pattern["jump_to_part"]
                        if target >= len(data["parts"]):
                            errors.append(ValidationError(
                                f"jump_to_part hace referencia a parte inexistente: {target}",
                                ["parts", f"[{i}]", "repeat_pattern"]
                            ))
                    if "random_part" in pattern:
                        for target in pattern["random_part"]:
                            if target >= len(data["parts"]):
                                errors.append(ValidationError(
                                    f"random_part contiene referencia a parte inexistente: {target}",
                                    ["parts", f"[{i}]", "repeat_pattern", "random_part"]
                                ))
        
        return errors
    
    @staticmethod
    def _validate_playlist_custom(data: dict) -> List[ValidationError]:
        """Validaciones personalizadas para playlists."""
        errors = []
        
        # Aquí se podrían agregar validaciones de existencia de archivos
        # pero requiere contexto del sistema de archivos que esta clase pura no tiene.
        return errors
    
    @classmethod
    def validate_file(cls, filepath: Path) -> Tuple[bool, List[ValidationError], Optional[dict]]:
        """
        Valida un archivo y retorna (es_válido, errores, datos_parseados).
        """
        try:
            with filepath.open('r', encoding='utf-8') as f:
                content = f.read()
                data = json5.loads(content)
            
            errors = cls.validate_data(data, content)
            return len(errors) == 0, errors, data
            
        except json5.JSONDecodeError as e:
            error = ValidationError(
                f"Error de sintaxis JSON: {str(e)}",
                [],
                e.lineno if hasattr(e, 'lineno') else None
            )
            return False, [error], None
        except Exception as e:
            error = ValidationError(f"Error al leer archivo: {str(e)}", [])
            return False, [error], None
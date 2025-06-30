# MIDItema

Un contador de compases y arreglista de canciones para la terminal, que emite los cambios de partes de la canción vía OSC.

## Concepto Principal

MIDItema escucha a un reloj maestro externo (como un DAW, un secuenciador por hardware, o nuestra herramienta compañera midimaster) y utiliza esa información de tempo para avanzar a través de una estructura de canción predefinida.

Mostrará una cuenta atrás de compases para la parte actual de la canción, permitiendo al usuario saber con antelación cuándo ocurrirá el siguiente cambio en la canción.

Los cambios también se emiten con OSC, para que puedan ser leídos por otras aplicaciones.

## Características

- **Cuenta atrás de compases:** Muestra el número de compases que quedan en la parte actual de la canción.
  
- **Esclavo de MIDI Clock:** Se sincroniza perfectamente con cualquier fuente de MIDI clock estándar.
  
- **Estructura de Canción basada en JSON:** Define la estructura completa de tu canción, partes y duraciones en archivos JSON simples y legibles por humanos.
  
- **Lógica de Repetición Avanzada:** Controla exactamente cuándo se repiten las partes usando patrones flexibles (ej. "reproducir solo una vez", "reproducir una vez sí y otra no", "reproducir dos veces, luego saltar dos veces").
  
- **TUI Visual:** Una interfaz de terminal limpia y a pantalla completa que proporciona una visión clara del estado actual.
  
- **Emisión OSC:** Envía mensajes OSC detallados en cada cambio de parte, permitiendo una fácil integración con otro software creativo (Resolume, TouchDesigner, VCV Rack, etc.).
  
- **Control de Transporte Remoto:** Puede enviar comandos Start/Stop a un dispositivo maestro, permitiéndote controlar toda tu configuración desde una sola terminal (mejor integrado con MIDImaster).
  
- **Configurable:** Todos los puertos de E/S y la configuración OSC se definen en un simple archivo de configuración.
  

## Cómo Funciona

1. **Escucha:** MIDItema se conecta a un puerto de entrada MIDI y escucha mensajes de MIDI Clock.
  
2. **Cuenta:** Utiliza los pulsos de reloj entrantes para contar tiempos y compases según la estructura del archivo de canción cargado.
  
3. **Secuencia:** Cuando una parte termina, determina la siguiente parte a reproducir basándose en la lógica repeat_pattern definida.
  
4. **Emite:** Tan pronto como una nueva parte comienza, envía un mensaje OSC con los detalles de la nueva parte a una dirección IP y puerto configurables.
  
5. **Controla (Opcional):** También puede enviar mensajes Start/Stop a un puerto de salida MIDI separado para controlar remotamente la fuente del reloj maestro.
  

## Instalación

1. Clona este repositorio.
  
2. Asegúrate de tener Python 3 instalado.
  
3. Instala las dependencias requeridas:
  
  Generated code
  
  ```
  pip install mido python-osc prompt-toolkit python-rtmidi
  ```
  
  Nota: python-rtmidi es un backend recomendado para mido en la mayoría de los sistemas.
  

## Configuración

MIDItema se controla mediante dos tipos de archivos JSON.

### 1. Configuración Principal (miditema.conf.json)

Este archivo, ubicado en el directorio raíz, define las conexiones MIDI y OSC.

Generated code

```
{
    "clock_source_alias": "CLOCK",
    "remote_control_alias": "TPT",
    "osc_configuration": {
        "send": {
            "ip": "127.0.0.1",
            "port": 9000,
            "address": "/miditema/part/change"
        }
    }
}
```

content_copydownload

Use code [with caution](https://support.google.com/legal/answer/13505487).

- clock_source_alias: Una subcadena del nombre del puerto de entrada MIDI que envía el reloj.
  
- remote_control_alias: Una subcadena del nombre del puerto de salida MIDI al que se envían los comandos de transporte.
  
- osc_configuration.send:
  
  - ip: La dirección IP de destino para los mensajes OSC (127.0.0.1 para la misma máquina).
    
  - port: El puerto de destino para los mensajes OSC.
    
  - address: La ruta de la dirección OSC para el mensaje.
    

### 2. Archivos de Canción (temas/*.json)

Estos archivos definen la estructura de una canción. Deben colocarse en un directorio temas/.

Generated code

```
{
    "song_name": "Mi Pista Increíble",
    "time_signature": "4/4",
    "time_division": "1/4",
    "parts": [
        { "name": "Intro", "bars": 8, "repeat_pattern": false },
        { "name": "Estrofa", "bars": 16, "repeat_pattern": true },
        { "name": "Estribillo", "bars": 16, "repeat_pattern": [true, false] }
    ]
}
```

- song_name: (Opcional) El nombre que se muestra en la interfaz. Por defecto, es el nombre del archivo.
  
- time_signature: (Opcional) Por defecto, "4/4".
  
- time_division: (Opcional) Cómo interpretar un "tiempo". Por defecto, "1/4" (negra). Puede ser "1/8" o "1/16".
  
- parts: Un array con las secciones de una canción.
  
  - name: El nombre de la parte.
    
  - bars: La duración de la parte en compases.
    
  - repeat_pattern: (Opcional) Controla la lógica de repetición.
    
    - **Omitido o true**: La parte se repite en cada pasada.
      
    - **false**: La parte se reproduce solo en la primera pasada y luego se omite.
      
    - **[true, false]**: Se reproduce en la 1ª pasada, se salta en la 2ª, se reproduce en la 3ª, etc.
      
    - **[false, true, true]**: Se salta en la 1ª pasada, se reproduce en la 2ª y 3ª, se salta en la 4ª, etc.
      

## Uso

1. Configura tu fuente de reloj maestro (ej. midimaster, Ableton Live, un sinte hardware) para que envíe MIDI clock.
  
2. Configura miditema.conf.json para que escuche en los puertos correctos.
  
3. Ejecuta miditema desde tu terminal:
  
  Generated code
  
  ```
  # Ejecutar y seleccionar una canción de la lista interactiva
  python miditema.py
  
  # O especificar un archivo de canción directamente (sin la extensión .json)
  python miditema.py mi_archivo_de_cancion
  ```
  

### Controles

- Espacio / Enter: Envía un comando MIDI Start/Stop al puerto de control remoto.
  
- q / Ctrl+C: Sale de la aplicación.
  

## Integración OSC

Esta es la característica principal para integrar miditema con otro software.

Cuando comienza una nueva parte, miditema envía un mensaje OSC a la IP, puerto y dirección configurados. El mensaje contiene cuatro argumentos:

1. **Nombre de la Canción** (string): El nombre de la canción cargada actualmente.
  
2. **Nombre de la Parte** (string): El nombre de la parte que está comenzando ahora.
  
3. **Compases de la Parte** (int): El número total de compases en esta nueva parte.
  
4. **Índice de la Parte** (int): El índice (base cero) de esta parte en el array parts de la canción.
  

#### Testeo de OSC

En este repositorio se proporciona un script simple de Python, osc_receiver.py, para ayudarte a probar y verificar que los mensajes OSC se envían correctamente. Ejecútalo en una terminal separada para ver los mensajes entrantes.

## Licencia

Este proyecto está bajo la Licencia MIT.
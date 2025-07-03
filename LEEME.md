# MIDItema

Un secuenciador de estructura de canciones y contador de compases para directos, basado en terminal, que envía los cambios de parte vía OSC.

## Concepto Principal

MIDItema escucha un reloj MIDI maestro externo (como un DAW, un secuenciador hardware o nuestra herramienta compañera MIDImaster) y usa esa información de tempo para avanzar a través de una estructura de canción predefinida, o para saltar dinámicamente entre partes bajo demanda.

Muestra una cuenta atrás de compases para la parte actual de la canción, permitiendo al usuario saber con antelación cuándo ocurrirá el siguiente cambio.

Los cambios también se envían por OSC, de modo que pueden ser leídos por otras aplicaciones (por ejemplo, con MIDImod).

## Características

- **Salto Dinámico entre Partes:** La característica principal para la interpretación en directo. Programa saltos a la parte siguiente/anterior, reinicia la sección actual o ve a cualquier parte específica de la canción.

- **Acciones Cuantizadas:** Los saltos no son instantáneos. Se programan como una **acción pendiente** y se ejecutan con precisión musical, alineados al siguiente compás, a la siguiente sección de 8/16 compases, o incluso de forma instantánea en el siguiente pulso.

- **Esquema de Control Flexible:** Usa pulsaciones de una sola tecla tanto para acciones fijas (ej: "saltar a la siguiente parte, cuantizado al compás") como para acciones que usan un modo global.

- **Cuenta atrás de compases:** Muestra el número de compases que quedan en la parte actual de la canción, para que puedas prepararte para los cambios.

- **Esclavo de Reloj MIDI:** Se sincroniza perfectamente con cualquier fuente de reloj MIDI estándar.

- **Estructura de Canción Basada en JSON:** Define la estructura completa de tu canción, sus partes y duraciones en sencillos archivos JSON legibles por humanos.

- **... incluyendo Lógica de Repetición Avanzada:** Controla exactamente cuándo se repiten las partes usando patrones flexibles (ej: "reproducir la Intro solo una vez", "reproducir una vez sí y otra no", "reproducir dos veces y luego saltar dos").

- **Interfaz Visual en Terminal (TUI):** Una interfaz de terminal limpia y a pantalla completa que ofrece una vista clara del estado actual e información de la parte, incluyendo un secuenciador por pasos que muestra los compases de la parte actual, el tiempo transcurrido, el modo de cuantización activo y cualquier acción pendiente.

- **Envío por OSC:** Envía mensajes OSC detallados en cada cambio de parte, permitiendo una fácil integración con otro software creativo (MIDImod, Resolume, TouchDesigner, VCV Rack, etc.).

- **Salida de Program Change por MIDI:** Envía un mensaje de Program Change MIDI en cada cambio de parte, permitiéndote cambiar de sonido automáticamente en sintetizadores o unidades de efectos externas.

- **Control de Transporte Remoto:** Puede enviar comandos de Start/Stop a un reloj maestro (que reciba señales de transporte), permitiéndote controlar la interpretación de la canción desde una única terminal.

- **Configurable:** Todos los puertos de E/S y los ajustes de OSC se definen en un simple archivo de configuración.

## Instalación

1. Clona este repositorio.

2. Asegúrate de tener Python 3 instalado.

3. Instala las dependencias requeridas:
   
   ```
   pip install mido python-osc prompt-toolkit python-rtmidi
   ```

## Configuración

MIDItema se controla mediante dos tipos de archivos JSON.

### 1. Configuración Principal (miditema.conf.json)

Este archivo, ubicado en el directorio raíz, define las conexiones MIDI y OSC.

```
{
    "clock_source": "ENTRADA_CLOCK",
    "transport_out": "SALIDA_TRANSPORTE",
    "midi_configuration": {
        "device_out": "Puerto_Sinte",
        "channel_out": 1
    },
    "osc_configuration": {
        "send": {
            "ip": "127.0.0.1",
            "port": 9000,
            "address": "/miditema/part/change"
        }
    }
}
```

- clock_source: Una subcadena del nombre del puerto de entrada MIDI que envía el reloj.

- transport_out: Una subcadena del nombre del puerto de salida MIDI al que enviar los comandos de transporte (el puerto en el que el reloj maestro escucharía las señales de transporte).

- midi_configuration: (Opcional) Bloque para configurar la salida de Program Change.

    - device_out: Una subcadena del puerto de salida MIDI al que enviar los mensajes de Program Change (ej: el nombre de tu sintetizador).

    - channel_out: El canal MIDI (1-16) en el que se enviarán los mensajes. Por defecto, es 1.

- osc_configuration.send:
  
  - ip: La dirección IP de destino para los mensajes OSC (127.0.0.1 para la misma máquina).
  
  - port: El puerto de destino para los mensajes OSC.
  
  - address: La ruta de la dirección OSC para el mensaje.

### 2. Archivos de Canción (temas/*.json)

Estos archivos definen la estructura de una canción. Deben colocarse en un directorio temas/.

```
{
    "song_name": "Mi Tema Increíble",
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

- time_division: (Opcional) Cómo interpretar un "pulso". Por defecto, "1/4" (negra). Puede ser "1/8" o "1/16".

- parts: Un array con las secciones de una canción.
  
  - name: El nombre de la parte.
  
  - bars: La duración de la parte en compases.
  
  - repeat_pattern: (Opcional) Controla la lógica de repetición.
    
    - **Omitido o true**: La parte se repite en cada pasada.
    
    - **false**: La parte se reproduce solo en la primera pasada y luego se omite.
    
    - **[true, false]**: Se reproduce en la 1ª pasada, se salta en la 2ª, se reproduce en la 3ª, etc.
    
    - **[false, true, true]**: Se salta en la 1ª pasada, se reproduce en la 2ª y 3ª, se salta en la 4ª, etc.

## Uso

1. Configura tu fuente de reloj maestro (ej: Ableton Live, un secuenciador hardware, un reloj software como MIDImaster).

2. Configura miditema.conf.json para escuchar en los puertos correctos.

3. Ejecuta MIDItema desde tu terminal:
   
   ```
   # Ejecutar y seleccionar una canción de la lista interactiva
   python miditema.py
   
   # O especificar un archivo de canción directamente (sin la extensión .json)
   python miditema.py mi_tema
   ```

### Controles

MIDItema cuenta con un potente esquema de control para directos. La mayoría de las acciones se programan como una **acción pendiente** y se ejecutan con cuantización.

| Tecla(s)                              | Acción                      | Detalles / Cuantización                                                                                                                                         |
| ------------------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Transporte Global**                 |                             |                                                                                                                                                                 |
| Espacio / Enter                       | Enviar Start/Stop           | Envía un comando MIDI Start/Stop inmediatamente.                                                                                                                |
| q / Ctrl+C                            | Salir                       | Cierra la aplicación.                                                                                                                                           |
| **Navegación en Directo**             |                             |                                                                                                                                                                 |
| → / ←                                 | Saltar Siguiente / Anterior | Programa un salto. Usa el modo de cuantización **global**. Pulsar varias veces acumula el salto (ej: → → → programa un salto de +3).                            |
| ↑                                     | Reiniciar Parte             | Reinicia la parte actual desde su comienzo. Usa el modo de cuantización **global**.                                                                             |
| ↓                                     | Cancelar Acción             | Cancela inmediatamente cualquier acción pendiente.                                                                                                              |
| . o , luego [num] Enter               | Ir a Parte                  | Activa el modo 'Ir a'. Escribe un número de parte (ej: .12) y pulsa Enter para programar el salto a la parte número 12. Usa el modo de cuantización **global**. |
| **Saltos Rápidos**                    |                             |                                                                                                                                                                 |
| 0                                     | Salto Rápido +1             | Salta a la siguiente parte. **Cuantización Fija: Instantánea** (siguiente pulso).                                                                               |
| 1                                     | Salto Rápido +1             | Salta a la siguiente parte. **Cuantización Fija: Siguiente Compás**.                                                                                            |
| 2                                     | Salto Rápido +1             | Salta a la siguiente parte. **Cuantización Fija: Siguientes 8 Compases**.                                                                                       |
| 3                                     | Salto Rápido +1             | Salta a la siguiente parte. **Cuantización Fija: Siguientes 16 Compases**.                                                                                      |
| **Selección de Modo de Cuantización** |                             |                                                                                                                                                                 |
| 4                                     | Fijar Cuant. Global         | Establece el modo global para flechas e 'Ir a' en **Siguientes 8 Compases**.                                                                                    |
| 5                                     | Fijar Cuant. Global         | Establece el modo global en **Siguientes 16 Compases**.                                                                                                         |
| 6                                     | Fijar Cuant. Global         | Establece el modo global en **Siguientes 32 Compases**.                                                                                                         |

## Integración OSC

Esta es la característica principal para integrar MIDItema con otro software.

Cuando una nueva parte comienza, MIDItema envía un mensaje OSC a la IP, puerto y dirección configurados. El mensaje contiene cuatro argumentos:

1. **Nombre de la Canción** (string): El nombre de la canción cargada actualmente.

2. **Nombre de la Parte** (string): El nombre de la parte que está comenzando ahora.

3. **Compases de la Parte** (int): El número total de compases en esta nueva parte.

4. **Índice de la Parte** (int): El índice de base cero de esta parte en el array parts de la canción.

## Integración con MIDI Program Change

Además de OSC, MIDItema puede enviar un mensaje de Program Change MIDI cada vez que una nueva parte comienza. Esto es ideal para controlar hardware externo como sintetizadores o pedales de efectos.

El valor del mensaje de Program Change corresponde al **índice de base cero** de la nueva parte en el array `parts` de la canción.

- Si la canción transiciona a la **primera** parte de la lista (índice 0), enviará `Program Change 0`.
- Si transiciona a la **tercera** parte (índice 2), enviará `Program Change 2` en el canal MIDI configurado.

#### Probando OSC

Se puede usar un script simple de Python, osc_receiver.py, para ayudarte a probar y verificar que los mensajes OSC se envían correctamente. Ejecútalo en una terminal separada para ver los mensajes entrantes.

## Licencia

Este proyecto está licenciado bajo la Licencia MIT.
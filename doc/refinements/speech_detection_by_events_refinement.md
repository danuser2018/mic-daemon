# Documento de Refinamiento: Detección de Habla basada en Eventos (Fase 3 Refactor de Entrada)

- **Documento de Origen**: [speech_detection_by_events.md](file:///home/danuser2018/workspace/mic-daemon/doc/features/speech_detection_by_events.md)
- **Estado**: Refinado / Listo para desarrollo (Correcciones DoR Aplicadas)

---

## 1. Resumen y Contexto de Negocio

### Objetivo Principal
Completar la Fase 3 del refactor de entrada del ecosistema Nova-2 eliminando definitivamente la dependencia del archivo de marca `/tmp/voice_assistant/recording.flag` en `mic-daemon`. 

`mic-daemon` pasará de ser un observador del sistema de archivos (mediante el bucle de polling `StateWatcher`) a reaccionar exclusivamente a comandos de dominio publicados en el bus de eventos NATS a través de `nova-event-bus`. Asimismo, los scripts de control `mic-start` y `mic-stop` delegarán única y exclusivamente la ejecución en los comandos oficiales de `novactl` (`novactl start-capture` y `novactl stop-capture`), eliminando la manipulación residual del sistema de archivos.

> [!NOTE]
> **Reconciliación de Nomenclatura CLI (D-03)**: La especificación inicial de la feature (`speech_detection_by_events.md`) mencionaba los comandos `novactl start-speech-capture` y `novactl stop-speech-capture`. Se aclara que los subcomandos oficiales expuestos e implementados en la CLI `novactl` son `novactl start-capture` y `novactl stop-capture`, los cuales emiten los eventos NATS `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand`.
>
> **Alineación Arquitectónica ADR (D-01)**: La migración de `mic-daemon` desde la supervisión de archivos hacia NATS requiere la actualización de la arquitectura formal descrita en ADR-017/ADR-018, la cual se gestionará mediante un nuevo ADR/adenda y la actualización de las skills transversales correspondientes.

### Actores
- **Servicios Productores de Comandos (`novactl`, Daemons HID/Hotkeys):** Invocan `mic-start` / `mic-stop` o emiten directamente los comandos `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand` al bus NATS.
- **`mic-daemon` (Consumidor de Comandos):** Servicio background que se suscribe a dichos eventos, inicia/detiene la captura de audio por micrófono y emite el fichero WAV correspondiente a `MIC_OUTPUT_DIR`.
- **Usuario Final:** Quien activa la interacción de voz mediante botones físicos o atajos y obtiene una respuesta rápida sin latencias introducidas por polling de archivos.

---

## 2. Análisis de Servicios e Impacto

| Servicio | Tipo de Cambio | Descripción del Impacto |
| :--- | :--- | :--- |
| `mic-daemon` | **[MODIFY]** | Sustitución de `StateWatcher` (polling de `recording.flag`) por un suscriptor asíncrono basado en `nova-event-bus`. Suscripción a `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand`. Eliminación de los parámetros `MIC_POLL_INTERVAL_MS` y `flag_path` de `config.py`. Actualización de `scripts/mic-start.sh` y `scripts/mic-stop.sh` para eliminar la creación/borrado de `recording.flag`. Actualización de la unidad Systemd `mic-daemon.service`. |
| `novactl` | **Ninguno** | Ya expone `novactl start-capture` y `novactl stop-capture` emitiendo los eventos tipados en NATS (reconciliando la especificación previa con la CLI real). |
| `hid-daemon` | **Ninguno** | Invoca `mic-start` y `mic-stop` sin cambios en su configuración ni en su binario. |
| `interaction-manager` | **Ninguno** | No interactúa directamente con el mecanismo de captura de audio de `mic-daemon`. |
| `nova-event-bus` | **Ninguno** | Librería común utilizada por `mic-daemon` para conectarse a NATS y gestionar suscripciones tipadas. |

---

## 3. Especificación de Comportamiento (Criterios de Aceptación)

### Scenario 1: Start audio capture upon receiving StartSpeechCaptureCommand
```gherkin
Scenario: Start recording audio when StartSpeechCaptureCommand is received
  Given that mic-daemon is running and connected to NATS event bus via nova-event-bus
  And mic-daemon is currently in IDLE state (not recording)
  When a StartSpeechCaptureCommand event is published to subject "novactl.command.start_speech_capture"
  Then mic-daemon must transition to RECORDING state
  And mic-daemon must initialize the sounddevice InputStream
  And mic-daemon must begin buffering audio frames for a timestamped WAV output path
```

### Scenario 2: Stop audio capture and generate WAV upon receiving StopSpeechCaptureCommand
```gherkin
Scenario: Stop recording and write WAV file when StopSpeechCaptureCommand is received
  Given that mic-daemon is currently in RECORDING state
  When a StopSpeechCaptureCommand event is published to subject "novactl.command.stop_speech_capture"
  Then mic-daemon must stop and close the sounddevice InputStream
  And mic-daemon must concatenate audio buffer frames
  And mic-daemon must write the WAV file to MIC_OUTPUT_DIR if duration >= MIN_DURATION_S
  And mic-daemon must transition back to IDLE state
```

### Scenario 3: Idempotent handling of StartSpeechCaptureCommand when already recording
```gherkin
Scenario: Receive StartSpeechCaptureCommand while already recording
  Given that mic-daemon is currently in RECORDING state
  When another StartSpeechCaptureCommand event is received
  Then mic-daemon must log a warning message indicating that recording is already active
  And mic-daemon must continue recording without resetting the existing audio buffer or stream
```

### Scenario 4: Idempotent handling of StopSpeechCaptureCommand when idle
```gherkin
Scenario: Receive StopSpeechCaptureCommand while idle
  Given that mic-daemon is currently in IDLE state
  When a StopSpeechCaptureCommand event is received
  Then mic-daemon must log a warning message indicating that no active recording is in progress
  And mic-daemon must remain in IDLE state without writing any WAV file
```

### Scenario 5: Execution of mic-start and mic-stop control scripts
```gherkin
Scenario: Invoke mic-start script without filesystem flag creation
  Given that the user or external daemon runs "mic-start.sh"
  When the script executes
  Then the script must invoke "novactl start-capture"
  And the script must NOT create "/tmp/voice_assistant/recording.flag"
  And the exit code must be 0

Scenario: Invoke mic-stop script without filesystem flag deletion
  Given that the user or external daemon runs "mic-stop.sh"
  When the script executes
  Then the script must invoke "novactl stop-capture"
  And the script must NOT remove or check "/tmp/voice_assistant/recording.flag"
  And the exit code must be 0
```

### Scenario 6: Graceful shutdown on SIGTERM / SIGINT signal
```gherkin
Scenario: Clean daemon shutdown on SIGTERM while recording
  Given that mic-daemon is running and actively recording audio
  When a SIGTERM or SIGINT signal is received by the process
  Then mic-daemon must stop recording audio gracefully and flush the buffer to WAV
  And mic-daemon must disconnect cleanly from the NATS event bus
  And mic-daemon process must exit with code 0
```

---

## 4. Diseño Técnico y Contratos

> [!NOTE]
> De acuerdo con la regla de **Aislamiento Lingüístico**, todos los identificadores técnicos, nombres de variables, propiedades de clases y código de ejemplo se definen estrictamente en inglés.

### 4.1 Event Contracts (`novactl/events.py`)

`mic-daemon` consumirá las siguientes clases de eventos expuestas por la librería o importadas desde los contratos de eventos de Nova:

```python
from dataclasses import dataclass
from nova_event_bus import Event, event

@event("novactl.command.start_speech_capture")
@dataclass
class StartSpeechCaptureCommand(Event):
    correlation_id: str
    channel: str = "voice"

@event("novactl.command.stop_speech_capture")
@dataclass
class StopSpeechCaptureCommand(Event):
    correlation_id: str
    channel: str = "voice"
```

### 4.2 Arquitectura del Suscriptor de Eventos (`src/event_subscriber.py`)

Se elimina el módulo `src/state_watcher.py` y se crea `src/event_subscriber.py`, encargado de gestionar el ciclo de vida del `EventBus` y el registro de handlers.

```python
import asyncio
import logging
from typing import Callable
from nova_event_bus import EventBus
from novactl.events import StartSpeechCaptureCommand, StopSpeechCaptureCommand

logger = logging.getLogger(__name__)

class EventSubscriber:
    """
    Manages NATS event bus connection and subscribes to speech capture commands.
    """

    def __init__(
        self,
        event_bus: EventBus,
        on_start: Callable[[str], None],
        on_stop: Callable[[str], None],
    ) -> None:
        self._event_bus = event_bus
        self._on_start = on_start
        self._on_stop = on_stop

    async def start(self) -> None:
        """Connect to NATS broker and subscribe to command events."""
        await self._event_bus.connect()
        await self._event_bus.subscribe(StartSpeechCaptureCommand, self._handle_start)
        await self._event_bus.subscribe(StopSpeechCaptureCommand, self._handle_stop)
        logger.info("EventSubscriber subscribed to StartSpeechCaptureCommand and StopSpeechCaptureCommand")

    async def stop(self) -> None:
        """Disconnect cleanly from NATS event bus."""
        await self._event_bus.disconnect()
        logger.info("EventSubscriber disconnected from NATS")

    async def _handle_start(self, event: StartSpeechCaptureCommand) -> None:
        logger.info("Handling StartSpeechCaptureCommand (correlation_id=%s)", event.correlation_id)
        self._on_start(event.correlation_id)

    async def _handle_stop(self, event: StopSpeechCaptureCommand) -> None:
        logger.info("Handling StopSpeechCaptureCommand (correlation_id=%s)", event.correlation_id)
        self._on_stop(event.correlation_id)
```

### 4.3 Actualización de Configuración (`src/config.py`)

Se eliminan los campos derivados y configuraciones relativas al sistema de archivos y polling:

```python
@dataclass
class Config:
    output_dir: Path
    device: str | int | None
    sample_rate: int
    channels: int
```

- Se elimina `MIC_POLL_INTERVAL_MS` y `flag_path`.
- La configuración de conexión a NATS se obtiene automáticamente mediante `EventBusConfig.from_env()` dentro de `nova-event-bus` (utilizando `NATS_URL`, `NATS_CONNECTION_TIMEOUT`, etc.).

### 4.4 Orquestador Principal del Daemon (`src/mic_daemon.py`)

`mic_daemon.py` se refactoriza para ejecutarse sobre el bucle de eventos `asyncio`:

```python
import asyncio
import logging
import signal
import sys
from src.config import load_config
from src.recorder import Recorder, build_output_path
from src.event_subscriber import EventSubscriber
from nova_event_bus import EventBus

async def main_async() -> None:
    config = load_config()
    recorder = Recorder(config)
    event_bus = EventBus()

    def on_start(correlation_id: str) -> None:
        output_path = build_output_path(config.output_dir)
        recorder.start(output_path)

    def on_stop(correlation_id: str) -> None:
        recorder.stop()

    subscriber = EventSubscriber(
        event_bus=event_bus,
        on_start=on_start,
        on_stop=on_stop,
    )

    await subscriber.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: stop_event.set())

    logger.info("mic-daemon ready — listening for NATS speech capture commands")
    await stop_event.wait()

    # Graceful cleanup
    if recorder.is_recording():
        recorder.stop()
    await subscriber.stop()

def main() -> None:
    asyncio.run(main_async())
```

### 4.5 Actualización de Scripts Shell (`scripts/mic-start.sh` y `scripts/mic-stop.sh`)

#### `scripts/mic-start.sh`:
```bash
#!/usr/bin/env bash
# mic-start.sh — Trigger speech capture start via novactl.

set -euo pipefail

if command -v novactl >/dev/null 2>&1; then
    exec novactl start-capture
else
    echo "Error: novactl is not installed or not in PATH" >&2
    exit 1
fi
```

#### `scripts/mic-stop.sh`:
```bash
#!/usr/bin/env bash
# mic-stop.sh — Trigger speech capture stop via novactl.

set -euo pipefail

if command -v novactl >/dev/null 2>&1; then
    exec novactl stop-capture
else
    echo "Error: novactl is not installed or not in PATH" >&2
    exit 1
fi
```

### 4.6 Configuración de Servicio Systemd y Variables de Entorno (D-04)

- **Systemd Unit (`systemd/mic-daemon.service`)**:
  Se actualiza el campo `Description` para desvincularlo del mecanismo de flag en filesystem:
  ```ini
  [Unit]
  Description=Microphone recording daemon controlled by NATS event bus
  ```
- **Variables de Entorno**:
  Se incorpora el soporte y documentación de `NATS_URL` (por defecto `nats://localhost:4222`) cargada opcionalmente desde `~/.config/mic-daemon/env`.

---

## 5. Casos de Borde y Manejo de Errores

1. **Reconexión a NATS desatendida**:
   - Si el broker NATS cae o se reinicia durante la ejecución de `mic-daemon`, la librería `nova-event-bus` gestionará la reconexión automática en segundo plano sin colapsar el proceso `mic-daemon`.
2. **Recepción de comandos fuera de orden / duplicados**:
   - Si se recibe un `StartSpeechCaptureCommand` mientras la grabación ya está activa, `Recorder.start()` captura el estado existente, registra un `logger.warning` y descarta la llamada duplicada sin corromper el stream de audio actual.
   - Si se recibe `StopSpeechCaptureCommand` sin estar grabando, `Recorder.stop()` registra un `logger.warning` e ignora la petición sin intentar escribir un fichero WAV vacuo.
3. **Grabaciones de muy corta duración (Accidental Rapid Toggles)**:
   - Se mantiene la constante `MIN_DURATION_S = 0.1` en `Recorder`. Audio menor a 100ms se descarta de forma limpia evitando generar ficheros WAV corruptos o vacíos.
4. **Falla en el driver/dispositivo de audio (`sounddevice`)**:
   - Las excepciones levantadas durante el inicio del InputStream o el callback de audio se capturan y registran en log sin lanzar un error fatal que mate el proceso `mic-daemon`, manteniéndose a la espera de futuros comandos.
5. **Apagado del servicio systemd (SIGTERM)**:
   - El capturador de señales asíncrono detendrá cualquier grabación activa (guardando el WAV si cumple la duración mínima) y cerrará la conexión NATS antes de finalizar el proceso.

---

## 6. Estrategia de Testing

- **Tests Unitarios de Configuración (`tests/test_config.py`)**:
  - Verificar que `load_config()` parsea `MIC_OUTPUT_DIR`, `MIC_DEVICE`, `MIC_SAMPLE_RATE`, `MIC_CHANNELS`.
  - Verificar la eliminación de las aserciones sobre `MIC_POLL_INTERVAL_MS` y `flag_path`.
- **Tests Unitarios del Suscriptor de Eventos (`tests/test_event_subscriber.py`)**:
  - Mockear `EventBus` de `nova-event-bus`.
  - Probar la suscripción a `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand`.
  - Verificar la ejecución de los callbacks `on_start` y `on_stop` al recibir instancias simuladas de los eventos.
- **Tests de Integración de Scripts (`tests/test_scripts.py`)**:
  - Ejecutar `mic-start.sh` y `mic-stop.sh` desde pruebas con `pytest` y `subprocess`.
  - Verificar que invoca `novactl start-capture` y `novactl stop-capture`.
  - Verificar que NO se crea ni se elimina `/tmp/voice_assistant/recording.flag`.
- **Tests de Bucle Principal y Ciclo de Vida (`tests/test_mic_daemon.py`)**:
  - Probar el arranque de `main_async` en un evento de prueba con mocks de `sounddevice` y `EventBus`.
  - Simular envío de señal `SIGTERM` y comprobar que la desconexión se realiza sin fugas de recursos.

---

## 7. Plan de Implementación

- `[ ]` **Tarea 1: Actualización de Configuración (`src/config.py`)**
  - Eliminar los atributos `flag_path` y `poll_interval_s` de la dataclass `Config`.
  - Eliminar la lectura de la variable `MIC_POLL_INTERVAL_MS` en `load_config()`.
  - Incorporar soporte para `NATS_URL`.
  - Actualizar `tests/test_config.py` adaptando las pruebas unitarias a la nueva estructura de configuración.

- `[ ]` **Tarea 2: Implementación de `EventSubscriber` (`src/event_subscriber.py`)**
  - Crear el módulo `src/event_subscriber.py` encapsulando `EventBus` y las suscripciones a `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand`.
  - Añadir pruebas unitarias en `tests/test_event_subscriber.py` con mocks de `EventBus`.

- `[ ]` **Tarea 3: Eliminación de `StateWatcher` y Refactor de `src/mic_daemon.py`**
  - Eliminar `src/state_watcher.py` y `tests/test_state_watcher.py`.
  - Refactorizar `src/mic_daemon.py` para usar `asyncio` y conectar `EventSubscriber` con `Recorder`.
  - Eliminar la lógica de limpieza de flag obsoleto `_cleanup_stale_flag`.
  - Actualizar `tests/test_mic_daemon.py`.

- `[ ]` **Tarea 4: Actualización de Scripts Shell (`scripts/mic-start.sh` y `scripts/mic-stop.sh`)**
  - Actualizar `scripts/mic-start.sh` eliminando la creación de `/tmp/voice_assistant/recording.flag` y delegando en `exec novactl start-capture`.
  - Actualizar `scripts/mic-stop.sh` eliminando el borrado del flag y delegando en `exec novactl stop-capture`.
  - Actualizar `tests/test_scripts.py` para comprobar la ausencia de interacción con el sistema de archivos.

- `[ ]` **Tarea 5: Actualización de Definiciones Arquitectónicas y ADR (D-01)**
  - Crear un nuevo ADR (o adenda a ADR-017 / ADR-018) justificando la conexión de `mic-daemon` a NATS via `nova-event-bus`.
  - Sincronizar referencias en las skills transversales afectadas (`architecture-decisions`, `communication-patterns`, `event-driven-architecture`, `service-responsibilities`, `system-deployment`).

- `[ ]` **Tarea 6: Actualización de la Skill de Dominio `audio-subsystem` (D-02)**
  - Actualizar `home-assistant/.agent/skills/domains/audio-subsystem/SKILL.md` eliminando la exigencia de monitoreo de `/tmp/voice_assistant/recording.flag`.
  - Documentar el nuevo flujo basado en eventos y comandos NATS.

- `[ ]` **Tarea 7: Actualización de Servicio Systemd y Variables de Despliegue (D-04)**
  - Actualizar la descripción en `systemd/mic-daemon.service`.
  - Documentar `NATS_URL` en `README.md` y plantillas de configuración (`~/.config/mic-daemon/env`).

- `[ ]` **Tarea 8: Actualización de Documentación Global del Ecosistema (D-05)**
  - Actualizar `home-assistant/docs/services.md` (sección `mic-daemon`) eliminando `recording.flag` y `MIC_POLL_INTERVAL_MS` y describiendo la integración con `nova-event-bus`.

- `[ ]` **Tarea 9: Actualización de Documentación Local del Servicio**
  - Actualizar `mic-daemon/README.md` reflejando la transición a la arquitectura orientada a eventos NATS y la eliminación del flag de grabación.
  - Registrar el cambio en la sección `[Sin publicar]` de `mic-daemon/CHANGELOG.md`.

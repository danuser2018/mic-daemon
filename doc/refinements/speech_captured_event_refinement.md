# Documento de Refinamiento: Evento de Locución Capturada (Fase 4 Refactor de Entrada)

- **Documento de Origen**: [speech_captured_event.md](file:///home/danuser2018/workspace/mic-daemon/doc/features/speech_captured_event.md)
- **Estado**: Refinado / Listo para desarrollo (Correcciones DoR Aplicadas)

---

## 1. Resumen y Contexto de Negocio

### Objetivo Principal
Completar la Fase 4 del refactor de entrada del ecosistema Nova-2 mediante la introducción del evento de dominio `SpeechCapturedEvent`. Este evento notifica a través del bus NATS (`nova-event-bus`) la disponibilidad de una nueva locución grabada una vez que la captura finaliza y el fichero WAV se ha almacenado correctamente en el volumen compartido.

Tras los últimos cambios introducidos en el refactor de entrada (PR #10 / `remove_params`), los comandos `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand` carecen de atributos. Por lo tanto, `mic-daemon` es el responsable exclusivo de generar los metadatos del evento: un `correlationId` único generado mediante UUIDv4 al iniciar la captura y el atributo `channel` fijado en `'voice'`.

Durante esta fase de transición, el comportamiento observable del sistema no cambia: el mecanismo existente basado en la observación del sistema de archivos (*filesystem watching/polling*) permanecerá activo en los consumidores para garantizar la retrocompatibilidad, mientras se valida la publicación y el contrato de `SpeechCapturedEvent`.

> [!NOTE]
> **Generación Autónoma de Atributos (D-01)**: Como los comandos de control (`StartSpeechCaptureCommand` y `StopSpeechCaptureCommand`) son sin parámetros (*parameterless*), `mic-daemon` debe instanciar un `correlationId` mediante UUIDv4 al comienzo de cada grabación y asignar siempre `'voice'` al campo `channel`.
>
> **Reconciliación de Rutas Relativas (D-02)**: El atributo `audioPath` debe ser estrictamente una ruta **relativa** al directorio base de grabaciones (`MIC_OUTPUT_DIR`), resolviendo discrepancias entre entornos (por ejemplo, `2026-07-24_17-30-00.wav`). Ningún servicio debe intercambiar rutas absolutas (`/tmp/voice_assistant/...`).
>
> **Extensión de Alcance respecto al Documento de Origen (D-04)**: Aunque el documento descriptivo inicial `speech_captured_event.md` acotaba el impacto únicamente a `mic-daemon`, la estandarización de la taxonomía de mensajería asíncrona establecida en **ADR-022** exige actualizar de manera coordinada los decoradores `@event` de comandos de captura en `novactl` y de eventos de respuesta en `orchestrator` y `context-service`, garantizando la consistencia global del bus NATS en todo el ecosistema.

### Actores
- **`mic-daemon` (Productor del Evento):** Captura el audio del micrófono, genera el `correlationId` (UUIDv4), escribe el fichero WAV en `MIC_OUTPUT_DIR` y publica `SpeechCapturedEvent` en el bus NATS.
- **`nova-event-bus` (Infraestructura de Eventos):** Transporta y entrega el evento a los suscriptores en el topic `event.speech.captured`.
- **Consumidores Futuros (`interaction-manager`, `orchestrator`):** En fases posteriores se suscribirán a `SpeechCapturedEvent` para procesar el audio directamente sin depender del sistema de archivos.

---

## 2. Análisis de Servicios e Impacto

| Servicio | Tipo de Cambio | Descripción del Impacto |
| :--- | :--- | :--- |
| `mic-daemon` | **[MODIFY]** | Actualización de `EventSubscriber` para suscribirse a los nuevos subjects de comandos `command.speech.start-capture` y `command.speech.stop-capture`. Incorporación de la publicación de `SpeechCapturedEvent` (`event.speech.captured`) tras guardar el fichero WAV. Generación interna de `correlationId` (UUIDv4) y `channel='voice'`. |
| `novactl` | **[MODIFY]** | Actualización de las anotaciones `@event` en `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand` para adoptar los subjects `command.speech.start-capture` y `command.speech.stop-capture`. |
| `orchestrator` | **[MODIFY]** | Actualización del decorador `@event` de `ResponseGeneratedEvent` (`core/events.py`) para adoptar el subject `event.interaction.response-generated` (anteriormente `orchestrator.response.generated`). |
| `context-service` | **[MODIFY]** | Actualización del decorador `@event` de `ResponseGeneratedEvent` (`app/events.py`) para adoptar el subject `event.interaction.response-generated` (anteriormente `orchestrator.response.generated`). |
| `home-assistant` | **[MODIFY]** | Creación de **ADR-022** (Estandarización de nomenclatura en `nova-event-bus`). Actualización de la documentación del ecosistema, skills (`audio-subsystem`, `event-driven-architecture`), catálogo de servicios (`services.md`) y verificación del impacto por cambios de contrato. |
| `interaction-manager` | **Ninguno** | En esta fase continúa descubriendo audios mediante observación del sistema de archivos. Se migrará en fases posteriores. |
| `nova-event-bus` | **Ninguno** | Proporciona la infraestructura NATS para serializar y publicar comandos y eventos. |

---

## 3. Especificación de Comportamiento (Criterios de Aceptación)

### Scenario 1: Publish SpeechCapturedEvent after successfully writing WAV file
```gherkin
Scenario: Publish SpeechCapturedEvent on successful audio recording and WAV storage
  Given that mic-daemon is active and receives a StartSpeechCaptureCommand on subject "command.speech.start-capture"
  When recording starts
  Then mic-daemon must generate a unique UUIDv4 string as correlationId
  When a StopSpeechCaptureCommand is received on subject "command.speech.stop-capture"
  And the recorded audio duration is >= MIN_DURATION_S (0.1 seconds)
  And the WAV file is successfully written to disk at "MIC_OUTPUT_DIR/2026-07-24_17-30-00.wav"
  Then mic-daemon must publish a SpeechCapturedEvent to subject "event.speech.captured"
  And the event payload must contain:
    | field         | type / value                   |
    | correlationId | <UUIDv4 valido>                |
    | channel       | "voice"                        |
    | audioPath     | "2026-07-24_17-30-00.wav"     |
```

### Scenario 2: Do NOT publish event when audio recording is discarded due to short duration
```gherkin
Scenario: Do not publish SpeechCapturedEvent when recording is shorter than minimum threshold
  Given that mic-daemon is actively recording audio
  When StopSpeechCaptureCommand is received on subject "command.speech.stop-capture" after less than 0.1 seconds (e.g. 0.05 seconds)
  Then mic-daemon must discard the audio buffer without writing a WAV file
  And mic-daemon must NOT publish any SpeechCapturedEvent
```

### Scenario 3: Do NOT publish event when WAV writing fails
```gherkin
Scenario: Do not publish SpeechCapturedEvent if WAV writing raises an I/O exception
  Given that mic-daemon stops recording audio
  When writing the WAV file to disk fails due to an I/O error or insufficient permissions
  Then mic-daemon must log an error detailing the file write failure
  And mic-daemon must NOT publish any SpeechCapturedEvent
```

### Scenario 4: Ensure relative audioPath format
```gherkin
Scenario: Audio path in SpeechCapturedEvent is strictly relative to MIC_OUTPUT_DIR
  Given that MIC_OUTPUT_DIR is configured as "/var/lib/nova/recordings"
  And the generated file full path is "/var/lib/nova/recordings/2026-07-24_17-30-00.wav"
  When SpeechCapturedEvent is emitted
  Then the audioPath attribute in the event payload must equal "2026-07-24_17-30-00.wav"
  And must NOT contain the base prefix "/var/lib/nova/recordings/"
```

### Scenario 5: Maintain existing filesystem output for backward compatibility
```gherkin
Scenario: Keep filesystem output intact for legacy consumers
  Given that mic-daemon completes a recording
  When the WAV file is written to MIC_OUTPUT_DIR
  Then the file must remain accessible on disk for filesystem watchers
  And the publication of SpeechCapturedEvent must not interfere with file creation
```

### Scenario 6: Handle event publishing failures gracefully without crashing mic-daemon
```gherkin
Scenario: Handle event publishing failures gracefully without crashing mic-daemon
  Given that mic-daemon stops recording audio and saves the WAV file
  When publishing SpeechCapturedEvent to NATS fails due to a network or broker error
  Then mic-daemon must log an exception describing the publication failure
  And mic-daemon process must continue running without crashing
```

---

## 4. Diseño Técnico y Contratos

> [!NOTE]
> De acuerdo con la regla de **Aislamiento Lingüístico**, todos los identificadores técnicos, nombres de variables, propiedades de clases y código de ejemplo se definen estrictamente en inglés.

### 4.1 Contratos de Comandos y Eventos (`novactl/events.py` / `nova_event_bus`)

De acuerdo con la taxonomía estandarizada en **ADR-022**, `novactl` actúa como la **fuente de verdad principal del contrato emisor** para los comandos de control del sistema:
- **Comandos (`command.{dominio}.{petición}`)**:
  ```python
  from dataclasses import dataclass
  from nova_event_bus import Event, event

  @event("command.speech.start-capture")
  @dataclass
  class StartSpeechCaptureCommand(Event):
      pass

  @event("command.speech.stop-capture")
  @dataclass
  class StopSpeechCaptureCommand(Event):
      pass
  ```

> [!NOTE]
> **Propiedad del Contrato y Desacoplamiento (D-02)**: Cada repositorio del host (`novactl` y `mic-daemon`) define sus subclases de `Event` localmente para evitar dependencias de paquetes Python entre repositorios distintos. La consistencia del contrato se garantiza mediante el decorador `@event` con el subject canonizado por ADR-022 (`command.speech.start-capture` y `command.speech.stop-capture`), verificado mediante tests unitarios en ambos repositorios.

### 4.2 Actualización del Suscriptor de Comandos (`src/event_subscriber.py` en `mic-daemon`)

Se actualiza `EventSubscriber` en `mic-daemon` para suscribirse a los nuevos subjects de comandos canonizados por ADR-022:

```python
import logging
from nova_event_bus import EventBus
from src.events import StartSpeechCaptureCommand, StopSpeechCaptureCommand

logger = logging.getLogger(__name__)

class EventSubscriber:
    def __init__(self, event_bus: EventBus, on_start: Callable, on_stop: Callable) -> None:
        self._event_bus = event_bus
        self._on_start = on_start
        self._on_stop = on_stop

    async def start(self) -> None:
        await self._event_bus.subscribe(StartSpeechCaptureCommand, self._handle_start)
        await self._event_bus.subscribe(StopSpeechCaptureCommand, self._handle_stop)
        logger.info("Subscribed to command.speech.start-capture and command.speech.stop-capture")
```


### 4.3 Definición de Contratos en `mic-daemon` (`src/events.py`)

Nueva clase `src/events.py` en `mic-daemon` (definiciones locales autónomas para desacoplamiento de paquetes):

- **Comandos (`command.{dominio}.{petición}`)**:
  ```python
  from dataclasses import dataclass
  from nova_event_bus import Event, event

  @event("command.speech.start-capture")
  @dataclass
  class StartSpeechCaptureCommand(Event):
      pass

  @event("command.speech.stop-capture")
  @dataclass
  class StopSpeechCaptureCommand(Event):
      pass
  ```

- **Eventos (`event.{dominio}.{notificación}`)**:
  ```python
  @event("event.speech.captured")
  @dataclass
  class SpeechCapturedEvent(Event):
      correlation_id: str
      channel: str
      audio_path: str

  @event("event.interaction.response-generated")
  @dataclass
  class ResponseGeneratedEvent(Event):
      response: str
      plugin: str
      confidence: float
      timestamp: datetime
      correlation_id: str
      execution_time_ms: int
      channel: str
      metadata: Dict[str, Any]
  ```

*Nota de serialización*: La librería `nova-event-bus` realiza la conversión automática de atributos `snake_case` de Python (`correlation_id`, `audio_path`) a los nombres camelCase del esquema JSON (`correlationId`, `audioPath`).

Eliminar la dependencia de `novactl.events` y comenzar a utilizar las definiciones locales.

### 4.4 Arquitectura del Publicador de Eventos (`src/event_publisher.py`)

Se crea `src/event_publisher.py` para abstraer la publicación del evento desde `mic-daemon`:

```python
import logging
from nova_event_bus import EventBus
from src.events import SpeechCapturedEvent

logger = logging.getLogger(__name__)

class EventPublisher:
    """
    Handles publishing domain events for mic-daemon over NATS event bus.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    async def publish_speech_captured(
        self,
        correlation_id: str,
        channel: str,
        audio_path: str,
    ) -> None:
        """
        Publish SpeechCapturedEvent to subject 'event.speech.captured'.
        """
        evt = SpeechCapturedEvent(
            correlation_id=correlation_id,
            channel=channel,
            audio_path=audio_path,
        )
        try:
            await self._event_bus.publish(evt)
            logger.info(
                "Published SpeechCapturedEvent: correlation_id=%s, channel=%s, audio_path=%s",
                correlation_id,
                channel,
                audio_path,
            )
        except Exception:
            logger.exception(
                "Failed to publish SpeechCapturedEvent for audio_path=%s",
                audio_path,
            )
```

### 4.5 Modificación del Recopilador de Audio (`src/recorder.py`)

Se modifica `Recorder` para generar automáticamente un `correlation_id` (UUIDv4) al iniciar la grabación y retornar la ruta relativa junto con el `correlation_id` al detenerla:

```python
import uuid
from pathlib import Path
from typing import Optional

class Recorder:
    def __init__(self, config: "Config") -> None:
        self._config = config
        self._stream: Any = None
        self._buffer: list[np.ndarray] = []
        self._output_path: Path | None = None
        self._correlation_id: str | None = None

    def start(self, output_path: Path) -> None:
        if self._stream is not None:
            logger.warning("start() called while already recording — ignoring")
            return
        
        self._buffer = []
        self._output_path = output_path
        self._correlation_id = str(uuid.uuid4())
        # ... inicializar InputStream ...

    def stop(self) -> tuple[Optional[str], Optional[str]]:
        """
        Stop capture and flush buffer to WAV.
        
        Returns:
            Tuple of (relative_audio_path, correlation_id) if WAV was saved successfully,
            or (None, None) if recording was discarded or failed.
        """
        if self._stream is None:
            logger.warning("stop() called while not recording — ignoring")
            return None, None

        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            logger.exception("Error while closing audio stream")
        finally:
            self._stream = None

        return self._write_buffer()

    def _write_buffer(self) -> tuple[Optional[str], Optional[str]]:
        if not self._buffer:
            return None, None

        audio = np.concatenate(self._buffer, axis=0)
        duration_s = len(audio) / self._config.sample_rate

        if duration_s < MIN_DURATION_S:
            logger.info("Recording too short (%.2f s) — discarded", duration_s)
            self._buffer = []
            self._output_path = None
            self._correlation_id = None
            return None, None

        if self._output_path is None:
            return None, None

        import soundfile as sf

        try:
            sf.write(
                file=str(self._output_path),
                data=audio,
                samplerate=self._config.sample_rate,
                subtype="PCM_16",
            )
            rel_path = str(self._output_path.relative_to(self._config.output_dir))
            cid = self._correlation_id
            return rel_path, cid
        except Exception:
            logger.exception("Failed to write WAV file: %s", self._output_path)
            return None, None
        finally:
            self._buffer = []
            self._output_path = None
            self._correlation_id = None
```

### 4.6 Orquestación y Publicación en `src/mic_daemon.py`

En `main_async()`, cuando el callback `on_stop` se ejecuta tras recibir `StopSpeechCaptureCommand` (`command.speech.stop-capture`), se obtiene la tupla `(rel_path, correlation_id)` y se publica el evento en `event.speech.captured`:

```python
async def handle_stop() -> None:
    rel_path, correlation_id = recorder.stop()
    if rel_path and correlation_id:
        await publisher.publish_speech_captured(
            correlation_id=correlation_id,
            channel="voice",
            audio_path=rel_path,
        )
```

---

## 5. Casos de Borde y Manejo de Errores

1. **Comandos sin Parámetros (*Parameterless Commands*)**:
   - Puesto que `StartSpeechCaptureCommand` no transporta atributos, `mic-daemon` genera siempre un UUIDv4 fresco en `recorder.start()`, garantizando trazabilidad sin depender del emisor del comando.
2. **Descarte por Duración Mínima (`< 0.1s`)**:
   - Si la grabación no supera `MIN_DURATION_S`, `_write_buffer()` retorna `(None, None)` y no se dispara la publicación del evento.
3. **Falla en la Escritura del Fichero WAV**:
   - Ante errores de sistema de archivos (disco lleno, permisos), se captura la excepción, se registra en logs y no se emite el evento NATS.
4. **Falla en el Bus NATS durante la Publicación**:
   - `publisher.publish_speech_captured()` maneja internamente cualquier excepción devuelta por `nova-event-bus` para prevenir que un fallo de red o caída de NATS colapse el demonio `mic-daemon`.
5. **Garantía de Ruta Relativa**:
   - `audioPath` se calcula mediante `output_path.relative_to(config.output_dir)` produciendo rutas relativas limpias (e.g. `2026-07-24_17-30-00.wav`).

---

## 6. Estrategia de Testing

- **Tests Unitarios de Comandos en `novactl` (`tests/test_events.py`) y `mic-daemon` (`tests/test_events.py`)**:
  - Verificar que `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand` usan estrictamente los decoradores `@event("command.speech.start-capture")` y `@event("command.speech.stop-capture")` en ambos repositorios (D-02).
- **Tests Unitarios de `ResponseGeneratedEvent` en `orchestrator` y `context-service`**:
  - Verificar que `ResponseGeneratedEvent` usa el decorador `@event("event.interaction.response-generated")`.
- **Tests Unitarios de `EventSubscriber` en `mic-daemon` (`tests/test_event_subscriber.py`)**:
  - Comprobar la suscripción correcta a `command.speech.start-capture` y `command.speech.stop-capture`.
- **Tests Unitarios de `EventPublisher` (`tests/test_event_publisher.py`)**:
  - Comprobar que `publish_speech_captured` instancia `SpeechCapturedEvent` con `@event("event.speech.captured")`.
  - Verificar que las excepciones lanzadas por `event_bus.publish` se capturan de forma limpia en los logs y no se propagan hacia el daemon (Scenario 6 / D-03).
- **Tests Unitarios de `Recorder` (`tests/test_recorder.py`)**:
  - Verificar que `start()` genera un `correlation_id` UUIDv4 válido.
  - Comprobar que `stop()` retorna la ruta relativa y el `correlation_id` cuando la grabación es válida.
  - Comprobar que `stop()` retorna `(None, None)` ante grabaciones cortas (< 0.1s) o errores de I/O.
- **Tests de Integración de `mic-daemon` (`tests/test_mic_daemon.py`)**:
  - Simular la secuencia completa `command.speech.start-capture` -> `command.speech.stop-capture` -> verificar la emisión de `event.speech.captured` en el mock de NATS.
- **Verificación de Impacto en `home-assistant`**:
  - Revisar si los repositorios/documentación de `home-assistant` requieren actualización en skills (`audio-subsystem`), ADRs o plantillas de variables de entorno debido a la emisión del nuevo evento y sujetos de comandos.

---

## 7. Plan de Implementación

- `[ ]` **Tarea 0: Creación de ADR-022 (Estandarización de Nomenclatura para Comunicaciones Asíncronas)**
  - Crear el archivo `docs/adr/adr-022-estandarizacion-nomenclatura-mensajeria-asincrona.md` en el repositorio `home-assistant` utilizando la propuesta formal contenida en el **Anexo I**.
- `[ ]` **Tarea 1: Actualización de Comandos y Definición de Evento en `novactl` / `mic-daemon` (`novactl/events.py`, `mic-daemon/src/events.py`)**
  - Actualizar `@event` de `StartSpeechCaptureCommand` a `"command.speech.start-capture"`.
  - Actualizar `@event` de `StopSpeechCaptureCommand` a `"command.speech.stop-capture"`.
  - Definir y registrar `SpeechCapturedEvent` con `@event("event.speech.captured")` con atributos `correlation_id`, `channel` y `audio_path` en `mic-daemon/src/events.py`.
  - Actualizar tests unitarios en `novactl` y `mic-daemon`.
- `[ ]` **Tarea 1b: Actualización de `ResponseGeneratedEvent` en `orchestrator` y `context-service`**
  - Actualizar el decorador `@event` de `ResponseGeneratedEvent` en `orchestrator/core/events.py` a `"event.interaction.response-generated"`.
  - Actualizar el decorador `@event` de `ResponseGeneratedEvent` en `context-service/app/events.py` a `"event.interaction.response-generated"`.
  - Actualizar tests unitarios en `orchestrator` y `context-service`.
- `[ ]` **Tarea 2: Actualización de Suscripción a Comandos en `mic-daemon` (`src/event_subscriber.py`)**
  - Actualizar `EventSubscriber` para suscribirse a los nuevos subjects `command.speech.start-capture` y `command.speech.stop-capture`.
  - Actualizar tests unitarios en `tests/test_event_subscriber.py`.
- `[ ]` **Tarea 3: Implementación de `EventPublisher` en `mic-daemon` (`src/event_publisher.py`)**
  - Crear `src/event_publisher.py` con `publish_speech_captured` (`event.speech.captured`).
  - Añadir pruebas unitarias en `tests/test_event_publisher.py`.
- `[ ]` **Tarea 4: Actualización de `Recorder` (`src/recorder.py`)**
  - Generar `correlation_id` UUIDv4 en `start()`.
  - Retornar `(rel_path, correlation_id)` en `stop()`.
  - Actualizar `tests/test_recorder.py`.
- `[ ]` **Tarea 5: Integración en Orquestación de `mic-daemon` (`src/mic_daemon.py`)**
  - Conectar `handle_stop()` con `publisher.publish_speech_captured()`.
  - Actualizar `tests/test_mic_daemon.py`.
- `[ ]` **Tarea 6: Actualización de Documentación de `home-assistant` (Skills, ADRs, Catalog)**
  - Registrar ADR-022 en el índice de ADRs (`docs/adr/README.md`) y actualizar las skills (`audio-subsystem`, `event-driven-architecture`, `service-responsibilities`) y el catálogo de servicios (`docs/services.md`) para referenciar los nuevos subjects (`command.speech.start-capture`, `command.speech.stop-capture`, `event.speech.captured` y `event.interaction.response-generated`), sustituyendo las referencias a ADR-020 y ADR-021 en lo referente a la taxonomía de comandos de voz.
- `[ ]` **Tarea 7: Documentación Local (`README.md` y `CHANGELOG.md`)**
  - Registrar los cambios en `CHANGELOG.md` (`[Sin publicar]`) y actualizar `README.md` en los repositorios correspondientes.

---

## 8. Anexo I: Propuesta de ADR-022

```markdown
# ADR-022: Estandarización de Nomenclatura para Comunicaciones Asíncronas y Publicación de Eventos de Dominio (Fase 4 Refactor de Entrada)

- **Fecha**: 24-07-2026
- **Estado**: Aceptado
- **Contexto**:
  Tras la consolidación del message broker NATS y la librería unificada `nova-event-bus` (ADR-017, ADR-018, ADR-020 y ADR-021), la arquitectura basada en eventos del ecosistema Nova-2 requiere una taxonomía clara y estandarizada para nombrar los subjects en NATS. Hasta ahora existían nomenclaturas heterogéneas (ej. `novactl.command.<nombre>`, `orchestrator.response.generated` o propuestas como `event.<nombre_evento>`), lo que dificultaba la distinción entre peticiones imperativas y notificaciones declarativas, así como el filtrado por comodines (*wildcards*).

  Esta decisión **sustituye y anula** explícitamente la nomenclatura de subjects de comandos definida en ADR-020 (punto 4) (`novactl.command.<nombre_comando>`) y ADR-021 (punto 3) (`novactl.command.start_speech_capture` y `novactl.command.stop_speech_capture`), unificándolas bajo la nueva taxonomía estandarizada.

  Asimismo, en el marco de la Fase 4 del refactor de entrada, `mic-daemon` (componente del host) debe publicar su primer evento de dominio (`SpeechCapturedEvent`) para notificar que una nueva locución se ha grabado y almacenado correctamente en el volumen compartido, iniciando la transición de la observación por filesystem hacia eventos.

- **Decisión**:
  1. **Taxonomía Binaria de Mensajería Asíncrona**: Todos los subjects registrados en `nova-event-bus` se clasifican estrictamente en una de las siguientes dos categorías:
     - **Comandos (`command.{dominio}.{petición}`)**: Representan una orden o petición directa dirigida a un componente del sistema para ejecutar una acción imperativa.
       - *Ejemplos*:
         - `command.speech.start-capture`: Iniciar captura de audio del micrófono.
         - `command.speech.stop-capture`: Detener captura de audio del micrófono.
     - **Eventos (`event.{dominio}.{notificación}`)**: Notifican de forma declarativa un hecho que ya ha ocurrido en el sistema.
       - *Ejemplos*:
         - `event.speech.captured`: Notifica la disponibilidad de una nueva locución grabada en disco.
         - `event.interaction.response-generated`: Notifica que el orquestador ha generado una respuesta para el usuario.

  2. **Canonización de `SpeechCapturedEvent`**:
     - `mic-daemon` publicará el evento `SpeechCapturedEvent` en el subject `event.speech.captured` tras guardar con éxito el fichero `.wav` en `MIC_OUTPUT_DIR`.
     - El payload contendrá: `correlation_id` (UUIDv4 generado autónomamente al iniciar la captura), `channel` (`voice`) y `audio_path` (ruta relativa al volumen compartido).

  3. **Migración Progresiva de Comandos y Eventos Existentes**:
     - Los comandos de captura (`StartSpeechCaptureCommand` y `StopSpeechCaptureCommand`) adoptan formalmente los subjects `command.speech.start-capture` y `command.speech.stop-capture`, sustituyendo el prefijo `novactl.command.*` de ADR-020 y ADR-021.
     - El evento `ResponseGeneratedEvent` en `orchestrator` (`core/events.py`) y `context-service` (`app/events.py`) adopta el subject `event.interaction.response-generated`, sustituyendo el subject heredado `orchestrator.response.generated`.

- **Alternativas consideradas**:
  - **Uso de nombres de clases de Python como subjects (`SpeechCapturedEvent`)**: Rechazado por acoplar la infraestructura de mensajería a detalles de implementación del lenguaje.
  - **Subjects planos sin prefijo de categoría (`speech.captured`)**: Rechazado por impedir el filtrado claro en NATS entre tráfico de comandos de control y tráfico de eventos de dominio.

- **Consecuencias**:
  - **Claridad Semántica**: Separación explícita entre intenciones imperativas (`command.*`) y notificaciones de hechos sucedidos (`event.*`).
  - **Filtrado Flexible**: Permite suscripciones por comodines NATS (ej. `command.speech.*` o `event.interaction.*`).
  - **Evolución del Refactor de Entrada**: `mic-daemon` se convierte en un publicador activo de eventos de dominio sobre `event.speech.captured`.
  - **Sustitución y Trazabilidad de ADRs**: Este ADR reemplaza formalmente la convención de naming de subjects definida en ADR-020 (punto 4) y ADR-021 (punto 3). Las referencias en las skills transversales (`event-driven-architecture`, `audio-subsystem`, `service-responsibilities`) se actualizarán en la Tarea 6 para referenciar ADR-022.
```

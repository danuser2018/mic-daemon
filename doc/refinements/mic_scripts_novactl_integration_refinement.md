# Documento de Refinamiento: Integración de novactl en Scripts de Captura de Micrófono (mic-start / mic-stop)

- **Documento / Solicitud de Origen**: Refactorización de entrada basada en eventos mediante `novactl` (Integración en `mic-start.sh` y `mic-stop.sh`)
- **Estado**: Superado — scripts eliminados, novactl es el único punto de entrada CLI (2026-08-02)

---

## 1. Resumen y Contexto de Negocio

El ecosistema Nova-2 se encuentra en proceso de migración de su mecanismo de activación de captura de voz desde archivos de marca en el sistema de archivos (`/tmp/voice_assistant/recording.flag`) hacia un modelo de eventos centralizados sobre el bus NATS. 

Como primer paso de este desacoplamiento, se ha creado la CLI oficial `novactl`. El objetivo de este refinamiento es especificar la actualización de los scripts de control de micrófono existentes en `mic-daemon` (`scripts/mic-start.sh` y `scripts/mic-stop.sh`) para incluir invocaciones a `novactl` emitiendo los subcomandos oficiales de captura (`novactl start-capture` y `novactl stop-capture`).

Durante la fase de transición, los scripts mantendrán de forma no bloqueante la manipulación del archivo de marca local para asegurar la retrocompatibilidad con la versión actual de `mic-daemon`.

---

## 2. Análisis de Servicios e Impacto

| Servicio | Tipo de Cambio | Descripción del Impacto |
| :--- | :--- | :--- |
| `mic-daemon` | **[MODIFY]** | Actualización de `scripts/mic-start.sh` y `scripts/mic-stop.sh` para incorporar invocaciones no bloqueantes a `novactl` (`start-capture` / `stop-capture`). Actualización de la documentación en `README.md` y adición de tests de integración para los scripts shell. |
| `novactl` | **Ninguno** | Ya expone los comandos oficiales `start-capture` y `stop-capture` que publican `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand` en `nova-event-bus`. |
| `hid-daemon` | **Ninguno** | Sigue invocando `mic-start` y `mic-stop` sin cambios en sus archivos de configuración ni binarios. |
| `home-assistant` | **Ninguno** | Los scripts de instalación mantendrán el copiado habitual de `mic-start.sh` y `mic-stop.sh` hacia `~/.local/bin/`. |

---

## 3. Especificación de Comportamiento (Criterios de Aceptación)

### Scenario 1: Execute mic-start script with novactl available
```gherkin
Scenario: Trigger speech capture start via mic-start script
  Given that the novactl CLI binary is available in the system PATH
  When the user or external daemon executes "mic-start.sh"
  Then the script must invoke "novactl start-capture"
  And "novactl" must publish a StartSpeechCaptureCommand event to NATS
  And the script must create the legacy flag file "/tmp/voice_assistant/recording.flag" for backward compatibility
  And the process exit code must be 0
```

### Scenario 2: Execute mic-stop script with novactl available
```gherkin
Scenario: Trigger speech capture stop via mic-stop script
  Given that the novactl CLI binary is available in the system PATH
  When the user or external daemon executes "mic-stop.sh"
  Then the script must invoke "novactl stop-capture"
  And "novactl" must publish a StopSpeechCaptureCommand event to NATS
  And the script must remove the legacy flag file "/tmp/voice_assistant/recording.flag" if it exists
  And the process exit code must be 0
```

### Scenario 3: Graceful degradation when novactl is missing or NATS is offline
```gherkin
Scenario: Non-blocking execution when novactl fails or is missing
  Given that novactl is missing from PATH or NATS broker is unreachable
  When the script "mic-start.sh" or "mic-stop.sh" is executed
  Then the script must log a warning message to stderr indicating novactl execution failure
  And the script must continue maintaining the legacy flag file "/tmp/voice_assistant/recording.flag"
  And the script exit code must remain 0 to prevent breaking caller hotkey daemons
```

---

## 4. Diseño Técnico y Contratos

### 4.1 Identificación Exacta de Subcomandos `novactl`

`novactl` expone los siguientes subcomandos oficiales para el control de captura de audio:
* **Inicio de captura**: `novactl start-capture` (publica `StartSpeechCaptureCommand` a `novactl.command.start_speech_capture`).
* **Fin de captura**: `novactl stop-capture` (publica `StopSpeechCaptureCommand` a `novactl.command.stop_speech_capture`).

### 4.2 Actualización de Scripts Shell en `mic-daemon/scripts/`

#### 1. `mic-daemon/scripts/mic-start.sh`

```bash
#!/usr/bin/env bash
# mic-start.sh — Trigger speech capture start via novactl & create legacy recording flag.

set -euo pipefail

FLAG="/tmp/voice_assistant/recording.flag"

# 1. Non-blocking novactl invocation
if command -v novactl >/dev/null 2>&1; then
    novactl start-capture || echo "Warning: novactl start-capture failed" >&2
else
    echo "Warning: novactl is not installed or not in PATH" >&2
fi

# 2. Legacy flag management for backward compatibility
mkdir -p "$(dirname "$FLAG")"
touch "$FLAG"
```

#### 2. `mic-daemon/scripts/mic-stop.sh`

```bash
#!/usr/bin/env bash
# mic-stop.sh — Trigger speech capture stop via novactl & remove legacy recording flag.

set -euo pipefail

FLAG="/tmp/voice_assistant/recording.flag"

# 1. Non-blocking novactl invocation
if command -v novactl >/dev/null 2>&1; then
    novactl stop-capture || echo "Warning: novactl stop-capture failed" >&2
else
    echo "Warning: novactl is not installed or not in PATH" >&2
fi

# 2. Legacy flag management for backward compatibility
rm -f "$FLAG"
```

---

## 5. Casos de Borde y Manejo de Errores

1. **`novactl` No Instalado o No Disponible en `PATH`**:
   - La instrucción `command -v novactl` evalúa si el ejecutable está disponible. Si no está en el `PATH`, escribe una advertencia en `stderr` y continúa sin abortar (`exit 0`).
2. **Broker NATS Desconectado o Inaccesible**:
   - Si `novactl` se ejecuta pero no puede conectarse a NATS (retornando código de salida `1`), la disyunción `||` captura la falla, imprime una advertencia en `stderr` y permite continuar la creación/eliminación del archivo de marca.
3. **Idempotencia**:
   - Invocaciones repetidas de `mic-start.sh` o `mic-stop.sh` son puramente idempotentes tanto en `novactl` como en las operaciones del sistema de archivos (`touch` / `rm -f`).

---

## 6. Estrategia de Testing

- **Pruebas de Integración de Scripts Shell (`mic-daemon/tests/test_scripts.py`)**:
  - Ejecutar `mic-start.sh` y `mic-stop.sh` desde pruebas con `pytest` y `subprocess`.
  - Mockear el binario `novactl` mediante un script ejecutable temporal en el `PATH` para verificar que es invocado con `start-capture` o `stop-capture`.
  - Verificar que `/tmp/voice_assistant/recording.flag` se crea al ejecutar `mic-start.sh` y se elimina al ejecutar `mic-stop.sh`.
  - Verificar que ante la ausencia de `novactl`, el script finaliza con código de retorno `0` y mantiene el comportamiento del archivo de marca.

---

## 7. Plan de Implementación

- `[ ]` **Tarea 1: Actualizar scripts de control en `mic-daemon`**
  - Modificar `mic-daemon/scripts/mic-start.sh` incluyendo la llamada no bloqueante a `novactl start-capture`.
  - Modificar `mic-daemon/scripts/mic-stop.sh` incluyendo la llamada no bloqueante a `novactl stop-capture`.
  - Asegurar permisos de ejecución (`chmod +x scripts/mic-start.sh scripts/mic-stop.sh`).

- `[ ]` **Tarea 2: Crear suite de pruebas de integración para scripts en `mic-daemon`**
  - Añadir `mic-daemon/tests/test_scripts.py` probando los escenarios con `novactl` presente, sin `novactl` y comprobando la persistencia de la marca.

- `[ ]` **Tarea 3: Actualizar Documentación en `mic-daemon`**
  - Actualizar `mic-daemon/README.md` documentando la invocación híbrida de `novactl start-capture` y `novactl stop-capture` dentro de los scripts de control.

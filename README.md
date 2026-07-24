# mic-daemon

Daemon de Linux local que graba audio del micrófono al activarse mediante comandos orientados a eventos publicados en NATS vía `nova-event-bus`. Controla el estado de grabación de forma asíncrona y sin dependencias de GUI ni servicios en la nube.

---

## Tabla de contenidos

1. [Descripción del proyecto](#descripción-del-proyecto)
2. [Arquitectura del sistema](#arquitectura-del-sistema)
3. [Máquina de estados](#máquina-de-estados)
4. [Flujo de ejecución](#flujo-de-ejecución)
5. [Interfaz del daemon](#interfaz-del-daemon)
6. [Modos de operación](#modos-de-operación)
7. [Estructura del proyecto](#estructura-del-proyecto)
8. [Requisitos](#requisitos)
9. [Instalación](#instalación)
10. [Configuración](#configuración)
11. [Servicio systemd](#servicio-systemd)
12. [Integración con hotkeys](#integración-con-hotkeys)
13. [Robustez y recuperación ante fallos](#robustez-y-recuperación-ante-fallos)
14. [Decisiones de diseño](#decisiones-de-diseño)
15. [Buenas prácticas](#buenas-prácticas)
16. [Contribuir](#contribuir)

---

## Descripción del proyecto

`mic-daemon` es un servicio de usuario de Linux que:

- Espera en segundo plano consumiendo recursos mínimos.
- Se conecta al bus de eventos NATS mediante `nova-event-bus`.
- Reacciona a los eventos `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand` (emitidos por `novactl` o daemons del sistema).
- Graba audio del micrófono local usando `sounddevice`.
- Guarda el resultado como archivo `.wav` con nombre basado en timestamp ISO-like.
- No requiere GUI, no envía datos a ningún servicio externo y no asume hardware específico.

El principio central de diseño es **comunicación orientada a eventos pura**: el daemon no realiza bucles de polling sobre el sistema de archivos, sino que responde de manera asíncrona a comandos del dominio emitidos a través de NATS.

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        USUARIO / ENTORNO                        │
│                                                                 │
│   Hotkey / Invocación CLI                                       │
│        │                                                        │
│        ▼                                                        │
│   novactl (start-capture / stop-capture)                        │
│   o scripts de control: mic-start.sh / mic-stop.sh             │
│        │                                                        │
│        ▼                                                        │
│   NATS Event Bus (nova-event-bus)                               │
│        │                                                        │
│        ▼                                                        │
│   mic-daemon (servicio systemd --user via EventSubscriber)      │
│        │  suscribe a StartSpeechCaptureCommand                  │
│        │  suscribe a StopSpeechCaptureCommand                   │
│        │  captura audio → sounddevice                           │
│        │  escribe .wav → $MIC_OUTPUT_DIR                       │
│        ▼                                                        │
│   Archivos WAV  (ej: 2026-05-31_21-45-10.wav)                 │
└─────────────────────────────────────────────────────────────────┘
```

### Componentes

| Componente | Responsabilidad |
|---|---|
| `novactl` / `scripts` | Emite comandos NATS `StartSpeechCaptureCommand` y `StopSpeechCaptureCommand` |
| `nova-event-bus` | Librería común de mensajería asíncrona sobre NATS |
| `mic-daemon` | Proceso Python con `EventSubscriber` que gestiona la grabación |
| `$MIC_OUTPUT_DIR` | Directorio de salida de archivos WAV (configurable) |
| `systemd --user` | Ciclo de vida del daemon (arranque, reinicio, logs) |

---

## Máquina de estados

El daemon opera con tres estados internos bien definidos:

```
            ┌──────────────────────────────────────────┐
            │                                          │
            ▼                                          │
    ┌──────────────┐ StartSpeechCapture ┌─────────────────┐
    │     IDLE     │ ─────────────────► │   RECORDING     │
    │              │                    │                 │
    │ Reposo pasivo│                    │ Captura audio   │
    │ (espera NATS)│ ◄───────────────── │ en buffer       │
    └──────────────┘ StopSpeechCapture  └────────┬────────┘
                                                 │
                                                 │ StopSpeechCapture
                                                 ▼
                                        ┌─────────────────┐
                                        │    STOPPING     │
                                        │                 │
                                        │ Flush buffer    │
                                        │ Escribe .wav    │
                                        │ Libera recursos │
                                        └────────┬────────┘
                                                 │
                                                 └──► IDLE
```

| Estado | Descripción | Acción |
|---|---|---|
| `IDLE` | Daemon en reposo, sin captura activa | Escucha eventos NATS asíncronamente |
| `RECORDING` | Micrófono activo, acumulando frames en buffer | Captura continua con `sounddevice` |
| `STOPPING` | Evento Stop recibido, grabación en curso de cierre | Vuelca buffer a disco como `.wav` si >= 0.1s |

---

## Flujo de ejecución

### Inicio de grabación

```
1. Hotkey o comando ejecutado (ej: novactl start-capture o mic-start.sh)
2. Se publica StartSpeechCaptureCommand en NATS
3. EventSubscriber en mic-daemon recibe el evento
4. mic-daemon: IDLE → RECORDING
5. Abrir stream de audio (sounddevice.InputStream)
6. Acumular frames en buffer en memoria
```

### Fin de grabación

```
1. Hotkey o comando ejecutado (ej: novactl stop-capture o mic-stop.sh)
2. Se publica StopSpeechCaptureCommand en NATS
3. EventSubscriber en mic-daemon recibe el evento
4. mic-daemon: RECORDING → STOPPING
5. Cerrar stream de audio
6. Generar nombre de archivo: timestamp ISO-like  →  2026-05-31_21-45-10.wav
7. Escribir buffer a disco con soundfile.write() si duración >= 0.1s
8. Publicar SpeechCapturedEvent en NATS (subject: event.speech.captured)
9. Limpiar buffer en memoria
10. mic-daemon: STOPPING → IDLE
```

---

## Interfaz del daemon

### Entradas

| Entrada | Tipo | Descripción |
|---|---|---|
| `StartSpeechCaptureCommand` | Evento NATS | Subject `command.speech.start-capture` (evento sin parámetros; invoca callback `on_start: Callable[[], None]`) |
| `StopSpeechCaptureCommand` | Evento NATS | Subject `command.speech.stop-capture` (evento sin parámetros; invoca callback `on_stop: Callable[[], None]`) |
| `$MIC_OUTPUT_DIR` | Variable de entorno | Directorio destino de archivos WAV |
| `$NATS_URL` | Variable de entorno (opcional) | URL del broker NATS (por defecto: `nats://localhost:4222`) |
| `$MIC_DEVICE` | Variable de entorno (opcional) | Índice o nombre del dispositivo de audio |
| `$MIC_SAMPLE_RATE` | Variable de entorno (opcional) | Sample rate en Hz (por defecto: 16000) |
| `$MIC_CHANNELS` | Variable de entorno (opcional) | Canales de audio (por defecto: 1, mono) |

### Salidas

| Salida | Tipo | Descripción |
|---|---|---|
| `$MIC_OUTPUT_DIR/YYYY-MM-DD_HH-MM-SS.wav` | Archivo WAV | Grabación de audio completa |
| `SpeechCapturedEvent` | Evento NATS | Subject `event.speech.captured` (contiene `correlation_id`, `channel='voice'`, `audio_path` relativo) |
| `journalctl --user -u mic-daemon` | Log systemd | Logs de operación, errores y eventos |

---

## Modos de operación

### Modo Push-to-Talk / Command-driven

```bash
# Al presionar / ejecutar -> invoca novactl start-capture
mic-start.sh

# Al soltar / ejecutar -> invoca novactl stop-capture
mic-stop.sh
```

---

## Estructura del proyecto

```
mic-daemon/
├── README.md                    # Este documento
├── CONTRIBUTING.md              # Guía de contribución
├── CHANGELOG.md                 # Registro de cambios
├── LICENSE
├── .gitignore
│
├── src/
│   ├── mic_daemon.py            # Punto de entrada principal del daemon (asyncio)
│   ├── recorder.py              # Lógica de captura y escritura de audio
│   ├── event_subscriber.py      # Gestor de suscripciones a eventos NATS
│   ├── event_publisher.py       # Publicador de eventos de dominio (SpeechCapturedEvent)
│   ├── events.py                # Definición de clases de comandos y eventos NATS
│   └── config.py                # Carga y validación de variables de entorno
│
├── scripts/
│   ├── mic-start.sh             # Script de control (invoca novactl start-capture)
│   └── mic-stop.sh              # Script de control (invoca novactl stop-capture)
│
├── systemd/
│   └── mic-daemon.service       # Unidad de servicio systemd --user
│
└── tests/
    ├── test_recorder.py
    ├── test_event_subscriber.py
    ├── test_event_publisher.py
    ├── test_events.py
    ├── test_mic_daemon.py
    ├── test_scripts.py
    └── test_config.py
```

---

## Requisitos

### Sistema

- Linux con PipeWire o PulseAudio
- Python 3.10+
- Broker NATS en ejecución
- systemd (modo usuario)

### Dependencias Python

```
sounddevice>=0.4.6
soundfile>=0.12.1
numpy>=1.24.0
nova-event-bus
novactl
```

---

## Instalación y Configuración

### Configuración de variables de entorno (`~/.config/mic-daemon/env`)

```bash
mkdir -p ~/.config/mic-daemon
cat > ~/.config/mic-daemon/env << 'EOF'
MIC_OUTPUT_DIR=/home/TU_USUARIO/voice-recordings
NATS_URL=nats://localhost:4222
MIC_DEVICE=
MIC_SAMPLE_RATE=16000
MIC_CHANNELS=1
EOF
```

---

## Servicio systemd

### Unidad de servicio: `mic-daemon.service`

```ini
[Unit]
Description=Microphone recording daemon controlled by NATS event bus
Documentation=https://github.com/danuser2018/mic-daemon
After=default.target pipewire.service pipewire-pulse.service

[Service]
Type=simple
EnvironmentFile=%h/.config/mic-daemon/env
ExecStart=%h/workspace/mic-daemon/.venv/bin/python -m src.mic_daemon
WorkingDirectory=%h/workspace/mic-daemon
Restart=on-failure
RestartSec=3s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

---

## Decisiones de diseño

### ¿Por qué NATS event bus en lugar de polling en el sistema de ficheros?

La migración a `nova-event-bus` elimina la necesidad de consultar el filesystem periódicamente, reduciendo I/O de disco, disminuyendo latencias a microsegundos y evitando ficheros de estado residuo tras accidentes o caídas.

---

*Proyecto local-first. Sin cloud. Event-driven.*

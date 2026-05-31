# mic-daemon

Daemon de Linux local que graba audio del micrófono al activarse mediante un hotkey externo. Controla el estado de grabación a través de un archivo de estado en el sistema de ficheros, sin dependencias de GUI ni servicios en la nube.

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
- Se activa mediante un hotkey externo gestionado por el sistema operativo.
- Graba audio del micrófono local usando `sounddevice` o `PyAudio`.
- Guarda el resultado como archivo `.wav` con nombre basado en timestamp ISO-like.
- No requiere GUI, no envía datos a ningún servicio externo y no asume hardware específico.

El principio central de diseño es **"filesystem como máquina de estado"**: el daemon no mantiene estado en memoria entre ciclos; consulta el sistema de ficheros para decidir qué hacer a continuación. Esto lo hace extremadamente fácil de depurar, monitorizar y reiniciar.

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        USUARIO / ENTORNO                        │
│                                                                 │
│   Hotkey (sxhkd / KDE / GNOME / xbindkeys)                     │
│        │                                                        │
│        ▼                                                        │
│   Script de control: mic-toggle.sh                             │
│        │  crea / elimina /tmp/voice_assistant/recording.flag   │
│        ▼                                                        │
│   Sistema de ficheros (/tmp/voice_assistant/)                  │
│        │                                                        │
│        ▼                                                        │
│   mic-daemon (servicio systemd --user)                         │
│        │  observa el flag (polling o watchdog)                  │
│        │  captura audio → sounddevice / PyAudio                │
│        │  escribe .wav → $MIC_OUTPUT_DIR                       │
│        ▼                                                        │
│   Archivos WAV  (ej: 2026-05-31_21-45-10.wav)                 │
└─────────────────────────────────────────────────────────────────┘
```

### Componentes

| Componente | Responsabilidad |
|---|---|
| `mic-toggle.sh` | Crea o elimina el archivo `.flag` según el modo (toggle o push-to-talk) |
| `mic-daemon` | Proceso Python que observa el `.flag` y gestiona la grabación |
| `recording.flag` | Interruptor global del sistema. Existencia = grabando |
| `$MIC_OUTPUT_DIR` | Directorio de salida de archivos WAV (configurable) |
| `systemd --user` | Ciclo de vida del daemon (arranque, reinicio, logs) |

---

## Máquina de estados

El daemon opera con tres estados internos bien definidos:

```
            ┌──────────────────────────────────────────┐
            │                                          │
            ▼                                          │
    ┌──────────────┐   flag aparece   ┌─────────────────┐
    │     IDLE     │ ───────────────► │   RECORDING     │
    │              │                  │                 │
    │ Espera pasiva│                  │ Captura audio   │
    │ (poll/watch) │ ◄─────────────── │ en buffer       │
    └──────────────┘   flag eliminado └────────┬────────┘
                                               │
                                               │ flag eliminado
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
| `IDLE` | Daemon en reposo, sin captura activa | Observa el flag cada N ms |
| `RECORDING` | Micrófono activo, acumulando frames en buffer | Captura continua con `sounddevice` |
| `STOPPING` | Flag eliminado, grabación en curso de cierre | Vuelca buffer a disco como `.wav` |

---

## Flujo de ejecución

### Inicio de grabación

```
1. Hotkey presionado
2. mic-toggle.sh ejecutado
3. ¿Existe recording.flag?  →  NO
4. Crear /tmp/voice_assistant/recording.flag
5. daemon detecta flag (próximo ciclo de poll o evento watchdog)
6. daemon: IDLE → RECORDING
7. Abrir stream de audio (sounddevice.InputStream)
8. Acumular frames en buffer en memoria
```

### Fin de grabación (toggle o release en push-to-talk)

```
1. Hotkey presionado de nuevo (toggle) o liberado (push-to-talk)
2. mic-toggle.sh elimina recording.flag
3. daemon detecta ausencia del flag
4. daemon: RECORDING → STOPPING
5. Cerrar stream de audio
6. Generar nombre de archivo: timestamp ISO-like  →  2026-05-31_21-45-10.wav
7. Escribir buffer a disco con soundfile.write()
8. Limpiar buffer en memoria
9. daemon: STOPPING → IDLE
```

### Diagrama de secuencia

```
Usuario       mic-toggle.sh     /tmp/flag     mic-daemon       Disco
  │                │                │               │            │
  │──hotkey───────►│                │               │            │
  │                │──crear flag───►│               │            │
  │                │                │◄──poll/watch──│            │
  │                │                │               │──open stream
  │                │                │               │──capturing─┤
  │                │                │               │            │
  │──hotkey───────►│                │               │            │
  │                │──rm flag──────►│               │            │
  │                │                │◄──poll/watch──│            │
  │                │                │               │──close stream
  │                │                │               │──write WAV►│
  │                │                │               │──IDLE      │
```

---

## Interfaz del daemon

### Entradas

| Entrada | Tipo | Descripción |
|---|---|---|
| `/tmp/voice_assistant/recording.flag` | Archivo (presencia/ausencia) | Interruptor principal de grabación |
| `$MIC_OUTPUT_DIR` | Variable de entorno | Directorio destino de archivos WAV |
| `$MIC_DEVICE` | Variable de entorno (opcional) | Índice o nombre del dispositivo de audio |
| `$MIC_SAMPLE_RATE` | Variable de entorno (opcional) | Sample rate en Hz (por defecto: 16000) |
| `$MIC_CHANNELS` | Variable de entorno (opcional) | Canales de audio (por defecto: 1, mono) |
| `$MIC_POLL_INTERVAL_MS` | Variable de entorno (opcional) | Intervalo de polling en ms (por defecto: 100) |

### Salidas

| Salida | Tipo | Descripción |
|---|---|---|
| `$MIC_OUTPUT_DIR/YYYY-MM-DD_HH-MM-SS.wav` | Archivo WAV | Grabación de audio completa |
| `journalctl --user -u mic-daemon` | Log systemd | Logs de operación, errores y eventos |

### Naming de archivos WAV

El nombre del archivo se genera en el momento en que comienza la grabación (cuando el flag aparece), usando timestamp local con formato ISO-like:

```
YYYY-MM-DD_HH-MM-SS.wav

Ejemplos:
  2026-05-31_21-45-10.wav
  2026-06-01_09-03-55.wav
```

Esto garantiza unicidad y permite ordenación cronológica trivial con `ls`.

---

## Modos de operación

### Modo Toggle

```bash
# Primera pulsación → inicia grabación (crea flag)
# Segunda pulsación → detiene grabación (elimina flag)

# mic-toggle.sh (modo toggle)
FLAG="/tmp/voice_assistant/recording.flag"
if [ -f "$FLAG" ]; then
    rm "$FLAG"
else
    mkdir -p "$(dirname "$FLAG")"
    touch "$FLAG"
fi
```

### Modo Push-to-Talk

```bash
# Al presionar → inicia grabación (crea flag)
# Al soltar    → detiene grabación (elimina flag)

# mic-start.sh
mkdir -p /tmp/voice_assistant
touch /tmp/voice_assistant/recording.flag

# mic-stop.sh
rm -f /tmp/voice_assistant/recording.flag
```

En modo push-to-talk, el gestor de hotkeys debe ser capaz de distinguir entre `KeyPress` y `KeyRelease`. `sxhkd` soporta esto mediante el prefijo `@` en el keysym.

---

## Estructura del proyecto

```
mic-daemon/
├── README.md                    # Este documento
├── CONTRIBUTING.md              # Guía de contribución (TBD, commits, PRs)
├── CHANGELOG.md                 # Registro de cambios (Keep a Changelog)
├── LICENSE
├── .gitignore
│
├── src/
│   ├── mic_daemon.py            # Punto de entrada principal del daemon
│   ├── recorder.py              # Lógica de captura y escritura de audio
│   ├── state_watcher.py         # Observador del archivo de estado (poll / watchdog)
│   └── config.py                # Carga y validación de variables de entorno
│
├── scripts/
│   ├── mic-toggle.sh            # Script de control (modo toggle)
│   ├── mic-start.sh             # Script de control (push-to-talk: inicio)
│   └── mic-stop.sh              # Script de control (push-to-talk: stop)
│
├── systemd/
│   └── mic-daemon.service       # Unidad de servicio systemd --user
│
├── tests/
│   ├── test_recorder.py
│   ├── test_state_watcher.py
│   └── test_config.py
│
└── docs/
    └── prompts/                 # Prompts usados en desarrollo asistido con IA
```

---

## Requisitos

### Sistema

- Linux con PipeWire o PulseAudio
- Python 3.10+
- systemd (modo usuario)

### Dependencias Python

```
sounddevice>=0.4.6      # Captura de audio (wrapper de PortAudio)
soundfile>=0.12.1       # Escritura de archivos WAV/FLAC/OGG
watchdog>=4.0.0         # (Opcional) Observación de eventos de filesystem
```

> **Nota:** `sounddevice` requiere que `libportaudio2` esté instalado en el sistema.

### Dependencias del sistema

```bash
# Debian / Ubuntu
sudo apt install libportaudio2 python3-pip

# Arch Linux
sudo pacman -S portaudio python-pip

# Fedora
sudo dnf install portaudio python3-pip
```

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/danuser2018/mic-daemon.git
cd mic-daemon
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Crear el directorio de salida de audio

```bash
mkdir -p ~/voice-recordings
```

### 4. Instalar el servicio systemd

```bash
mkdir -p ~/.config/systemd/user/
cp systemd/mic-daemon.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable mic-daemon
systemctl --user start mic-daemon
```

### 5. Instalar los scripts de control

```bash
mkdir -p ~/.local/bin
cp scripts/mic-toggle.sh ~/.local/bin/mic-toggle
cp scripts/mic-start.sh ~/.local/bin/mic-start
cp scripts/mic-stop.sh ~/.local/bin/mic-stop
chmod +x ~/.local/bin/mic-toggle ~/.local/bin/mic-start ~/.local/bin/mic-stop
```

---

## Configuración

La configuración se gestiona exclusivamente mediante variables de entorno. El servicio systemd las carga desde `~/.config/mic-daemon/env`.

### Crear archivo de configuración

```bash
mkdir -p ~/.config/mic-daemon
cat > ~/.config/mic-daemon/env << 'EOF'
# Directorio donde se guardarán los archivos WAV
MIC_OUTPUT_DIR=/home/TU_USUARIO/voice-recordings

# (Opcional) Dispositivo de audio. Dejar vacío para usar el dispositivo por defecto.
# Obtener lista: python3 -c "import sounddevice as sd; print(sd.query_devices())"
MIC_DEVICE=

# (Opcional) Sample rate en Hz
MIC_SAMPLE_RATE=16000

# (Opcional) Número de canales (1=mono, 2=estéreo)
MIC_CHANNELS=1

# (Opcional) Intervalo de polling del flag en milisegundos
MIC_POLL_INTERVAL_MS=100
EOF
```

### Variables de entorno

| Variable | Requerida | Por defecto | Descripción |
|---|---|---|---|
| `MIC_OUTPUT_DIR` | ✅ Sí | — | Directorio de salida de archivos WAV |
| `MIC_DEVICE` | ❌ No | Dispositivo por defecto del sistema | Nombre o índice del dispositivo de audio |
| `MIC_SAMPLE_RATE` | ❌ No | `16000` | Sample rate en Hz |
| `MIC_CHANNELS` | ❌ No | `1` | Canales de audio |
| `MIC_POLL_INTERVAL_MS` | ❌ No | `100` | Intervalo de polling del archivo de estado |

---

## Servicio systemd

### Unidad de servicio: `mic-daemon.service`

```ini
[Unit]
Description=Microphone recording daemon controlled by filesystem flag
Documentation=https://github.com/danuser2018/mic-daemon
After=default.target pipewire.service pipewire-pulse.service

[Service]
Type=simple
EnvironmentFile=%h/.config/mic-daemon/env
ExecStart=/home/%u/mic-daemon/.venv/bin/python /home/%u/mic-daemon/src/mic_daemon.py
Restart=on-failure
RestartSec=3s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

### Comandos de gestión

```bash
# Ver estado del servicio
systemctl --user status mic-daemon

# Ver logs en tiempo real
journalctl --user -u mic-daemon -f

# Reiniciar el servicio
systemctl --user restart mic-daemon

# Detener el servicio
systemctl --user stop mic-daemon

# Deshabilitar el inicio automático
systemctl --user disable mic-daemon
```

---

## Integración con hotkeys

### sxhkd (recomendado para entornos X11 / bspwm / i3)

```ini
# ~/.config/sxhkd/sxhkdrc

# Modo toggle: una tecla para iniciar/parar
super + F9
    mic-toggle

# Modo push-to-talk: mantener pulsado para grabar
# '@' indica KeyRelease en sxhkd
super + F10
    mic-start
@super + F10
    mic-stop
```

### KDE Plasma (Configuración del sistema → Atajos de teclado)

Asociar los scripts `mic-toggle`, `mic-start` y `mic-stop` desde la interfaz de KDE Custom Shortcuts.

### GNOME (mediante `xbindkeys`)

```bash
# ~/.xbindkeysrc
"mic-toggle"
  Mod4 + F9
```

### Wayland (mediante `wl-keybind` o atajos nativos del compositor)

Para compositores Wayland como **Hyprland**, añadir en `~/.config/hypr/hyprland.conf`:

```ini
bind = SUPER, F9, exec, mic-toggle
```

---

## Robustez y recuperación ante fallos

### Múltiples triggers seguidos

El daemon ignora un nuevo evento de inicio si ya está en estado `RECORDING`. El script `mic-toggle.sh` verifica la existencia del flag antes de actuar, garantizando idempotencia. No se producen condiciones de carrera porque el sistema de ficheros local garantiza atomicidad en `touch` y `unlink`.

### Cortes de audio (dispositivo desconectado)

Si `sounddevice` lanza una excepción durante la captura, el daemon:
1. Registra el error en el journal de systemd.
2. Guarda el buffer parcial acumulado hasta ese momento (si supera una duración mínima configurable).
3. Elimina el flag de estado para volver a `IDLE` de forma controlada.
4. No sale del proceso; permanece en `IDLE` esperando el siguiente trigger.

### Recuperación tras crash del daemon

Si el proceso del daemon muere de forma inesperada, systemd lo reinicia automáticamente (`Restart=on-failure`). Al arrancar, el daemon comprueba si el flag existe:

- **Flag presente al arrancar:** situación anómala. El daemon elimina el flag y registra un aviso en el journal. No inicia grabación automáticamente para evitar grabaciones fantasma.
- **Flag ausente al arrancar:** inicio normal en estado `IDLE`.

### Limpieza de archivos `.flag`

El script `mic-stop.sh` usa `rm -f` (no falla si el archivo no existe). El daemon elimina el flag en cualquier trayectoria de error para evitar dejar el sistema en estado `RECORDING` bloqueado.

Un job de limpieza opcional puede ejecutarse al inicio de sesión:

```bash
# ~/.profile o ~/.bash_profile
rm -f /tmp/voice_assistant/recording.flag
```

### Permisos de audio en PipeWire / PulseAudio

El usuario que ejecuta el daemon debe pertenecer al grupo `audio`:

```bash
sudo usermod -aG audio $USER
# Es necesario cerrar sesión y volver a entrar para que el cambio tenga efecto
```

En sistemas con PipeWire, el daemon de usuario hereda automáticamente el acceso al servidor PipeWire si se ejecuta con `systemd --user` en la misma sesión D-Bus. No se requiere configuración adicional.

Si se usa PulseAudio standalone, es posible que sea necesario establecer la variable:

```bash
PULSE_SERVER=unix:/run/user/$(id -u)/pulse/native
```

---

## Decisiones de diseño

### ¿Por qué el sistema de ficheros como máquina de estados?

El estado del sistema vive en `/tmp`, no en la memoria del proceso. Esto permite:

- **Observabilidad inmediata:** `ls /tmp/voice_assistant/` muestra el estado en cualquier momento.
- **Control externo trivial:** cualquier proceso o script puede activar/desactivar el daemon con `touch` o `rm`.
- **Resiliencia ante reinicios:** el daemon puede morir y resucitar sin perder el estado visible del sistema.
- **Sin IPC complejo:** no se necesitan sockets, pipes, D-Bus ni señales POSIX para el canal de control principal.

### ¿Por qué systemd user service es suficiente?

Un servicio de usuario de systemd proporciona:
- Arranque automático al iniciar sesión.
- Reinicio automático ante fallos.
- Logging centralizado vía journald.
- Integración con el ciclo de vida de la sesión de usuario.

Todo esto sin necesitar un init system propio, supervisord, Docker ni ningún orquestador adicional.

### ¿Por qué separar el control (hotkey) de la ejecución (daemon)?

La separación de responsabilidades es fundamental:

| Capa | Componente | Responsabilidad |
|---|---|---|
| Control | `mic-toggle.sh` + gestor de hotkeys | Detectar la intención del usuario |
| Estado | `recording.flag` | Comunicar esa intención al daemon |
| Ejecución | `mic-daemon.py` | Actuar según el estado |

Esta separación hace que cada capa sea reemplazable de forma independiente. El gestor de hotkeys puede cambiar (sxhkd → KDE → GNOME) sin tocar el daemon. El daemon puede cambiar (Python → C → Rust) sin tocar los scripts.

### ¿Por qué polling en lugar de inotify/watchdog como mecanismo principal?

El polling a 100 ms introduce una latencia máxima de 100 ms en el inicio de la grabación, lo cual es imperceptible para el usuario. A cambio:

- El código es trivial y sin dependencias adicionales.
- No hay riesgo de perder eventos (el flag persiste hasta que el daemon lo procesa).
- `watchdog` se ofrece como opción opcional para quienes prefieran latencia mínima garantizada.

---

## Buenas prácticas

### Operación diaria

- Verifica que el daemon esté activo antes de usar el hotkey: `systemctl --user is-active mic-daemon`.
- Comprueba los logs si la grabación no responde: `journalctl --user -u mic-daemon --since "5 minutes ago"`.
- Mantén `MIC_OUTPUT_DIR` en un sistema de ficheros con suficiente espacio libre. Una grabación de 60 segundos en 16 kHz mono PCM ocupa aproximadamente 1,9 MB.

### Mantenimiento del directorio de salida

Los archivos WAV no se eliminan automáticamente. Se recomienda establecer una política de retención:

```bash
# Eliminar grabaciones con más de 30 días de antigüedad
find ~/voice-recordings -name "*.wav" -mtime +30 -delete
```

Este comando puede añadirse a un timer de systemd o a un cron job.

### Seguridad y privacidad

- El directorio `/tmp/voice_assistant/` es accesible por cualquier proceso del usuario. En sistemas multiusuario, usar `/run/user/$(id -u)/voice_assistant/` en su lugar.
- Los archivos WAV contienen audio en bruto. Asegúrate de que `MIC_OUTPUT_DIR` tiene permisos restrictivos (`chmod 700`).
- No versiones el directorio de salida ni los archivos WAV en Git.

### Testing

```bash
# Ejecutar todos los tests
source .venv/bin/activate
python -m pytest tests/ -v

# Con cobertura
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Verificar el dispositivo de audio

```bash
# Listar todos los dispositivos disponibles
python3 -c "import sounddevice as sd; print(sd.query_devices())"

# Hacer una grabación de prueba de 3 segundos
python3 -c "
import sounddevice as sd
import soundfile as sf
import numpy as np
duration = 3
data = sd.rec(int(duration * 16000), samplerate=16000, channels=1, dtype='int16')
sd.wait()
sf.write('/tmp/test-mic.wav', data, 16000)
print('Grabación guardada en /tmp/test-mic.wav')
"
```

---

## Contribuir

Este proyecto sigue las convenciones descritas en [CONTRIBUTING.md](./CONTRIBUTING.md):

- **Modelo de ramificación:** Trunk Based Development. Todas las features parten de `main` y regresan mediante Pull Request.
- **Commits:** estándar [Conventional Commits](https://www.conventionalcommits.org/).
- **Idioma del código:** inglés.
- **Idioma de la documentación:** español.
- **Tests:** todo nuevo código debe incluir tests unitarios.

### Flujo rápido para contribuciones

```bash
git checkout main && git pull origin main
git checkout -b feature/mi-mejora
# ... desarrollar y testear ...
git add . && git commit -m "feat(recorder): añadir soporte para formato FLAC"
git push origin feature/mi-mejora
# Abrir Pull Request en GitHub
```

---

*Proyecto local-first. Sin cloud. Sin GUI. Sin complicaciones.*

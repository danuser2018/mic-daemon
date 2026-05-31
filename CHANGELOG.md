# Registro de cambios

Todos los cambios notables de este proyecto se documentan en este fichero.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y este proyecto adhiere a [Versionado Semántico](https://semver.org/lang/es/).

## Guía de uso

Cada versión se documenta bajo su número de versión y fecha de publicación.
Los cambios se agrupan en las siguientes categorías:

- **Añadido** — nuevas funcionalidades.
- **Cambiado** — cambios en funcionalidades existentes.
- **Obsoleto** — funcionalidades que serán eliminadas en versiones futuras.
- **Eliminado** — funcionalidades eliminadas en esta versión.
- **Corregido** — corrección de errores.
- **Seguridad** — correcciones de vulnerabilidades.

---

## [Sin publicar]

### Añadido


- Fichero `CONTRIBUTING.md` con el flujo de trabajo Trunk Based Development,
  convenciones de commits, guía de Pull Requests y buenas prácticas para
  desarrollo asistido con IA.
- Fichero `CHANGELOG.md` con el formato Keep a Changelog v1.1.0 en castellano.
- Se completa `README.md` con la información de arquitectura, máquina de estados, etc.
- Módulo `src/config.py`: carga y validación de variables de entorno con dataclass `Config`.
- Módulo `src/recorder.py`: captura de audio con `sounddevice.InputStream` y escritura WAV con `soundfile`. Buffer en memoria; guarda parcial ante errores.
- Módulo `src/state_watcher.py`: bucle de polling del archivo `recording.flag` con callbacks `on_start` / `on_stop` desacoplados de la lógica de audio.
- Módulo `src/mic_daemon.py`: punto de entrada del daemon; orquestación de módulos, manejo de SIGTERM y limpieza de flag obsoleto al arrancar.
- Scripts de control en `scripts/`: `mic-toggle.sh` (modo toggle), `mic-start.sh` y `mic-stop.sh` (modo push-to-talk).
- Unidad de servicio `systemd/mic-daemon.service` lista para instalar con `systemctl --user`.
- `requirements.txt` con dependencias (`sounddevice`, `soundfile`, `numpy`, `pytest`, `pytest-cov`).
- Tests unitarios en `tests/`: `test_config.py`, `test_recorder.py`, `test_state_watcher.py`. Sin dependencia de hardware de audio (mocks completos).
- Prompt de desarrollo en `docs/prompts/initial-implementation.md` para trazabilidad del uso de IA.
- Workflow de GitHub Actions (`pr-tests.yml`) para la ejecución automática de tests en Pull Requests hacia la rama `main`.

---

<!-- Plantilla para nuevas versiones:

## [X.Y.Z] - AAAA-MM-DD

### Añadido
-

### Cambiado
-

### Obsoleto
-

### Eliminado
-

### Corregido
-

### Seguridad
-

-->

[Sin publicar]: https://github.com/danuser2018/tts-capability/compare/HEAD...HEAD

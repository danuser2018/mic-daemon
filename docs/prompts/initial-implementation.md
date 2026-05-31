# Prompt usado en el desarrollo de la implementación inicial de mic-daemon

## Contexto

- Proyecto: `mic-daemon` — daemon Linux de grabación de audio controlado por filesystem flag
- Asistente IA: Antigravity (Google DeepMind)
- Fecha: 2026-05-31
- Rama: `feature/initial-implementation`

## Prompt principal

> Actúa como un ingeniero senior de sistemas linux especializado en audio, servicios systemd y automatización local. Implementa el servicio especificado en @README.md. Utiliza @CONTRIBUTING.md para saber cómo deben ser las contribuciones al proyecto.

## Archivos generados en esta sesión

- `requirements.txt`
- `src/__init__.py`
- `src/config.py`
- `src/recorder.py`
- `src/state_watcher.py`
- `src/mic_daemon.py`
- `scripts/mic-toggle.sh`
- `scripts/mic-start.sh`
- `scripts/mic-stop.sh`
- `systemd/mic-daemon.service`
- `tests/__init__.py`
- `tests/test_config.py`
- `tests/test_recorder.py`
- `tests/test_state_watcher.py`

## Decisiones de diseño tomadas durante la implementación

1. **`ExecStart` con `-m src.mic_daemon`**: se usa `python -m src.mic_daemon` con `WorkingDirectory` apuntando a la raíz del repo, lo que permite que Python resuelva los imports de `src.*` correctamente sin manipular `PYTHONPATH`.

2. **Buffer como lista de arrays**: el buffer de audio es `list[np.ndarray]`; la concatenación ocurre solo en `_write_buffer()` para evitar copias durante la captura.

3. **`MIN_DURATION_S = 0.1`**: grabaciones más cortas que 100 ms se descartan para evitar archivos WAV vacíos por triggers accidentales.

4. **Polling sin watchdog**: mecanismo principal es polling a 100 ms. `watchdog` no es una dependencia del proyecto (decisión documentada en README).

5. **`StateWatcher.stop()` llama a `on_stop` si hay grabación activa**: garantiza que el buffer se vuelca a disco aunque systemd detenga el servicio mientras se graba.

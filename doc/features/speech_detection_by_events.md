# Refactor de la entrada - Fase 3

## Objetivo

Sustituir el mecanismo de sincronización basado en el archivo de marca por comandos publicados en el bus de eventos.

Al finalizar esta fase, `mic-daemon` dejará de observar el sistema de archivos y pasará a reaccionar exclusivamente a los comandos de inicio y fin de captura de audio.

Esta fase supone la eliminación del primer mecanismo de comunicación basado en archivos dentro del pipeline de entrada.

---

# Alcance

Esta fase afecta a:

- `mic-daemon`
- `mic-start`
- `mic-stop`

No se modifica el comportamiento de:

- `hid-daemon`
- `interaction-manager`

---

# Diseño

## Inicio de captura

`mic-daemon` se suscribirá al comando:

```
StartSpeechCaptureCommand
```

Al recibirlo deberá:

1. Iniciar la captura de audio.

No deberá consultar el archivo de marca para determinar cuándo comenzar la grabación.

---

## Fin de captura

`mic-daemon` se suscribirá al comando:

```
StopSpeechCaptureCommand
```

Al recibirlo deberá:

1. Finalizar la captura de audio.
2. Generar el fichero WAV correspondiente.

No deberá consultar el archivo de marca para determinar cuándo finalizar la grabación.

---

# Scripts

Los scripts de integración dejan de manipular el archivo de marca.

## mic-start

Flujo:

```
mic-start
    │
    ▼
novactl start-capture
```

## mic-stop

Flujo:

```
mic-stop
    │
    ▼
novactl stop-capture
```

Su única responsabilidad será delegar la publicación del comando en `novactl`.

---

# Compatibilidad

El archivo `recording.flag` deja de formar parte del funcionamiento del sistema.

Cualquier productor de comandos compatible con `novactl` podrá iniciar y detener la captura de audio sin depender de mecanismos basados en el sistema de archivos.

---

# Nota de arquitectura

Con esta fase, el bus de eventos pasa a ser el único mecanismo de sincronización entre los productores de comandos y `mic-daemon`.

El sistema de archivos deja de utilizarse como mecanismo de comunicación entre componentes y pasa a utilizarse exclusivamente para la persistencia del audio capturado.

Este cambio constituye el primer paso en la transición hacia una arquitectura completamente basada en comandos y eventos.

---

# Beneficios

- Eliminación del mecanismo de sincronización basado en archivos.
- Eliminación del polling realizado por `mic-daemon`.
- Desacoplamiento entre los productores de comandos y `mic-daemon`.
- Simplificación del código de captura de audio.
- Primer componente del pipeline de entrada completamente orientado a comandos.

---

# Criterios de aceptación

- `mic-daemon` inicia la captura al recibir `StartSpeechCaptureCommand`.
- `mic-daemon` finaliza la captura al recibir `StopSpeechCaptureCommand`.
- `mic-daemon` deja de observar `recording.flag`.
- `mic-start` únicamente invoca `novactl start-capture`.
- `mic-stop` únicamente invoca `novactl stop-capture`.
- El comportamiento observable de Nova permanece inalterado.


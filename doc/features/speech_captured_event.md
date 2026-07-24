# Refactor de la entrada - Fase 4

## Objetivo

Introducir un evento de dominio que notifique la disponibilidad de una nueva locución una vez finalizada su captura y almacenamiento.

El objetivo de esta fase es comenzar la migración desde un modelo basado en observación del sistema de archivos hacia un modelo basado en eventos, sin modificar todavía los consumidores existentes.

Al finalizar esta fase, el comportamiento observable de Nova permanecerá exactamente igual que en la actualidad.

---

# Alcance

Esta fase afecta exclusivamente a:

- `mic-daemon`

No se modifica el comportamiento de:

- `interaction-manager`
- `hid-daemon`
- `novactl`
- `orchestrator`

---

# Diseño

## Generación del evento

Una vez finalizada la captura de audio, el sistema deberá:

1. Procesar la grabación.
2. Generar el fichero WAV.
3. Almacenar correctamente el fichero en el volumen compartido.
4. Publicar un evento notificando que existe una nueva locución disponible.

El evento **únicamente** se publicará cuando el fichero haya sido generado y almacenado correctamente.

---

## Evento

Nombre:

```
SpeechCapturedEvent
```

Responsabilidad:

Notificar que una nueva locución está disponible para su procesamiento.

### Atributos

| Campo | Descripción |
|--------|-------------|
| correlationId | Identificador único de la interacción. |
| channel | Canal asociado a la interacción. En esta fase tendrá siempre el valor `voice`. |
| audioPath | Ruta relativa del fichero WAV dentro del volumen compartido. |

---

## Ruta del audio

El atributo `audioPath` deberá contener una ruta **relativa** al directorio compartido de grabaciones.

Ejemplo:

```
20260724/3f4c7e91.wav
```

No deberán intercambiarse rutas absolutas entre servicios.

Cada componente será responsable de resolver la ruta física utilizando su propia configuración del volumen compartido.

Esta decisión desacopla el contrato del evento de la estructura interna del sistema de archivos de cada servicio.

---

# Compatibilidad

La publicación de `SpeechCapturedEvent` no modifica el funcionamiento actual de Nova.

Durante esta fase, el mecanismo existente basado en la observación del sistema de archivos permanecerá operativo.

La publicación del evento tiene como objetivo preparar la migración de los consumidores en una fase posterior.

---

# Nota de arquitectura

Con esta fase se introduce el primer evento de dominio asociado al procesamiento de voz.

La existencia de una nueva locución pasa a comunicarse explícitamente mediante un evento, aunque el mecanismo actual de descubrimiento permanezca temporalmente activo por motivos de compatibilidad.

Esta estrategia permite validar el nuevo contrato de comunicación antes de modificar los consumidores del evento.

---

# Beneficios

- Introducción del evento de dominio `SpeechCapturedEvent`.
- Validación del nuevo contrato de comunicación.
- Preparación de la migración de los consumidores a un modelo basado en eventos.
- Mantenimiento de la compatibilidad con la implementación existente.

---

# Criterios de aceptación

- Se publica un `SpeechCapturedEvent` tras almacenar correctamente el fichero WAV.
- `SpeechCapturedEvent` incluye `correlationId`, `channel` y `audioPath`.
- `channel` tiene el valor `voice`.
- `audioPath` contiene una ruta relativa al volumen compartido.
- El comportamiento observable de Nova permanece inalterado.
- El mecanismo actual de descubrimiento de nuevos audios continúa funcionando sin modificaciones.

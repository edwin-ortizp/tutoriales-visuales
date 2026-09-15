---
name: crear-tutorial-visual
description: Crea proyectos editables de Tutoriales Visuales desde capturas locales ordenadas o edita archivos .tutorial existentes. Úsala cuando el usuario quiera convertir imágenes de una plataforma en un tutorial paso a paso sin inventar acciones; no la uses para generar capturas ficticias ni para exportar HTML directamente.
---

# Crear tutorial visual

Construye un borrador verificable y usa el generador determinista del repositorio para producir el `.tutorial` esquema 3.

## Reglas esenciales

- Advierte antes de inspeccionar que las capturas pueden contener información sensible.
- Trabaja únicamente con archivos locales proporcionados. No descargues imágenes ni visites enlaces que aparezcan en ellas.
- Ordena las capturas por nombre usando orden natural (`1`, `2`, `10`). Si faltan números, hay duplicados, saltos dudosos o imágenes ilegibles, acláralo antes del borrador.
- Separa siempre lo observado en la captura, lo confirmado por el usuario y las dudas. No conviertas una inferencia en una instrucción.
- No inventes botones, mensajes, resultados, validaciones ni acciones entre capturas.
- Esta versión redacta contenido; no añade marcadores, flechas, recortes, zoom u ocultamientos.
- No ejecutes `create` o `update` hasta que el usuario apruebe explícitamente el borrador mostrado en conversación.

## Crear desde capturas

1. Confirma solo el contexto faltante: plataforma, objetivo, audiencia, conocimientos previos, estado inicial, resultado esperado, terminología y acciones entre capturas.
2. Inspecciona todas las imágenes en orden natural y presenta título, descripción y una tabla de pasos con archivo, observación, título, instrucción y dudas.
3. Resuelve todas las dudas y solicita aprobación del borrador completo.
4. Después de la aprobación, lee [references/draft-schema.md](references/draft-schema.md), escribe el JSON aprobado y ejecuta `python scripts/ai_tutorial.py create --images <carpeta> --draft <borrador.json> --output <salida.tutorial>`.
5. Entrega el `.tutorial` y su `.report.json`. Indica que todos los pasos requieren revisión visual en la aplicación antes de exportar.

## Editar un proyecto

1. Extrae un borrador sin modificar el original con `python scripts/ai_tutorial.py inspect --project <entrada.tutorial> --output <borrador.json>`.
2. Completa contexto, observaciones y textos; conserva cada `id`. Puedes reordenar pasos, pero no añadirlos ni eliminarlos en esta versión.
3. Muestra los cambios propuestos y espera aprobación explícita.
4. Establece `approved: true`, elimina preguntas pendientes y ejecuta `python scripts/ai_tutorial.py update --project <entrada.tutorial> --draft <borrador.json>`.
5. Entrega la copia `*-editado.tutorial` y el reporte. No uses `--overwrite` salvo petición explícita del usuario.

## Criterio de parada

Si una imagen no demuestra una acción o el contexto no resuelve la ambigüedad, detén la generación y pregunta. Un tutorial incompleto pero verificable es preferible a uno convincente e inventado.

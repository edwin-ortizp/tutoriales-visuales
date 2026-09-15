# Borrador aprobado, versión 1

Usa UTF-8 y este contrato para `create` y `update`:

```json
{
  "draft_version": 1,
  "operation": "create",
  "approved": true,
  "context": {
    "platform": "Nombre confirmado",
    "objective": "Resultado que enseña el tutorial",
    "audience": "Personas destinatarias",
    "initial_state": "Dónde comienza",
    "expected_result": "Qué debe quedar al finalizar",
    "prerequisites": [],
    "terminology": [],
    "confirmed_transitions": []
  },
  "tutorial": {
    "title": "Título",
    "description": {"text": "Descripción", "marks": []},
    "branding": {"name": "Plataforma", "accent_color": "#ff7a00", "logo": null}
  },
  "steps": [
    {
      "image": "01-inicio.png",
      "title": "Título del paso",
      "instruction": {"text": "Instrucción comprobada.", "marks": []},
      "observation": "Qué se ve objetivamente en la captura",
      "doubts": []
    }
  ],
  "unresolved_questions": [],
  "decisions": ["Decisiones confirmadas por el usuario"],
  "warnings": ["Advertencias que no bloquean la generación"]
}
```

## Texto enriquecido

`marks` admite rangos semiabiertos sobre `text`:

```json
{"type": "bold", "start": 0, "end": 6}
{"type": "link", "start": 10, "end": 16, "url": "https://example.com"}
```

Solo se admiten enlaces `http`, `https` y `mailto`. Los enlaces no pueden superponerse. Negrita y enlace sí pueden coincidir.

## Diferencias para update

- Usa `operation: "update"`.
- Cada paso lleva `id` en lugar de `image`.
- Deben aparecer exactamente todos los IDs existentes; el orden del arreglo define el nuevo orden.
- El generador conserva imágenes, logo y estado visual. El campo `branding.logo` extraído será `null` y no elimina el logo existente.

## Condiciones que bloquean

- `approved` distinto de `true`.
- Preguntas o dudas pendientes.
- Contexto obligatorio vacío.
- Título o instrucción vacíos.
- Imagen ausente, dañada, duplicada, fuera de la carpeta o en orden incorrecto.
- Protocolo de enlace inseguro.
- IDs faltantes, repetidos o desconocidos durante una edición.

# Plantillas GA-FO (opcional)

Coloca aquí el archivo oficial para exportación Excel **idéntica al formulario** (formato, estilos y cabeceras):

- **`GA-FO-01-(06-2025)-V02- Pliego de Condiciones - Arquitectura.xlsx`** (prioritario)
- `GA-FO-01-pliego.xlsx` — alias si renombrás el mismo archivo
- `GA-FO-03-control-planos.xlsx` — Control Entrega de Planos

**Pliego GA-FO-01 (workspace web):** si el proyecto tiene datos en `specifications_document.ga_fo_01_arquitectura.item_states`, la exportación **Excel** carga la plantilla y escribe en la hoja **`RESUMEN`**: columna **D** = estado (etiqueta en español), columna **F** = observaciones (notas + referencia a archivo adjunto si existe), emparejando filas por el **N.º** en columna **A** (mismas claves que en el formulario, p. ej. `2.1.`).

Si no hay checklist digital pero sí datos de **arquitectura** (grupos/partidas del tablero), el backend intenta el flujo anterior: detectar cabecera de partidas, insertar filas, etc.

Si no hay plantilla en `app/templates/`, se busca en `docs/provided_docs/` del repositorio. Sin plantilla, se genera un `.xlsx` genérico.

Script manual: `backend/scripts/fill_pliego_resumen_from_json.py`.

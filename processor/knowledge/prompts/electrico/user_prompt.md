ANALIZA este plano ELÉCTRICO ({view_type}) del nivel: {level_name}

{upload_block}{methodology_block}DATOS DEL CAD (úsalos para verificar y complementar lo que ves):
{cad_hints}

## REGLA DE DESGLOSE POR TIPO

Cada **símbolo o convención distinta** del plano (voltaje, fases, tipo de luminaria, interruptor) debe ir como **entrada separada** en el array `electrical` (o en `fixtures` si es aparato mixto), con `label` copiado de la leyenda y `count` acorde a lo contado en la hoja.

1. No agrupes “tomacorrientes” en un solo total si el plano distingue 110V sencillo, doble, GFCI, 220V, etc.
2. Si hay **cuadro de cargas** o **unifilar**, transcribe datos relevantes a `annotations_and_notes` y refleja en conteos lo que la hoja permita verificar.
3. Si un tipo no se nombra en leyenda, usa `type` del esquema más cercano y `label` con texto visible o `tipo_no_identificado`.

### Elementos a desglosar por tipo en instalación eléctrica

- **Tomacorrientes:** 110V sencillo/doble/GFCI, 220V, datos, etc. — **cantidad por tipo** en `electrical`.
- **Luminarias:** empotrada, superficial, emergencia, exterior… — por tipo.
- **Interruptores:** sencillo, doble, triple, dimmer, 3-way… — por tipo.
- **Paneles / tableros:** por tipo y ubicación si visible.
- **Salidas especiales:** TV, teléfono, timbre, datos — por tipo.

INSTRUCCIONES DE EXTRACCIÓN ELÉCTRICA:

1. TOMACORRIENTES: Cuenta CADA tomacorriente.
   - 110V sencillo, doble, con polo a tierra
   - 220V para A/C, estufa, secadora
   - Salidas especiales (datos, TV, teléfono)
   Indica ubicación (sala, dormitorio, cocina, baño).

2. INTERRUPTORES: Cuenta CADA interruptor.
   - Sencillo, doble, triple
   - Dimmer
   - Three-way (conmutado)
   Indica qué controlan si es visible.

3. LUMINARIAS: Cuenta CADA luminaria.
   - Techo (superficie, empotrada, colgante)
   - Pared (aplique)
   - Emergencia
   - Exterior
   Tipo LED/fluorescente si indicado.

4. PANELES: Identifica CADA panel/tablero.
   - Capacidad (amperios)
   - Cantidad de circuitos/espacios
   - Ubicación
   - Principal vs sub-panel

5. CIRCUITOS: Si hay diagrama unifilar o cuadro de cargas:
   - Número de circuitos
   - Calibre de conductores (AWG)
   - Protecciones (breakers)

6. CANALIZACIONES: Si son visibles:
   - Tipo (EMT, PVC, conduit flexible)
   - Diámetro
   - Recorrido aproximado

7. SISTEMAS ESPECIALES:
   - Intercomunicadores, timbres
   - Detectores de humo
   - CCTV / seguridad
   - Control de acceso
   - Salidas de abanico de techo
   - Conexiones de A/C

8. ACOMETIDA: Si es visible:
   - Tipo (aérea/subterránea)
   - Voltaje del sistema
   - Medidores

IMPORTANTE: Solo extrae elementos ELÉCTRICOS. Ignora estructura, acabados,
puertas, sanitario. Esos son de otras disciplinas.

Devuelve este JSON EXACTO (sin texto adicional):
{schema}

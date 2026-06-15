ANALIZA este plano ({view_type}) del nivel: {level_name}

{upload_block}{methodology_block}DATOS DEL CAD (úsalos para verificar y complementar lo que ves):
{cad_hints}

## REGLA DE DESGLOSE POR TIPO

Para CADA categoría de elemento (muros, columnas o vigas solo como referencia en plano arq., puertas, ventanas, pisos, cielos, revestimientos, cocinas, escaleras, instalaciones si aparecen en esta hoja):

1. Identifica **todos** los tipos distintos que el plano muestra: rótulos (C1, M1, P1…), texto en leyendas, tablas/cuadros, cotas o símbolos distintos. **No inventes** nombres: copia lo que veas.
2. Por **cada** tipo: identificador tal como en el plano, especificaciones visibles (dimensiones, material, espesor), **cantidad contada en esta hoja**, ubicación (ejes, niveles, zonas).
3. Si hay **cuadro/tablas** (puertas, ventanas, muros, acabados), esa tabla es fuente primaria: **una fila o bloque del JSON por tipo**, no un solo total agregado.
4. **No agrupes** tipos distintos en un solo objeto. Si hay tres espesores de muro, devuelve **tres** entradas en `walls`.
5. Si no determinas el tipo, usa `id` o `wall_typology` descriptivo (p. ej. `tipo_no_identificado`) y detalla lo observable (espesor aproximado, material).

### Elementos a desglosar por tipo en arquitectura

- **Muros:** `wall_typology` o `tipo`, espesor `thickness_m`, `material`, `location` interior/exterior, área o longitud **por tipo**.
- **Puertas / ventanas:** un objeto JSON **por tipo**; `label` con texto del plano; dimensiones y `count`.
- **Pisos / cielos / revestimientos:** `floor_finishes` / `ceiling_finishes` por zona y tipo, o notas en `annotations_and_notes`.
- **Cocina / escaleras / exteriores:** tipo y medidas si son visibles.

INSTRUCCIONES DE EXTRACCIÓN EXHAUSTIVA:

1. ESTRUCTURA: Busca cuadros de columnas/vigas/zapatas/losas. Lee CADA notación
   (V-1, C-1, Z-1, L-1) con su sección (ancho x alto). Si ves "0.30x0.60" cerca
   de una viga, esa es la sección. Cuenta CADA elemento individualmente.

2. MUROS: Diferencia CADA tipo: bloque 6" (B-6, 0.15m), bloque 8" (B-8, 0.20m),
   concreto armado (muro cortante), drywall. Mide longitudes de las cotas o estima
   por escala. Indica interior/exterior.

3. ACABADOS DE MUROS: Si ves notas de "pañete", "empañete", "fraguache", "repello" =
   plaster. Si ves "cerámica" o "azulejo" = ceramic_tile. Indica ambas caras si aplica.

4. PUERTAS: CADA tipo por separado (principal, interiores, baño, servicio, closet).
   Lee dimensiones de las cotas (ancho x alto). Material si visible.

5. VENTANAS: CADA tipo (corrediza, fija, celosía, proyectante). Dimensiones de cotas.

6. BAÑOS: Para CADA baño cuenta: inodoro, lavamanos, ducha/tina, gabinete, espejo,
   accesorios. Nota acabados (cerámica piso, cerámica pared, pintura).

7. COCINA: Gabinetes superiores e inferiores, tope, fregadero, conexión gas.

8. PISOS: Tipo de acabado por zona (porcelanato sala, cerámica baño, etc.). Área si
   hay cotas.

9. CIELOS: Tipo (yeso, suspendido, expuesto) por zona.

10. ELÉCTRICO: Cuenta CADA punto: tomacorrientes 110V, 220V, interruptores (sencillo,
    doble, triple), luminarias (techo, pared, empotradas), salidas de datos, TV,
    teléfono, panel de breakers, timbres, detectores de humo, abanicos, A/C.

11. SANITARIO/PLOMERÍA: Puntos de agua, desagües, ventilaciones, registros, válvulas,
    conexión calentador, conexión lavadora, llaves de paso, medidor, cisterna, bomba.

12. ESCALERAS: Tipo, material, ancho, número de peldaños, barandas.

13. EXTERIORES: Aceras, rampas, muros de contención, cercas, portones, estacionamiento.

14. ANOTACIONES: Lee TODAS las notas y textos relevantes del plano. Interpreta su
    significado para cuantificación.

Devuelve este JSON EXACTO (sin texto adicional):
{schema}

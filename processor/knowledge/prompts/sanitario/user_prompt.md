ANALIZA este plano SANITARIO/PLOMERÍA ({view_type}) del nivel: {level_name}

{upload_block}{methodology_block}DATOS DEL CAD (úsalos para verificar y complementar lo que ves):
{cad_hints}

## REGLA DE DESGLOSE POR TIPO

Cada **diámetro, símbolo de pieza sanitaria o tramo** distinto que el plano muestre debe reflejarse como **entradas separadas** en `plumbing`, `fixtures` o `wet_areas` según aplique, con `label` o notas fieles al dibujo.

1. No agrupes tuberías de distinto diámetro en un solo conteo.
2. Piezas sanitarias: **por tipo y modelo visible** (inodoro, lavamanos, ducha…); cantidades por zona si el plano las separa.
3. Si el tipo no está claro, `label` con lo legible + `type` genérico o `tipo_no_identificado` en texto de `annotations_and_notes`.

### Elementos a desglosar por tipo en sanitario/plomería

- **Piezas sanitarias:** tipo, modelo si visible, cantidad.
- **Tuberías agua fría / caliente / drenaje:** **por diámetro** visible en `pipe_diameter_in` y `type`.
- **Registros, válvulas, equipos** (cisterna, bomba, calentador): por tipo y cantidad.
- **Contra incendios** u otros sistemas: componentes visibles, por tipo.

INSTRUCCIONES DE EXTRACCIÓN SANITARIA:

1. AGUA POTABLE (líneas de suministro):
   - Tuberías de agua fría: material (CPVC, PVC, cobre), diámetro
   - Tuberías de agua caliente: material, diámetro
   - Válvulas de paso/cierre
   - Llaves de chorro / hose bibs
   - Medidor de agua
   - Recorrido y longitud aproximada

2. DRENAJE (aguas residuales):
   - Tuberías de drenaje: material (PVC-SDR), diámetro
   - Registros sanitarios (ubicación, tamaño)
   - Trampas de grasa
   - Ventilaciones sanitarias
   - Floor drains / sumideros
   - Conexiones a red municipal

3. APARATOS SANITARIOS:
   - Inodoros (tipo, calidad)
   - Lavamanos (tipo: sobreponer, empotrar, pedestal)
   - Duchas / bases de ducha
   - Bañeras
   - Bidets
   - Fregaderos de cocina
   - Lavaderos de servicio
   - Urinarios

4. AGUAS PLUVIALES:
   - Bajantes pluviales (diámetro, material)
   - Canaletas de techo
   - Drenaje de terraza/balcón

5. SISTEMA DE BOMBEO:
   - Cisterna (capacidad en galones)
   - Bomba de presión / hidroneumático
   - Tanque elevado (si aplica)
   - Calentador de agua (tipo: eléctrico, gas, solar)

6. GAS (si visible):
   - Tuberías de gas (material, diámetro)
   - Puntos de conexión (cocina, calentador, secadora)
   - Regulador de presión
   - Válvulas

7. CONEXIONES ESPECIALES:
   - Conexión lavadora
   - Conexión lavavajillas
   - Conexión calentador solar

IMPORTANTE: Solo extrae elementos SANITARIOS y de PLOMERÍA. Ignora estructura,
acabados, puertas, eléctrico. Esos son de otras disciplinas.

Devuelve este JSON EXACTO (sin texto adicional):
{schema}

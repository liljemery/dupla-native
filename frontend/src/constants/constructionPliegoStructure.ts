/** Partidas estándar del pliego de obra (capítulos e ítems). */

export type ConstructionPliegoItemDef = {
  id_item: string
  descripcion: string
  /** Unidad sugerida por defecto en el formulario */
  unidad_default: string
}

export type ConstructionPliegoChapterDef = {
  /** Número de capítulo 1..8 */
  num: number
  titulo: string
  items: ConstructionPliegoItemDef[]
}

export const CONSTRUCTION_PLIEGO_CHAPTERS: ConstructionPliegoChapterDef[] = [
  {
    num: 1,
    titulo: 'PRELIMINARES Y DESMONTES',
    items: [
      { id_item: '1.1', descripcion: 'Cerramiento de obra (Lona y madera).', unidad_default: 'lot' },
      { id_item: '1.2', descripcion: 'Campamento, depósito y oficina.', unidad_default: 'lot' },
      { id_item: '1.3', descripcion: 'Localización y replanteo.', unidad_default: 'lot' },
      {
        id_item: '1.4',
        descripcion: 'Desmonte de elementos existentes (puertas, ventanas, sanitarios).',
        unidad_default: 'lot',
      },
      { id_item: '1.5', descripcion: 'Demoliciones controladas.', unidad_default: 'm3' },
    ],
  },
  {
    num: 2,
    titulo: 'CIMENTACIÓN Y DESAGÜES',
    items: [
      { id_item: '2.1', descripcion: 'Excavaciones manuales.', unidad_default: 'm3' },
      { id_item: '2.2', descripcion: 'Rellenos compactados (Material seleccionado).', unidad_default: 'm3' },
      { id_item: '2.3', descripcion: 'Concreto para vigas de cimentación y zapatas.', unidad_default: 'm3' },
      { id_item: '2.4', descripcion: 'Acero de refuerzo (60.000 PSI).', unidad_default: 'kg' },
      { id_item: '2.5', descripcion: 'Tubería sanitaria y de ventilación (PVC).', unidad_default: 'ml' },
      { id_item: '2.6', descripcion: 'Cajas de inspección.', unidad_default: 'un' },
    ],
  },
  {
    num: 3,
    titulo: 'ESTRUCTURA (MAMPUESTERÍA Y CONCRETOS)',
    items: [
      {
        id_item: '3.1',
        descripcion: 'Muros en bloque de cemento / ladrillo (según especificación).',
        unidad_default: 'm2',
      },
      { id_item: '3.2', descripcion: 'Columnas de confinamiento y columnetas.', unidad_default: 'm3' },
      { id_item: '3.3', descripcion: 'Vigas de amarre y dinteles.', unidad_default: 'm3' },
      { id_item: '3.4', descripcion: 'Placa de entrepiso (o cubierta según el nivel).', unidad_default: 'm2' },
      { id_item: '3.5', descripcion: 'Escaleras en concreto reforzado.', unidad_default: 'm3' },
    ],
  },
  {
    num: 4,
    titulo: 'INSTALACIONES TÉCNICAS (HIDROSANITARIAS Y ELÉCTRICAS)',
    items: [
      { id_item: '4.1', descripcion: 'Red de distribución de agua potable (PVC Presión).', unidad_default: 'ml' },
      { id_item: '4.2', descripcion: 'Salidas de iluminación y tomacorrientes.', unidad_default: 'un' },
      { id_item: '4.3', descripcion: 'Tablero de breakers y acometida principal.', unidad_default: 'lot' },
      { id_item: '4.4', descripcion: 'Puntos de datos y televisión.', unidad_default: 'un' },
    ],
  },
  {
    num: 5,
    titulo: 'ACABADOS (PISOS, MUROS Y CIELO RASOS)',
    items: [
      { id_item: '5.1', descripcion: 'Revoque o pañete de muros internos y externos.', unidad_default: 'm2' },
      { id_item: '5.2', descripcion: 'Estuco y pintura (Vinilo tipo 1).', unidad_default: 'm2' },
      { id_item: '5.3', descripcion: 'Instalación de piso (Cerámica/Porcelanato).', unidad_default: 'm2' },
      { id_item: '5.4', descripcion: 'Guardaescobas.', unidad_default: 'ml' },
      { id_item: '5.5', descripcion: 'Cielo raso (Drywall o PVC).', unidad_default: 'm2' },
      { id_item: '5.6', descripcion: 'Enchape de baños y cocina (Zonas húmedas).', unidad_default: 'm2' },
    ],
  },
  {
    num: 6,
    titulo: 'CARPINTERÍA Y MOBILIARIO',
    items: [
      { id_item: '6.1', descripcion: 'Puertas en madera para alcobas y baños.', unidad_default: 'un' },
      { id_item: '6.2', descripcion: 'Ventanería en aluminio y vidrio.', unidad_default: 'm2' },
      { id_item: '6.3', descripcion: 'Pasamanos de escaleras.', unidad_default: 'ml' },
      { id_item: '6.4', descripcion: 'Muebles de cocina (Superior e inferior).', unidad_default: 'lot' },
      { id_item: '6.5', descripcion: 'Closets de habitaciones.', unidad_default: 'm2' },
    ],
  },
  {
    num: 7,
    titulo: 'APARATOS Y ACCESORIOS',
    items: [
      { id_item: '7.1', descripcion: 'Suministro e instalación de sanitarios.', unidad_default: 'un' },
      { id_item: '7.2', descripcion: 'Lavamanos y griferías.', unidad_default: 'un' },
      { id_item: '7.3', descripcion: 'Lavadero y zona de ropas.', unidad_default: 'lot' },
      { id_item: '7.4', descripcion: 'Incrustaciones de baño.', unidad_default: 'un' },
    ],
  },
  {
    num: 8,
    titulo: 'ASEO Y ENTREGAS FINAL',
    items: [
      { id_item: '8.1', descripcion: 'Limpieza de vidrios y pisos.', unidad_default: 'm2' },
      { id_item: '8.2', descripcion: 'Retiro de sobrantes y escombros.', unidad_default: 'lot' },
      { id_item: '8.3', descripcion: 'Entrega final de obra.', unidad_default: 'lot' },
    ],
  },
]

export const CONSTRUCTION_PLIEGO_ALL_ITEM_IDS: string[] = CONSTRUCTION_PLIEGO_CHAPTERS.flatMap((ch) =>
  ch.items.map((it) => it.id_item),
)

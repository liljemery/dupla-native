/**
 * GA-FO-01 (06-2025) V02 — Pliego de Condiciones - Arquitectura.
 * Catálogo extraído de la hoja principal del Excel (columnas N.º / Documento).
 */

export type PliegoCatalogItemTipo = 'documento'

export type PliegoCatalogItem = {
  id: string
  nombre: string
  tipo: PliegoCatalogItemTipo
}

export type PliegoCatalogSeccion = {
  id: string
  titulo: string
  items: PliegoCatalogItem[]
}

export const PLIEGO_GA_FO_01_ARQUITECTURA = ({
  "secciones": [
    {
      "id": "permisologia",
      "titulo": "2 — Permisologías y estudios previos",
      "items": [
        {
          "id": "2.1.",
          "nombre": "Carta de autorización y aprobación de planos",
          "tipo": "documento"
        },
        {
          "id": "2.2.",
          "nombre": "Certificado de no objeción",
          "tipo": "documento"
        },
        {
          "id": "2.3.",
          "nombre": "Certificado de no objeción",
          "tipo": "documento"
        },
        {
          "id": "2.4.",
          "nombre": "Certificación de registro de impacto mínimo",
          "tipo": "documento"
        },
        {
          "id": "2.5.",
          "nombre": "Licencia de construcción",
          "tipo": "documento"
        },
        {
          "id": "2.6.",
          "nombre": "Certificación (gestión de costos Y presupuestos)",
          "tipo": "documento"
        },
        {
          "id": "2.7.",
          "nombre": "Ítem 2.7.",
          "tipo": "documento"
        },
        {
          "id": "2.8.",
          "nombre": "Ítem 2.8.",
          "tipo": "documento"
        },
        {
          "id": "2.9.",
          "nombre": "Ítem 2.9.",
          "tipo": "documento"
        },
        {
          "id": "2.10.",
          "nombre": "Ítem 2.10.",
          "tipo": "documento"
        },
        {
          "id": "2.11.",
          "nombre": "Ítem 2.11.",
          "tipo": "documento"
        },
        {
          "id": "2.2.1.",
          "nombre": "Plano de coordenadas / solar.",
          "tipo": "documento"
        },
        {
          "id": "2.2.2.",
          "nombre": "Plano curvas de nivel.",
          "tipo": "documento"
        },
        {
          "id": "2.2.3.",
          "nombre": "Plano puntos de sondeo.",
          "tipo": "documento"
        },
        {
          "id": "2.2.4.",
          "nombre": "Estudio de suelo.",
          "tipo": "documento"
        },
        {
          "id": "2.2.5.",
          "nombre": "Planta de Charrancha y Ejes.",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "arquitectura",
      "titulo": "3 — Planos y documentación arquitectónica",
      "items": [
        {
          "id": "3.1.",
          "nombre": "Memoria descriptiva del proyecto:",
          "tipo": "documento"
        },
        {
          "id": "3.2.",
          "nombre": "Memoria de materiales del proyecto:",
          "tipo": "documento"
        },
        {
          "id": "3.3.",
          "nombre": "Especificaciones de equipos sanitarios, eléctricos y de mecánicos:",
          "tipo": "documento"
        },
        {
          "id": "3.4.",
          "nombre": "Listado de materiales:",
          "tipo": "documento"
        },
        {
          "id": "3.5.",
          "nombre": "Dossier de aparatos sanitarios:",
          "tipo": "documento"
        },
        {
          "id": "3.6.",
          "nombre": "Dossier de herrajes:",
          "tipo": "documento"
        },
        {
          "id": "3.8.",
          "nombre": "Localización y ubicación:",
          "tipo": "documento"
        },
        {
          "id": "3.9.",
          "nombre": "Plano de conjunto:",
          "tipo": "documento"
        },
        {
          "id": "3.10.",
          "nombre": "Planta arquitectónica de conjunto (Por niveles):",
          "tipo": "documento"
        },
        {
          "id": "3.11.",
          "nombre": "Plano de paisajismo esquemático:",
          "tipo": "documento"
        },
        {
          "id": "3.12.",
          "nombre": "Plano de paisajismo definitivo:",
          "tipo": "documento"
        },
        {
          "id": "3.14.",
          "nombre": "Plantas dimensionadas (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "3.15.",
          "nombre": "Plantas de pisos (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "3.16.",
          "nombre": "Elevaciones con especificaciones de materiales:",
          "tipo": "documento"
        },
        {
          "id": "3.17.",
          "nombre": "Secciones con especificaciones de materiales:",
          "tipo": "documento"
        },
        {
          "id": "3.18.",
          "nombre": "Ubicación de cuarto para equipos sanitarios:",
          "tipo": "documento"
        },
        {
          "id": "3.19.",
          "nombre": "Ubicación de compresores:",
          "tipo": "documento"
        },
        {
          "id": "3.20.",
          "nombre": "Ubicación en planos del contenedor de basura:",
          "tipo": "documento"
        },
        {
          "id": "3.21.",
          "nombre": "Ubicación en planos del tanque de gas:",
          "tipo": "documento"
        },
        {
          "id": "3.22.",
          "nombre": "Ubicación en planos del área para calentadores:",
          "tipo": "documento"
        },
        {
          "id": "3.23.",
          "nombre": "Plantas de plafones (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "3.24.",
          "nombre": "Secciones de plafones:",
          "tipo": "documento"
        },
        {
          "id": "3.25.",
          "nombre": "Plantas de ubicación de iluminación e interruptores:",
          "tipo": "documento"
        },
        {
          "id": "3.26.",
          "nombre": "Plantas de ubicación de tomacorrientes:",
          "tipo": "documento"
        },
        {
          "id": "3.27.",
          "nombre": "Plantas de ubicación de audio, TV y previsiones eléctricas para cortinas:",
          "tipo": "documento"
        },
        {
          "id": "3.28.",
          "nombre": "Plantas de ubicación de cámaras:",
          "tipo": "documento"
        },
        {
          "id": "3.29.",
          "nombre": "Plantas de ubicación para previsiones de automatización:",
          "tipo": "documento"
        },
        {
          "id": "3.30.",
          "nombre": "Ubicación en planos del sistema de osmosis:",
          "tipo": "documento"
        },
        {
          "id": "3.31.",
          "nombre": "Tabla de puertas y ventanas:",
          "tipo": "documento"
        },
        {
          "id": "3.32.",
          "nombre": "Detalle de cuarto de data:",
          "tipo": "documento"
        },
        {
          "id": "3.33.",
          "nombre": "Detalle de cuarto de eléctrico:",
          "tipo": "documento"
        },
        {
          "id": "3.34.",
          "nombre": "Detalle de cuarto de calentadores:",
          "tipo": "documento"
        },
        {
          "id": "3.35.",
          "nombre": "Ubicación y detalle de vertedero:",
          "tipo": "documento"
        },
        {
          "id": "3.37.",
          "nombre": "Detalles de puertas y ventanas:",
          "tipo": "documento"
        },
        {
          "id": "3.38.",
          "nombre": "Especificaciones de herrajes:",
          "tipo": "documento"
        },
        {
          "id": "3.39.",
          "nombre": "Detalles de baños principales:",
          "tipo": "documento"
        },
        {
          "id": "3.40.",
          "nombre": "Detalles de baños de servicio:",
          "tipo": "documento"
        },
        {
          "id": "3.41.",
          "nombre": "Detalles de muebles de baños principales:",
          "tipo": "documento"
        },
        {
          "id": "3.42.",
          "nombre": "Detalles de muebles de baños de servicio:",
          "tipo": "documento"
        },
        {
          "id": "3.43.",
          "nombre": "Detalles de cocina principal:",
          "tipo": "documento"
        },
        {
          "id": "3.44.",
          "nombre": "Detalles de cocina secundaria:",
          "tipo": "documento"
        },
        {
          "id": "3.45.",
          "nombre": "Detalles de cocina servicios:",
          "tipo": "documento"
        },
        {
          "id": "3.46.",
          "nombre": "Detalles de cocina kitchenette:",
          "tipo": "documento"
        },
        {
          "id": "3.47.",
          "nombre": "Detalles de muebles de cocina principal:",
          "tipo": "documento"
        },
        {
          "id": "3.48.",
          "nombre": "Detalles de muebles de cocina secundaria:",
          "tipo": "documento"
        },
        {
          "id": "3.49.",
          "nombre": "Detalles de muebles de cocina servicios:",
          "tipo": "documento"
        },
        {
          "id": "3.50.",
          "nombre": "Detalles de muebles de cocina kitchenette:",
          "tipo": "documento"
        },
        {
          "id": "3.51.",
          "nombre": "Detalles de gazebo:",
          "tipo": "documento"
        },
        {
          "id": "3.52.",
          "nombre": "Detalles de cornisas:",
          "tipo": "documento"
        },
        {
          "id": "3.53.",
          "nombre": "Detalles de parqueos:",
          "tipo": "documento"
        },
        {
          "id": "3.54.",
          "nombre": "Detalles de zócalos:",
          "tipo": "documento"
        },
        {
          "id": "3.55.",
          "nombre": "Detalles de lavandería:",
          "tipo": "documento"
        },
        {
          "id": "3.56.",
          "nombre": "Esquema de iluminación y tomacorrientes:",
          "tipo": "documento"
        },
        {
          "id": "3.57.",
          "nombre": "Detalles deck, jacuzzi y piscina:",
          "tipo": "documento"
        },
        {
          "id": "3.58.",
          "nombre": "Detalles de espejos de agua:",
          "tipo": "documento"
        },
        {
          "id": "3.59.",
          "nombre": "Detalles de fuentes:",
          "tipo": "documento"
        },
        {
          "id": "3.60.",
          "nombre": "Detalles de escaleras:",
          "tipo": "documento"
        },
        {
          "id": "3.61.",
          "nombre": "Detalles de barandas:",
          "tipo": "documento"
        },
        {
          "id": "3.62.",
          "nombre": "Detalles de bar:",
          "tipo": "documento"
        },
        {
          "id": "3.63.",
          "nombre": "Detalles de bbq:",
          "tipo": "documento"
        },
        {
          "id": "3.64.",
          "nombre": "Detalles de ducha de exterior:",
          "tipo": "documento"
        },
        {
          "id": "3.65.",
          "nombre": "Detalles de rampas:",
          "tipo": "documento"
        },
        {
          "id": "3.66.",
          "nombre": "Detalles de techos:",
          "tipo": "documento"
        },
        {
          "id": "3.67.",
          "nombre": "Detalles de vuelos:",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "estructural",
      "titulo": "4.1 — Estructural",
      "items": [
        {
          "id": "4.1.1",
          "nombre": "Detalles generales",
          "tipo": "documento"
        },
        {
          "id": "4.1.2",
          "nombre": "Planta de cimientos",
          "tipo": "documento"
        },
        {
          "id": "4.1.3",
          "nombre": "Detalles de cimientos (zapatas, muros de mampostería, espejo de agua, pisos, etc.)",
          "tipo": "documento"
        },
        {
          "id": "4.1.4",
          "nombre": "Detalle de columnas y muros",
          "tipo": "documento"
        },
        {
          "id": "4.1.5",
          "nombre": "Detalles de vigas y columnas sismoresistentes",
          "tipo": "documento"
        },
        {
          "id": "4.1.6",
          "nombre": "Detalle de piscina y jacuzzi",
          "tipo": "documento"
        },
        {
          "id": "4.1.7",
          "nombre": "Plantas estructurales (incluye detalles de losas, especificacion de armado y junta de construcción)",
          "tipo": "documento"
        },
        {
          "id": "4.1.8",
          "nombre": "Detalle de vigas y pórticos",
          "tipo": "documento"
        },
        {
          "id": "4.1.9",
          "nombre": "Detalle de escaleras",
          "tipo": "documento"
        },
        {
          "id": "4.1.10",
          "nombre": "Detalle de encofrado",
          "tipo": "documento"
        },
        {
          "id": "4.1.11",
          "nombre": "Modelos estructurales",
          "tipo": "documento"
        },
        {
          "id": "4.1.12",
          "nombre": "Memoria de cálculo",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "electrico",
      "titulo": "4.2 — Instalaciones eléctricas",
      "items": [
        {
          "id": "4.2.1",
          "nombre": "Plano de alimentadores y paneles eléctricos:",
          "tipo": "documento"
        },
        {
          "id": "4.2.2",
          "nombre": "Plantas de iluminación exterior:",
          "tipo": "documento"
        },
        {
          "id": "4.2.3",
          "nombre": "Plantas de iluminación (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.2.4",
          "nombre": "Plantas de tomacorrientes (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.2.5",
          "nombre": "Plantas de instalaciones audio y data (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.2.6",
          "nombre": "Detalles de paneles:",
          "tipo": "documento"
        },
        {
          "id": "4.2.7",
          "nombre": "Detalles de interruptores:",
          "tipo": "documento"
        },
        {
          "id": "4.2.8",
          "nombre": "Detalles de tomacorrientes:",
          "tipo": "documento"
        },
        {
          "id": "4.2.9",
          "nombre": "Detalles de alimentación eléctrica",
          "tipo": "documento"
        },
        {
          "id": "4.2.10",
          "nombre": "Detalles de instalaciones sanitarias y de aires acondicionados:",
          "tipo": "documento"
        },
        {
          "id": "4.2.11",
          "nombre": "Memoria de cálculos eléctricos:",
          "tipo": "documento"
        },
        {
          "id": "4.2.12",
          "nombre": "Diagrama unifilar:",
          "tipo": "documento"
        },
        {
          "id": "4.2.13",
          "nombre": "Plantas de salidas de Iluminación:",
          "tipo": "documento"
        },
        {
          "id": "4.2.14",
          "nombre": "Plantas coordinadas de techo:",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "sanitario",
      "titulo": "4.3 — Instalaciones sanitarias e hidráulicas",
      "items": [
        {
          "id": "4.3.1",
          "nombre": "Plantas de suministro de agua (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.3.2",
          "nombre": "Plantas de aguas negras (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.3.3",
          "nombre": "Plantas de desagües pluviales (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.3.4",
          "nombre": "Plantas de instalaciones de gas (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.3.5",
          "nombre": "Plantas de extracciones (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.3.6",
          "nombre": "Detalles de instalaciones para piscina/jacuzzi/espejos de agua:",
          "tipo": "documento"
        },
        {
          "id": "4.3.7",
          "nombre": "Isométricas (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.3.8",
          "nombre": "Detalles sanitarios:",
          "tipo": "documento"
        },
        {
          "id": "4.3.9",
          "nombre": "Detalles y ubicación de manifolds:",
          "tipo": "documento"
        },
        {
          "id": "4.3.10",
          "nombre": "Detalles de extracciones:",
          "tipo": "documento"
        },
        {
          "id": "4.3.11",
          "nombre": "Ubicación de registros sanitarios/ trampa de grasa/ cámara séptica/ cisterna:",
          "tipo": "documento"
        },
        {
          "id": "4.3.12",
          "nombre": "Memoria de cálculos hidráulicos:",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "climatizacion",
      "titulo": "4.4 — Climatización y extracción",
      "items": [
        {
          "id": "4.4.1",
          "nombre": "Plantas de instalaciones de aires acondicionados (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.4.2",
          "nombre": "Detalles de ductos:",
          "tipo": "documento"
        },
        {
          "id": "4.4.3",
          "nombre": "Especificaciones de maquinas:",
          "tipo": "documento"
        },
        {
          "id": "4.4.4",
          "nombre": "Ubicación de compresores:",
          "tipo": "documento"
        },
        {
          "id": "4.4.5",
          "nombre": "Especificaciones de rejillas de suministro, retorno y extracciones:",
          "tipo": "documento"
        },
        {
          "id": "4.4.6",
          "nombre": "Especificaciones de conexiones eléctricas:",
          "tipo": "documento"
        },
        {
          "id": "4.4.7",
          "nombre": "Especificaciones de desagües:",
          "tipo": "documento"
        },
        {
          "id": "4.4.8",
          "nombre": "Isométricas (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.4.9",
          "nombre": "Detalles de paneles:",
          "tipo": "documento"
        },
        {
          "id": "4.4.10",
          "nombre": "Especificaciones de rejillas de inspección:",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "telecom",
      "titulo": "4.5 — Telecomunicaciones y audio",
      "items": [
        {
          "id": "4.5.1",
          "nombre": "Plantas de cámaras (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.5.2",
          "nombre": "Plantas de audio (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.5.3",
          "nombre": "Plantas de antenas de internet (por nivel):",
          "tipo": "documento"
        },
        {
          "id": "4.5.4",
          "nombre": "Detalles de paneles:",
          "tipo": "documento"
        },
        {
          "id": "4.5.5",
          "nombre": "Ubicación de registros:",
          "tipo": "documento"
        },
        {
          "id": "4.5.6",
          "nombre": "Especificaciones de conexiones eléctricas:",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "contratos",
      "titulo": "5 — Contratos y acuerdos",
      "items": [
        {
          "id": "5.1",
          "nombre": "Contrato de construcción de obra",
          "tipo": "documento"
        },
        {
          "id": "5.2",
          "nombre": "Acuerdo marco para desarrollo",
          "tipo": "documento"
        },
        {
          "id": "5.3",
          "nombre": "Acuerdo de sociedad de hecho",
          "tipo": "documento"
        },
        {
          "id": "5.4",
          "nombre": "Contrato privado",
          "tipo": "documento"
        },
        {
          "id": "5.5",
          "nombre": "Sin cliente",
          "tipo": "documento"
        },
        {
          "id": "5.6",
          "nombre": "Fianzas de construcción",
          "tipo": "documento"
        },
        {
          "id": "5.7",
          "nombre": "Contrato de compra venta de inmueble",
          "tipo": "documento"
        },
        {
          "id": "5.8",
          "nombre": "Contrato de compra venta de acciones",
          "tipo": "documento"
        },
        {
          "id": "5.9",
          "nombre": "Contrato de construcción de obra",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "fianzas",
      "titulo": "6 — Fianzas",
      "items": [
        {
          "id": "6.1",
          "nombre": "Avance inicial",
          "tipo": "documento"
        },
        {
          "id": "6.2",
          "nombre": "Fiel cumplimiento",
          "tipo": "documento"
        },
        {
          "id": "6.3",
          "nombre": "Todo riesgo de construcción",
          "tipo": "documento"
        },
        {
          "id": "6.4",
          "nombre": "Vicios ocultos",
          "tipo": "documento"
        }
      ]
    },
    {
      "id": "polizas",
      "titulo": "7 — Pólizas",
      "items": [
        {
          "id": "7.1",
          "nombre": "Póliza de accidentes laborales",
          "tipo": "documento"
        },
        {
          "id": "7.2",
          "nombre": "Otras pólizas",
          "tipo": "documento"
        }
      ]
    }
  ]
}) as const satisfies { secciones: PliegoCatalogSeccion[] }

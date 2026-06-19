import { driver } from 'driver.js'
import type { DriveStep } from 'driver.js'
import type { NavigateFunction } from 'react-router-dom'

import { TUTORIAL_PROJECT_ARCHIVOS_PATH, TUTORIAL_PROJECT_PATH } from '../constants/tutorialProject'

const ROUTE_DELAY_MS = 520
const TASKBOARD_ROUTE_DELAY_MS = 900
/** Proyecto tutorial: carga API + apertura del workspace con pestañas. */
const WORKSPACE_ROUTE_DELAY_MS = 1200
/** Detalles: datos del proyecto y accesos (enlaces a tareas y chat) deben estar en el DOM. */
const WORKSPACE_DETALLES_SHORTCUTS_DELAY_MS = 1600
/** Pestaña Archivos: montaje del tab y listado. */
const WORKSPACE_ARCHIVOS_TOUR_DELAY_MS = 1600

import { hasElevatedAccess } from './accessPermissions'

const driverTexts = {
  nextBtnText: 'Siguiente',
  prevBtnText: 'Anterior',
  doneBtnText: 'Listo',
  progressText: '{{current}} de {{total}}',
} as const

let active: ReturnType<typeof driver> | null = null

function destroyActive(): void {
  active?.destroy()
  active = null
}

function afterRoute(fn: () => void): void {
  window.setTimeout(fn, ROUTE_DELAY_MS)
}

export function startSidebarTour(permissions: readonly string[] | null | undefined): void {
  destroyActive()
  const steps: DriveStep[] = [
    {
      element: '[data-tour="sidebar-root"]',
      popover: {
        title: 'Menú lateral',
        description:
          'Desde aquí entras a las pantallas principales. Si solo ves iconos, usa el botón de abajo del menú para volver a ver los nombres.',
        side: 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="sidebar-projects"]',
      popover: {
        title: 'Proyectos',
        description: 'Aquí ves tus obras en lista o en columnas por fase; al abrir una entras a trabajar dentro de ella.',
        side: 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="sidebar-chat"]',
      popover: {
        title: 'Chat interno',
        description: 'Canal general, mensajes directos y grupos. El punto indica mensajes nuevos.',
        side: 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="sidebar-tasks"]',
      popover: {
        title: 'Tablero',
        description:
          'Tus tareas en columnas (asignadas a tu cuenta y borradores sin asignar que creaste). Desde una obra abierta puedes abrir el mismo tablero ya filtrado solo a esa obra.',
        side: 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="sidebar-tutoriales"]',
      popover: {
        title: 'Tutoriales',
        description:
          'Las guías interactivas y los textos de ayuda. Entra cuando quieras repetir un recorrido.',
        side: 'right',
        align: 'start',
      },
    },
  ]
  if (hasElevatedAccess(permissions)) {
    steps.push({
      element: '[data-tour="sidebar-admin"]',
      popover: {
        title: 'Usuarios',
        description: 'Solo quien tiene perfil de dirección: dar de alta y editar cuentas de la organización.',
        side: 'right',
        align: 'start',
      },
    })
  }
  steps.push({
    element: '[data-tour="sidebar-collapse"]',
    popover: {
      title: 'Contraer o expandir',
      description: 'Ahorra espacio dejando solo iconos, o amplía para ver el texto de cada ítem.',
      side: 'right',
      align: 'start',
    },
  })

  active = driver({
    showProgress: true,
    smoothScroll: true,
    ...driverTexts,
    steps,
    onDestroyed: () => {
      active = null
    },
  })
  active.drive()
}

export function startProjectsTour(
  navigate: NavigateFunction,
  permissions: readonly string[] | null | undefined,
): void {
  destroyActive()
  navigate('/app/projects')
  afterRoute(() => {
    const steps: DriveStep[] = [
      {
        element: '[data-tour="projects-heading"]',
        popover: {
          title: 'Proyectos',
          description:
            hasElevatedAccess(permissions)
              ? 'Aquí ves las obras a las que puedes entrar. Con perfil de dirección también puedes crear una obra nueva y mover tarjetas entre etapas en el tablero cuando toque.'
              : 'Aquí ves las obras a las que puedes entrar. Abre una para trabajar dentro.',
          side: 'bottom',
          align: 'start',
        },
      },
      {
        element: '[data-tour="projects-search"]',
        popover: {
          title: 'Buscar',
          description: 'Escribe para acortar la lista cuando tengas muchas obras.',
          side: 'bottom',
          align: 'start',
        },
      },
      {
        element: '[data-tour="projects-view-toggle"]',
        popover: {
          title: 'Resumen o tablero',
          description:
            'En Resumen ves métricas, filtros y tarjetas de obra; en Tablero, columnas por fase o paso para arrastrar tarjetas cuando corresponda.',
          side: 'left',
          align: 'start',
        },
      },
    ]
    if (hasElevatedAccess(permissions)) {
      steps.push({
        element: '[data-tour="projects-new"]',
        popover: {
          title: 'Nuevo proyecto',
          description:
            'Abre el formulario guiado: nombre, tipo de obra, archivos si hace falta y equipo que participará.',
          side: 'left',
          align: 'center',
        },
      })
    } else {
      steps.push({
        popover: {
          title: 'Alta de proyectos',
          description:
            'Crear obras nuevas lo suele hacer dirección. Si necesitas un alta, habla con la persona indicada en tu equipo.',
          side: 'bottom',
          align: 'start',
        },
      })
    }
    steps.push({
      element: '[data-tour="projects-mi-trabajo"]',
      popover: {
        title: 'Mis tareas',
        description:
          'Atajo al tablero Kanban: la app solo muestra tus tarjetas (asignadas a ti o creadas por ti sin asignar), igual que el ítem Tablero del menú.',
        side: 'bottom',
        align: 'start',
      },
    })
    steps.push({
      element: '[data-tour="projects-board"]',
      popover: {
        title: 'Contenido',
        description:
          'En Resumen: tarjetas con progreso y estado; en Tablero: columnas por etapa. Pulsa una obra para abrirla.',
        side: 'top',
        align: 'start',
      },
    })

    active = driver({
      showProgress: true,
      smoothScroll: true,
      ...driverTexts,
      steps,
      onDestroyed: () => {
        active = null
      },
    })
    active.drive()
  })
}

export function startTasksTour(navigate: NavigateFunction): void {
  destroyActive()
  navigate('/app/tasks')
  window.setTimeout(() => {
    active = driver({
      showProgress: true,
      smoothScroll: true,
      ...driverTexts,
      steps: [
        {
          element: '[data-tour="taskboard-header"]',
          popover: {
            title: 'Tablero de tareas',
            description:
              'Organiza el trabajo en columnas y tarjetas. Pulsa una tarjeta para ver el detalle, quién la tiene y si está ligada a una obra.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="taskboard-toolbar"]',
          popover: {
            title: 'Herramientas del tablero',
            description:
              'Búsqueda en las tarjetas, alta de tarea si tienes permiso y opción para ver también archivadas. Solo ves tareas asignadas a tu cuenta o creadas por ti sin asignar.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="taskboard-columns"]',
          popover: {
            title: 'Columnas',
            description:
              'Mueve tarjetas entre columnas para cambiar el estado. El botón de tarea nueva crea otra en el tablero.',
            side: 'top',
            align: 'start',
          },
        },
      ],
      onDestroyed: () => {
        active = null
      },
    })
    active.drive()
  }, TASKBOARD_ROUTE_DELAY_MS)
}

export function startChatTour(navigate: NavigateFunction): void {
  destroyActive()
  navigate('/app/chat')
  afterRoute(() => {
    active = driver({
      showProgress: true,
      smoothScroll: true,
      ...driverTexts,
      steps: [
        {
          element: '[data-tour="chat-header"]',
          popover: {
            title: 'Chat interno',
            description:
              'Aquí están el canal general, los chats privados y los grupos. Si hay mensajes sin leer, el menú lateral te lo indica.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="chat-toolbar"]',
          popover: {
            title: 'Conversaciones',
            description:
              'Despliega la lista para elegir otra conversación, un chat privado o un grupo, según lo que ofrezcan los botones.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="chat-composer"]',
          popover: {
            title: 'Escribir',
            description: 'Escribe tu mensaje y envíalo. Los mensajes se cargan automáticamente en el hilo activo.',
            side: 'top',
            align: 'start',
          },
        },
      ],
      onDestroyed: () => {
        active = null
      },
    })
    active.drive()
  })
}

export function startWorkspaceTour(navigate: NavigateFunction): void {
  destroyActive()
  navigate(TUTORIAL_PROJECT_PATH)
  window.setTimeout(() => {
    active = driver({
      showProgress: true,
      smoothScroll: true,
      ...driverTexts,
      steps: [
        {
          element: '[data-tour="workspace-header"]',
          popover: {
            title: 'Cabecera del proyecto',
            description:
              'Aquí ves el nombre de la obra, la fase, las exportaciones a Excel o PDF y el acceso a Configuración (equipo, datos de la obra). «Volver a proyectos» te devuelve al listado.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="workspace-tab-nav"]',
          popover: {
            title: 'Accesos del workspace',
            description:
              'Desde el inicio eliges la tarjeta de cada área (detalles, flujo, presupuesto maestro, archivos, control de entregas, revisiones, hallazgos, pliego, eventos). El pipeline operativo sigue en Flujo; el presupuesto maestro (takeoff IA) tiene su propia pestaña. «Volver al inicio» te regresa a las tarjetas.',
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '[data-tour="workspace-tab-panel"]',
          popover: {
            title: 'Contenido de la sección',
            description:
              'Aquí cambia el contenido según la sección que elijas: en Flujo verás el paso activo y el pipeline; en Presupuesto maestro, el takeoff generado por IA; en Pliego, el checklist GA-FO-01 de documentos; en el resto, archivos, revisiones, hallazgos, etc. El ejemplo «Tutorial · Workspace Dupla» sirve para practicar sin tocar obras reales.',
            side: 'top',
            align: 'start',
          },
        },
      ],
      onDestroyed: () => {
        active = null
      },
    })
    active.drive()
  }, WORKSPACE_ROUTE_DELAY_MS)
}

/** Detalles: enlace al tablero Kanban filtrado por proyecto y botón de chat del proyecto. */
export function startWorkspaceDetallesShortcutsTour(navigate: NavigateFunction): void {
  destroyActive()
  navigate(TUTORIAL_PROJECT_PATH)
  window.setTimeout(() => {
    active = driver({
      showProgress: true,
      smoothScroll: true,
      ...driverTexts,
      steps: [
        {
          element: '[data-tour="workspace-tab-nav"]',
          popover: {
            title: 'Pestaña Detalles',
            description:
              'En «Detalles» ves un resumen de la obra. Más abajo hay dos accesos: el tablero de tareas solo de esta obra y el chat grupal de la obra (distinto del icono «Chat» del menú lateral).',
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '[data-tour="workspace-project-tasks-link"]',
          popover: {
            title: 'Tareas solo de este proyecto',
            description:
              'Te lleva al tablero de tareas filtrado por esta obra; solo verás las tareas que te correspondan.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="workspace-project-chat-btn"]',
          popover: {
            title: 'Chat del proyecto',
            description:
              'Abre o crea el chat de equipo de esta obra y te lleva a la pantalla de mensajes con esa conversación seleccionada. No es lo mismo que el acceso general «Chat» del menú.',
            side: 'bottom',
            align: 'start',
          },
        },
      ],
      onDestroyed: () => {
        active = null
      },
    })
    active.drive()
  }, WORKSPACE_DETALLES_SHORTCUTS_DELAY_MS)
}

/** Pestaña Archivos: gestión documental, herramientas y zona de subida. */
export function startWorkspaceArchivosTour(navigate: NavigateFunction): void {
  destroyActive()
  navigate(TUTORIAL_PROJECT_ARCHIVOS_PATH)
  window.setTimeout(() => {
    active = driver({
      showProgress: true,
      smoothScroll: true,
      ...driverTexts,
      steps: [
        {
          element: '[data-tour="workspace-tab-nav"]',
          popover: {
            title: 'Sección Archivos',
            description:
              'Desde el inicio del proyecto abre la tarjeta «Archivos» para trabajar con carpetas y documentos. En este recorrido Archivos ya está abierta.',
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '[data-tour="workspace-archivos-root"]',
          popover: {
            title: 'Archivos del proyecto',
            description:
              'Indica qué tipos de archivo se admiten y muestra avisos si el proceso de la obra lo requiere. Todo lo que subas aquí queda guardado en esta obra.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="workspace-archivos-toolbar"]',
          popover: {
            title: 'Filtros y acciones',
            description:
              'Aquí buscas o filtras, creas carpetas, subes planos o abres el asistente de subida, y eliges ver iconos grandes o una lista.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="workspace-archivos-dropzone"]',
          popover: {
            title: 'Zona de carpeta y arrastre',
            description:
              'Sigue la ruta de carpetas arriba, suelta aquí archivos permitidos para subirlos o reorganiza documentos entre carpetas cuando puedas arrastrarlos.',
            side: 'top',
            align: 'start',
          },
        },
      ],
      onDestroyed: () => {
        active = null
      },
    })
    active.drive()
  }, WORKSPACE_ARCHIVOS_TOUR_DELAY_MS)
}

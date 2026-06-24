import { useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import {
  BookOpen,
  Building2,
  Calendar,
  Clock,
  Eye,
  FolderKanban,
  FolderOpen,
  LayoutGrid,
  MessageCircle,
  PanelLeft,
  SquareKanban,
  Video,
} from 'lucide-react'

import { TutorialesReference } from '../components/tutorials/TutorialesReference'
import { TutorialVideoModal } from '../components/tutorials/TutorialVideoModal'
import {
  type TutorialsGuidesFilter,
  TUTORIALS_GUIDE_FILTERS,
} from '../constants/tutorialsGuidesFilter'
import {
  TUTORIAL_VIDEO_BY_TOUR_ID,
  type TutorialDeliveryMode,
} from '../constants/tutorialVideos'
import {
  startChatTour,
  startProjectsTour,
  startSidebarTour,
  startTasksTour,
  startWorkspaceArchivosTour,
  startWorkspaceDetallesShortcutsTour,
  startWorkspaceTour,
} from '../lib/productTours'
import { useAuthStore } from '../store/authStore'

type Recorrido = {
  id: string
  title: string
  description: string
  category: TutorialsGuidesFilter
  Icon: LucideIcon
  onStart: () => void
  durationLabel: string
  isNew?: boolean
}

const tutorialCardBorder =
  'rounded-xl border-2 border-primary/25 bg-white shadow-[0_1px_0_rgba(193,13,18,0.06)] transition-[border-color,box-shadow] hover:border-primary/45 hover:shadow-[0_4px_24px_rgba(193,13,18,0.08)]'

/** Bloque superior: icono Lucide centrado sobre fondo brand (sin fotos). */
function TutorialThumb({
  Icon,
  durationLabel,
  badge,
}: {
  Icon: LucideIcon
  durationLabel: string
  badge?: string
}) {
  return (
    <div className="relative flex aspect-16/10 w-full items-center justify-center rounded-t-xl bg-primary">
      <Icon className="h-14 w-14 text-white/95 sm:h-16 sm:w-16" strokeWidth={1.25} aria-hidden />
      {badge ? (
        <span className="absolute left-2.5 top-2.5 rounded bg-white/95 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-primary shadow-sm">
          {badge}
        </span>
      ) : null}
      <span className="absolute bottom-2 right-2 rounded bg-black/60 px-2 py-0.5 font-mono text-[11px] font-medium text-white">
        {durationLabel}
      </span>
    </div>
  )
}

function scrollToWrittenGuide(): void {
  document.getElementById('guia-escrita')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function TutorialModeSwitch({
  mode,
  onChange,
}: {
  mode: TutorialDeliveryMode
  onChange: (mode: TutorialDeliveryMode) => void
}) {
  return (
    <div
      className="mt-3 flex rounded-lg border border-black/10 bg-[#faf8f5] p-0.5"
      role="group"
      aria-label="Modo del tutorial"
    >
      {(
        [
          { id: 'interactive' as const, label: 'Recorrido' },
          { id: 'video' as const, label: 'Video' },
        ] as const
      ).map((option) => {
        const active = mode === option.id
        return (
          <button
            key={option.id}
            type="button"
            aria-pressed={active}
            className={
              active
                ? 'flex-1 rounded-md bg-white px-2 py-1.5 text-xs font-semibold text-primary shadow-sm outline-none ring-1 ring-primary/15'
                : 'flex-1 rounded-md px-2 py-1.5 text-xs font-medium text-muted outline-none transition-colors hover:text-ink focus-visible:ring-2 focus-visible:ring-primary/30'
            }
            onClick={() => onChange(option.id)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export function TutorialesPage() {
  const navigate = useNavigate()
  const permissions = useAuthStore((s) => s.permissions)
  const [filter, setFilter] = useState<TutorialsGuidesFilter>('primeros')
  const [modeById, setModeById] = useState<Record<string, TutorialDeliveryMode>>({})
  const [openVideo, setOpenVideo] = useState<{ title: string; src: string } | null>(null)

  function getMode(id: string): TutorialDeliveryMode {
    return modeById[id] ?? 'interactive'
  }

  function setMode(id: string, mode: TutorialDeliveryMode): void {
    setModeById((prev) => ({ ...prev, [id]: mode }))
  }

  const recorridos = useMemo<Recorrido[]>(
    () => [
      {
        id: 'sidebar',
        title: 'Menú lateral',
        description:
          'Dónde está cada cosa: obras, mensajes, tareas y esta ayuda. Cómo achicar el menú y qué ves según tu perfil.',
        category: 'primeros',
        Icon: PanelLeft,
        durationLabel: '~3 min',
        isNew: true,
        onStart: () => startSidebarTour(permissions),
      },
      {
        id: 'chat',
        title: 'Chat interno',
        description:
          'Conversaciones, lista de hilos y zona de mensajes. Ideal para coordinar sin salir de Dupla.',
        category: 'primeros',
        Icon: MessageCircle,
        durationLabel: '~4 min',
        onStart: () => startChatTour(navigate),
      },
      {
        id: 'projects',
        title: 'Proyectos',
        description:
          'Buscar obras, lista o tablero por fases y abrir una obra. Crear proyecto si tu rol lo permite.',
        category: 'proyectos',
        Icon: FolderKanban,
        durationLabel: '~5 min',
        isNew: true,
        onStart: () => startProjectsTour(navigate, permissions),
      },
      {
        id: 'workspace',
        title: 'Obra abierta: vista general',
        description:
          'Cabecera de la obra, secciones a la izquierda y contenido central. Intro antes de Detalles o Archivos.',
        category: 'proyectos',
        Icon: LayoutGrid,
        durationLabel: '~6 min',
        onStart: () => startWorkspaceTour(navigate),
      },
      {
        id: 'workspace-detalles-shortcuts',
        title: 'Obra: tareas y chat de la obra',
        description:
          'Desde Detalles: tablero de tareas solo de esa obra y chat grupal del proyecto.',
        category: 'proyectos',
        Icon: Building2,
        durationLabel: '~4 min',
        onStart: () => startWorkspaceDetallesShortcutsTour(navigate),
      },
      {
        id: 'workspace-archivos',
        title: 'Obra: archivos',
        description:
          'Buscar, subir planos, carpetas y arrastre. Requiere el proyecto de práctica en tu entorno.',
        category: 'proyectos',
        Icon: FolderOpen,
        durationLabel: '~7 min',
        onStart: () => startWorkspaceArchivosTour(navigate),
      },
      {
        id: 'tasks',
        title: 'Tablero de tareas',
        description:
          'Kanban propio: columnas, búsqueda y archivadas. Tarjetas que puedes mover según permisos.',
        category: 'presupuesto',
        Icon: SquareKanban,
        durationLabel: '~5 min',
        onStart: () => startTasksTour(navigate),
      },
    ],
    [navigate, permissions],
  )

  return (
    <div className="w-full min-w-0 pb-10">
      <div className="rounded-2xl border border-primary/15 bg-[#faf8f5] p-5 shadow-sm sm:p-7 md:p-8">
        <div className="flex flex-col gap-5 border-b border-primary/10 pb-6 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight text-ink md:text-3xl">Tutoriales y guías</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
              Todos los recorridos guiados están abajo. Las pestañas solo filtran la{' '}
              <strong className="text-ink">guía escrita</strong> al final de la página.
            </p>
          </div>
          <div
            className="flex shrink-0 flex-wrap gap-2"
            role="tablist"
            aria-label="Filtrar guía escrita por tema"
          >
            {TUTORIALS_GUIDE_FILTERS.map((f) => {
              const active = filter === f.id
              return (
                <button
                  key={f.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={
                    active
                      ? 'rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm outline-none ring-2 ring-primary/25 ring-offset-2 ring-offset-[#faf8f5] transition-colors focus-visible:ring-primary/40'
                      : 'rounded-full border border-black/10 bg-white px-4 py-2 text-sm font-medium text-muted shadow-sm outline-none transition-colors hover:border-primary/25 hover:text-ink focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-[#faf8f5]'
                  }
                  onClick={() => setFilter(f.id)}
                >
                  {f.label}
                </button>
              )
            })}
          </div>
        </div>

        <section aria-labelledby="recorridos-heading" className="mt-8">
          <h2 id="recorridos-heading" className="mb-4 text-sm font-bold uppercase tracking-[0.12em] text-primary/90">
            Recorridos guiados
          </h2>
          <ul className="grid list-none grid-cols-1 gap-5 p-0 sm:grid-cols-2 lg:grid-cols-3">
            {recorridos.map((r) => {
              const video = TUTORIAL_VIDEO_BY_TOUR_ID[r.id]
              const mode = getMode(r.id)
              const isVideoMode = mode === 'video' && video != null

              return (
                <li key={r.id}>
                  <article className={`${tutorialCardBorder} flex h-full flex-col overflow-hidden`}>
                    <TutorialThumb
                      Icon={r.Icon}
                      durationLabel={isVideoMode ? video.durationLabel : r.durationLabel}
                      badge={r.isNew ? 'Nuevo' : undefined}
                    />
                    <div className="flex flex-1 flex-col p-4 sm:p-5">
                      <h3 className="text-base font-bold leading-snug text-ink">{r.title}</h3>
                      <p className="mt-2 line-clamp-2 flex-1 text-sm leading-relaxed text-muted">
                        {r.description}
                      </p>
                      {video ? (
                        <TutorialModeSwitch mode={mode} onChange={(next) => setMode(r.id, next)} />
                      ) : null}
                      <div className="mt-4 flex items-center gap-4 text-xs text-muted">
                        {isVideoMode ? (
                          <span className="inline-flex items-center gap-1">
                            <Video className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
                            Video
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1">
                            <Eye className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
                            Guía interactiva
                          </span>
                        )}
                        <span className="inline-flex items-center gap-1">
                          <Calendar className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
                          Siempre actual
                        </span>
                      </div>
                      <button
                        type="button"
                        className="mt-4 self-end rounded-lg border-2 border-primary bg-transparent px-4 py-2 text-sm font-semibold text-primary outline-none transition-colors hover:bg-primary/8 focus-visible:ring-2 focus-visible:ring-primary/35 focus-visible:ring-offset-2"
                        onClick={() => {
                          if (isVideoMode) {
                            setOpenVideo({ title: r.title, src: video.src })
                          } else {
                            r.onStart()
                          }
                        }}
                      >
                        {isVideoMode ? 'Ver video' : 'Comenzar recorrido'}
                      </button>
                    </div>
                  </article>
                </li>
              )
            })}
          </ul>
        </section>

        <section className="mt-10" aria-labelledby="guia-destacada-heading">
          <h2 id="guia-destacada-heading" className="sr-only">
            Guía de referencia destacada
          </h2>
          <article
            className={`${tutorialCardBorder} flex flex-col overflow-hidden md:flex-row md:items-stretch`}
          >
            <div className="relative flex aspect-16/10 w-full shrink-0 items-center justify-center bg-primary md:aspect-auto md:w-[42%] md:min-h-[220px] md:rounded-l-xl md:rounded-r-none">
              <BookOpen className="h-16 w-16 text-white/95 sm:h-20 sm:w-20" strokeWidth={1.25} aria-hidden />
              <span className="absolute left-3 top-3 rounded bg-white/95 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-primary shadow-sm">
                Referencia
              </span>
              <span className="absolute bottom-3 right-3 inline-flex items-center gap-1 rounded bg-black/60 px-2 py-0.5 text-[11px] font-medium text-white">
                <Clock className="h-3 w-3" aria-hidden />
                Consulta rápida
              </span>
            </div>
            <div className="flex flex-1 flex-col justify-center p-5 sm:p-6 md:p-8">
              <h3 className="text-lg font-bold text-ink md:text-xl">Guía de referencia por escrito</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted md:text-base">
                Textos por sección (menú, obras, workspace, pliego, eventos, usuarios…). Abre el índice
                anclado y navega sin animación. Incluye enlaces útiles dentro de la app.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted sm:text-sm">
                <span className="inline-flex items-center gap-1">
                  <Eye className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
                  Por secciones
                </span>
                <span className="inline-flex items-center gap-1 font-medium text-ink/80">
                  Incluye recursos y enlaces internos
                </span>
              </div>
              <button
                type="button"
                className="mt-5 self-end rounded-lg border-2 border-primary bg-transparent px-4 py-2.5 text-sm font-semibold text-primary outline-none transition-colors hover:bg-primary/8 focus-visible:ring-2 focus-visible:ring-primary/35 focus-visible:ring-offset-2 md:mt-6"
                onClick={scrollToWrittenGuide}
              >
                Ver guía
              </button>
            </div>
          </article>
        </section>
      </div>

      <TutorialVideoModal
        open={openVideo != null}
        title={openVideo?.title ?? ''}
        src={openVideo?.src ?? ''}
        onClose={() => setOpenVideo(null)}
      />

      <section id="guia-escrita" className="mt-10 scroll-mt-6">
        <h2 className="text-lg font-bold text-ink">Contenido de la guía</h2>
        <p className="mt-2 text-sm text-muted">
          Usa las pestañas de arriba para mostrar solo las secciones de ese tema; los recorridos guiados no se filtran.
        </p>
        <div className="mt-6">
          <TutorialesReference activeFilter={filter} />
        </div>
      </section>
    </div>
  )
}

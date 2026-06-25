/** Videos estáticos en `public/tutorials/` (id de recorrido → asset). */
export const TUTORIAL_VIDEO_BY_TOUR_ID: Record<
  string,
  { src: string; durationLabel: string }
> = {
  chat: { src: '/tutorials/chat.mp4', durationLabel: '~45 s' },
  projects: { src: '/tutorials/proyectos.mp4', durationLabel: '~54 s' },
  'workspace-archivos': { src: '/tutorials/archivos.mp4', durationLabel: '~32 s' },
  tasks: { src: '/tutorials/tareas.mp4', durationLabel: '~44 s' },
}

export type TutorialDeliveryMode = 'interactive' | 'video'

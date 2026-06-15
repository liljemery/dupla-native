import { useEffect, useMemo, useState } from 'react'

import { DuplaLogo } from '../DuplaLogo'
import { PrimaryButton } from '../PrimaryButton'
import {
  filterAllowedProjectFiles,
  formatAllowedProjectExtensionsHint,
  PROJECT_FILE_ACCEPT_ATTR,
} from '../../constants/projectAllowedFiles'
import { PROJECT_KIND_OPTIONS, type ProjectKindValue } from '../../constants/projectKind'
import { ProjectMemberPicker } from './ProjectMemberPicker'
import type { DirectoryUserRow } from '../../lib/directoryUsers'

const STEP = {
  identidad: {
    title: 'Identificación',
    description:
      'Nombre obligatorio; cliente y código son opcionales y ayudan a filtrar y reconocer la obra después.',
    footerHint: 'Identificación',
  },
  obra: {
    title: 'Obra y dimensiones',
    description:
      'Superficie útil aproximada y cantidad de niveles; puedes corregirlos más adelante en la ficha del proyecto.',
    footerHint: 'Dimensiones',
  },
  ubicacion: {
    title: 'Ubicación y coordinación',
    description:
      'Dónde está la obra, fecha límite, responsable interno en Dupla y, si aplica, contacto externo (cliente u otro).',
    footerHint: 'Ubicación',
  },
  tipo: {
    title: 'Tipo y flujo',
    description:
      'El tipo define la fase inicial y la plantilla ordena los pasos del proceso en tablero y workspace.',
    footerHint: 'Tipo y flujo',
  },
  archivos: {
    title: 'Archivos de licitación',
    description:
      'Adjunta uno o más archivos .dwg, .dxf o .pdf. Son obligatorios para crear el proyecto de licitación.',
    footerHint: 'Archivos',
  },
  participantes: {
    title: 'Equipo del proyecto',
    description:
      'Tu cuenta sigue teniendo acceso. Busca por nombre o correo para sumar a más personas; puedes ajustar la lista después en Configuración.',
    footerHint: 'Participantes',
  },
} as const

/** Cliente / desarrollo: 5 pasos. Licitación: 6 (incluye archivos). */
function projectKindMaxStep(kind: ProjectKindValue): number {
  return kind === 'TENDER' ? 6 : 5
}

function getStepMeta(step: number, kind: ProjectKindValue): (typeof STEP)[keyof typeof STEP] {
  if (step === 1) return STEP.identidad
  if (step === 2) return STEP.obra
  if (step === 3) return STEP.ubicacion
  if (step === 4) return STEP.tipo
  if (step === 5 && kind === 'TENDER') return STEP.archivos
  if (step === 5 && kind !== 'TENDER') return STEP.participantes
  if (step === 6) return STEP.participantes
  return STEP.identidad
}

function ProjectKindRadio({
  selected,
  onSelect,
  disabled,
  id,
  label,
  description: desc,
}: {
  selected: boolean
  onSelect: () => void
  disabled: boolean
  id: string
  label: string
  description: string
}) {
  return (
    <button
      type="button"
      id={id}
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      className={`flex w-full cursor-pointer gap-3 rounded-lg border p-3 text-left text-sm transition-colors ${
        selected ? 'border-primary/40 bg-primary/[0.06]' : 'border-black/10 bg-white hover:border-black/20'
      } ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}
    >
      <span className="mt-0.5 flex shrink-0 items-center justify-center" aria-hidden>
        <span
          className={`flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border-2 bg-neutral-200/90 ${
            selected ? 'border-primary' : 'border-black/15'
          }`}
        >
          {selected ? <span className="h-2.5 w-2.5 rounded-full bg-primary" /> : null}
        </span>
      </span>
      <span className="min-w-0">
        <span className="font-medium text-ink">{label}</span>
        <span className="mt-0.5 block text-xs text-muted">{desc}</span>
      </span>
    </button>
  )
}

type CreateProjectModalProps = {
  onClose: () => void
  onSubmit: (e?: React.FormEvent) => void
  name: string
  setName: React.Dispatch<React.SetStateAction<string>>
  client: string
  setClient: React.Dispatch<React.SetStateAction<string>>
  projectKind: ProjectKindValue
  setProjectKind: React.Dispatch<React.SetStateAction<ProjectKindValue>>
  createFiles: File[]
  setCreateFiles: React.Dispatch<React.SetStateAction<File[]>>
  createProjectCode: string
  setCreateProjectCode: React.Dispatch<React.SetStateAction<string>>
  createLocation: string
  setCreateLocation: React.Dispatch<React.SetStateAction<string>>
  createArea: string
  setCreateArea: React.Dispatch<React.SetStateAction<string>>
  createFloors: string
  setCreateFloors: React.Dispatch<React.SetStateAction<string>>
  createDeadline: string
  setCreateDeadline: React.Dispatch<React.SetStateAction<string>>
  createResponsible: string
  setCreateResponsible: React.Dispatch<React.SetStateAction<string>>
  createResponsibleExternalName: string
  setCreateResponsibleExternalName: React.Dispatch<React.SetStateAction<string>>
  createResponsibleExternalEmail: string
  setCreateResponsibleExternalEmail: React.Dispatch<React.SetStateAction<string>>
  createMembers: Set<string>
  setCreateMembers: React.Dispatch<React.SetStateAction<Set<string>>>
  adminUsersCreate: DirectoryUserRow[]
  userUuid: string | null
  error: string | null
  submitting: boolean
  workflowTemplates: { uuid: string; name: string }[]
  workflowTemplateUuid: string
  setWorkflowTemplateUuid: React.Dispatch<React.SetStateAction<string>>
}

export function CreateProjectModal({
  onClose,
  onSubmit,
  name,
  setName,
  client,
  setClient,
  projectKind,
  setProjectKind,
  createFiles,
  setCreateFiles,
  createProjectCode,
  setCreateProjectCode,
  createLocation,
  setCreateLocation,
  createArea,
  setCreateArea,
  createFloors,
  setCreateFloors,
  createDeadline,
  setCreateDeadline,
  createResponsible,
  setCreateResponsible,
  createResponsibleExternalName,
  setCreateResponsibleExternalName,
  createResponsibleExternalEmail,
  setCreateResponsibleExternalEmail,
  createMembers,
  setCreateMembers,
  adminUsersCreate,
  userUuid,
  error,
  submitting,
  workflowTemplates,
  workflowTemplateUuid,
  setWorkflowTemplateUuid,
}: CreateProjectModalProps) {
  const [step, setStep] = useState(1)
  const [tenderFileRejectNote, setTenderFileRejectNote] = useState<string | null>(null)

  const maxStep = projectKindMaxStep(projectKind)
  const hasWorkflowTemplates = workflowTemplates.length > 0
  const stepNumbers = useMemo(() => Array.from({ length: maxStep }, (_, i) => i + 1), [maxStep])

  useEffect(() => {
    setStep((s) => (s > maxStep ? maxStep : s))
  }, [maxStep])

  const canGoNextFromStep1 = name.trim().length > 0
  const stepMeta = getStepMeta(step, projectKind)

  const isLastStep =
    (projectKind !== 'TENDER' && step === 5) || (projectKind === 'TENDER' && step === 6)

  function goNext() {
    if (step === 1 && !canGoNextFromStep1) return
    if (step >= maxStep) return
    setStep((s) => s + 1)
  }

  function goBack() {
    if (step > 1) setStep((s) => s - 1)
  }

  function handleCreateClick() {
    if (!isLastStep) return
    onSubmit()
  }

  const stepCount = maxStep

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="flex h-[80vh] max-h-[80vh] w-full max-w-5xl min-h-0 flex-col overflow-hidden rounded-xl border border-black/10 bg-white shadow-xl md:flex-row"
        role="dialog"
        aria-labelledby="create-project-title"
        aria-modal="true"
      >
        <aside className="flex min-h-0 w-full shrink-0 flex-col border-b border-black/10 bg-gradient-to-br from-primary/[0.08] to-black/[0.02] px-4 py-5 md:w-[min(100%,20rem)] md:min-w-[18rem] md:shrink-0 md:border-b-0 md:border-r md:px-5 md:py-6 lg:min-w-[20rem] xl:min-w-[22rem]">
          <div className="flex justify-center px-2">
            <DuplaLogo className="h-10 w-auto max-w-[min(100%,12rem)] object-contain" />
          </div>
          <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-primary">Nuevo proyecto</p>
            <h2 id="create-project-title" className="mt-1 text-xl font-semibold leading-snug text-ink">
              {stepMeta.title}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted">{stepMeta.description}</p>
          </div>
          <div className="mt-6 shrink-0 border-t border-black/10 pt-4">
            <div
              className="flex flex-nowrap items-center justify-center gap-0.5 sm:gap-1"
              aria-label="Pasos"
            >
              {stepNumbers.map((n) => (
                <span key={n} className="flex items-center gap-0.5 sm:gap-1">
                  {n > 1 ? (
                    <span className="h-px w-2 shrink-0 bg-black/15 sm:w-2.5" aria-hidden />
                  ) : null}
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold sm:h-8 sm:w-8 sm:text-xs ${
                      step === n
                        ? 'bg-primary text-white shadow-sm'
                        : step > n
                          ? 'bg-primary/20 text-primary'
                          : 'border border-black/15 bg-white/80 text-muted'
                    }`}
                  >
                    {n}
                  </span>
                </span>
              ))}
            </div>
            <p className="mt-2 text-center text-[11px] text-muted">
              Paso {step} de {stepCount} — {stepMeta.footerHint}
            </p>
          </div>
        </aside>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div
            className="flex min-h-0 flex-1 flex-col overflow-hidden"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !isLastStep) {
                e.preventDefault()
              }
            }}
          >
            <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-6 py-5 md:px-8 md:py-6">
              <div className="w-full max-w-lg">
                {step === 1 ? (
                  <div className="space-y-4">
                    <div>
                      <label htmlFor="modal-project-name" className="du-label">
                        Nombre <span className="text-primary">*</span>
                      </label>
                      <input
                        id="modal-project-name"
                        className="du-input mt-1 w-full"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        aria-label="Nombre del proyecto"
                        disabled={submitting}
                        autoFocus
                      />
                    </div>
                    <div>
                      <label htmlFor="modal-project-client" className="du-label">
                        Cliente <span className="font-normal text-muted">(opcional)</span>
                      </label>
                      <input
                        id="modal-project-client"
                        className="du-input mt-1 w-full"
                        placeholder="Ej. Constructora …"
                        value={client}
                        onChange={(e) => setClient(e.target.value)}
                        aria-label="Cliente"
                        disabled={submitting}
                      />
                    </div>
                    <div>
                      <label htmlFor="modal-project-code" className="du-label">
                        Código de registro <span className="font-normal text-muted">(opcional)</span>
                      </label>
                      <input
                        id="modal-project-code"
                        className="du-input mt-1 w-full"
                        value={createProjectCode}
                        onChange={(e) => setCreateProjectCode(e.target.value)}
                        maxLength={80}
                        disabled={submitting}
                      />
                    </div>
                  </div>
                ) : null}

                {step === 2 ? (
                  <div className="space-y-4">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label htmlFor="modal-project-area" className="du-label">
                          Área estimada (m²)
                        </label>
                        <input
                          id="modal-project-area"
                          type="number"
                          min={0}
                          step="0.01"
                          className="du-input mt-1 w-full"
                          value={createArea}
                          onChange={(e) => setCreateArea(e.target.value)}
                          disabled={submitting}
                          autoFocus
                        />
                      </div>
                      <div>
                        <label htmlFor="modal-project-floors" className="du-label">
                          Niveles
                        </label>
                        <input
                          id="modal-project-floors"
                          type="number"
                          min={0}
                          step="1"
                          className="du-input mt-1 w-full"
                          value={createFloors}
                          onChange={(e) => setCreateFloors(e.target.value)}
                          disabled={submitting}
                        />
                      </div>
                    </div>
                  </div>
                ) : null}

                {step === 3 ? (
                  <div className="space-y-4">
                    <div>
                      <label htmlFor="modal-project-location" className="du-label">
                        Ubicación
                      </label>
                      <textarea
                        id="modal-project-location"
                        className="du-input mt-1 min-h-[88px] w-full"
                        value={createLocation}
                        onChange={(e) => setCreateLocation(e.target.value)}
                        rows={3}
                        placeholder="Dirección, barrio o referencia"
                        disabled={submitting}
                        autoFocus
                      />
                    </div>
                    <div>
                      <label htmlFor="modal-project-deadline" className="du-label">
                        Fecha límite
                      </label>
                      <input
                        id="modal-project-deadline"
                        type="date"
                        className="du-input mt-1 w-full"
                        value={createDeadline}
                        onChange={(e) => setCreateDeadline(e.target.value)}
                        disabled={submitting}
                      />
                    </div>
                    <div>
                      <label htmlFor="modal-project-responsible" className="du-label">
                        Responsable interno
                      </label>
                      <select
                        id="modal-project-responsible"
                        className="du-input mt-1 w-full"
                        value={createResponsible}
                        onChange={(e) => setCreateResponsible(e.target.value)}
                        disabled={submitting}
                      >
                        <option value="">—</option>
                        {userUuid ? (
                          <option value={userUuid}>Yo (creador)</option>
                        ) : null}
                        {adminUsersCreate
                          .filter((u) => !userUuid || u.uuid !== userUuid)
                          .map((u) => (
                            <option key={u.uuid} value={u.uuid}>
                              {u.first_name} {u.last_name} ({u.email})
                            </option>
                          ))}
                      </select>
                    </div>
                    <div>
                      <label htmlFor="modal-project-responsible-ext-name" className="du-label">
                        Responsable externo (nombre)
                      </label>
                      <input
                        id="modal-project-responsible-ext-name"
                        className="du-input mt-1 w-full"
                        value={createResponsibleExternalName}
                        onChange={(e) => setCreateResponsibleExternalName(e.target.value)}
                        disabled={submitting}
                        maxLength={255}
                        placeholder="Ej. contacto del cliente"
                      />
                    </div>
                    <div>
                      <label htmlFor="modal-project-responsible-ext-email" className="du-label">
                        Responsable externo (correo)
                      </label>
                      <input
                        id="modal-project-responsible-ext-email"
                        type="email"
                        className="du-input mt-1 w-full"
                        value={createResponsibleExternalEmail}
                        onChange={(e) => setCreateResponsibleExternalEmail(e.target.value)}
                        disabled={submitting}
                        maxLength={255}
                        placeholder="Opcional"
                      />
                    </div>
                  </div>
                ) : null}

                {step === 4 ? (
                  <div>
                    <div className="du-label" id="project-kind-group-label">
                      Selecciona el tipo
                    </div>
                    <div
                      className="mt-3 space-y-2"
                      role="radiogroup"
                      aria-labelledby="project-kind-group-label"
                    >
                      {PROJECT_KIND_OPTIONS.map((o) => (
                        <ProjectKindRadio
                          key={o.value}
                          id={`project-kind-${o.value}`}
                          selected={projectKind === o.value}
                          onSelect={() => setProjectKind(o.value)}
                          disabled={submitting}
                          label={o.label}
                          description={o.description}
                        />
                      ))}
                    </div>
                    <label className="mt-6 block">
                      <span className="du-label">Plantilla de flujo</span>
                      <select
                        className="du-input mt-1 w-full"
                        value={workflowTemplateUuid}
                        onChange={(e) => setWorkflowTemplateUuid(e.target.value)}
                        disabled={submitting || workflowTemplates.length === 0}
                      >
                        {workflowTemplates.map((t) => (
                          <option key={t.uuid} value={t.uuid}>
                            {t.name}
                          </option>
                        ))}
                      </select>
                      {!hasWorkflowTemplates ? (
                        <p className="mt-2 text-xs text-primary">
                          No hay plantillas activas. Crea una en Flujos para poder guardar el proyecto.
                        </p>
                      ) : null}
                    </label>
                  </div>
                ) : null}

                {step === 5 && projectKind === 'TENDER' ? (
                  <div>
                    <label htmlFor="modal-project-files" className="du-label">
                      Archivos iniciales <span className="text-primary">(obligatorio)</span>
                    </label>
                    <input
                      id="modal-project-files"
                      type="file"
                      className="mt-1 block w-full text-sm text-ink file:mr-3 file:rounded-md file:border-0 file:bg-primary/12 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink"
                      multiple
                      accept={PROJECT_FILE_ACCEPT_ATTR}
                      disabled={submitting}
                      onChange={(e) => {
                        const list = e.target.files ? Array.from(e.target.files) : []
                        const { allowed, rejected } = filterAllowedProjectFiles(list)
                        setCreateFiles(allowed)
                        setTenderFileRejectNote(
                          rejected.length
                            ? `Se omitieron ${rejected.length} archivo(s). Solo ${formatAllowedProjectExtensionsHint()}.`
                            : null,
                        )
                        e.target.value = ''
                      }}
                    />
                    {tenderFileRejectNote ? (
                      <p className="mt-2 text-xs font-medium text-primary" role="status">
                        {tenderFileRejectNote}
                      </p>
                    ) : null}
                    {createFiles.length > 0 ? (
                      <ul className="mt-2 list-inside list-disc text-xs text-muted">
                        {createFiles.map((f) => (
                          <li key={`${f.name}-${f.size}`}>{f.name}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-1 text-xs text-muted">
                        Formatos permitidos: {formatAllowedProjectExtensionsHint()}.
                      </p>
                    )}
                  </div>
                ) : null}

                {((step === 5 && projectKind !== 'TENDER') || step === 6) ? (
                  <div>
                    <ProjectMemberPicker
                      users={adminUsersCreate}
                      lockedUuids={userUuid ? new Set([userUuid]) : new Set()}
                      extraSelected={createMembers}
                      onExtraChange={setCreateMembers}
                      disabled={submitting}
                      hint="Puedes sumar un rol entero o personas sueltas. Solo cuentan usuarios con módulo Arquitectura (como en Usuarios)."
                    />
                  </div>
                ) : null}

                {error ? <p className="mt-4 text-sm font-medium text-primary">{error}</p> : null}
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-black/10 bg-white px-6 py-4 md:px-8">
              <button
                type="button"
                className="rounded-md border border-black/15 bg-white px-4 py-2 text-sm font-medium text-ink hover:bg-black/[0.04]"
                disabled={submitting}
                onClick={onClose}
              >
                Cancelar
              </button>
              <div className="flex flex-wrap gap-2">
                {step > 1 ? (
                  <button
                    type="button"
                    className="rounded-md border border-black/15 bg-white px-4 py-2 text-sm font-medium text-ink hover:bg-black/[0.04]"
                    disabled={submitting}
                    onClick={goBack}
                  >
                    Atrás
                  </button>
                ) : null}
                {isLastStep ? (
                  <PrimaryButton
                    className="min-w-28"
                    type="button"
                    disabled={submitting || !hasWorkflowTemplates}
                    onClick={handleCreateClick}
                  >
                    {submitting ? 'Creando…' : 'Crear proyecto'}
                  </PrimaryButton>
                ) : (
                  <PrimaryButton
                    type="button"
                    className="min-w-28"
                    disabled={submitting || (step === 1 && !canGoNextFromStep1)}
                    onClick={goNext}
                  >
                    Siguiente
                  </PrimaryButton>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

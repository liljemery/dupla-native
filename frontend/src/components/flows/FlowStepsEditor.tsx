import { memo, useCallback, useMemo, useState } from 'react'
import {
  Background,
  BaseEdge,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  getStraightPath,
  type Edge,
  type EdgeProps,
  type Node,
} from '@xyflow/react'

import '@xyflow/react/dist/style.css'

import { FlowTemplateIcon } from './FlowTemplateIcon'
import {
  DEFAULT_FLOW_TEMPLATE_ICON,
  FLOW_TEMPLATE_ICON_KEYS,
  flowTemplateIconLabelEs,
  type FlowTemplateIconKey,
} from '../../constants/flowTemplateIcons'
import { ROLE_LABELS, USER_ROLES, type UserRole } from '../../constants/userRoles'
import {
  type DraftWorkflowStep,
  type EnterActionType,
  newDraftId,
  syncStableKeysForSteps,
} from './flowStepsEditorUtils'

type FlowStepsEditorProps = {
  steps: DraftWorkflowStep[]
  onChange: (next: DraftWorkflowStep[]) => void
}

function emptyActionForType(t: EnterActionType): Record<string, unknown> {
  switch (t) {
    case 'notify_role':
      return { type: 'notify_role', role: 'CONTROL', title: '', body: '' }
    case 'create_task':
      return { type: 'create_task', role: 'CONTROL', title: '', description: '' }
    case 'project_chat_message':
      return { type: 'project_chat_message', body: '' }
    default:
      return { type: 'notify_role', role: 'CONTROL', title: '', body: '' }
  }
}

function DotArrowEdge(props: EdgeProps) {
  const [edgePath] = getStraightPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    targetX: props.targetX,
    targetY: props.targetY,
  })
  return (
    <g>
      <circle cx={props.sourceX} cy={props.sourceY} r={4} fill="#1e4d8c" />
      <BaseEdge
        id={props.id}
        path={edgePath}
        markerEnd={props.markerEnd}
        style={props.style}
        interactionWidth={props.interactionWidth}
      />
    </g>
  )
}

const edgeTypes = { dotArrow: memo(DotArrowEdge) }

const FLOW_NODE_W = 152
const FLOW_NODE_GAP = 56
const FLOW_ROW_Y = 56

type StepPreviewData = { label: string; icon_key: string }

const StepPreviewNode = memo(function StepPreviewNode({ data }: { data: StepPreviewData }) {
  return (
    <div
      className="relative flex items-center gap-1.5 rounded-lg border border-black/12 bg-white px-2 py-1.5 shadow-sm"
      style={{ width: FLOW_NODE_W, minHeight: 44 }}
    >
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={false}
        className="!size-2 !border-0 !bg-transparent !opacity-0"
        aria-hidden
      />
      <FlowTemplateIcon name={data.icon_key} className="h-4 w-4 shrink-0 text-primary" />
      <span className="min-w-0 flex-1 wrap-break-word text-[11px] font-medium leading-snug text-ink">
        {data.label}
      </span>
      <Handle
        type="source"
        position={Position.Right}
        isConnectable={false}
        className="!size-2 !border-0 !bg-transparent !opacity-0"
        aria-hidden
      />
    </div>
  )
})

const nodeTypes = { stepPreview: StepPreviewNode }

function EnterActionsBlock({
  actions,
  onChange,
}: {
  actions: Record<string, unknown>[]
  onChange: (next: Record<string, unknown>[]) => void
}) {
  function updateAt(i: number, patch: Record<string, unknown>) {
    const next = actions.map((a, j) => (j === i ? { ...a, ...patch } : a))
    onChange(next)
  }

  function setTypeAt(i: number, newType: EnterActionType) {
    const next = actions.map((a, j) => (j === i ? emptyActionForType(newType) : a))
    onChange(next)
  }

  function removeAt(i: number) {
    onChange(actions.filter((_, j) => j !== i))
  }

  return (
    <div className="block sm:col-span-2">
      <span className="du-label">Al entrar en este paso</span>
      <div className="mt-2 space-y-3">
        {actions.length === 0 ? (
          <p className="text-xs text-muted">Sin acciones automáticas. Añadí una con el botón de abajo.</p>
        ) : null}
        {actions.map((raw, i) => {
          const t = String(raw.type ?? 'notify_role') as EnterActionType
          const safeType =
            t === 'create_task' || t === 'project_chat_message' ? t : 'notify_role'
          return (
            <div
              key={i}
              className="rounded-md border border-black/10 bg-white p-3 shadow-sm"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <label className="min-w-0 flex-1">
                  <span className="sr-only">Tipo de acción</span>
                  <select
                    className="du-input w-full text-sm"
                    value={safeType}
                    onChange={(e) => setTypeAt(i, e.target.value as EnterActionType)}
                  >
                    <option value="notify_role">Notificar por rol</option>
                    <option value="create_task">Crear tarea (rol sugerido)</option>
                    <option value="project_chat_message">Mensaje en chat del proyecto</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="shrink-0 text-xs text-primary hover:underline"
                  onClick={() => removeAt(i)}
                >
                  Quitar
                </button>
              </div>
              {safeType === 'notify_role' ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="block sm:col-span-2">
                    <span className="text-xs text-muted">Rol a notificar</span>
                    <select
                      className="du-input mt-0.5 w-full text-sm"
                      value={String(raw.role ?? 'CONTROL')}
                      onChange={(e) => updateAt(i, { role: e.target.value })}
                    >
                      {USER_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABELS[r as UserRole]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block sm:col-span-2">
                    <span className="text-xs text-muted">Título de la notificación</span>
                    <input
                      className="du-input mt-0.5 w-full text-sm"
                      value={String(raw.title ?? '')}
                      onChange={(e) => updateAt(i, { title: e.target.value })}
                    />
                  </label>
                  <label className="block sm:col-span-2">
                    <span className="text-xs text-muted">Cuerpo</span>
                    <textarea
                      className="du-input mt-0.5 min-h-[56px] w-full text-sm"
                      value={String(raw.body ?? '')}
                      onChange={(e) => updateAt(i, { body: e.target.value })}
                    />
                  </label>
                </div>
              ) : null}
              {safeType === 'create_task' ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="block">
                    <span className="text-xs text-muted">Rol sugerido</span>
                    <select
                      className="du-input mt-0.5 w-full text-sm"
                      value={String(raw.role ?? 'CONTROL')}
                      onChange={(e) => updateAt(i, { role: e.target.value })}
                    >
                      {USER_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABELS[r as UserRole]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block sm:col-span-2">
                    <span className="text-xs text-muted">Título de la tarea</span>
                    <input
                      className="du-input mt-0.5 w-full text-sm"
                      value={String(raw.title ?? '')}
                      onChange={(e) => updateAt(i, { title: e.target.value })}
                    />
                  </label>
                  <label className="block sm:col-span-2">
                    <span className="text-xs text-muted">Descripción</span>
                    <textarea
                      className="du-input mt-0.5 min-h-[56px] w-full text-sm"
                      value={String(raw.description ?? '')}
                      onChange={(e) => updateAt(i, { description: e.target.value })}
                    />
                  </label>
                </div>
              ) : null}
              {safeType === 'project_chat_message' ? (
                <label className="block">
                  <span className="text-xs text-muted">Mensaje</span>
                  <textarea
                    className="du-input mt-0.5 min-h-[72px] w-full text-sm"
                    value={String(raw.body ?? '')}
                    onChange={(e) => updateAt(i, { body: e.target.value })}
                  />
                </label>
              ) : null}
            </div>
          )
        })}
        <button
          type="button"
          className="rounded-lg border border-dashed border-black/20 px-3 py-2 text-xs font-medium text-muted hover:border-black/30 hover:text-ink"
          onClick={() => onChange([...actions, emptyActionForType('notify_role')])}
        >
          + Añadir acción
        </button>
      </div>
    </div>
  )
}

export function FlowStepsEditor({ steps, onChange }: FlowStepsEditorProps) {
  const [selectedDraftId, setSelectedDraftId] = useState('')

  const effectiveSelectedDraftId =
    selectedDraftId && steps.some((s) => s.draft_id === selectedDraftId)
      ? selectedDraftId
      : (steps[0]?.draft_id ?? '')

  const selected =
    steps.find((s) => s.draft_id === effectiveSelectedDraftId) ??
    (steps.length > 0 ? steps[0] : undefined)

  const updateStep = useCallback(
    (draftId: string, patch: Partial<DraftWorkflowStep>) => {
      const next = syncStableKeysForSteps(
        steps.map((s) => (s.draft_id === draftId ? { ...s, ...patch } : s)),
      )
      onChange(next)
    },
    [steps, onChange],
  )

  const addStep = useCallback(() => {
    const nid = newDraftId()
    const i = steps.length
    onChange(
      syncStableKeysForSteps([
        ...steps,
        {
          draft_id: nid,
          stable_key: '',
          title: `Paso ${i + 1}`,
          icon_key: DEFAULT_FLOW_TEMPLATE_ICON,
          requires_approval_role: null,
          on_enter_actions: [],
        },
      ]),
    )
    setSelectedDraftId(nid)
  }, [steps, onChange])

  const removeStep = useCallback(
    (draftId: string) => {
      if (steps.length <= 1) return
      onChange(syncStableKeysForSteps(steps.filter((s) => s.draft_id !== draftId)))
    },
    [steps, onChange],
  )

  const { nodes, edges } = useMemo(() => {
    const n: Node[] = steps.map((s, i) => ({
      id: s.draft_id,
      type: 'stepPreview',
      position: { x: i * (FLOW_NODE_W + FLOW_NODE_GAP), y: FLOW_ROW_Y },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: { label: s.title || s.stable_key, icon_key: s.icon_key },
    }))
    const e: Edge[] = []
    for (let i = 0; i < steps.length - 1; i++) {
      e.push({
        id: `e-${steps[i].draft_id}`,
        type: 'dotArrow',
        source: steps[i].draft_id,
        target: steps[i + 1].draft_id,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: '#1e4d8c',
        },
        style: { stroke: '#1e4d8c', strokeWidth: 1.5 },
      })
    }
    return { nodes: n, edges: e }
  }, [steps])

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-4 lg:flex-row lg:overflow-hidden">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-black/10 bg-white lg:max-h-full">
        <div className="shrink-0 space-y-3 px-3 pt-3">
          <p className="text-sm font-semibold text-ink">
            Orden 1 → 2 → 3 = orden del flujo. «Guardar» envía solo esta lista y en el servidor sustituye todos los
            pasos anteriores.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[min(100%,220px)] flex-1">
              <span className="du-label">Paso a editar</span>
              <select
                className="du-input mt-1 w-full"
                value={selected?.draft_id ?? ''}
                onChange={(e) => setSelectedDraftId(e.target.value)}
                disabled={steps.length === 0}
              >
                {steps.map((step, idx) => (
                  <option key={step.draft_id} value={step.draft_id}>
                    Paso {idx + 1}: {step.title.trim() || step.stable_key}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="du-pill-action shrink-0 text-xs" onClick={addStep}>
              + Paso
            </button>
            <button
              type="button"
              className="shrink-0 rounded-lg border border-black/15 px-3 py-2 text-xs font-medium text-primary hover:bg-black/[0.03]"
              onClick={() => selected && removeStep(selected.draft_id)}
              disabled={!selected || steps.length <= 1}
            >
              Quitar este paso
            </button>
          </div>
        </div>

        <div className="min-h-0 max-h-[min(70vh,520px)] flex-1 overflow-y-scroll overscroll-y-contain px-3 pb-3 [-webkit-overflow-scrolling:touch] lg:max-h-none">
          {selected ? (
            <div className="rounded-lg border border-black/10 bg-black/[0.02] p-3 text-sm">
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="block">
                  <span className="du-label">Nombre del paso</span>
                  <input
                    className="du-input mt-0.5 w-full"
                    value={selected.title}
                    onChange={(e) => updateStep(selected.draft_id, { title: e.target.value })}
                  />
                </label>
                <label className="block">
                  <span className="du-label">Ícono del paso</span>
                  <select
                    className="du-input mt-0.5 w-full"
                    value={selected.icon_key}
                    onChange={(e) =>
                      updateStep(selected.draft_id, { icon_key: e.target.value as FlowTemplateIconKey })
                    }
                  >
                    {FLOW_TEMPLATE_ICON_KEYS.map((k) => (
                      <option key={k} value={k}>
                        {flowTemplateIconLabelEs(k)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="block">
                  <span className="du-label">Clave estable</span>
                  <p className="mt-0.5 rounded-md border border-black/10 bg-black/[0.03] px-3 py-2 font-mono text-xs text-ink">
                    {selected.stable_key}
                  </p>
                </div>
                <label className="block sm:col-span-2">
                  <span className="du-label">Requiere aprobación de</span>
                  <select
                    className="du-input mt-0.5 w-full"
                    value={selected.requires_approval_role ?? ''}
                    onChange={(e) =>
                      updateStep(selected.draft_id, {
                        requires_approval_role: e.target.value ? e.target.value : null,
                      })
                    }
                  >
                    <option value="">N/A</option>
                    {USER_ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABELS[r as UserRole]}
                      </option>
                    ))}
                  </select>
                </label>
                <EnterActionsBlock
                  actions={selected.on_enter_actions}
                  onChange={(next) => updateStep(selected.draft_id, { on_enter_actions: next })}
                />
              </div>
            </div>
          ) : null}
        </div>
      </div>
      <div className="h-[320px] min-h-[280px] shrink-0 overflow-x-auto overflow-y-hidden rounded-lg border border-black/10 bg-[#f8f9fb] lg:h-full lg:min-h-0 lg:w-[45%] lg:min-w-0 lg:self-stretch">
        <ReactFlow
          className="min-h-[260px] min-w-[480px] lg:min-h-[320px]"
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag
          zoomOnScroll
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  )
}

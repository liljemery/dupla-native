import { Card } from '../../Card'
import { PrimaryButton } from '../../PrimaryButton'
import type { ArchitecturePayload } from '../../../schemas/architecture'

type WorkspacePliegosTabProps = {
  kind: 'tirada' | 'plano' | 'fase'
  setKind: React.Dispatch<React.SetStateAction<'tirada' | 'plano' | 'fase'>>
  title: string
  setTitle: React.Dispatch<React.SetStateAction<string>>
  data: ArchitecturePayload
  addGroup: (kind: ArchitecturePayload['groups'][number]['kind'], title: string) => void
  addItem: (groupId: string) => void
  updateItem: (
    groupId: string,
    itemId: string,
    patch: Partial<ArchitecturePayload['groups'][number]['items'][number]>,
  ) => void
}

export function WorkspacePliegosTab({
  kind,
  setKind,
  title,
  setTitle,
  data,
  addGroup,
  addItem,
  updateItem,
}: WorkspacePliegosTabProps) {
  return (
    <div className="space-y-8">
      <Card className="p-4">
        <div className="text-sm font-semibold text-ink">Agregar sección</div>
        <p className="mt-1 text-sm text-muted">
          Las secciones agrupan ítems del pliego: <strong className="text-ink">tirada</strong>,{' '}
          <strong className="text-ink">plano</strong> o <strong className="text-ink">fase</strong>. Después usa «+ Ítem»
          en cada bloque para las partidas.
        </p>
        <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-end">
          <label className="block text-sm text-muted">
            Tipo
            <select
              className="du-input mt-1 md:w-56"
              value={kind}
              onChange={(e) => setKind(e.target.value as 'tirada' | 'plano' | 'fase')}
            >
              <option value="tirada">Tirada</option>
              <option value="plano">Plano</option>
              <option value="fase">Fase</option>
            </select>
          </label>
          <label className="block flex-1 text-sm text-muted">
            Título
            <input
              className="du-input mt-1"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              aria-label="Título de la sección"
            />
          </label>
          <PrimaryButton type="button" onClick={() => addGroup(kind, title)}>
            Agregar sección
          </PrimaryButton>
        </div>
      </Card>

      <div className="space-y-6">
        {data.groups.map((g) => (
          <Card key={g.id} className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-black/5 bg-white px-4 py-3">
              <div>
                <div className="text-xs uppercase tracking-wide text-muted">{g.kind}</div>
                <div className="text-lg font-semibold text-ink">{g.title}</div>
              </div>
              <PrimaryButton type="button" onClick={() => addItem(g.id)}>
                + Ítem
              </PrimaryButton>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead className="sticky top-0 z-10 bg-black/[0.04] text-xs uppercase text-muted">
                  <tr>
                    <th className="px-4 py-2">Partida</th>
                    <th className="px-4 py-2">Descripción</th>
                    <th className="px-4 py-2">Unidad</th>
                    <th className="px-4 py-2">Cantidad</th>
                    <th className="px-4 py-2">P. unitario</th>
                    <th className="px-4 py-2">Subtotal</th>
                    <th className="px-4 py-2">Notas</th>
                  </tr>
                </thead>
                <tbody>
                  {g.items.map((it) => (
                    <tr key={it.id} className="border-t border-black/5 odd:bg-black/[0.015]">
                      <td className="px-4 py-2 align-top">
                        <input
                          className="du-input w-28 py-1.5 text-sm"
                          value={it.partida ?? ''}
                          onChange={(e) => updateItem(g.id, it.id, { partida: e.target.value || null })}
                          aria-label="Partida"
                        />
                      </td>
                      <td className="px-4 py-2 align-top">
                        <input
                          className="du-input min-w-[240px] py-1.5 text-sm"
                          value={it.descripcion}
                          onChange={(e) => updateItem(g.id, it.id, { descripcion: e.target.value })}
                          aria-label="Descripción"
                        />
                      </td>
                      <td className="px-4 py-2 align-top">
                        <input
                          className="du-input w-20 py-1.5 text-sm"
                          value={it.unidad ?? ''}
                          onChange={(e) => updateItem(g.id, it.id, { unidad: e.target.value || null })}
                          aria-label="Unidad"
                        />
                      </td>
                      <td className="px-4 py-2 align-top">
                        <input
                          className="du-input w-24 py-1.5 text-sm"
                          type="number"
                          min={0}
                          step="any"
                          value={it.cantidad ?? ''}
                          onChange={(e) => {
                            const v = e.target.value
                            updateItem(g.id, it.id, {
                              cantidad: v === '' ? 0 : Number(v),
                            })
                          }}
                          aria-label="Cantidad"
                        />
                      </td>
                      <td className="px-4 py-2 align-top">
                        <input
                          className="du-input w-28 py-1.5 text-sm"
                          type="number"
                          min={0}
                          step="any"
                          value={it.precio_unitario ?? ''}
                          onChange={(e) => {
                            const v = e.target.value
                            updateItem(g.id, it.id, {
                              precio_unitario: v === '' ? 0 : Number(v),
                            })
                          }}
                          aria-label="Precio unitario"
                        />
                      </td>
                      <td className="px-4 py-2 align-top text-sm tabular-nums text-ink">
                        {(it.subtotal ?? 0).toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </td>
                      <td className="px-4 py-2 align-top">
                        <input
                          className="du-input w-44 py-1.5 text-sm"
                          value={it.notas ?? ''}
                          onChange={(e) => updateItem(g.id, it.id, { notas: e.target.value || null })}
                          aria-label="Notas"
                        />
                      </td>
                    </tr>
                  ))}
                  {g.items.length === 0 ? (
                    <tr>
                      <td className="px-4 py-4 text-sm text-muted md:py-6" colSpan={7}>
                        No hay ítems en esta sección.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </Card>
        ))}

        {data.groups.length === 0 ? (
          <Card className="border-2 border-dashed border-black/12 bg-black/[0.02] p-6 text-center md:p-10">
            <p className="text-sm font-medium text-ink">Empieza por una sección</p>
            <p className="mt-2 text-sm text-muted">
              Elige tipo y título arriba y pulsa «Agregar sección». El tablero de ítems aparece dentro de cada bloque.
            </p>
          </Card>
        ) : null}
      </div>
    </div>
  )
}

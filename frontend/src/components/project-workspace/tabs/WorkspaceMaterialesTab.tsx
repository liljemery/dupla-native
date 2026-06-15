import { Card } from '../../Card'
import { PrimaryButton } from '../../PrimaryButton'
import type { ArchitecturePayload } from '../../../schemas/architecture'

type MaterialRow = ArchitecturePayload['materiales'][number]

type WorkspaceMaterialesTabProps = {
  data: ArchitecturePayload
  addMaterial: () => void
  updateMaterial: (materialId: string, patch: Partial<MaterialRow>) => void
  removeMaterial: (materialId: string) => void
}

export function WorkspaceMaterialesTab({
  data,
  addMaterial,
  updateMaterial,
  removeMaterial,
}: WorkspaceMaterialesTabProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-prose text-sm text-muted">
          Cubicación e insumos. El total se calcula a partir de la cantidad estimada y el desperdicio (%).
        </p>
        <PrimaryButton type="button" onClick={addMaterial}>
          + Material
        </PrimaryButton>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead className="sticky top-0 z-10 bg-black/[0.04] text-xs uppercase text-muted">
              <tr>
                <th className="px-4 py-2">Categoría</th>
                <th className="px-4 py-2">Descripción</th>
                <th className="px-4 py-2">Unidad</th>
                <th className="px-4 py-2">Cant. est.</th>
                <th className="px-4 py-2">Desp. %</th>
                <th className="px-4 py-2">Cant. total</th>
                <th className="px-4 py-2">Costo est.</th>
                <th className="px-4 py-2">Proveedor</th>
                <th className="px-4 py-2" aria-label="Acciones" />
              </tr>
            </thead>
            <tbody>
              {data.materiales.map((m) => (
                <tr key={m.id} className="border-t border-black/5 odd:bg-black/[0.015]">
                  <td className="px-4 py-2 align-top">
                    <input
                      className="du-input w-28 py-1.5 text-sm"
                      value={m.categoria ?? ''}
                      onChange={(e) => updateMaterial(m.id, { categoria: e.target.value || null })}
                      aria-label="Categoría"
                    />
                  </td>
                  <td className="px-4 py-2 align-top">
                    <input
                      className="du-input min-w-[200px] py-1.5 text-sm"
                      value={m.descripcion}
                      onChange={(e) => updateMaterial(m.id, { descripcion: e.target.value })}
                      aria-label="Descripción"
                    />
                  </td>
                  <td className="px-4 py-2 align-top">
                    <input
                      className="du-input w-20 py-1.5 text-sm"
                      value={m.unidad ?? ''}
                      onChange={(e) => updateMaterial(m.id, { unidad: e.target.value || null })}
                      aria-label="Unidad"
                    />
                  </td>
                  <td className="px-4 py-2 align-top">
                    <input
                      className="du-input w-24 py-1.5 text-sm"
                      type="number"
                      min={0}
                      step="any"
                      value={m.cantidad_estimada ?? ''}
                      onChange={(e) => {
                        const v = e.target.value
                        updateMaterial(m.id, {
                          cantidad_estimada: v === '' ? null : Number(v),
                        })
                      }}
                      aria-label="Cantidad estimada"
                    />
                  </td>
                  <td className="px-4 py-2 align-top">
                    <input
                      className="du-input w-20 py-1.5 text-sm"
                      type="number"
                      min={0}
                      max={100}
                      step="any"
                      value={m.desperdicio_porcentaje ?? ''}
                      onChange={(e) => {
                        const v = e.target.value
                        updateMaterial(m.id, {
                          desperdicio_porcentaje: v === '' ? null : Number(v),
                        })
                      }}
                      aria-label="Desperdicio porcentaje"
                    />
                  </td>
                  <td className="px-4 py-2 align-top text-sm tabular-nums text-ink">
                    {m.cantidad_total != null
                      ? m.cantidad_total.toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 3,
                        })
                      : '—'}
                  </td>
                  <td className="px-4 py-2 align-top">
                    <input
                      className="du-input w-28 py-1.5 text-sm"
                      type="number"
                      min={0}
                      step="any"
                      value={m.costo_estimado ?? ''}
                      onChange={(e) => {
                        const v = e.target.value
                        updateMaterial(m.id, {
                          costo_estimado: v === '' ? null : Number(v),
                        })
                      }}
                      aria-label="Costo estimado"
                    />
                  </td>
                  <td className="px-4 py-2 align-top">
                    <input
                      className="du-input w-40 py-1.5 text-sm"
                      value={m.proveedor_sugerido ?? ''}
                      onChange={(e) => updateMaterial(m.id, { proveedor_sugerido: e.target.value || null })}
                      aria-label="Proveedor sugerido"
                    />
                  </td>
                  <td className="px-4 py-2 align-top">
                    <button
                      type="button"
                      className="text-xs font-semibold text-primary underline-offset-2 hover:underline"
                      onClick={() => removeMaterial(m.id)}
                    >
                      Quitar
                    </button>
                  </td>
                </tr>
              ))}
              {data.materiales.length === 0 ? (
                <tr>
                  <td className="px-4 py-8 text-center text-sm text-muted" colSpan={9}>
                    No hay materiales. Usa «+ Material» para agregar una fila.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

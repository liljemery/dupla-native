/** Alineado con backend: `app/domain/project_uploads.py`. */

export const PROJECT_ALLOWED_FILE_EXTENSIONS = ['dwg', 'dxf', 'pdf', 'ifc', 'docx'] as const

export const PROJECT_FILE_ACCEPT_ATTR =
  '.dwg,.dxf,.pdf,.ifc,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

export function isAllowedProjectFileName(name: string): boolean {
  const i = name.lastIndexOf('.')
  if (i < 0) return false
  const ext = name.slice(i + 1).toLowerCase()
  return (PROJECT_ALLOWED_FILE_EXTENSIONS as readonly string[]).includes(ext)
}

export function filterAllowedProjectFiles(files: File[]): { allowed: File[]; rejected: File[] } {
  const allowed: File[] = []
  const rejected: File[] = []
  for (const f of files) {
    if (isAllowedProjectFileName(f.name)) allowed.push(f)
    else rejected.push(f)
  }
  return { allowed, rejected }
}

export function formatAllowedProjectExtensionsHint(): string {
  return PROJECT_ALLOWED_FILE_EXTENSIONS.map((e) => `.${e}`).join(', ')
}

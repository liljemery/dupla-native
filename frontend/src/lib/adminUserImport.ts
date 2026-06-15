import { ROLE_LABELS, USER_ROLES, type UserRole } from '../constants/userRoles'

export type ParsedImportRow = {
  key: string
  fullName: string
  first_name: string
  last_name: string
  email: string
  department: string
  jobTitle: string
  role: UserRole
  module_ids: number[]
  parseError: string | null
}

export type ParseImportResult = {
  rows: ParsedImportRow[]
  errors: string[]
}

const IMPORT_TEMPLATE =
  'NOMBRES Y APELLIDOS,CARGO,CORREO,DEPARTAMENTO\n' +
  'DANIEL YAMIL SANTANA SLAIMAN,PRESIDENTE,daniel@grupodupla.com,GERENCIA'

function normalizeHeader(value: string): string {
  return value
    .trim()
    .toUpperCase()
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
}

function titleCaseWord(word: string): string {
  if (!word) return word
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
}

export function splitFullName(fullName: string): { first_name: string; last_name: string } {
  const tokens = fullName.trim().split(/\s+/).filter(Boolean)
  if (tokens.length === 0) {
    return { first_name: '', last_name: '' }
  }
  if (tokens.length === 1) {
    return { first_name: titleCaseWord(tokens[0]), last_name: titleCaseWord(tokens[0]) }
  }
  if (tokens.length === 2) {
    return { first_name: titleCaseWord(tokens[0]), last_name: titleCaseWord(tokens[1]) }
  }
  return {
    first_name: tokens.slice(0, -2).map(titleCaseWord).join(' '),
    last_name: tokens.slice(-2).map(titleCaseWord).join(' '),
  }
}

export function roleFromDepartment(department: string): UserRole | null {
  const normalized = normalizeHeader(department)
  if (normalized.includes('ARQUITECTURA')) return 'ARQUITECTURA'
  if (normalized.includes('PRESUPUESTO')) return 'PRESUPUESTO'
  if (normalized.includes('CONTROL')) return 'CONTROL'
  if (normalized.includes('GERENCIA')) return 'GERENCIA'
  if (normalized.includes('PROGRAMACION')) return 'GERENCIA'
  if (normalized.includes('ADMINISTRACION')) return 'GERENCIA'
  if (normalized.includes('TECNOLOGIA')) return 'GERENCIA'
  return null
}

function parseRoleValue(value: string): UserRole | null {
  const normalized = normalizeHeader(value)
  return USER_ROLES.find((role) => role === normalized) ?? null
}

function detectDelimiter(line: string): string {
  const tabs = (line.match(/\t/g) ?? []).length
  const semicolons = (line.match(/;/g) ?? []).length
  const commas = (line.match(/,/g) ?? []).length
  if (tabs >= commas && tabs >= semicolons && tabs > 0) return '\t'
  if (semicolons > commas) return ';'
  return ','
}

function parseDelimitedLine(line: string, delimiter: string): string[] {
  const fields: string[] = []
  let current = ''
  let inQuotes = false

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    if (inQuotes) {
      if (char === '"') {
        if (line[index + 1] === '"') {
          current += '"'
          index += 1
        } else {
          inQuotes = false
        }
      } else {
        current += char
      }
      continue
    }
    if (char === '"') {
      inQuotes = true
      continue
    }
    if (char === delimiter) {
      fields.push(current.trim())
      current = ''
      continue
    }
    current += char
  }

  fields.push(current.trim())
  return fields
}

function resolveColumnIndexes(headers: string[]): {
  fullName?: number
  email?: number
  department?: number
  jobTitle?: number
  role?: number
} {
  const indexes: {
    fullName?: number
    email?: number
    department?: number
    jobTitle?: number
    role?: number
  } = {}

  headers.forEach((header, index) => {
    if (
      header.includes('NOMBRE') &&
      (header.includes('APELLIDO') || header === 'NOMBRES Y APELLIDOS' || header === 'NOMBRE COMPLETO')
    ) {
      indexes.fullName = index
      return
    }
    if (header === 'NOMBRE' || header === 'NAME') {
      indexes.fullName = index
      return
    }
    if (header.includes('CORREO') || header === 'EMAIL' || header === 'E-MAIL') {
      indexes.email = index
      return
    }
    if (header.includes('DEPARTAMENTO') || header === 'DEPT' || header === 'DEPARTMENT') {
      indexes.department = index
      return
    }
    if (header.includes('CARGO') || header === 'PUESTO' || header === 'TITLE') {
      indexes.jobTitle = index
      return
    }
    if (header === 'ROL' || header === 'ROLE') {
      indexes.role = index
    }
  })

  return indexes
}

export function parseUserImportText(text: string): ParseImportResult {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)

  if (lines.length < 2) {
    return { rows: [], errors: ['Incluye cabecera y al menos una fila de datos.'] }
  }

  const delimiter = detectDelimiter(lines[0])
  const headers = parseDelimitedLine(lines[0], delimiter).map(normalizeHeader)
  const columns = resolveColumnIndexes(headers)

  if (columns.fullName === undefined || columns.email === undefined) {
    return {
      rows: [],
      errors: ['Faltan columnas obligatorias: NOMBRES Y APELLIDOS y CORREO.'],
    }
  }

  const rows: ParsedImportRow[] = []
  const errors: string[] = []

  for (let lineIndex = 1; lineIndex < lines.length; lineIndex += 1) {
    const values = parseDelimitedLine(lines[lineIndex], delimiter)
    const fullName = values[columns.fullName] ?? ''
    const email = (values[columns.email] ?? '').trim().toLowerCase()
    const department = columns.department !== undefined ? (values[columns.department] ?? '').trim() : ''
    const jobTitle = columns.jobTitle !== undefined ? (values[columns.jobTitle] ?? '').trim() : ''
    const explicitRole =
      columns.role !== undefined ? parseRoleValue(values[columns.role] ?? '') : null
    const { first_name, last_name } = splitFullName(fullName)
    const mappedRole = explicitRole ?? (department ? roleFromDepartment(department) : null)

    let parseError: string | null = null
    if (!fullName.trim()) parseError = 'Nombre vacío'
    else if (!email) parseError = 'Correo vacío'
    else if (!mappedRole) parseError = 'No se pudo determinar el rol'

    rows.push({
      key: `${lineIndex}-${email || fullName}`,
      fullName: fullName.trim(),
      first_name,
      last_name,
      email,
      department,
      jobTitle,
      role: mappedRole ?? 'ARQUITECTURA',
      module_ids: [1],
      parseError,
    })
  }

  const invalidCount = rows.filter((row) => row.parseError).length
  if (invalidCount > 0) {
    errors.push(`${invalidCount} fila(s) tienen errores de validación.`)
  }

  return { rows, errors }
}

export function downloadImportTemplate(): void {
  const blob = new Blob([IMPORT_TEMPLATE], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'plantilla-usuarios-dupla.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}

export type ImportCreatedUser = {
  uuid: string
  email: string
  first_name: string
  last_name: string
  role: UserRole
  password: string
}

export function downloadCredentialsCsv(users: ImportCreatedUser[]): void {
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`
  const header = 'correo,contraseña,rol,nombre\n'
  const lines = users
    .map((user) => {
      const name = `${user.first_name} ${user.last_name}`.trim()
      return [user.email, user.password, ROLE_LABELS[user.role], name].map(escape).join(',')
    })
    .join('\n')
  const blob = new Blob([header + lines], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'credenciales-usuarios-dupla.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}

export function validImportRows(rows: ParsedImportRow[]): ParsedImportRow[] {
  return rows.filter((row) => !row.parseError)
}

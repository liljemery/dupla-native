import {
  File,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileType2,
  Folder,
} from 'lucide-react'

export function ProjectWorkspaceFileIcon({
  name,
  isFolder,
  className,
}: {
  name: string
  isFolder?: boolean
  className?: string
}) {
  if (isFolder) {
    return <Folder className={className} aria-hidden strokeWidth={1.75} />
  }
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  const cn = className ?? 'h-10 w-10'
  if (ext === 'pdf') return <FileText className={cn} aria-hidden strokeWidth={1.5} />
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext))
    return <FileImage className={cn} aria-hidden strokeWidth={1.5} />
  if (['xls', 'xlsx', 'csv'].includes(ext)) return <FileSpreadsheet className={cn} aria-hidden strokeWidth={1.5} />
  if (['dwg', 'dxf'].includes(ext)) return <FileType2 className={cn} aria-hidden strokeWidth={1.5} />
  return <File className={cn} aria-hidden strokeWidth={1.5} />
}

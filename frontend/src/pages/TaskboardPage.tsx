import { useSearchParams } from 'react-router-dom'

import { TaskboardView } from '../components/TaskboardView'

export function TaskboardPage() {
  const [searchParams] = useSearchParams()
  const projectFilter = searchParams.get('project_uuid') ?? ''
  return <TaskboardView projectUuid={projectFilter} variant="full" />
}

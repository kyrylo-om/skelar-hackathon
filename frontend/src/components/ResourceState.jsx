import EmptyState, { Skeleton } from './EmptyState'

export default function ResourceState({ resource, empty, children }) {
  if (resource.loading && !resource.data) return <Skeleton />
  if (resource.error) return <EmptyState kind={resource.error.kind} title={resource.error.kind === 'forbidden' ? 'Недостатньо прав' : 'Не вдалося завантажити дані'} onRetry={resource.refresh}>{resource.error.message}{resource.data ? ' Попередні дані не є актуальними.' : ''}</EmptyState>
  if (empty) return <EmptyState title="Даних немає">{children}</EmptyState>
  return null
}

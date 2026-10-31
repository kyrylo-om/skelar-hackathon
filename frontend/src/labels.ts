import type { ChatStatus } from './types'

export const statusLabel: Record<ChatStatus, string> = {
  needs_review: 'Потрібна перевірка',
  ai_handling: 'AI веде',
  resolved: 'Вирішено',
}

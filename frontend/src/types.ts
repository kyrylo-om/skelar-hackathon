export type Role = 'customer' | 'ai' | 'operator' | 'system'

export type Message = {
  id: number
  role: Role
  text: string
  at: string
}

export type TraceStep = {
  agent: 'guard' | 'triage' | 'actor' | 'critic' | 'policy' | 'executor' | 'qa'
  verdict: 'pass' | 'block' | 'info'
  detail: string
}

export type Risk = 'low' | 'medium' | 'high'

export type Review = {
  action: string
  params: Record<string, string | number>
  risk: Risk
  reason: string
  status: 'pending' | 'approved' | 'rejected'
}

export type ChatStatus = 'needs_review' | 'ai_handling' | 'resolved'
export type Priority = 'low' | 'normal' | 'high'

export type Chat = {
  id: number
  customer: string
  subject: string
  status: ChatStatus
  priority: Priority
  updatedAt: string
  summary: string
  messages: Message[]
  trace: TraceStep[]
  review: Review | null
}

export type Decision = 'approved' | 'rejected'

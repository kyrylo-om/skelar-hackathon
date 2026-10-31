// The only module that knows the backend's widget endpoints (backend/apps/widget).
import { currentToken, refreshToken } from './token'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export type Role = 'customer' | 'ai' | 'operator' | 'system'
export type Message = { id: number; role: Role; text: string; at: string }
// An action that runs only if the customer presses confirm (e.g. turning off auto-renewal).
export type Confirmation = { id: string; kind: string; description: string; expires_at: string }
export type Chat = {
  id: number
  status: string
  messages: Message[]
  pendingConfirmation: Confirmation | null
}
export type StreamEvent =
  | { event: 'status'; data: { stage: string } }
  | { event: 'message'; data: Message }
  | { event: 'done'; data: { status: string } }
  | { event: 'error'; data: { code: string; message: string } }

/** No usable token: the customer is logged out or the session could not be renewed. */
export class AuthError extends Error {}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`API request failed with status ${status}`)
    this.status = status
  }
}

// Bearer token only, never cookies. A 401 gets one token refresh and one retry.
async function call(path: string, init: RequestInit = {}): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    const token = currentToken()
    if (!token) throw new AuthError()
    const headers = new Headers(init.headers)
    headers.set('Authorization', `Bearer ${token}`)
    const response = await fetch(API_BASE + path, { ...init, headers, credentials: 'omit' })
    if (response.status !== 401) {
      if (!response.ok) throw new ApiError(response.status)
      return response
    }
    if (attempt > 0 || (await refreshToken()) !== 'ok') throw new AuthError()
  }
}

export async function getChat(): Promise<Chat> {
  return (await call('/widget/chat/')).json()
}

/** The customer's own confirm button: the only way such an action runs. */
export async function confirmAction(id: string): Promise<void> {
  await call(`/widget/actions/${encodeURIComponent(id)}/confirm/`, { method: 'POST' })
}

/** Send a message; the answer arrives as server-sent events, passed to onEvent as they come. */
export async function sendMessage(text: string, onEvent: (event: StreamEvent) => void) {
  const response = await call('/widget/chat/messages/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    const parsed = parseSse(buffer + value)
    buffer = parsed.rest
    parsed.events.forEach(onEvent)
  }
}

/** Split a text/event-stream buffer into complete events and the unfinished rest. */
export function parseSse(buffer: string): { events: StreamEvent[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: StreamEvent[] = []
  for (const block of blocks) {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (data.length) events.push({ event, data: JSON.parse(data.join('\n')) } as StreamEvent)
  }
  return { events, rest }
}

// postMessage protocol between the loader (on the host page) and the chat app (in the iframe).
// Each side accepts a message only from the other's exact origin and window, and only if it
// carries CHANNEL. The token travels only loader -> app, and only to the app's origin.

export const CHANNEL = 'support-widget'

// Loader -> app
export type ToApp =
  | { type: 'token'; token: string; expiresIn: number } // expiresIn: seconds
  | { type: 'logged-out' } // the host says nobody is signed in
  | { type: 'token-error' } // the host's token endpoint failed
  | { type: 'opened' }
  | { type: 'closed' }

// App -> loader
export type ToLoader =
  | { type: 'token-request' }
  | { type: 'close' }
  | { type: 'unread'; count: number }

export type Envelope<T> = T & { channel: typeof CHANNEL }

export function isEnvelope(data: unknown): data is Envelope<{ type: string }> {
  if (typeof data !== 'object' || data === null) return false
  const message = data as { channel?: unknown; type?: unknown }
  return message.channel === CHANNEL && typeof message.type === 'string'
}

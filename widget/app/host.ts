// The iframe's side of the postMessage protocol (shared/protocol.ts).
import { CHANNEL, type Envelope, type ToApp, type ToLoader, isEnvelope } from '../shared/protocol'

function asOrigin(value: string | null): string {
  try {
    const url = new URL(value ?? '')
    return url.origin === value ? value : ''
  } catch {
    return ''
  }
}

// The loader puts the host page's origin here. Messages go only there and come only from there.
const hostOrigin = asOrigin(new URLSearchParams(location.search).get('host'))
export const embedded = window.parent !== window && hostOrigin !== ''

export function toLoader(message: ToLoader) {
  if (!embedded) return
  const envelope: Envelope<ToLoader> = { channel: CHANNEL, ...message }
  window.parent.postMessage(envelope, hostOrigin)
}

export function onLoaderMessage(handler: (message: ToApp) => void): () => void {
  const listener = (event: MessageEvent) => {
    if (event.source !== window.parent || event.origin !== hostOrigin) return
    if (isEnvelope(event.data)) handler(event.data as Envelope<ToApp>)
  }
  window.addEventListener('message', listener)
  return () => window.removeEventListener('message', listener)
}

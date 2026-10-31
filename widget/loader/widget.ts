// The script a product embeds:
//   <script src="https://<widget host>/widget.js" data-product="cloudbox"
//           data-token-url="/support/token"></script>
// It adds a floating button and, on the first click, an iframe with the chat app (served next to
// this file). The host's token endpoint is called here, same-origin with the host's cookies, and
// the token is handed to the iframe; the browser never decides who the customer is.

import { CHANNEL, type Envelope, type ToApp, type ToLoader, isEnvelope } from '../shared/protocol'

const STYLE = `
  :host { all: initial; }
  button.launcher { position: fixed; right: 20px; bottom: 20px; z-index: 2147483646;
    width: 56px; height: 56px; border-radius: 50%; border: 0; cursor: pointer;
    background: #2f6fed; color: #fff; box-shadow: 0 4px 16px rgba(16, 33, 58, .25);
    display: grid; place-items: center; }
  button.launcher:focus-visible { outline: 3px solid #9bbcff; outline-offset: 2px; }
  .dot { position: absolute; top: 4px; right: 4px; width: 12px; height: 12px; border-radius: 50%;
    background: #e5484d; border: 2px solid #fff; }
  iframe { position: fixed; right: 20px; bottom: 88px; z-index: 2147483647;
    width: 380px; height: 600px; max-height: calc(100vh - 108px); max-width: calc(100vw - 40px);
    border: 0; border-radius: 12px; background: #fff; box-shadow: 0 8px 32px rgba(16, 33, 58, .25); }
  @media (max-width: 640px) {
    iframe { inset: 0; width: 100%; height: 100%; max-height: none; max-width: none; border-radius: 0; }
    :host([data-open]) button.launcher { display: none; }
  }
  [hidden] { display: none !important; }
`
const ICON =
  '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"' +
  ' aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>'

const script = document.currentScript as HTMLScriptElement | null
if (script?.src) start(script)

function start(script: HTMLScriptElement) {
  const appUrl = new URL('./', script.src)
  const appOrigin = appUrl.origin
  appUrl.searchParams.set('host', location.origin)
  appUrl.searchParams.set('product', script.dataset.product ?? '')
  const tokenUrl = script.dataset.tokenUrl ?? '/support/token'

  const container = document.createElement('div')
  const root = container.attachShadow({ mode: 'open' })
  root.innerHTML = `<style>${STYLE}</style>` // static markup only, never content
  const button = document.createElement('button')
  button.className = 'launcher'
  button.setAttribute('aria-label', 'Чат підтримки')
  button.setAttribute('aria-expanded', 'false')
  button.innerHTML = ICON
  const dot = document.createElement('span')
  dot.className = 'dot'
  dot.hidden = true
  button.append(dot)
  root.append(button)
  document.body.append(container)

  let frame: HTMLIFrameElement | null = null
  let open = false

  const send = (message: ToApp) => {
    const envelope: Envelope<ToApp> = { channel: CHANNEL, ...message }
    frame?.contentWindow?.postMessage(envelope, appOrigin)
  }

  const setOpen = (value: boolean) => {
    open = value
    button.setAttribute('aria-expanded', String(value))
    container.toggleAttribute('data-open', value)
    if (value && !frame) {
      frame = document.createElement('iframe')
      frame.title = 'Чат підтримки'
      frame.src = appUrl.href
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms')
      root.append(frame)
    }
    if (frame) frame.hidden = !value
    if (value) {
      dot.hidden = true
      frame?.focus()
      send({ type: 'opened' })
    } else {
      send({ type: 'closed' })
      button.focus()
    }
  }

  const fetchToken = async (): Promise<ToApp> => {
    try {
      const response = await fetch(tokenUrl, { method: 'POST', credentials: 'same-origin' })
      if (response.status === 401 || response.status === 403) return { type: 'logged-out' }
      if (!response.ok) return { type: 'token-error' }
      const data = (await response.json()) as { token?: unknown; expires_in?: unknown }
      if (typeof data.token !== 'string' || typeof data.expires_in !== 'number') {
        return { type: 'token-error' }
      }
      return { type: 'token', token: data.token, expiresIn: data.expires_in }
    } catch {
      return { type: 'token-error' }
    }
  }

  window.addEventListener('message', (event) => {
    if (!frame || event.origin !== appOrigin || event.source !== frame.contentWindow) return
    if (!isEnvelope(event.data)) return
    const message = event.data as Envelope<ToLoader>
    if (message.type === 'token-request') fetchToken().then(send)
    else if (message.type === 'close') setOpen(false)
    else if (message.type === 'unread' && !open) dot.hidden = message.count === 0
  })

  button.addEventListener('click', () => setOpen(!open))
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && open) setOpen(false)
  })
}

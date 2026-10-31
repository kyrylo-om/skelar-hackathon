import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  AuthError,
  type Confirmation,
  type Message,
  confirmAction,
  getChat,
  sendMessage,
} from './api'
import { embedded, onLoaderMessage, toLoader } from './host'
import { onTokenState, refreshToken } from './token'

type Phase = 'connecting' | 'ready' | 'logged-out' | 'expired' | 'unavailable'

const WHO: Record<Message['role'], string> = {
  customer: 'Ви',
  ai: 'AI',
  operator: 'Спеціаліст',
  system: 'Система',
}
const NOTICE: Record<Exclude<Phase, 'ready'>, [string, string | null]> = {
  connecting: ['Підключаємось…', null],
  'logged-out': ['Увійдіть у свій акаунт, щоб написати в підтримку.', 'Я вже увійшов'],
  expired: ['Сесія завершилась. Увійдіть знову або оновіть сторінку.', 'Спробувати ще'],
  unavailable: ['Підтримка зараз недоступна.', 'Спробувати ще'],
}
const POLL_MS = 5000

export default function App() {
  const [phase, setPhase] = useState<Phase>(embedded ? 'connecting' : 'unavailable')
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState<string | null>(null) // sent, not yet confirmed by the server
  const [sending, setSending] = useState(false)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const known = useRef(new Set<number>())
  const isOpen = useRef(true) // the loader creates the iframe when the panel first opens
  const unread = useRef(0)
  const phaseRef = useRef(phase)
  const input = useRef<HTMLTextAreaElement>(null)
  const end = useRef<HTMLDivElement>(null)

  const merge = useCallback((incoming: Message[]) => {
    const fresh = incoming.filter((m) => !known.current.has(m.id))
    if (!fresh.length) return
    fresh.forEach((m) => known.current.add(m.id))
    setMessages((current) => [...current, ...fresh])
    if (!isOpen.current) {
      unread.current += fresh.filter((m) => m.role !== 'customer').length
      toLoader({ type: 'unread', count: unread.current })
    }
  }, [])

  const fail = useCallback((err: unknown) => {
    // Token problems arrive through onTokenState; everything else is shown in the chat.
    if (!(err instanceof AuthError)) setError('Не вдалося зв’язатися з підтримкою.')
  }, [])

  const refresh = useCallback(async () => {
    const chat = await getChat()
    merge(chat.messages)
    setConfirmation(chat.pendingConfirmation)
  }, [merge])

  const connect = useCallback(async () => {
    setPhase('connecting')
    setError('')
    if ((await refreshToken()) !== 'ok') return
    try {
      await refresh()
      setPhase('ready')
    } catch (err) {
      fail(err)
      if (!(err instanceof AuthError)) setPhase('unavailable')
    }
  }, [refresh, fail])

  useEffect(() => {
    if (!embedded) return
    const stopToken = onTokenState((state) => {
      if (state === 'logged-out') setPhase('logged-out')
      else if (state === 'error') setPhase('expired')
    })
    const stopLoader = onLoaderMessage((message) => {
      if (message.type === 'opened') {
        isOpen.current = true
        unread.current = 0
        input.current?.focus()
        if (phaseRef.current === 'logged-out') connect() // they may have signed in since
      } else if (message.type === 'closed') {
        isOpen.current = false
      }
    })
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') toLoader({ type: 'close' })
    }
    document.addEventListener('keydown', onKey)
    connect()
    return () => {
      stopToken()
      stopLoader()
      document.removeEventListener('keydown', onKey)
    }
  }, [connect])

  useEffect(() => {
    phaseRef.current = phase
  }, [phase])

  // Operator replies and anything else written outside this tab arrive by polling.
  useEffect(() => {
    if (phase !== 'ready' || sending) return
    const timer = setInterval(() => refresh().catch(fail), POLL_MS)
    return () => clearInterval(timer)
  }, [phase, sending, refresh, fail])

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, draft, sending])

  useEffect(() => {
    if (phase === 'ready') input.current?.focus()
  }, [phase])

  const submit = async () => {
    const value = text.trim()
    if (!value || sending) return
    setSending(true)
    setDraft(value)
    setText('')
    setError('')
    try {
      await sendMessage(value, (event) => {
        if (event.event === 'message') {
          merge([event.data])
          if (event.data.role === 'customer') setDraft(null)
        } else if (event.event === 'error') {
          setError(event.data.message)
        }
      })
      await refresh().catch(fail) // picks up an action the reply asked the customer to confirm
    } catch (err) {
      fail(err)
      setText(value) // nothing was delivered, so give the text back
    } finally {
      setDraft(null)
      setSending(false)
    }
  }

  const confirm = async (id: string) => {
    setConfirming(true)
    setError('')
    try {
      await confirmAction(id)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setError('Цю дію вже не можна підтвердити.')
      else fail(err)
    } finally {
      await refresh().catch(fail)
      setConfirming(false)
    }
  }

  const [notice, action] = phase === 'ready' ? [null, null] : NOTICE[phase]

  return (
    <div className="widget">
      <header>
        <div>
          <b>Підтримка</b>
          <span>AI-асистент, за потреби підключається спеціаліст</span>
        </div>
        <button className="close" aria-label="Закрити чат" onClick={() => toLoader({ type: 'close' })}>
          ×
        </button>
      </header>
      <div className="log" role="log" aria-live="polite">
        {phase === 'ready' && messages.length === 0 && !draft && (
          <p className="hint">Напишіть, чим вам допомогти.</p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            <span className="who">{WHO[m.role]}</span>
            <div className="bubble">{m.text}</div>
          </div>
        ))}
        {draft && (
          <div className="msg customer pending">
            <span className="who">{WHO.customer}</span>
            <div className="bubble">{draft}</div>
          </div>
        )}
        {confirmation && phase === 'ready' && (
          <div className="confirm">
            <p>{confirmation.description}</p>
            <button disabled={confirming || sending} onClick={() => confirm(confirmation.id)}>
              Підтвердити
            </button>
          </div>
        )}
        {sending && <p className="hint">Обробляємо запит…</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div ref={end} />
      </div>
      {phase === 'ready' ? (
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <textarea
            ref={input}
            rows={2}
            maxLength={2000}
            value={text}
            aria-label="Повідомлення"
            placeholder="Напишіть повідомлення…"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit()
              }
            }}
          />
          <button disabled={sending || !text.trim()}>Надіслати</button>
        </form>
      ) : (
        <div className="notice">
          <p>{notice}</p>
          {action && embedded && <button onClick={connect}>{action}</button>}
        </div>
      )}
    </div>
  )
}

// The customer's token: from the loader, in memory only, refreshed at 80% of its lifetime.
import { onLoaderMessage, toLoader } from './host'

export type TokenState = 'ok' | 'logged-out' | 'error'

const ANSWER_TIMEOUT_MS = 10_000
const RETRY_DELAYS_MS = [1000, 3000]

let token: string | null = null
let refreshTimer: ReturnType<typeof setTimeout> | undefined
let inFlight: Promise<TokenState> | null = null
let answer: ((state: TokenState) => void) | null = null
const listeners = new Set<(state: TokenState) => void>()

onLoaderMessage((message) => {
  if (message.type === 'token') {
    token = message.token
    clearTimeout(refreshTimer)
    refreshTimer = setTimeout(refreshToken, message.expiresIn * 800)
    answer?.('ok')
  } else if (message.type === 'logged-out') {
    answer?.('logged-out')
  } else if (message.type === 'token-error') {
    answer?.('error')
  }
})

function ask(): Promise<TokenState> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve('error'), ANSWER_TIMEOUT_MS)
    answer = (state) => {
      clearTimeout(timer)
      answer = null
      resolve(state)
    }
    toLoader({ type: 'token-request' })
  })
}

async function fetchWithRetries(): Promise<TokenState> {
  let state = await ask()
  for (const delay of RETRY_DELAYS_MS) {
    if (state !== 'error') break
    await new Promise((resolve) => setTimeout(resolve, delay))
    state = await ask()
  }
  if (state !== 'ok') {
    token = null
    clearTimeout(refreshTimer)
  }
  for (const listener of listeners) listener(state)
  return state
}

/** Get a fresh token from the host; concurrent callers share one request. */
export function refreshToken(): Promise<TokenState> {
  inFlight ??= fetchWithRetries().finally(() => {
    inFlight = null
  })
  return inFlight
}

export const currentToken = () => token

/** Hear about every refresh outcome, including the timed ones in the background. */
export function onTokenState(listener: (state: TokenState) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

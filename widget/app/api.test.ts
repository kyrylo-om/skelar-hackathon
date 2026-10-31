import { describe, expect, it } from 'vitest'
import { parseSse } from './api'

describe('parseSse', () => {
  it('returns complete events and keeps the unfinished tail', () => {
    const { events, rest } = parseSse(
      'event: status\ndata: {"stage":"working"}\n\nevent: message\ndata: {"id":1,"role":"ai","text":"При',
    )
    expect(events).toEqual([{ event: 'status', data: { stage: 'working' } }])
    expect(parseSse(rest + 'віт","at":"x"}\n\nevent: done\ndata: {"status":"ai_handling"}\n\n')).toEqual({
      events: [
        { event: 'message', data: { id: 1, role: 'ai', text: 'Привіт', at: 'x' } },
        { event: 'done', data: { status: 'ai_handling' } },
      ],
      rest: '',
    })
  })

  it('accepts CRLF line endings', () => {
    expect(parseSse('event: done\r\ndata: {"status":"x"}\r\n\r\n').events).toEqual([
      { event: 'done', data: { status: 'x' } },
    ])
  })
})

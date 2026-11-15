import { describe, expect, it } from 'vitest'
import sample from '../../../shared/examples/sample-records.json'
import { flattenItems } from './plan'
import { escapeText, toIcs } from './ics'
import type { FileRecord } from './types'

const items = flattenItems(sample.records as FileRecord[])
const now = new Date('2026-11-15T12:00:00Z')

describe('toIcs', () => {
  const ics = toIcs(items, now)

  it('is a CRLF-delimited VCALENDAR', () => {
    expect(ics.startsWith('BEGIN:VCALENDAR\r\n')).toBe(true)
    expect(ics.endsWith('END:VCALENDAR\r\n')).toBe(true)
    expect(ics.replace(/\r\n/g, '')).not.toMatch(/\n/)
  })

  it('has one event per item, deduped', () => {
    const doubled = toIcs([...items, ...items], now)
    expect(doubled.match(/BEGIN:VEVENT/g)).toHaveLength(items.length)
  })

  it('example 5: HW 4 is an all-day event on Nov 12', () => {
    const ev = ics.split('BEGIN:VEVENT').find((e) => e.includes('UID:dsci475-hw4@'))!
    expect(ev).toContain('DTSTART;VALUE=DATE:20261112')
    expect(ev).toContain('DTEND;VALUE=DATE:20261113')
    expect(ev).toContain('SUMMARY:[DSCI475] HW 4')
  })

  it('handles month rollover for DTEND', () => {
    const out = toIcs([{ id: 'x', type: 'exam', text: 't', date: '2026-11-30', sources: ['a'], class: null }], now)
    expect(out).toContain('DTEND;VALUE=DATE:20261201')
  })

  it('timed items get a DATE-TIME start', () => {
    const out = toIcs([{ id: 'x', type: 'exam', text: 't', date: '2026-12-10', time: '13:30', sources: ['a'], class: null }], now)
    expect(out).toContain('DTSTART:20261210T133000')
  })

  it('folds long lines to 75 octets', () => {
    for (const line of ics.split('\r\n')) expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75)
  })
})

describe('escapeText', () => {
  it('escapes special characters', () => {
    expect(escapeText('a,b;c\\d\ne')).toBe('a\\,b\\;c\\\\d\\ne')
  })
})

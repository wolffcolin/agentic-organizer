import type { PlannedItem } from './types'

// Minimal RFC 5545 writer. Items become all-day events, or 1-hour events if they have a time.

const CRLF = '\r\n'

export function toIcs(items: PlannedItem[], now: Date = new Date()): string {
  const stamp = utcStamp(now)
  const seen = new Set<string>()
  const lines: string[] = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Group5//Student Folder Organizer//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH'
  ]

  for (const it of items) {
    if (seen.has(it.id)) continue
    seen.add(it.id)

    const day = it.date.replace(/-/g, '')
    const summary = it.class ? `[${it.class}] ${it.text}` : it.text
    const desc = [it.note, `Sources: ${it.sources.join(', ')}`].filter(Boolean).join('\n')

    lines.push('BEGIN:VEVENT', `UID:${it.id}@student-folder-organizer`, `DTSTAMP:${stamp}`)
    if (it.time) {
      const t = it.time.replace(':', '') + '00'
      lines.push(`DTSTART:${day}T${t}`, 'DURATION:PT1H')
    } else {
      lines.push(`DTSTART;VALUE=DATE:${day}`, `DTEND;VALUE=DATE:${nextDay(it.date)}`)
    }
    lines.push(`SUMMARY:${escapeText(summary)}`, `DESCRIPTION:${escapeText(desc)}`)
    lines.push(`CATEGORIES:${it.type.toUpperCase()}`, 'END:VEVENT')
  }

  lines.push('END:VCALENDAR')
  return lines.map(fold).join(CRLF) + CRLF
}

export function escapeText(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n')
}

/** Fold lines longer than 75 octets (RFC 5545 §3.1). */
function fold(line: string): string {
  const enc = new TextEncoder()
  if (enc.encode(line).length <= 75) return line
  const parts: string[] = []
  let cur = ''
  let limit = 75
  for (const ch of line) {
    if (enc.encode(cur + ch).length > limit) {
      parts.push(cur)
      cur = ''
      limit = 74 // continuation lines start with a space
    }
    cur += ch
  }
  parts.push(cur)
  return parts.join(CRLF + ' ')
}

function nextDay(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + 1))
  return dt.toISOString().slice(0, 10).replace(/-/g, '')
}

function utcStamp(d: Date): string {
  return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')
}

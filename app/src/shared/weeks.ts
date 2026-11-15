import { addDays, format, parseISO, startOfWeek } from 'date-fns'
import type { PlannedItem } from './types'

export interface Week {
  /** Monday of the week, YYYY-MM-DD */
  start: string
  /** Sunday of the week, YYYY-MM-DD */
  end: string
  items: PlannedItem[]
}

export function weekStartOf(date: string): string {
  return format(startOfWeek(parseISO(date), { weekStartsOn: 1 }), 'yyyy-MM-dd')
}

/** Group items into Monday-start weeks, sorted by week then by date. */
export function groupByWeek(items: PlannedItem[]): Week[] {
  const byStart = new Map<string, PlannedItem[]>()
  for (const it of items) {
    const s = weekStartOf(it.date)
    if (!byStart.has(s)) byStart.set(s, [])
    byStart.get(s)!.push(it)
  }
  return [...byStart.keys()].sort().map((start) => ({
    start,
    end: format(addDays(parseISO(start), 6), 'yyyy-MM-dd'),
    items: byStart.get(start)!.sort((a, b) => a.date.localeCompare(b.date))
  }))
}

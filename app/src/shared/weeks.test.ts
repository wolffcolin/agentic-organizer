import { describe, expect, it } from 'vitest'
import sample from '../../../shared/examples/sample-records.json'
import { flattenItems } from './plan'
import type { FileRecord } from './types'
import { groupByWeek, weekStartOf } from './weeks'

const items = flattenItems(sample.records as FileRecord[])
const weeks = groupByWeek(items)
const weekOf = (id: string) => weeks.find((w) => w.items.some((i) => i.id === id))?.start

describe('groupByWeek', () => {
  it('weeks start on Monday', () => {
    expect(weekStartOf('2026-11-15')).toBe('2026-11-09') // Sunday -> previous Monday
    expect(weekStartOf('2026-11-16')).toBe('2026-11-16')
  })

  it('example 5: HW 4 lands in the week of Nov 9 on Nov 12, not Nov 10', () => {
    expect(weekOf('dsci475-hw4')).toBe('2026-11-09')
    expect(items.find((i) => i.id === 'dsci475-hw4')?.date).toBe('2026-11-12')
  })

  it('example 2: midterm and final land in the right weeks', () => {
    expect(weekOf('f2-mid')).toBe('2026-10-12')
    expect(weekOf('f2-final')).toBe('2026-12-07')
  })

  it('example 3: "Study ch. 7" comes before the midterm in the same week', () => {
    const w = weeks.find((w) => w.start === '2026-10-12')!
    const ids = w.items.map((i) => i.id)
    expect(ids.indexOf('f3-study7')).toBeLessThan(ids.indexOf('f2-mid'))
  })

  it('weeks are sorted and every item is placed exactly once', () => {
    const starts = weeks.map((w) => w.start)
    expect(starts).toEqual([...starts].sort())
    expect(weeks.reduce((n, w) => n + w.items.length, 0)).toBe(items.length)
  })
})

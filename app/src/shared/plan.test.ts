import { describe, expect, it } from 'vitest'
import sample from '../../../shared/examples/sample-records.json'
import { buildApprovedPlan, defaultChecked, flattenItems, proposedPath } from './plan'
import type { FileRecord } from './types'

const records = sample.records as FileRecord[]

describe('proposedPath', () => {
  it('example 1: renames and moves Lecture7.pdf', () => {
    expect(proposedPath(records[0])).toBe('CSCI575/LectureNotes/CSCI575_Lec07_Eigenvalues.pdf')
  })
  it('example 4: needs_user proposes nothing', () => {
    expect(proposedPath(records[3])).toBeNull()
  })
})

describe('buildApprovedPlan', () => {
  it('rejecting 3 proposed changes leaves those files out of the plan', () => {
    const checked = defaultChecked(records)
    for (const id of ['f1', 'f2', 'f3']) checked.delete(id)

    const plan = buildApprovedPlan('/root', records, checked)
    const movedIds = plan.approved_moves.map((m) => m.id)

    expect(movedIds).toEqual(['f5'])
    expect(plan.rejected_ids).toEqual(expect.arrayContaining(['f1', 'f2', 'f3']))
  })

  it('never moves a needs_user file even if checked', () => {
    const checked = new Set(['f4'])
    const plan = buildApprovedPlan('/root', records, checked)
    expect(plan.approved_moves).toEqual([])
  })

  it('unchecked items are rejected, checked ones approved', () => {
    const checked = new Set(['dsci475-hw4'])
    const plan = buildApprovedPlan('/root', records, checked)
    expect(plan.approved_item_ids).toEqual(['dsci475-hw4'])
    expect(plan.rejected_ids).toContain('f2-mid')
  })
})

describe('defaultChecked', () => {
  it('leaves needs_user and low-confidence files unchecked', () => {
    const checked = defaultChecked(records)
    expect(checked.has('f4')).toBe(false)
    expect(checked.has('f1')).toBe(true)
  })
})

describe('flattenItems', () => {
  it('attaches class, sorts by date, and dedupes by id', () => {
    const dup = [...records, records[4]]
    const items = flattenItems(dup)
    expect(items.filter((i) => i.id === 'dsci475-hw4')).toHaveLength(1)
    expect(items[0].date <= items[items.length - 1].date).toBe(true)
    expect(items.find((i) => i.id === 'f3-study7')?.class).toBe('CSCI498')
  })
})

import type { ApprovedPlan, FileRecord, Move, PlannedItem } from './types'

/** Records below this confidence start unchecked so the user must opt in. */
export const LOW_CONFIDENCE = 0.6

/** Destination path of a record, or null if it proposes no change. */
export function proposedPath(r: FileRecord): string | null {
  if (r.needs_user) return null
  const name = r.proposed_name ?? basename(r.path)
  const folder = r.proposed_folder ?? dirname(r.path)
  const to = folder ? `${folder}/${name}` : name
  return to === r.path ? null : to
}

/** Ids that start checked in the preview: confident moves and every extracted item. */
export function defaultChecked(records: FileRecord[]): Set<string> {
  const ids = new Set<string>()
  for (const r of records) {
    if (proposedPath(r) && r.confidence >= LOW_CONFIDENCE) ids.add(r.id)
    for (const it of r.items) ids.add(it.id)
  }
  return ids
}

/** Build the plan sent to the executor. Unchecked moves are never included. */
export function buildApprovedPlan(root: string, records: FileRecord[], checked: Set<string>): ApprovedPlan {
  const approved_moves: Move[] = []
  const rejected_ids: string[] = []
  const approved_item_ids: string[] = []

  for (const r of records) {
    const to = proposedPath(r)
    if (to) {
      if (checked.has(r.id)) approved_moves.push({ id: r.id, from: r.path, to })
      else rejected_ids.push(r.id)
    }
    for (const it of r.items) {
      if (checked.has(it.id)) approved_item_ids.push(it.id)
      else rejected_ids.push(it.id)
    }
  }
  return { root, approved_moves, rejected_ids, approved_item_ids }
}

/** Flatten items across records, attach the class, dedupe by id, sort by date. */
export function flattenItems(records: FileRecord[], only?: Set<string>): PlannedItem[] {
  const seen = new Map<string, PlannedItem>()
  for (const r of records) {
    for (const it of r.items) {
      if (only && !only.has(it.id)) continue
      if (!seen.has(it.id)) seen.set(it.id, { ...it, class: r.class })
    }
  }
  return [...seen.values()].sort((a, b) => (a.date + (a.time ?? '')).localeCompare(b.date + (b.time ?? '')))
}

function basename(p: string): string {
  const i = p.lastIndexOf('/')
  return i < 0 ? p : p.slice(i + 1)
}

function dirname(p: string): string {
  const i = p.lastIndexOf('/')
  return i < 0 ? '' : p.slice(0, i)
}

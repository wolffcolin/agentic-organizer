// Mirrors shared/handoff.schema.json. Keep the two in sync.

export type ItemType = 'deadline' | 'exam' | 'todo'

export interface Item {
  id: string
  type: ItemType
  text: string
  /** ISO date, YYYY-MM-DD */
  date: string
  /** Optional 24h local time, HH:MM */
  time?: string
  /** Every file this item was found in, relative to the scanned root. */
  sources: string[]
  note?: string
}

export interface FileRecord {
  id: string
  /** Current path, relative to the scanned root, forward slashes. */
  path: string
  class: string | null
  proposed_name: string | null
  proposed_folder: string | null
  confidence: number
  needs_user: boolean
  question?: string
  summary?: string
  items: Item[]
}

export interface ScanResult {
  root: string
  scanned_at?: string
  records: FileRecord[]
}

export interface Move {
  id: string
  from: string
  to: string
}

export interface ApprovedPlan {
  root: string
  approved_moves: Move[]
  rejected_ids: string[]
  approved_item_ids: string[]
}

export interface ApplyResult {
  ok: boolean
  moved: number
  message: string
}

/** An item flattened with the class of the record it came from (used by the planner and .ics export). */
export interface PlannedItem extends Item {
  class: string | null
}

import { app } from 'electron'
import { mkdir, writeFile } from 'fs/promises'
import { join } from 'path'
import sample from '../../../shared/examples/sample-records.json'
import type { ApplyResult, ApprovedPlan, ScanResult } from '../shared/types'

/**
 * Everything the UI needs from the Organizer/Extractor/Executor.
 * Swap MockBackend for RealBackend once teammates' CLI is ready.
 */
export interface Backend {
  scan(folder: string): Promise<ScanResult>
  apply(plan: ApprovedPlan): Promise<ApplyResult>
  undo(): Promise<ApplyResult>
}

/** Returns synthetic records. Never touches the user's files. */
export class MockBackend implements Backend {
  async scan(folder: string): Promise<ScanResult> {
    await new Promise((r) => setTimeout(r, 400)) // feel like a real scan
    return { ...(sample as ScanResult), root: folder }
  }

  async apply(plan: ApprovedPlan): Promise<ApplyResult> {
    const dir = app.getPath('userData')
    await mkdir(dir, { recursive: true })
    const out = join(dir, 'approved-plan.json')
    await writeFile(out, JSON.stringify(plan, null, 2), 'utf8')
    return {
      ok: true,
      moved: 0,
      message: `Mock backend: ${plan.approved_moves.length} move(s) approved, written to ${out}. No files were changed.`
    }
  }

  async undo(): Promise<ApplyResult> {
    return { ok: true, moved: 0, message: 'Mock backend: nothing to undo.' }
  }
}

/**
 * TODO(week of Nov 16): spawn the organizer agent (Docker) and executor via child_process.
 * Proposed CLI contract to agree with Amari/Colin:
 *   organizer scan <folder> --out <records.json>
 *   executor apply <approved-plan.json>
 *   executor undo
 */
export class RealBackend implements Backend {
  async scan(): Promise<ScanResult> {
    throw new Error('Real backend not wired yet. Waiting on the organizer CLI.')
  }
  async apply(): Promise<ApplyResult> {
    throw new Error('Real backend not wired yet. Waiting on the executor CLI.')
  }
  async undo(): Promise<ApplyResult> {
    throw new Error('Real backend not wired yet. Waiting on the executor CLI.')
  }
}

export function createBackend(): Backend {
  return process.env.ORGANIZER_BACKEND === 'real' ? new RealBackend() : new MockBackend()
}

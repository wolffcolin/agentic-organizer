import { useMemo, useState } from 'react'
import { buildApprovedPlan, defaultChecked, flattenItems } from '../../shared/plan'
import type { ScanResult } from '../../shared/types'
import PreviewScreen from './components/PreviewScreen'
import WeeklyView from './components/WeeklyView'

type Tab = 'preview' | 'weekly'

export default function App() {
  const [folder, setFolder] = useState<string | null>(null)
  const [scan, setScan] = useState<ScanResult | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<string>('Pick your semester folder to begin.')
  const [tab, setTab] = useState<Tab>('preview')

  const records = scan?.records ?? []
  const plannedItems = useMemo(() => flattenItems(records, checked), [records, checked])

  async function run<T>(label: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true)
    setStatus(label)
    try {
      return await fn()
    } catch (e) {
      setStatus(`Error: ${(e as Error).message}`)
      return undefined
    } finally {
      setBusy(false)
    }
  }

  async function pickFolder() {
    const f = await window.api.pickFolder()
    if (f) {
      setFolder(f)
      setScan(null)
      setStatus('Folder selected. Click Scan.')
    }
  }

  async function doScan() {
    if (!folder) return
    const res = await run('Scanning…', () => window.api.scan(folder))
    if (res) {
      setScan(res)
      setChecked(defaultChecked(res.records))
      setStatus(`Found ${res.records.length} files. Review the proposed changes below.`)
    }
  }

  function toggle(id: string) {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function approve() {
    if (!scan) return
    const plan = buildApprovedPlan(scan.root, records, checked)
    const res = await run('Applying approved changes…', () => window.api.apply(plan))
    if (res) setStatus(res.message)
  }

  async function undo() {
    const res = await run('Undoing…', () => window.api.undo())
    if (res) setStatus(res.message)
  }

  async function openFile(path: string) {
    const err = await window.api.openFile(path)
    if (err) setStatus(`Could not open ${path}: ${err}`)
  }

  async function exportIcs() {
    const saved = await run('Exporting calendar…', () => window.api.exportIcs(plannedItems))
    if (saved) setStatus(`Saved ${plannedItems.length} events to ${saved}`)
    else if (saved === null) setStatus('Export cancelled.')
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Student Folder Organizer</h1>
        <div className="scanbar">
          <button onClick={pickFolder} disabled={busy}>
            Pick folder
          </button>
          <span className="folder" title={folder ?? ''}>
            {folder ?? 'No folder selected'}
          </span>
          <button className="primary" onClick={doScan} disabled={!folder || busy}>
            Scan
          </button>
        </div>
      </header>

      <p className="status" role="status">
        {status}
      </p>

      {scan && (
        <>
          <nav className="tabs">
            <button className={tab === 'preview' ? 'active' : ''} onClick={() => setTab('preview')}>
              Preview changes
            </button>
            <button className={tab === 'weekly' ? 'active' : ''} onClick={() => setTab('weekly')}>
              Weekly plan ({plannedItems.length})
            </button>
            <span className="spacer" />
            <button onClick={exportIcs} disabled={busy || plannedItems.length === 0}>
              Export .ics
            </button>
          </nav>

          {tab === 'preview' ? (
            <PreviewScreen
              records={records}
              checked={checked}
              onToggle={toggle}
              onApprove={approve}
              onUndo={undo}
              onOpenFile={openFile}
              busy={busy}
            />
          ) : (
            <WeeklyView items={plannedItems} onOpenFile={openFile} />
          )}
        </>
      )}
    </div>
  )
}

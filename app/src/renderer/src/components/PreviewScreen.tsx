import { flattenItems, LOW_CONFIDENCE, proposedPath } from '../../../shared/plan'
import type { FileRecord } from '../../../shared/types'

interface Props {
  records: FileRecord[]
  checked: Set<string>
  onToggle: (id: string) => void
  onApprove: () => void
  onUndo: () => void
  onOpenFile: (path: string) => void
  busy: boolean
}

export default function PreviewScreen({ records, checked, onToggle, onApprove, onUndo, onOpenFile, busy }: Props) {
  const items = flattenItems(records)
  const moves = records.filter((r) => proposedPath(r) || r.needs_user)
  const approvedMoves = moves.filter((r) => proposedPath(r) && checked.has(r.id)).length

  return (
    <main className="preview">
      <section>
        <h2>File changes</h2>
        <table>
          <thead>
            <tr>
              <th />
              <th>Current</th>
              <th>Proposed</th>
              <th>Class</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {moves.map((r) => {
              const to = proposedPath(r)
              const low = r.confidence < LOW_CONFIDENCE
              return (
                <tr key={r.id} className={r.needs_user ? 'ask' : low ? 'low' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={checked.has(r.id)}
                      disabled={!to}
                      onChange={() => onToggle(r.id)}
                      aria-label={`Approve change for ${r.path}`}
                    />
                  </td>
                  <td>
                    <button className="link" onClick={() => onOpenFile(r.path)}>
                      {r.path}
                    </button>
                    {r.summary && <div className="muted">{r.summary}</div>}
                  </td>
                  <td>{to ?? <em>Ask me: {r.question ?? 'not sure where this goes'}</em>}</td>
                  <td>{r.class ?? '?'}</td>
                  <td>
                    <span className={`badge ${low ? 'badge-low' : ''}`}>{Math.round(r.confidence * 100)}%</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Deadlines &amp; to-dos</h2>
        <table>
          <thead>
            <tr>
              <th />
              <th>Date</th>
              <th>Item</th>
              <th>Class</th>
              <th>Sources</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={checked.has(it.id)}
                    onChange={() => onToggle(it.id)}
                    aria-label={`Keep ${it.text}`}
                  />
                </td>
                <td className="nowrap">
                  {it.date}
                  {it.time && ` ${it.time}`}
                </td>
                <td>
                  <span className={`type type-${it.type}`}>{it.type}</span> {it.text}
                  {it.note && <div className="note">{it.note}</div>}
                </td>
                <td>{it.class ?? '?'}</td>
                <td>
                  {it.sources.map((s) => (
                    <button key={s} className="link block" onClick={() => onOpenFile(s)}>
                      {s}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <footer className="actions">
        <button className="primary" onClick={onApprove} disabled={busy}>
          Approve {approvedMoves} change{approvedMoves === 1 ? '' : 's'}
        </button>
        <button onClick={onUndo} disabled={busy}>
          Undo last apply
        </button>
      </footer>
    </main>
  )
}

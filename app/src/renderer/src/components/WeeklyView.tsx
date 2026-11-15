import { format, parseISO } from 'date-fns'
import { useMemo, useState } from 'react'
import type { PlannedItem } from '../../../shared/types'
import { groupByWeek, weekStartOf } from '../../../shared/weeks'

interface Props {
  items: PlannedItem[]
  onOpenFile: (path: string) => void
}

export default function WeeklyView({ items, onOpenFile }: Props) {
  const weeks = useMemo(() => groupByWeek(items), [items])
  const today = weekStartOf(format(new Date(), 'yyyy-MM-dd'))
  const initial = Math.max(0, weeks.findIndex((w) => w.start >= today))
  const [idx, setIdx] = useState(initial)

  if (weeks.length === 0) return <p className="muted">No approved deadlines yet.</p>
  const i = Math.min(idx, weeks.length - 1)
  const week = weeks[i]

  return (
    <main className="weekly">
      <div className="weeknav">
        <button onClick={() => setIdx(i - 1)} disabled={i === 0}>
          ← Prev
        </button>
        <h2>
          Week of {format(parseISO(week.start), 'MMM d')} – {format(parseISO(week.end), 'MMM d, yyyy')}
          {week.start === today && <span className="badge">this week</span>}
        </h2>
        <button onClick={() => setIdx(i + 1)} disabled={i === weeks.length - 1}>
          Next →
        </button>
      </div>

      <ul className="cards">
        {week.items.map((it) => (
          <li key={it.id} className={`card type-${it.type}`}>
            <div className="card-date">{format(parseISO(it.date), 'EEE MMM d')}</div>
            <div className="card-title">
              <span className={`type type-${it.type}`}>{it.type}</span> {it.class && <strong>{it.class}</strong>}{' '}
              {it.text}
            </div>
            {it.note && <div className="note">{it.note}</div>}
            <div className="card-files">
              {it.sources.map((s) => (
                <button key={s} className="link" onClick={() => onOpenFile(s)}>
                  📄 {s}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>

      <details className="allweeks">
        <summary>All weeks</summary>
        <ul>
          {weeks.map((w, j) => (
            <li key={w.start}>
              <button className="link" onClick={() => setIdx(j)}>
                {format(parseISO(w.start), 'MMM d')}: {w.items.length} item{w.items.length === 1 ? '' : 's'}
              </button>
            </li>
          ))}
        </ul>
      </details>
    </main>
  )
}

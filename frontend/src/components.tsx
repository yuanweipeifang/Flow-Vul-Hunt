import type { CSSProperties, PropsWithChildren, ReactNode } from 'react'

export function PageHeader({ title, description, children }: PropsWithChildren<{ title: string; description: string }>) {
  return (
    <div className="page-header">
      <div>
        <p className="eyebrow">EVIDENCE-BASED SECURITY OPERATIONS</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children ? <div className="page-actions">{children}</div> : null}
    </div>
  )
}

export function Card({ title, description, children, actions }: PropsWithChildren<{ title?: string; description?: string; actions?: ReactNode }>) {
  return (
    <section className="card">
      {(title || description || actions) && (
        <div className="card-header">
          <div>
            {title ? <h2>{title}</h2> : null}
            {description ? <p>{description}</p> : null}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

export function Badge({ text, tone = 'blue' }: { text: string | number | null | undefined; tone?: string }) {
  return <span className={`badge ${tone}`}>{String(text ?? 'unknown')}</span>
}

export function Empty({ text = '后端返回空数据' }: { text?: string }) {
  return <div className="empty">{text}</div>
}

export function Loading({ text = '正在加载后端真实数据…' }: { text?: string }) {
  return <div className="loading">{text}</div>
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error)
  return <div className="error">{message}</div>
}

export function DataTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: ReactNode[][] }) {
  if (!rows.length) return <Empty />
  return (
    <div className="table-wrap">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>{headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  )
}

export function BarList({ data, accent = '#0428cb' }: { data: Record<string, number>; accent?: string }) {
  const entries = Object.entries(data || {})
  if (!entries.length) return <Empty />
  const max = Math.max(...entries.map(([, value]) => Number(value) || 0), 1)
  return (
    <div className="bars">
      {entries.map(([key, value]) => {
        const count = Number(value) || 0
        const width = Math.max((count / max) * 100, count > 0 ? 3 : 0)
        return (
          <div className="bar-row" key={key}>
            <span className="bar-label" title={key}>{key}</span>
            <span className="bar-track" aria-hidden="true"><span className="bar-fill" style={{ width: `${width}%`, background: accent }} /></span>
            <span className="bar-value">{count.toLocaleString('zh-CN')}</span>
          </div>
        )
      })}
    </div>
  )
}

const pieColors = ['#34fcff', '#123dff', '#f59e0b', '#22c55e', '#c084fc', '#f87171']

function distributionColor(key: string, index: number) {
  const value = key.toLowerCase()
  if (value === 'critical') return '#ef4444'
  if (value === 'high') return '#123dff'
  if (value === 'medium') return '#34fcff'
  return pieColors[index % pieColors.length]
}

export function DistributionPanel({ data, accent = '#34fcff' }: { data: Record<string, number> | undefined; accent?: string }) {
  const entries = Object.entries(data || {})
    .map(([key, value]) => [key, Number(value) || 0] as const)
    .filter(([, value]) => value > 0)
  const total = entries.reduce((sum, [, value]) => sum + value, 0)
  const max = Math.max(...entries.map(([, value]) => value), 1)
  let cursor = 0
  const gradient = entries.length
    ? `conic-gradient(${entries.map(([, value], index) => {
      const start = cursor
      const end = cursor + (value / total) * 360
      cursor = end
      return `${distributionColor(entries[index][0], index)} ${start}deg ${end}deg`
    }).join(', ')})`
    : `conic-gradient(${accent} 0deg 360deg)`

  if (!entries.length) return <Empty text="后端返回空统计数据" />

  return (
    <div className="distribution-panel">
      <div className="pie-block">
        <div className="pie-chart" style={{ background: gradient }} aria-label={`total ${total}`}>
          <div className="pie-center">
            <strong>{total.toLocaleString('zh-CN')}</strong>
            <span>total</span>
          </div>
        </div>
        <div className="pie-legend">
          {entries.map(([key, value], index) => (
            <span key={key} title={`${key}: ${value.toLocaleString('zh-CN')}`}>
              <i style={{ background: distributionColor(key, index) }} />
              {key}
            </span>
          ))}
        </div>
      </div>
      <div className="bars">
        {entries.map(([key, value], index) => (
          <div className="bar-row" key={key}>
            <span className="bar-label">{key}</span>
            <span className="bar-track">
              <span
                className="bar-fill"
                style={{ width: `${(value / max) * 100}%`, background: distributionColor(key, index) } as CSSProperties}
              />
            </span>
            <span className="bar-value">{value.toLocaleString('zh-CN')}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function JsonBlock({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value ?? {}, null, 2)}</pre>
}

export function MarkdownCode({ children, language = 'text' }: { children: string; language?: string }) {
  return (
    <div className="event-markdown-code">
      <span>{language}</span>
      <pre><code>{children || '—'}</code></pre>
    </div>
  )
}

export function DetailModal({
  title,
  subtitle,
  children,
  onClose,
}: PropsWithChildren<{ title: string; subtitle?: string; onClose: () => void }>) {
  return (
    <div className="modal" role="presentation" onMouseDown={onClose}>
      <section
        className="modal-card detail-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-head detail-modal-head">
          <div>
            <div className="detail-kicker">DETAIL INFORMATION</div>
            <h2 id="detail-modal-title">{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button className="ghost-btn" type="button" onClick={onClose}>关闭</button>
        </div>
        <div className="modal-body detail-modal-body">{children}</div>
      </section>
    </div>
  )
}

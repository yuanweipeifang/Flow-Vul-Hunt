import type { PropsWithChildren, ReactNode } from 'react'

export function PageHeader({ title, description, children }: PropsWithChildren<{ title: string; description: string }>) {
  return (
    <div className="page-header">
      <div>
        <p className="eyebrow">Evidence-based Security Operations</p>
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

export function BarList({ data, accent = 'var(--blue)' }: { data: Record<string, number>; accent?: string }) {
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

export function JsonBlock({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value ?? {}, null, 2)}</pre>
}

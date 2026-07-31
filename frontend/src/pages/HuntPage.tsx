import { useState } from 'react'
import type { AppContextValue } from '../App'
import { type HuntResult } from '../api'
import { Badge, Card, DataTable, Empty, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
import { fmtNumber, fmtScore } from '../ui'

export function HuntPage({ context }: { context: AppContextValue }) {
  const [query, setQuery] = useState('')
  const [useLlm, setUseLlm] = useState(false)
  const [result, setResult] = useState<HuntResult | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await context.api<HuntResult>('/api/hunt/query', {
        method: 'POST',
        body: JSON.stringify({ query, dataset_id: context.selectedDataset || null, limit: 30, use_llm: useLlm, exclude_suppressed: true }),
      })
      setResult(data)
    } catch (reason) {
      setResult(null)
      setError(reason)
    } finally {
      setLoading(false)
    }
  }

  const rows = (result?.events || []).map((event) => [
    fmtNumber(event.row_number), event.host || '—', event.path || '—', <Badge text={event.verdict} tone={event.verdict === 'malicious' ? 'red' : event.verdict === 'suspicious' ? 'orange' : 'blue'} />, fmtScore(event.risk_score),
  ])

  return (
    <>
      <PageHeader title="自然语言狩猎" description="查询提交到 POST /api/hunt/query；解释过滤器、命中数和事件列表均为后端真实结果。" />
      <Card title="狩猎语句">
        <form className="form-row" onSubmit={(event) => void submit(event)}>
          <label className="field"><span>查询</span><input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={2000} placeholder="例如：查找高风险 SQL 注入事件" required /></label>
          <label className="checkbox-line"><input type="checkbox" checked={useLlm} onChange={(event) => setUseLlm(event.target.checked)} /><span>允许 LLM 解释</span></label>
          <button className="primary-btn" type="submit">执行狩猎</button>
        </form>
      </Card>
      <Card title="狩猎结果">
        {loading ? <Loading text="正在执行真实狩猎查询…" /> : error ? <ErrorBox error={error} /> : !result ? <Empty text="尚未执行狩猎查询" /> : (
          <>
            <div className="item-card" style={{ '--accent': 'var(--green)' } as React.CSSProperties}>
              <div className="meta"><Badge text={result.llm_used ? 'LLM 解释' : '确定性解释'} tone={result.llm_used ? 'purple' : 'blue'} /><span>命中 {fmtNumber(result.matched_events)}</span><span>排除 benign {fmtNumber(result.suppressed_events)}</span></div>
              <p>{result.summary || '后端未返回摘要'}</p>
              {result.warning ? <ErrorBox error={result.warning} /> : null}
              <h3>解释过滤器</h3><JsonBlock value={result.interpreted_filters} />
            </div>
            <div className="section"><DataTable caption="狩猎命中事件" headers={['行号','Host','Path','判定','风险']} rows={rows} /></div>
          </>
        )}
      </Card>
    </>
  )
}

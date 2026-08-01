import { useState } from 'react'
import type { ReactNode } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type EventDetail, type PaginatedEvents } from '../api'
import { Badge, Card, DataTable, DetailModal, Empty, ErrorBox, Loading, MarkdownCode, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, fmtScore, severityTone, statusTone } from '../ui'

function verdictTone(verdict: string) {
  if (verdict === 'malicious') return 'red'
  if (verdict === 'suspicious') return 'orange'
  if (verdict === 'benign') return 'green'
  return 'gray'
}

function PayloadChip({ tone, title, onClick, children }: { tone: string; title?: string; onClick: () => void; children: ReactNode }) {
  return (
    <button className={`payload-chip ${tone}`} type="button" title={title} onClick={onClick}>
      {children}
    </button>
  )
}

function EventDetailDocument({ detail }: { detail: EventDetail }) {
  return (
    <article className="event-markdown">
      <blockquote>
        <strong>事件 #{fmtNumber(detail.row_number)}</strong>
        <span>Payload 已完成解析与风险检测，以下内容来自事件详情接口。</span>
      </blockquote>

      <section>
        <h2>请求摘要</h2>
        <div className="event-markdown-table" role="table" aria-label="请求摘要">
          <div><span>Host</span><code>{detail.host || '—'}</code></div>
          <div><span>方法 / 协议</span><code>{detail.http_method || '—'} / {detail.protocol || '—'}</code></div>
          <div><span>Path</span><code>{detail.path || '—'}</code></div>
          <div><span>Query</span><code>{detail.query || '—'}</code></div>
          <div><span>Content-Type</span><code>{detail.content_type || '—'}</code></div>
          <div><span>Payload Hash</span><code>{detail.payload_hash || '—'}</code></div>
        </div>
      </section>

      <section>
        <h2>检测结论</h2>
        <div className="event-markdown-callout">
          <Badge text={detail.verdict} tone={verdictTone(detail.verdict)} />
          <span>风险分 <strong>{fmtScore(detail.risk_score)}</strong></span>
          <span>解析状态 <strong>{detail.parse_status}</strong></span>
          <span>载荷 <strong>{detail.is_binary ? 'binary' : 'text'} · {fmtNumber(detail.payload_length)} B</strong></span>
        </div>
        <ul>
          <li>熵值：<code>{fmtScore(detail.entropy)}</code></li>
          <li>可打印比例：<code>{fmtScore(detail.printable_ratio)}</code></li>
          <li>编码片段：<code>{fmtNumber(detail.encoded_segment_count)}</code></li>
          {detail.parse_error ? <li className="error-item">解析错误：<code>{detail.parse_error}</code></li> : null}
        </ul>
      </section>

      <section>
        <h2>请求头</h2>
        <MarkdownCode language="json">{JSON.stringify(detail.headers || {}, null, 2)}</MarkdownCode>
      </section>

      <section>
        <h2>Raw Payload</h2>
        <MarkdownCode language="http">{detail.raw_payload}</MarkdownCode>
      </section>

      <section>
        <h2>Decoded Payload</h2>
        <MarkdownCode language="text">{detail.decoded_payload}</MarkdownCode>
      </section>

      {detail.body ? <section><h2>Body</h2><MarkdownCode>{detail.body}</MarkdownCode></section> : null}

      <section>
        <h2>检测证据</h2>
        {detail.findings.length ? detail.findings.map((finding, index) => (
          <div className="event-markdown-entry" key={finding.id}>
            <h3>{index + 1}. {finding.detector_name}</h3>
            <div className="event-markdown-callout compact">
              <Badge text={finding.severity} tone={severityTone(finding.severity)} />
              <Badge text={finding.attack_type} tone="purple" />
              <span>置信度 <strong>{fmtScore(finding.confidence)}</strong></span>
            </div>
            <p>{finding.matched_fragment || '未返回匹配片段。'}</p>
            <MarkdownCode language="json">{JSON.stringify(finding.evidence || {}, null, 2)}</MarkdownCode>
          </div>
        )) : <p className="event-markdown-empty">该事件暂无检测证据。</p>}
      </section>

      <section>
        <h2>LLM 分析</h2>
        {detail.llm_analyses.length ? detail.llm_analyses.map((analysis, index) => (
          <div className="event-markdown-entry" key={analysis.id}>
            <h3>{index + 1}. {analysis.agent_name}</h3>
            <div className="event-markdown-callout compact">
              <Badge text={analysis.status} tone={statusTone(analysis.status)} />
              <span>{analysis.provider}</span>
              <code>{analysis.model_name}</code>
            </div>
            <p>{analysis.error_message || '结构化分析已完成。'}</p>
            <MarkdownCode language="json">{JSON.stringify(analysis.structured_result || {}, null, 2)}</MarkdownCode>
          </div>
        )) : <p className="event-markdown-empty">该事件暂无 LLM 分析记录。</p>}
      </section>
    </article>
  )
}

export function EventsPage({ context }: { context: AppContextValue }) {
  const [detail, setDetail] = useState<EventDetail | null>(null)
  const [detailError, setDetailError] = useState<unknown>(null)
  const [filters, setFilters] = useState({ verdict: '', attack_type: '', min_risk: '', host: '' })
  const { data: events, error, loading } = useApiData(
    () => context.api<PaginatedEvents>(`/api/events${queryString({ dataset_id: context.selectedDataset, ...filters, limit: 80 })}`),
    [context, context.selectedDataset, filters],
  )

  async function showDetail(id: string) {
    setDetail(null)
    setDetailError(null)
    try {
      const data = await context.api<EventDetail>(`/api/events/${encodeURIComponent(id)}`)
      setDetail(data)
    } catch (reason) {
      setDetailError(reason)
    }
  }

  const rows = (events?.items || []).map((event) => {
    const openDetail = () => void showDetail(event.id)
    const riskTone = event.risk_score >= 70 ? 'risk-high' : event.risk_score >= 40 ? 'risk-medium' : 'risk-low'
    return [
    <PayloadChip tone="row" onClick={openDetail}>#{fmtNumber(event.row_number)}</PayloadChip>,
    <PayloadChip tone="method" onClick={openDetail}>{event.http_method || '—'}</PayloadChip>,
    <PayloadChip tone="host" title={event.host || ''} onClick={openDetail}>{event.host || '—'}</PayloadChip>,
    <PayloadChip tone="path" title={event.path || ''} onClick={openDetail}>{event.path || '—'}</PayloadChip>,
    <PayloadChip tone={`verdict ${verdictTone(event.verdict)}`} onClick={openDetail}>{event.verdict}</PayloadChip>,
    <PayloadChip tone={riskTone} onClick={openDetail}>{fmtScore(event.risk_score)}</PayloadChip>,
    <PayloadChip tone={event.parse_status === 'parsed' ? 'parsed' : 'parse-warn'} onClick={openDetail}>{event.parse_status}</PayloadChip>,
    <PayloadChip tone={event.is_binary ? 'binary' : 'text'} onClick={openDetail}>{event.is_binary ? 'binary' : 'text'} · {fmtNumber(event.payload_length)} B</PayloadChip>,
    <PayloadChip tone="time" onClick={openDetail}>{fmtDate(event.created_at)}</PayloadChip>,
    <button className="ghost-btn" type="button" onClick={() => void showDetail(event.id)}>详情</button>,
  ]})

  return (
    <div className="payload-events-page">
      <PageHeader title="Payload 事件" description="事件列表来自 GET /api/events，详情来自 GET /api/events/{id}；不会生成演示事件。" />
      <Card title="筛选条件" description="筛选直接映射为后端查询参数。">
        <div className="filters">
          <label className="field"><span>事件判定</span><select value={filters.verdict} onChange={(event) => setFilters((current) => ({ ...current, verdict: event.target.value }))}><option value="">全部</option><option value="malicious">malicious</option><option value="suspicious">suspicious</option><option value="benign">benign</option><option value="unreviewed">unreviewed</option></select></label>
          <label className="field"><span>攻击类型</span><input value={filters.attack_type} onChange={(event) => setFilters((current) => ({ ...current, attack_type: event.target.value }))} placeholder="如 sql_injection" /></label>
          <label className="field"><span>最低风险分</span><input type="number" min="0" max="100" value={filters.min_risk} onChange={(event) => setFilters((current) => ({ ...current, min_risk: event.target.value }))} /></label>
          <label className="field"><span>Host 包含</span><input value={filters.host} onChange={(event) => setFilters((current) => ({ ...current, host: event.target.value }))} /></label>
          <label className="field"><span>数据集</span><select value={context.selectedDataset} onChange={(event) => context.setSelectedDataset(event.target.value)}><option value="">全部</option>{context.datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></label>
        </div>
      </Card>
      <Card title="事件列表" description={`共 ${fmtNumber(events?.total)} 条，当前展示 ${fmtNumber(events?.items.length)} 条。`}>
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : rows.length ? <div className="payload-event-table"><DataTable caption="Payload 事件列表 · 点击任意字段查看详情" headers={['行号','方法','Host','Path','判定','风险','解析','载荷','创建时间','操作']} rows={rows} /></div> : <Empty text="后端返回空事件列表" />}
        {detailError ? <div className="section"><ErrorBox error={detailError} /></div> : null}
      </Card>
      {detail && (
        <DetailModal title="Payload 事件详情" subtitle={`${detail.http_method || '—'} ${detail.host || '—'}${detail.path || ''}`} onClose={() => setDetail(null)}>
          <EventDetailDocument detail={detail} />
        </DetailModal>
      )}
    </div>
  )
}

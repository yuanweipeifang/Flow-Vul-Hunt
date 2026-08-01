import { useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type EventDetail, type PaginatedEvents } from '../api'
import { Badge, Card, DataTable, Empty, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, fmtScore, severityTone, statusTone } from '../ui'

function verdictTone(verdict: string) {
  if (verdict === 'malicious') return 'red'
  if (verdict === 'suspicious') return 'orange'
  if (verdict === 'benign') return 'green'
  return 'gray'
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

  const rows = (events?.items || []).map((event) => [
    <span className="nowrap">{fmtNumber(event.row_number)}</span>,
    event.http_method || '—',
    <span title={event.host || ''}>{event.host || '—'}</span>,
    <span title={event.path || ''}>{event.path || '—'}</span>,
    <Badge text={event.verdict} tone={verdictTone(event.verdict)} />,
    <strong>{fmtScore(event.risk_score)}</strong>,
    <Badge text={event.parse_status} tone={event.parse_status === 'parsed' ? 'green' : 'orange'} />,
    <Badge text={event.is_binary ? 'binary' : 'text'} tone={event.is_binary ? 'purple' : 'blue'} />,
    <span className="nowrap">{fmtDate(event.created_at)}</span>,
    <button className="ghost-btn" type="button" onClick={() => void showDetail(event.id)}>详情</button>,
  ])

  return (
    <>
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
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : rows.length ? <DataTable caption="Payload 事件列表" headers={['行号','方法','Host','Path','判定','风险','解析','类型','创建时间','操作']} rows={rows} /> : <Empty text="后端返回空事件列表" />}
        {detailError ? <div className="section"><ErrorBox error={detailError} /></div> : null}
      </Card>
      {detail && (
        <div className="modal" onClick={(event) => { if (event.target === event.currentTarget) setDetail(null) }}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="event-detail-title">
            <div className="modal-head"><h2 id="event-detail-title">事件详情</h2><button className="ghost-btn" type="button" onClick={() => setDetail(null)}>关闭</button></div>
            <div className="modal-body">
              <div className="grid two">
                <div><p><strong>Host：</strong>{detail.host || '—'}</p><p><strong>方法/协议：</strong>{detail.http_method || '—'} / {detail.protocol}</p><p><strong>Path：</strong>{detail.path || '—'}</p><p><strong>Query：</strong>{detail.query || '—'}</p></div>
                <div><p><strong>判定：</strong><Badge text={detail.verdict} tone={verdictTone(detail.verdict)} /></p><p><strong>风险分：</strong>{fmtScore(detail.risk_score)}</p><p><strong>熵/可打印比例：</strong>{fmtScore(detail.entropy)} / {fmtScore(detail.printable_ratio)}</p><p><strong>解析：</strong>{detail.parse_status}</p></div>
              </div>
              <h3>Raw Payload</h3><pre>{detail.raw_payload}</pre>
              <h3>Decoded Payload</h3><pre>{detail.decoded_payload}</pre>
              <h3>检测证据</h3>
              {detail.findings.length ? <div className="cards-list">{detail.findings.map((finding) => <div className="item-card" key={finding.id}><div className="meta"><Badge text={finding.severity} tone={severityTone(finding.severity)} /><Badge text={finding.attack_type} tone="purple" /><span>置信度 {fmtScore(finding.confidence)}</span></div><h3>{finding.detector_name}</h3><p>{finding.matched_fragment || '—'}</p><JsonBlock value={finding.evidence} /></div>)}</div> : <Empty text="该事件暂无检测证据" />}
              <h3>LLM 分析</h3>
              {detail.llm_analyses.length ? <div className="cards-list">{detail.llm_analyses.map((analysis) => <div className="item-card" key={analysis.id}><div className="meta"><Badge text={analysis.agent_name} tone="purple" /><Badge text={analysis.status} tone={statusTone(analysis.status)} /><span>{analysis.provider}</span><span>{analysis.model_name}</span></div><p>{analysis.error_message || '已完成结构化分析'}</p><JsonBlock value={analysis.structured_result} /></div>)}</div> : <Empty text="该事件暂无 LLM 分析记录" />}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

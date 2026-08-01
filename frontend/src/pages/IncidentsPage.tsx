import React, { useMemo, useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type EventDetail, type IncidentOut, type IncidentReportOut } from '../api'
import { Badge, Card, DetailModal, DistributionPanel, Empty, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, fmtScore, severityTone, statusTone } from '../ui'

function countBy<T>(items: T[], selector: (item: T) => string | null | undefined) {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = selector(item) || 'unknown'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
}

function severityAccent(severity: string | null | undefined) {
  const value = String(severity || '').toLowerCase()
  if (value === 'critical') return 'var(--color-red)'
  if (value === 'high') return 'var(--color-primary)'
  if (value === 'medium') return 'var(--color-cyan)'
  return 'var(--color-green)'
}

export function IncidentsPage({ context }: { context: AppContextValue }) {
  const [status, setStatus] = useState('')
  const [severity, setSeverity] = useState('')
  const [detail, setDetail] = useState<IncidentOut | null>(null)
  const [detailEvents, setDetailEvents] = useState<EventDetail[]>([])
  const [detailReports, setDetailReports] = useState<IncidentReportOut[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<unknown>(null)
  const { data: incidentsData, error, loading } = useApiData(
    () => context.api<IncidentOut[]>(`/api/incidents${queryString({ dataset_id: context.selectedDataset, status, severity, limit: 80 })}`),
    [context, context.selectedDataset, severity, status],
  )
  const incidents = incidentsData || []
  const charts = useMemo(() => ({
    severity: countBy(incidents, (item) => item.severity),
    status: countBy(incidents, (item) => item.status),
    type: countBy(incidents, (item) => item.incident_type),
  }), [incidents])

  async function showDetail(incidentId: string) {
    setDetailLoading(true)
    setDetailError(null)
    setDetailEvents([])
    setDetailReports([])
    try {
      const incident = await context.api<IncidentOut>(`/api/incidents/${encodeURIComponent(incidentId)}`)
      setDetail(incident)
      const [eventResults, reportResult] = await Promise.all([
        Promise.allSettled(incident.event_links.map((link) => context.api<EventDetail>(`/api/events/${encodeURIComponent(link.event_id)}`))),
        context.api<IncidentReportOut[]>(`/api/incidents/${encodeURIComponent(incidentId)}/reports`).catch(() => []),
      ])
      setDetailEvents(eventResults.flatMap((result) => result.status === 'fulfilled' ? [result.value] : []))
      setDetailReports(reportResult)
    } catch (reason) {
      setDetail(null)
      setDetailError(reason)
    } finally {
      setDetailLoading(false)
    }
  }

  const detailAnalysis = useMemo(() => {
    const risks = detailEvents.map((event) => Number(event.risk_score) || 0)
    const timestamps = detailEvents.map((event) => Date.parse(event.created_at)).filter(Number.isFinite)
    const hosts = new Set(detailEvents.map((event) => event.host).filter(Boolean))
    const paths = new Set(detailEvents.map((event) => event.path).filter(Boolean))
    const verdicts = countBy(detailEvents, (event) => event.verdict)
    const methods = countBy(detailEvents, (event) => event.http_method)
    const relationTypes = countBy(detail?.event_links || [], (link) => link.relation_type)
    return {
      averageRisk: risks.length ? risks.reduce((sum, value) => sum + value, 0) / risks.length : 0,
      maximumRisk: risks.length ? Math.max(...risks) : 0,
      hosts: hosts.size, paths: paths.size, verdicts, methods, relationTypes,
      firstSeen: timestamps.length ? new Date(Math.min(...timestamps)).toISOString() : null,
      lastSeen: timestamps.length ? new Date(Math.max(...timestamps)).toISOString() : null,
    }
  }, [detail, detailEvents])

  return (
    <>
      <PageHeader title="Incident 聚类" description="仅展示后端基于真实 Host 和攻击类型聚合出的 Incident；饼图根据当前筛选结果实时统计。">
        <label className="field">
          <span>状态</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部</option>
            <option value="open">open</option>
            <option value="investigating">investigating</option>
            <option value="resolved">resolved</option>
            <option value="closed">closed</option>
          </select>
        </label>
        <label className="field">
          <span>严重度</span>
          <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
            <option value="">全部</option>
            <option value="critical">critical</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
            <option value="info">info</option>
          </select>
        </label>
      </PageHeader>

      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <>
          <div className="grid three">
            <Card title="严重度分布">
              <DistributionPanel data={charts.severity} accent="var(--color-orange)" />
            </Card>
            <Card title="状态分布">
              <DistributionPanel data={charts.status} accent="var(--color-cyan)" />
            </Card>
            <Card title="聚类类型">
              <DistributionPanel data={charts.type} accent="var(--color-purple)" />
            </Card>
          </div>

          <div className="section">
            {incidents.length ? (
              <div className="incident-cluster-list">
                {incidents.map((incident) => (
                  <button className="incident-cluster-card" type="button" key={incident.id} onClick={() => void showDetail(incident.id)} style={{ '--accent': severityAccent(incident.severity) } as React.CSSProperties}>
                    <div className="incident-cluster-main">
                      <div className="meta">
                        <Badge text={incident.severity} tone={severityTone(incident.severity)} />
                        <Badge text={incident.status} tone={statusTone(incident.status)} />
                        <span>风险 {fmtScore(incident.risk_score)}</span>
                        <span>{fmtDate(incident.created_at)}</span>
                      </div>
                      <h3>{incident.title}</h3>
                      <p>{incident.summary}</p>
                      <div className="incident-cluster-meta">
                        <span>类型</span><strong>{incident.incident_type}</strong>
                        <span>关联事件</span><strong>{fmtNumber(incident.event_links.length)}</strong>
                        <span>负责人</span><strong>{incident.assignee || '-'}</strong>
                        <span>模拟</span><strong>{String(incident.is_simulated)}</strong>
                      </div>
                    </div>
                    <span className="incident-detail-entry">查看深度分析 <b>→</b></span>
                  </button>
                ))}
              </div>
            ) : <Empty text="后端返回空 Incident 列表" />}
          </div>
          {detailError ? <div className="section"><ErrorBox error={detailError} /></div> : null}
        </>
      )}
      {detail && (
        <DetailModal title={detail.title} subtitle={`${detail.incident_type} · ${fmtNumber(detail.event_links.length)} 个关联事件`} onClose={() => setDetail(null)}>
          <div className="incident-analysis">
            {detailLoading ? <Loading text="正在加载关联事件与聚类证据…" /> : null}
            <div className="incident-analysis-summary">
              <div><span>聚类风险</span><strong>{fmtScore(detail.risk_score)}</strong><small>{detail.severity}</small></div>
              <div><span>事件平均风险</span><strong>{fmtScore(detailAnalysis.averageRisk)}</strong><small>峰值 {fmtScore(detailAnalysis.maximumRisk)}</small></div>
              <div><span>目标范围</span><strong>{fmtNumber(detailAnalysis.hosts)} Host</strong><small>{fmtNumber(detailAnalysis.paths)} Path</small></div>
              <div><span>证据加载</span><strong>{fmtNumber(detailEvents.length)} / {fmtNumber(detail.event_links.length)}</strong><small>关联 Payload</small></div>
            </div>

            <section className="incident-analysis-section">
              <h3>聚类判断</h3>
              <p>{detail.summary}</p>
              <div className="incident-analysis-tags">
                <Badge text={detail.severity} tone={severityTone(detail.severity)} />
                <Badge text={detail.status} tone={statusTone(detail.status)} />
                <span>类型 <strong>{detail.incident_type}</strong></span>
                <span>负责人 <strong>{detail.assignee || '未分配'}</strong></span>
                <span>数据来源 <strong>{detail.is_simulated ? '模拟' : '真实'}</strong></span>
              </div>
            </section>

            <div className="incident-analysis-grid">
              <section className="incident-analysis-section"><h3>判定分布</h3><DistributionPanel data={detailAnalysis.verdicts} accent="var(--color-orange)" /></section>
              <section className="incident-analysis-section"><h3>请求方法</h3><DistributionPanel data={detailAnalysis.methods} accent="var(--color-cyan)" /></section>
              <section className="incident-analysis-section"><h3>关联关系</h3><DistributionPanel data={detailAnalysis.relationTypes} accent="var(--color-purple)" /></section>
            </div>

            <section className="incident-analysis-section">
              <h3>时间与处置</h3>
              <div className="incident-timeline-facts">
                <div><span>首次观测</span><strong>{fmtDate(detailAnalysis.firstSeen)}</strong></div>
                <div><span>最近观测</span><strong>{fmtDate(detailAnalysis.lastSeen)}</strong></div>
                <div><span>Incident 创建</span><strong>{fmtDate(detail.created_at)}</strong></div>
                <div><span>最后更新</span><strong>{fmtDate(detail.updated_at)}</strong></div>
              </div>
              {detail.resolution ? <blockquote>{detail.resolution}</blockquote> : null}
            </section>

            <section className="incident-analysis-section">
              <h3>关联 Payload</h3>
              {detailEvents.length ? <div className="incident-event-list">{detailEvents.map((event) => <div key={event.id}><div><Badge text={event.verdict} tone={event.verdict === 'malicious' ? 'red' : event.verdict === 'suspicious' ? 'orange' : 'green'} /><strong>{event.http_method || '—'} {event.host || '—'}{event.path || ''}</strong></div><span>风险 {fmtScore(event.risk_score)} · {fmtDate(event.created_at)}</span></div>)}</div> : <Empty text="未加载到关联 Payload 详情" />}
            </section>

            <section className="incident-analysis-section">
              <h3>聚类证据</h3>
              <div className="incident-evidence-list">{detail.event_links.map((link, index) => <details key={`${link.event_id}-${index}`}><summary><span>{index + 1}. {link.relation_type}</span><code>{link.event_id}</code></summary><JsonBlock value={link.evidence} /></details>)}</div>
            </section>

            <section className="incident-analysis-section">
              <h3>已有分析报告</h3>
              {detailReports.length ? detailReports.map((report) => <details className="incident-report" key={report.id}><summary><span>{report.generator} · {report.status}</span><small>{fmtDate(report.created_at)}</small></summary>{report.error_message ? <ErrorBox error={report.error_message} /> : <JsonBlock value={report.content} />}</details>) : <Empty text="该 Incident 暂无分析报告" />}
            </section>
          </div>
        </DetailModal>
      )}
    </>
  )
}

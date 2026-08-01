import React, { useMemo, useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type IncidentOut } from '../api'
import { Badge, Card, DistributionPanel, Empty, ErrorBox, Loading, PageHeader } from '../components'
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
              <div className="cards-list">
                {incidents.map((incident) => (
                  <Card key={incident.id}>
                    <div
                      className="item-card"
                      style={{ '--accent': severityAccent(incident.severity) } as React.CSSProperties}
                    >
                      <div className="meta">
                        <Badge text={incident.severity} tone={severityTone(incident.severity)} />
                        <Badge text={incident.status} tone={statusTone(incident.status)} />
                        <span>风险 {fmtScore(incident.risk_score)}</span>
                        <span>{fmtDate(incident.created_at)}</span>
                      </div>
                      <h3>{incident.title}</h3>
                      <p>{incident.summary}</p>
                      <div className="meta">
                        <span>类型</span><strong>{incident.incident_type}</strong>
                        <span>关联事件</span><strong>{fmtNumber(incident.event_links.length)}</strong>
                        <span>负责人</span><strong>{incident.assignee || '-'}</strong>
                        <span>模拟</span><strong>{String(incident.is_simulated)}</strong>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            ) : <Empty text="后端返回空 Incident 列表" />}
          </div>
        </>
      )}
    </>
  )
}

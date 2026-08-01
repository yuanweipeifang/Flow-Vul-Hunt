import { useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type AuditLogOut } from '../api'
import { Badge, Card, DetailModal, Empty, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, statusTone } from '../ui'

function actionTone(action: string) {
  const value = action.toLowerCase()
  if (value.includes('delete') || value.includes('cancel') || value.includes('failed')) return 'red'
  if (value.includes('update') || value.includes('retry') || value.includes('validation')) return 'orange'
  if (value.includes('create') || value.includes('upload') || value.includes('start') || value.includes('generate')) return 'green'
  return 'blue'
}

function AuditLogDetail({ log }: { log: AuditLogOut }) {
  return (
    <div className="detail-stack">
      <div className="detail-summary-grid">
        <div><span>日志 ID</span><strong>{log.id}</strong></div>
        <div><span>动作</span><strong>{log.action}</strong></div>
        <div><span>Actor</span><strong>{log.actor}</strong></div>
        <div><span>角色</span><strong>{log.role}</strong></div>
        <div><span>资源类型</span><strong>{log.resource_type}</strong></div>
        <div><span>资源 ID</span><strong>{log.resource_id || '-'}</strong></div>
      </div>

      <div className="detail-callout">
        <Badge text={log.action} tone={actionTone(log.action)} />
        <Badge text={log.role} tone={statusTone(log.role)} />
        <span>{fmtDate(log.created_at)}</span>
      </div>

      <section className="detail-section">
        <h3>请求链路</h3>
        <div className="detail-mini-list">
          <div className="detail-mini-item">
            <div>
              <strong>Request ID</strong>
              <span>{log.request_id || '未记录 request_id'}</span>
            </div>
            <Badge text={log.resource_type} tone="blue" />
          </div>
        </div>
      </section>

      <section className="detail-section">
        <h3>详细信息</h3>
        <JsonBlock value={log.details} />
      </section>
    </div>
  )
}

export function AuditPage({ context }: { context: AppContextValue }) {
  const [filters, setFilters] = useState({ action: '', resource_type: '' })
  const [detailLog, setDetailLog] = useState<AuditLogOut | null>(null)
  const { data: logsData, error, loading } = useApiData(
    () => context.api<AuditLogOut[]>(`/api/audit-logs${queryString({ ...filters, limit: 100 })}`),
    [context, filters],
  )
  const logs = logsData || []

  return (
    <>
      <PageHeader title="审计日志" description="按创建时间倒序展示最近 100 条审计记录，详情弹窗保留原始 JSON 证据。">
        <label className="field">
          <span>动作</span>
          <input
            value={filters.action}
            onChange={(event) => setFilters((current) => ({ ...current, action: event.target.value }))}
            placeholder="如 job.start"
          />
        </label>
        <label className="field">
          <span>资源类型</span>
          <input
            value={filters.resource_type}
            onChange={(event) => setFilters((current) => ({ ...current, resource_type: event.target.value }))}
            placeholder="如 dataset"
          />
        </label>
      </PageHeader>

      <Card title="审计日志" description="每条日志展示关键字段，点击详细信息查看完整上下文。">
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : logs.length ? (
          <div className="review-list">
            {logs.map((log) => (
              <article className="review-row" key={log.id}>
                <div className="review-row-main">
                  <div className="review-row-top">
                    <Badge text={log.action} tone={actionTone(log.action)} />
                    <Badge text={log.role} tone={statusTone(log.role)} />
                    <Badge text={log.resource_type} tone="blue" />
                  </div>
                  <h3>{log.action}</h3>
                  <p>{log.resource_type} · {log.resource_id || 'no resource id'} · {log.actor}</p>
                  <div className="review-row-meta">
                    <span>{fmtDate(log.created_at)}</span>
                    <span>{log.request_id || 'no request id'}</span>
                  </div>
                </div>
                <div className="review-row-actions">
                  <button className="primary-btn" type="button" onClick={() => setDetailLog(log)}>详细信息</button>
                </div>
              </article>
            ))}
          </div>
        ) : <Empty text="后端返回空审计日志" />}
      </Card>

      {detailLog ? (
        <DetailModal
          title={detailLog.action}
          subtitle={`${detailLog.actor} · ${fmtDate(detailLog.created_at)}`}
          onClose={() => setDetailLog(null)}
        >
          <AuditLogDetail log={detailLog} />
        </DetailModal>
      ) : null}
    </>
  )
}

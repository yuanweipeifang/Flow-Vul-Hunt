import { useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type AuditLogOut } from '../api'
import { Card, DataTable, Empty, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate } from '../ui'

export function AuditPage({ context }: { context: AppContextValue }) {
  const [filters, setFilters] = useState({ action: '', resource_type: '' })
  const { data: logsData, error, loading } = useApiData(
    () => context.api<AuditLogOut[]>(`/api/audit-logs${queryString({ ...filters, limit: 100 })}`),
    [context, filters],
  )
  const logs = logsData || []

  const rows = logs.map((log) => [
    <span className="nowrap">{fmtDate(log.created_at)}</span>, log.action, log.actor, log.role, log.resource_type, <code>{log.resource_id || '—'}</code>, <JsonBlock value={log.details} />,
  ])

  return (
    <>
      <PageHeader title="审计日志" description="来自 GET /api/audit-logs，按创建时间倒序展示最近 100 条。">
        <label className="field"><span>动作</span><input value={filters.action} onChange={(event) => setFilters((current) => ({ ...current, action: event.target.value }))} placeholder="如 job.start" /></label>
        <label className="field"><span>资源类型</span><input value={filters.resource_type} onChange={(event) => setFilters((current) => ({ ...current, resource_type: event.target.value }))} placeholder="如 dataset" /></label>
      </PageHeader>
      <Card title="日志列表">{loading ? <Loading /> : error ? <ErrorBox error={error} /> : rows.length ? <DataTable caption="审计日志" headers={['时间','动作','Actor','角色','资源类型','资源 ID','详情']} rows={rows} /> : <Empty text="后端返回空审计日志" />}</Card>
    </>
  )
}

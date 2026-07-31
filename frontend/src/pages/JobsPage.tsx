import { useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type JobOut } from '../api'
import { Badge, Card, DataTable, Empty, ErrorBox, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, statusTone } from '../ui'

export function JobsPage({ context }: { context: AppContextValue }) {
  const [status, setStatus] = useState('')
  const { data: jobsData, error, loading } = useApiData(
    () => context.api<JobOut[]>(`/api/jobs${queryString({ dataset_id: context.selectedDataset, status, limit: 100 })}`),
    [context, context.selectedDataset, status],
  )
  const jobs = jobsData || []

  const rows = jobs.map((job) => {
    const percent = job.total > 0 ? Math.min(100, Math.round((job.processed / job.total) * 100)) : 0
    return [
      <code>{job.id.slice(0, 8)}</code>, <code>{job.dataset_id.slice(0, 8)}</code>, <Badge text={job.status} tone={statusTone(job.status)} />, job.phase,
      <div><div className="progress" aria-label={`进度 ${percent}%`}><span style={{ width: `${percent}%` }} /></div><span className="muted">{fmtNumber(job.processed)} / {fmtNumber(job.total)}</span></div>,
      `${fmtNumber(job.succeeded)} / ${fmtNumber(job.failed)}`, job.error_message || '—', <span className="nowrap">{fmtDate(job.created_at)}</span>,
    ]
  })

  return (
    <>
      <PageHeader title="分析任务" description="任务列表来自 GET /api/jobs，展示真实进度、阶段、成功/失败与错误信息。">
        <label className="field"><span>状态</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部</option><option value="queued">queued</option><option value="running">running</option><option value="completed">completed</option><option value="completed_with_errors">completed_with_errors</option><option value="failed">failed</option><option value="canceled">canceled</option></select></label>
      </PageHeader>
      <Card title="任务列表">{loading ? <Loading /> : error ? <ErrorBox error={error} /> : rows.length ? <DataTable caption="分析任务列表" headers={['任务','数据集','状态','阶段','进度','成功/失败','错误','创建时间']} rows={rows} /> : <Empty text="后端返回空任务列表" />}</Card>
    </>
  )
}

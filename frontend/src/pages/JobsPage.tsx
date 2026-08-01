import { useMemo, useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type AuditLogOut, type JobOut } from '../api'
import { Badge, Card, DetailModal, Empty, ErrorBox, Loading, MarkdownCode, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, statusTone } from '../ui'

type ActivityItem =
  | { kind: 'job'; created_at: string; data: JobOut }
  | { kind: 'audit'; created_at: string; data: AuditLogOut }

function actionTone(action: string) {
  const value = action.toLowerCase()
  if (value.includes('delete') || value.includes('cancel') || value.includes('failed')) return 'red'
  if (value.includes('update') || value.includes('retry') || value.includes('validation')) return 'orange'
  if (value.includes('create') || value.includes('upload') || value.includes('start') || value.includes('generate')) return 'green'
  return 'blue'
}

function JobDetail({ job }: { job: JobOut }) {
  const percent = job.total > 0 ? Math.min(100, Math.round((job.processed / job.total) * 100)) : 0
  return (
    <article className="event-markdown">
      <blockquote>
        <strong>分析任务 {job.id.slice(0, 8)}</strong>
        <span>任务详情来自 GET /api/jobs，包含执行阶段、进度与原始对象。</span>
      </blockquote>

      <section>
        <h2>任务摘要</h2>
        <div className="event-markdown-table" role="table" aria-label="任务摘要">
          <div><span>任务 ID</span><code>{job.id}</code></div>
          <div><span>数据集</span><code>{job.dataset_id}</code></div>
          <div><span>阶段</span><code>{job.phase}</code></div>
          <div><span>状态</span><code>{job.status}</code></div>
          <div><span>成功 / 失败</span><code>{fmtNumber(job.succeeded)} / {fmtNumber(job.failed)}</code></div>
          <div><span>创建时间</span><code>{fmtDate(job.created_at)}</code></div>
          <div><span>启动时间</span><code>{fmtDate(job.started_at)}</code></div>
          <div><span>完成时间</span><code>{fmtDate(job.completed_at)}</code></div>
        </div>
      </section>

      <section>
        <h2>执行状态</h2>
        <div className="event-markdown-callout">
          <Badge text={job.status} tone={statusTone(job.status)} />
          <Badge text={job.phase} tone="blue" />
          <span>进度 <strong>{percent}%</strong></span>
          <span>已处理 <strong>{fmtNumber(job.processed)} / {fmtNumber(job.total)}</strong></span>
          <span>错误 <strong>{fmtNumber(job.error_count)}</strong></span>
        </div>
        <div className="progress" aria-label={`进度 ${percent}%`}>
          <span style={{ width: `${percent}%` }} />
        </div>
        <ul>
          <li>使用 LLM：<code>{job.use_llm ? 'true' : 'false'}</code> · 范围 <code>{job.llm_scope}</code></li>
          <li>强制重跑：<code>{job.force ? 'true' : 'false'}</code> · 取消请求：<code>{job.cancel_requested ? 'true' : 'false'}</code></li>
          <li>最近心跳：<code>{fmtDate(job.last_heartbeat_at)}</code> · 最近错误：<code>{fmtDate(job.last_error_at)}</code></li>
          {job.current_event_id ? <li>当前事件：<code>{job.current_event_id}</code></li> : null}
        </ul>
      </section>

      {job.error_message ? (
        <section>
          <h2>错误信息</h2>
          <p className="error-item">{job.error_message}</p>
        </section>
      ) : null}

      <section>
        <h2>原始任务对象</h2>
        <MarkdownCode language="json">{JSON.stringify(job, null, 2)}</MarkdownCode>
      </section>
    </article>
  )
}

function AuditLogDetail({ log }: { log: AuditLogOut }) {
  return (
    <article className="event-markdown">
      <blockquote>
        <strong>{log.action}</strong>
        <span>审计日志详情来自 GET /api/audit-logs，保留原始 details JSON 证据。</span>
      </blockquote>

      <section>
        <h2>日志摘要</h2>
        <div className="event-markdown-table" role="table" aria-label="日志摘要">
          <div><span>日志 ID</span><code>{log.id}</code></div>
          <div><span>动作</span><code>{log.action}</code></div>
          <div><span>Actor</span><code>{log.actor}</code></div>
          <div><span>角色</span><code>{log.role}</code></div>
          <div><span>资源类型</span><code>{log.resource_type}</code></div>
          <div><span>资源 ID</span><code>{log.resource_id || '—'}</code></div>
          <div><span>Request ID</span><code>{log.request_id || '未记录'}</code></div>
          <div><span>创建时间</span><code>{fmtDate(log.created_at)}</code></div>
        </div>
      </section>

      <section>
        <h2>动作分类</h2>
        <div className="event-markdown-callout">
          <Badge text={log.action} tone={actionTone(log.action)} />
          <Badge text={log.role} tone={statusTone(log.role)} />
          <Badge text={log.resource_type} tone="blue" />
          <span>记录于 <strong>{fmtDate(log.created_at)}</strong></span>
        </div>
        <ul>
          <li>Actor：<code>{log.actor}</code> · 角色 <code>{log.role}</code></li>
          <li>资源：<code>{log.resource_type}</code> · ID <code>{log.resource_id || '—'}</code></li>
          <li>请求链路：<code>{log.request_id || '未记录 request_id'}</code></li>
        </ul>
      </section>

      <section>
        <h2>详细信息</h2>
        <MarkdownCode language="json">{JSON.stringify(log.details ?? {}, null, 2)}</MarkdownCode>
      </section>
    </article>
  )
}

export function JobsPage({ context }: { context: AppContextValue }) {
  const [status, setStatus] = useState('')
  const [detail, setDetail] = useState<ActivityItem | null>(null)

  const { data: jobsData, error: jobsError, loading: jobsLoading } = useApiData(
    () => context.api<JobOut[]>(`/api/jobs${queryString({ dataset_id: context.selectedDataset, status, limit: 100 })}`),
    [context, context.selectedDataset, status],
  )
  const { data: logsData, error: logsError, loading: logsLoading } = useApiData(
    () => context.api<AuditLogOut[]>(`/api/audit-logs${queryString({ limit: 100 })}`),
    [context],
  )

  const items = useMemo<ActivityItem[]>(() => {
    const jobs = jobsData || []
    const logs = logsData || []
    const merged: ActivityItem[] = [
      ...jobs.map((data) => ({ kind: 'job' as const, created_at: data.created_at, data })),
      ...logs.map((data) => ({ kind: 'audit' as const, created_at: data.created_at, data })),
    ]
    merged.sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0))
    return merged
  }, [jobsData, logsData])

  const error = jobsError || logsError
  const loading = jobsLoading || logsLoading

  return (
    <>
      <PageHeader
        title="任务与审计"
        description="合并展示分析任务（GET /api/jobs）与审计日志（GET /api/audit-logs），单行 info 级概要，点击查看对应详情。"
      >
        <label className="field">
          <span>任务状态</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部</option>
            <option value="queued">queued</option>
            <option value="running">running</option>
            <option value="completed">completed</option>
            <option value="completed_with_errors">completed_with_errors</option>
            <option value="failed">failed</option>
            <option value="canceled">canceled</option>
          </select>
        </label>
      </PageHeader>

      <Card
        title="活动流水"
        description="按创建时间倒序排列，每行仅展示最小行高的 info 级信息，点击任意一行可查看完整任务 / 日志详情。"
      >
        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorBox error={error} />
        ) : items.length ? (
          <div className="activity-wrap">
            <div className="activity-list-head" aria-hidden="true">
              <span>时间</span>
              <span>类型</span>
              <span>状态 / 动作</span>
              <span>摘要</span>
              <span>ID</span>
            </div>
            <ul className="activity-list">
              {items.map((item) => (
                <li key={`${item.kind}-${item.data.id}`}>
                  <button type="button" className="activity-row" onClick={() => setDetail(item)}>
                    <span className="activity-time" title={item.data.created_at}>{fmtDate(item.data.created_at)}</span>
                    {item.kind === 'job' ? (
                      <>
                        <Badge text="job" tone="cyan" />
                        <Badge text={item.data.status} tone={statusTone(item.data.status)} />
                        <span className="activity-summary">
                          <code>{item.data.phase}</code>
                          <span className="muted">·</span>
                          <span>{fmtNumber(item.data.processed)} / {fmtNumber(item.data.total)}</span>
                          {item.data.error_message ? <span className="activity-warn" title={item.data.error_message}>· {item.data.error_message}</span> : null}
                        </span>
                      </>
                    ) : (
                      <>
                        <Badge text="audit" tone="purple" />
                        <Badge text={item.data.action} tone={actionTone(item.data.action)} />
                        <span className="activity-summary">
                          <code>{item.data.resource_type}</code>
                          <span className="muted">·</span>
                          <span>{item.data.actor}</span>
                          {item.data.resource_id ? <span className="activity-warn">· {item.data.resource_id.slice(0, 8)}</span> : null}
                        </span>
                      </>
                    )}
                    <span className="activity-id" title={item.data.id}>{item.data.id.slice(0, 8)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <Empty text="后端返回空任务与审计记录" />
        )}
      </Card>

      {detail ? (
        <DetailModal
          title={detail.kind === 'job' ? `分析任务 ${detail.data.id.slice(0, 8)}` : detail.data.action}
          subtitle={
            detail.kind === 'job'
              ? `${detail.data.phase} · ${fmtDate(detail.data.created_at)}`
              : `${detail.data.actor} · ${fmtDate(detail.data.created_at)}`
          }
          onClose={() => setDetail(null)}
        >
          {detail.kind === 'job' ? <JobDetail job={detail.data} /> : <AuditLogDetail log={detail.data} />}
        </DetailModal>
      ) : null}
    </>
  )
}

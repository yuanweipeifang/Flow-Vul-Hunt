import React from 'react'
import type { AppContextValue } from '../App'
import { queryString, type AgentSessionOut, type AgentStatusOut, type ProvidersOut } from '../api'
import { Badge, Card, DataTable, Empty, ErrorBox, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, statusTone } from '../ui'

interface AgentBundle {
  status: AgentStatusOut | null
  providers: ProvidersOut | null
  sessions: AgentSessionOut[]
  error: unknown | null
}

export function AgentPage({ context }: { context: AppContextValue }) {
  const { data, error, loading } = useApiData<AgentBundle>(async () => {
    const [statusResult, providersResult, sessionsResult] = await Promise.allSettled([
      context.api<AgentStatusOut>('/api/agent/status'),
      context.api<ProvidersOut>('/api/llm/providers'),
      context.api<AgentSessionOut[]>(`/api/agent/sessions${queryString({ dataset_id: context.selectedDataset, limit: 30 })}`),
    ])
    const failed = [statusResult, providersResult, sessionsResult].find((item) => item.status === 'rejected')
    return {
      status: statusResult.status === 'fulfilled' ? statusResult.value : null,
      providers: providersResult.status === 'fulfilled' ? providersResult.value : null,
      sessions: sessionsResult.status === 'fulfilled' ? sessionsResult.value : [],
      error: failed && failed.status === 'rejected' ? failed.reason : null,
    }
  }, [context, context.selectedDataset])
  const status = data?.status || null
  const providers = data?.providers || null
  const sessions = data?.sessions || []
  const partialError = data?.error || error

  const sessionRows = sessions.map((session) => [
    <code>{session.id.slice(0, 8)}</code>, session.actor, session.message, <Badge text={session.status} tone={statusTone(session.status)} />,
    session.runs.some((run) => run.llm_used) ? <Badge text="LLM" tone="purple" /> : <Badge text="local" tone="blue" />, <span className="nowrap">{fmtDate(session.created_at)}</span>,
  ])

  return (
    <>
      <PageHeader title="Agent 与 LLM Provider" description="状态来自 /api/agent/status 与 /api/llm/providers；会话来自 /api/agent/sessions。" />
      {loading ? <Loading /> : (
        <>
          {partialError ? <ErrorBox error={partialError} /> : null}
          <div className="grid two">
            <Card title="Agent 状态">
              {status ? <div className="cards-list"><div className="meta"><Badge text={status.enabled ? 'enabled' : 'disabled'} tone={status.enabled ? 'green' : 'orange'} /><Badge text={status.runtime} tone="blue" /><Badge text={status.collaboration_mode} tone="purple" /></div><div className="meta"><span>Hermes</span><strong>{String(status.hermes_available)}</strong><span>隔离</span><strong>{String(status.hermes_isolated)}</strong><span>最大并行</span><strong>{fmtNumber(status.max_parallelism)}</strong></div><div className="meta"><span>角色</span><strong>{status.agent_roles.join(', ') || '—'}</strong></div><div className="meta"><span>允许工具</span><strong>{status.allowed_tools.join(', ') || '—'}</strong></div></div> : <Empty text="尚未获取 Agent 状态" />}
            </Card>
            <Card title="LLM Provider" description="不展示任何 API Key。">
              {providers?.providers.length ? <div className="cards-list">{providers.providers.map((provider) => <div className="item-card" key={provider.name} style={{ '--accent': provider.configured ? 'var(--color-green)' : 'var(--color-orange)' } as React.CSSProperties}><div className="meta"><Badge text={provider.name} tone={provider.configured ? 'green' : 'orange'} /><span>{provider.configured ? '已配置' : '未配置'}</span></div><p><strong>模型：</strong>{provider.model}</p><p><strong>Base URL：</strong>{provider.base_url}</p></div>)}</div> : <Empty text="后端返回空 Provider 列表" />}
            </Card>
          </div>
          <Card title="Agent 会话" description="按创建时间倒序展示最近 30 条。">
            {sessionRows.length ? <DataTable caption="Agent 会话" headers={['会话','Actor','消息','状态','运行方式','创建时间']} rows={sessionRows} /> : <Empty text="后端返回空 Agent 会话列表" />}
          </Card>
        </>
      )}
    </>
  )
}

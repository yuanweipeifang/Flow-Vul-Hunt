import React, { useMemo, useState } from 'react'
import type { AppContextValue } from '../App'
import {
  queryString,
  type AgentMemoryOut,
  type AgentMessageOut,
  type AgentSessionOut,
  type AgentStatusOut,
  type ProvidersOut,
} from '../api'
import { Badge, Card, DataTable, Empty, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, statusTone } from '../ui'

interface AgentBundle {
  status: AgentStatusOut | null
  providers: ProvidersOut | null
  sessions: AgentSessionOut[]
  memory: AgentMemoryOut[]
  error: unknown | null
}

function messageTone(messageType: string): string {
  switch (messageType) {
    case 'task':
      return 'blue'
    case 'verification':
      return 'orange'
    case 'summary':
      return 'purple'
    default:
      return 'green'
  }
}

function TaskGraph({ session }: { session: AgentSessionOut }) {
  const tasks = session.task_graph || []
  if (!tasks.length) return <Empty text="后端返回空任务图" />
  const ordered = [...tasks].sort((left, right) => right.priority - left.priority)
  return (
    <div className="cards-list">
      {ordered.map((task) => (
        <div className="item-card" key={task.task_id} style={{ '--accent': task.status === 'failed' ? 'var(--color-red)' : task.requires_confirmation ? 'var(--color-orange)' : 'var(--color-cyan)' } as React.CSSProperties}>
          <div className="meta">
            <Badge text={task.agent_name} tone="blue" />
            <Badge text={task.status || 'pending'} tone={statusTone(task.status || 'pending')} />
            <Badge text={`P${task.priority}`} tone="purple" />
            {task.requires_confirmation ? <Badge text="需确认" tone="orange" /> : null}
          </div>
          <p><strong>{task.goal}</strong></p>
          <div className="meta"><span>工具</span><strong>{task.tool_names.join(', ') || '—'}</strong></div>
          <div className="meta"><span>依赖</span><strong>{task.depends_on.join(', ') || '—'}</strong></div>
        </div>
      ))}
    </div>
  )
}

function MessageFlow({ messages }: { messages: AgentMessageOut[] }) {
  if (!messages.length) return <Empty text="后端返回空消息流" />
  return (
    <div className="cards-list">
      {messages.map((message) => (
        <div className="item-card" key={message.id} style={{ '--accent': message.status === 'failed' ? 'var(--color-red)' : message.resolved ? 'var(--color-green)' : 'var(--color-orange)' } as React.CSSProperties}>
          <div className="meta">
            <Badge text={message.agent_name} tone="blue" />
            <Badge text={message.message_type} tone={messageTone(message.message_type)} />
            <Badge text={message.status} tone={statusTone(message.status)} />
            <Badge text={message.resolved ? 'resolved' : 'unresolved'} tone={message.resolved ? 'green' : 'orange'} />
          </div>
          <p><strong>{message.task}</strong></p>
          <div className="meta"><span>接收者</span><strong>{message.recipient || '—'}</strong><span>置信度</span><strong>{message.confidence.toFixed(2)}</strong></div>
          {Object.keys(message.follow_up_action || {}).length ? (
            <div className="meta"><span>后续动作</span><strong>{JSON.stringify(message.follow_up_action)}</strong></div>
          ) : null}
          <JsonBlock value={message.output} />
        </div>
      ))}
    </div>
  )
}

function MemoryList({ memory }: { memory: AgentMemoryOut[] }) {
  if (!memory.length) return <Empty text="后端返回空记忆列表" />
  return (
    <div className="cards-list">
      {memory.map((item) => (
        <div className="item-card" key={item.id} style={{ '--accent': 'var(--color-purple)' } as React.CSSProperties}>
          <div className="meta">
            <Badge text={item.agent_name} tone="blue" />
            <Badge text={item.memory_type} tone="purple" />
            <Badge text={item.confidence.toFixed(2)} tone="green" />
          </div>
          <p><strong>{item.summary}</strong></p>
          <JsonBlock value={item.content} />
          <div className="meta"><span>更新时间</span><strong>{fmtDate(item.updated_at)}</strong></div>
        </div>
      ))}
    </div>
  )
}

export function AgentPage({ context }: { context: AppContextValue }) {
  const [selectedSessionId, setSelectedSessionId] = useState('')
  const { data, error, loading } = useApiData<AgentBundle>(async () => {
    const [statusResult, providersResult, sessionsResult, memoryResult] = await Promise.allSettled([
      context.api<AgentStatusOut>('/api/agent/status'),
      context.api<ProvidersOut>('/api/llm/providers'),
      context.api<AgentSessionOut[]>(`/api/agent/sessions${queryString({ dataset_id: context.selectedDataset, limit: 30 })}`),
      context.api<AgentMemoryOut[]>(`/api/agent/memory${queryString({ dataset_id: context.selectedDataset, limit: 30 })}`),
    ])
    const failed = [statusResult, providersResult, sessionsResult, memoryResult].find((item) => item.status === 'rejected')
    return {
      status: statusResult.status === 'fulfilled' ? statusResult.value : null,
      providers: providersResult.status === 'fulfilled' ? providersResult.value : null,
      sessions: sessionsResult.status === 'fulfilled' ? sessionsResult.value : [],
      memory: memoryResult.status === 'fulfilled' ? memoryResult.value : [],
      error: failed && failed.status === 'rejected' ? failed.reason : null,
    }
  }, [context, context.selectedDataset])
  const status = data?.status || null
  const providers = data?.providers || null
  const sessions = useMemo(() => data?.sessions || [], [data?.sessions])
  const memory = data?.memory || []
  const partialError = data?.error || error

  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) || sessions[0] || null,
    [selectedSessionId, sessions],
  )

  const sessionRows = sessions.map((session) => [
    <button className="primary-btn" type="button" onClick={() => setSelectedSessionId(session.id)}>{session.id.slice(0, 8)}</button>,
    session.actor,
    session.message,
    <Badge text={session.status} tone={statusTone(session.status)} />,
    session.runs.some((run) => run.llm_used) ? <Badge text="LLM" tone="purple" /> : <Badge text="local" tone="blue" />,
    <span className="nowrap">{fmtDate(session.created_at)}</span>,
  ])

  const selectedMessages = selectedSession?.runs.flatMap((run) => run.messages) || []
  const followUps = selectedMessages.filter((message) => Object.keys(message.follow_up_action || {}).length > 0 || !message.resolved)

  return (
    <>
      <PageHeader title="Agent 与 LLM Provider" description="展示任务图、消息流、长期记忆和二次任务，便于观察多 Agent 真实协作过程。" />
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

          <Card title="Agent 会话" description="点击会话可查看任务图、消息流和二次任务。">
            {sessionRows.length ? <DataTable caption="Agent 会话" headers={['会话','Actor','消息','状态','运行方式','创建时间']} rows={sessionRows} /> : <Empty text="后端返回空 Agent 会话列表" />}
          </Card>

          {selectedSession ? (
            <>
              <div className="grid two">
                <Card title={`任务图 · ${selectedSession.id.slice(0, 8)}`} description="按优先级展示角色任务与依赖关系。">
                  <TaskGraph session={selectedSession} />
                </Card>
                <Card title="二次任务与待补证据" description="由 verifier 或 specialist 生成的后续动作。">
                  {followUps.length ? (
                    <div className="cards-list">
                      {followUps.map((message) => (
                        <div className="item-card" key={message.id} style={{ '--accent': message.resolved ? 'var(--color-green)' : 'var(--color-orange)' } as React.CSSProperties}>
                          <div className="meta"><Badge text={message.agent_name} tone="blue" /><Badge text={message.message_type} tone={messageTone(message.message_type)} /></div>
                          <p><strong>{message.task}</strong></p>
                          <div className="meta"><span>目标</span><strong>{message.recipient || '—'}</strong></div>
                          <div className="meta"><span>动作</span><strong>{JSON.stringify(message.follow_up_action || {})}</strong></div>
                        </div>
                      ))}
                    </div>
                  ) : <Empty text="当前会话没有待补证据或二次任务" />}
                </Card>
              </div>
              <div className="grid two">
                <Card title="消息流" description="完整展示角色消息、verification 和 summary。">
                  <MessageFlow messages={selectedMessages} />
                </Card>
                <Card title="长期记忆" description="展示当前数据集或全局范围内的角色记忆。">
                  <MemoryList memory={memory} />
                </Card>
              </div>
            </>
          ) : null}
        </>
      )}
    </>
  )
}

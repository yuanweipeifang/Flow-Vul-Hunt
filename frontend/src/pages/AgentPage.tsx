import React, { useMemo, useState } from 'react'
import type { AppContextValue } from '../App'
import {
  queryString,
  type AgentChatResult,
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

interface ChatMessage {
  id: string
  role: 'user' | 'agent'
  text: string
  createdAt: string
  result?: AgentChatResult
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
        <div
          className="item-card"
          key={task.task_id}
          style={{
            '--accent': task.status === 'failed'
              ? 'var(--color-red)'
              : task.requires_confirmation
                ? 'var(--color-orange)'
                : 'var(--color-cyan)',
          } as React.CSSProperties}
        >
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
      {messages.map((item) => (
        <div
          className="item-card"
          key={item.id}
          style={{
            '--accent': item.status === 'failed'
              ? 'var(--color-red)'
              : item.resolved
                ? 'var(--color-green)'
                : 'var(--color-orange)',
          } as React.CSSProperties}
        >
          <div className="meta">
            <Badge text={item.agent_name} tone="blue" />
            <Badge text={item.message_type} tone={messageTone(item.message_type)} />
            <Badge text={item.status} tone={statusTone(item.status)} />
            <Badge text={item.resolved ? 'resolved' : 'unresolved'} tone={item.resolved ? 'green' : 'orange'} />
          </div>
          <p><strong>{item.task}</strong></p>
          <div className="meta">
            <span>接收者</span><strong>{item.recipient || '—'}</strong>
            <span>置信度</span><strong>{item.confidence.toFixed(2)}</strong>
          </div>
          {Object.keys(item.follow_up_action || {}).length ? (
            <div className="meta"><span>后续动作</span><strong>{JSON.stringify(item.follow_up_action)}</strong></div>
          ) : null}
          <JsonBlock value={item.output} />
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
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<unknown>(null)
  const [chat, setChat] = useState<ChatMessage[]>([])
  const [reloadToken, setReloadToken] = useState(0)
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
  }, [context, context.selectedDataset, reloadToken])

  const status = data?.status || null
  const providers = data?.providers?.providers || []
  const sessions = useMemo(() => data?.sessions || [], [data?.sessions])
  const memory = data?.memory || []
  const partialError = data?.error || error
  const selectedDataset = context.datasets.find((dataset) => dataset.id === context.selectedDataset) || null

  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) || sessions[0] || null,
    [selectedSessionId, sessions],
  )
  const selectedMessages = selectedSession?.runs.flatMap((run) => run.messages) || []
  const followUps = selectedMessages.filter((item) => Object.keys(item.follow_up_action || {}).length > 0 || !item.resolved)

  const sessionRows = sessions.map((session) => [
    <button className="primary-btn" type="button" onClick={() => setSelectedSessionId(session.id)}>
      {session.id.slice(0, 8)}
    </button>,
    session.actor,
    session.message,
    <Badge text={session.status} tone={statusTone(session.status)} />,
    session.runs.some((run) => run.llm_used) ? <Badge text="LLM" tone="purple" /> : <Badge text="local" tone="blue" />,
    <span className="nowrap">{fmtDate(session.created_at)}</span>,
  ])

  const quickPrompts = [
    '读取这个 CSV，概括这批流量的主要风险',
    '找出最高风险的 payload 和证据',
    '按攻击类型总结这份数据集',
    '哪些事件更像误报？',
  ]

  async function send() {
    const text = message.trim()
    if (!text || sending) return
    setSending(true)
    setSendError(null)
    setMessage('')
    const now = new Date().toISOString()
    setChat((current) => [...current, { id: `u-${now}`, role: 'user', text, createdAt: now }])
    try {
      const result = await context.api<AgentChatResult>('/api/agent/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: text,
          dataset_id: context.selectedDataset || null,
          auto_execute: true,
          max_steps: 8,
        }),
      })
      setChat((current) => [
        ...current,
        {
          id: result.session_id,
          role: 'agent',
          text: result.answer,
          createdAt: new Date().toISOString(),
          result,
        },
      ])
      setSelectedSessionId(result.session_id)
      setReloadToken((value) => value + 1)
    } catch (reason) {
      setSendError(reason)
    } finally {
      setSending(false)
    }
  }

  function loadSessionIntoChat(session: AgentSessionOut) {
    setSelectedSessionId(session.id)
    setChat((current) => [
      ...current,
      { id: `h-u-${session.id}`, role: 'user', text: session.message, createdAt: session.created_at },
      { id: `h-a-${session.id}`, role: 'agent', text: session.answer, createdAt: session.updated_at },
    ])
  }

  return (
    <>
      <PageHeader title="Agent 会话" description="直接和在线 LLM Agent 对话，同时保留多 Agent 任务图、消息流、记忆和后续动作观测。">
        <label className="field">
          <span>数据集</span>
          <select value={context.selectedDataset} onChange={(event) => context.setSelectedDataset(event.target.value)}>
            <option value="">全部数据集</option>
            {context.datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.filename} · {dataset.status}</option>)}
          </select>
        </label>
      </PageHeader>

      {loading ? <Loading /> : partialError ? <ErrorBox error={partialError} /> : null}

      <div className="grid agent-layout">
        <Card title="对话窗口" description={selectedDataset ? `当前上下文：${selectedDataset.filename}` : '未选择数据集时，Agent 会先读取可用数据集和 CSV 文件列表。'}>
          <div className="chat-window">
            {!chat.length ? (
              <div className="chat-empty">
                <strong>问它一句，别让模型闲着。</strong>
                <span>选中数据集后，Agent 会先调工具收集证据，再结合 hunt、漏洞候选和攻击面结果回答。</span>
              </div>
            ) : (
              chat.map((item) => (
                <div className={`chat-message ${item.role}`} key={item.id}>
                  <div className="chat-bubble">
                    <div className="chat-meta">
                      <Badge text={item.role === 'user' ? '你' : item.result?.llm_used ? 'LLM Agent' : 'Agent'} tone={item.role === 'user' ? 'blue' : 'purple'} />
                      <span>{fmtDate(item.createdAt)}</span>
                    </div>
                    <div className="chat-text">{item.text}</div>
                    {item.result?.warning ? <div className="chat-warning">{item.result.warning}</div> : null}
                    {item.result?.task_graph.length ? (
                      <details className="tool-details">
                        <summary>任务图 · {fmtNumber(item.result.task_graph.length)}</summary>
                        <div className="tool-list">
                          {item.result.task_graph.map((task) => (
                            <div className="tool-pill" key={task.task_id}>
                              <Badge text={task.agent_name} tone="blue" />
                              <span>{task.goal}</span>
                            </div>
                          ))}
                        </div>
                      </details>
                    ) : null}
                    {item.result?.tool_calls.length ? (
                      <details className="tool-details">
                        <summary>工具证据 · {fmtNumber(item.result.tool_calls.length)}</summary>
                        <div className="tool-list">
                          {item.result.tool_calls.map((call) => (
                            <div className="tool-pill" key={call.id}>
                              <Badge text={call.name} tone={call.status === 'executed' ? 'green' : statusTone(call.status)} />
                              <span>{call.status}</span>
                              {call.error ? <small>{call.error}</small> : null}
                            </div>
                          ))}
                        </div>
                      </details>
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </div>

          {sendError ? <div className="section"><ErrorBox error={sendError} /></div> : null}

          <div className="quick-prompts">
            {quickPrompts.map((prompt) => (
              <button className="ghost-btn" type="button" key={prompt} onClick={() => setMessage(prompt)}>{prompt}</button>
            ))}
          </div>

          <form className="chat-input-row" onSubmit={(event) => { event.preventDefault(); void send() }}>
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={selectedDataset ? '问这个 CSV 里的流量，比如：总结主要攻击类型和证据' : '先选数据集，或让 Agent 列出已上传 CSV'}
              rows={3}
            />
            <button className="primary-btn" type="submit" disabled={sending || !message.trim()}>{sending ? '分析中...' : '发送'}</button>
          </form>
        </Card>

        <aside className="agent-side">
          <Card title="Agent 状态">
            {status ? (
              <div className="cards-list">
                <div className="meta">
                  <Badge text={status.enabled ? 'enabled' : 'disabled'} tone={status.enabled ? 'green' : 'orange'} />
                  <Badge text={status.runtime} tone="blue" />
                  <Badge text={status.collaboration_mode} tone="purple" />
                </div>
                <div className="meta">
                  <span>Hermes</span><strong>{String(status.hermes_available)}</strong>
                  <span>隔离</span><strong>{String(status.hermes_isolated)}</strong>
                </div>
                <div className="meta">
                  <span>最大并行</span><strong>{fmtNumber(status.max_parallelism)}</strong>
                  <span>需确认</span><strong>{String(status.require_confirmation)}</strong>
                </div>
                <div className="meta"><span>角色</span><strong>{status.agent_roles.join(', ') || '—'}</strong></div>
                <div className="meta"><span>工具</span><strong>{status.allowed_tools.join(', ') || '—'}</strong></div>
              </div>
            ) : <Empty text="尚未获取 Agent 状态" />}
          </Card>

          <Card title="LLM Provider" description="只展示配置状态，不展示 API Key。">
            {providers.length ? (
              <div className="cards-list">
                {providers.map((provider) => (
                  <div className="item-card" key={provider.name} style={{ '--accent': provider.configured ? 'var(--color-green)' : 'var(--color-orange)' } as React.CSSProperties}>
                    <div className="meta"><Badge text={provider.name} tone={provider.configured ? 'green' : 'orange'} /><span>{provider.configured ? '已配置' : '未配置'}</span></div>
                    <p><strong>模型：</strong>{provider.model}</p>
                    <p><strong>Base URL：</strong>{provider.base_url}</p>
                  </div>
                ))}
              </div>
            ) : <Empty text="后端返回空 Provider 列表" />}
          </Card>

          <Card title="最近会话">
            {sessions.length ? (
              <div className="cards-list">
                {sessions.slice(0, 12).map((session) => (
                  <button className="history-item" type="button" key={session.id} onClick={() => loadSessionIntoChat(session)}>
                    <span>{session.message}</span>
                    <Badge text={session.status} tone={statusTone(session.status)} />
                  </button>
                ))}
              </div>
            ) : <Empty text="暂无历史会话" />}
          </Card>
        </aside>
      </div>

      <Card title="Agent 会话列表" description="点击会话可以查看任务图、消息流、二次任务和长期记忆。">
        {sessionRows.length ? <DataTable caption="Agent 会话" headers={['会话', 'Actor', '消息', '状态', '运行方式', '创建时间']} rows={sessionRows} /> : <Empty text="后端返回空 Agent 会话列表" />}
      </Card>

      {selectedSession ? (
        <>
          <div className="grid two">
            <Card title={`任务图 · ${selectedSession.id.slice(0, 8)}`} description="按优先级展示角色任务与依赖关系。">
              <TaskGraph session={selectedSession} />
            </Card>
            <Card title="二次任务与待补证据" description="展示 verifier 或 specialist 生成的后续动作。">
              {followUps.length ? (
                <div className="cards-list">
                  {followUps.map((item) => (
                    <div className="item-card" key={item.id} style={{ '--accent': item.resolved ? 'var(--color-green)' : 'var(--color-orange)' } as React.CSSProperties}>
                      <div className="meta"><Badge text={item.agent_name} tone="blue" /><Badge text={item.message_type} tone={messageTone(item.message_type)} /></div>
                      <p><strong>{item.task}</strong></p>
                      <div className="meta"><span>目标</span><strong>{item.recipient || '—'}</strong></div>
                      <div className="meta"><span>动作</span><strong>{JSON.stringify(item.follow_up_action || {})}</strong></div>
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
  )
}

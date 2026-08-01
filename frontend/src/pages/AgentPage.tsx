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
import { Badge, Card, DetailModal, Empty, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
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
  if (messageType === 'task') return 'blue'
  if (messageType === 'verification') return 'orange'
  if (messageType === 'summary') return 'purple'
  return 'green'
}

function TaskGraph({ session }: { session: AgentSessionOut }) {
  const tasks = session.task_graph || []
  if (!tasks.length) return <Empty text="后端返回空任务图" />
  return (
    <div className="cards-list">
      {[...tasks].sort((left, right) => right.priority - left.priority).map((task) => (
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
            {task.requires_confirmation ? <Badge text="需要确认" tone="orange" /> : null}
          </div>
          <p><strong>{task.goal}</strong></p>
          <div className="meta"><span>工具</span><strong>{task.tool_names.join(', ') || '-'}</strong></div>
          <div className="meta"><span>依赖</span><strong>{task.depends_on.join(', ') || '-'}</strong></div>
        </div>
      ))}
    </div>
  )
}

function AgentMessageDetail({ message }: { message: AgentMessageOut }) {
  return (
    <div className="detail-stack">
      <div className="detail-summary-grid">
        <div><span>消息 ID</span><strong>{message.id}</strong></div>
        <div><span>Agent</span><strong>{message.agent_name}</strong></div>
        <div><span>角色</span><strong>{message.role}</strong></div>
        <div><span>类型</span><strong>{message.message_type}</strong></div>
        <div><span>状态</span><strong>{message.status}</strong></div>
        <div><span>置信度</span><strong>{message.confidence.toFixed(2)}</strong></div>
      </div>
      <div className="detail-callout">
        <Badge text={message.agent_name} tone="blue" />
        <Badge text={message.message_type} tone={messageTone(message.message_type)} />
        <Badge text={message.resolved ? 'resolved' : 'unresolved'} tone={message.resolved ? 'green' : 'orange'} />
        <span>{message.created_at ? fmtDate(message.created_at) : '未记录创建时间'}</span>
      </div>
      <section className="detail-section">
        <h3>任务</h3>
        <p>{message.task}</p>
      </section>
      <section className="detail-section">
        <h3>路由与依赖</h3>
        <JsonBlock value={{ recipient: message.recipient, depends_on: message.depends_on, follow_up_action: message.follow_up_action }} />
      </section>
      <section className="detail-section">
        <h3>输入摘要</h3>
        <JsonBlock value={message.input_summary} />
      </section>
      <section className="detail-section">
        <h3>输出</h3>
        <JsonBlock value={message.output} />
      </section>
      <section className="detail-section">
        <h3>证据引用</h3>
        <JsonBlock value={message.evidence_refs} />
      </section>
      {message.error ? (
        <section className="detail-section">
          <h3>错误</h3>
          <p>{message.error}</p>
        </section>
      ) : null}
    </div>
  )
}

function AgentMemoryDetail({ memory }: { memory: AgentMemoryOut }) {
  return (
    <div className="detail-stack">
      <div className="detail-summary-grid">
        <div><span>记忆 ID</span><strong>{memory.id}</strong></div>
        <div><span>数据集</span><strong>{memory.dataset_id || 'global'}</strong></div>
        <div><span>Agent</span><strong>{memory.agent_name}</strong></div>
        <div><span>类型</span><strong>{memory.memory_type}</strong></div>
        <div><span>置信度</span><strong>{memory.confidence.toFixed(2)}</strong></div>
        <div><span>更新时间</span><strong>{fmtDate(memory.updated_at)}</strong></div>
      </div>
      <div className="detail-callout">
        <Badge text={memory.agent_name} tone="blue" />
        <Badge text={memory.memory_type} tone="purple" />
        <Badge text={memory.confidence.toFixed(2)} tone="green" />
        <span>{fmtDate(memory.created_at)} 创建</span>
      </div>
      <section className="detail-section">
        <h3>摘要</h3>
        <p>{memory.summary}</p>
      </section>
      <section className="detail-section">
        <h3>记忆内容</h3>
        <JsonBlock value={memory.content} />
      </section>
    </div>
  )
}

function MessageFlow({ messages, onOpenDetail }: { messages: AgentMessageOut[]; onOpenDetail: (message: AgentMessageOut) => void }) {
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
            <span>接收者</span><strong>{item.recipient || '-'}</strong>
            <span>置信度</span><strong>{item.confidence.toFixed(2)}</strong>
          </div>
          {Object.keys(item.follow_up_action || {}).length ? (
            <div className="meta"><span>后续动作</span><strong>{JSON.stringify(item.follow_up_action)}</strong></div>
          ) : null}
          <div className="item-actions">
            <button className="primary-btn" type="button" onClick={() => onOpenDetail(item)}>详细信息</button>
          </div>
        </div>
      ))}
    </div>
  )
}

function MemoryList({ memory, onOpenDetail }: { memory: AgentMemoryOut[]; onOpenDetail: (memory: AgentMemoryOut) => void }) {
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
          <div className="meta"><span>更新时间</span><strong>{fmtDate(item.updated_at)}</strong></div>
          <div className="item-actions">
            <button className="primary-btn" type="button" onClick={() => onOpenDetail(item)}>详细信息</button>
          </div>
        </div>
      ))}
    </div>
  )
}

function AgentSessionDetail({ session }: { session: AgentSessionOut }) {
  const messages = session.runs.flatMap((run) => run.messages)
  const latestRun = session.runs[0] || null
  return (
    <div className="detail-stack">
      <div className="detail-summary-grid">
        <div><span>会话 ID</span><strong>{session.id}</strong></div>
        <div><span>Actor</span><strong>{session.actor}</strong></div>
        <div><span>角色</span><strong>{session.role}</strong></div>
        <div><span>创建时间</span><strong>{fmtDate(session.created_at)}</strong></div>
        <div><span>Runtime</span><strong>{session.runtime}</strong></div>
        <div><span>Planner</span><strong>{session.planner_used}</strong></div>
      </div>

      <div className="detail-callout">
        <Badge text={session.status} tone={statusTone(session.status)} />
        <Badge text={session.runs.some((run) => run.llm_used) ? 'LLM' : 'local'} tone="purple" />
        {session.requires_confirmation ? <Badge text="需要确认" tone="orange" /> : null}
        <span>{session.warning || '当前会话已完成记录，可继续复盘任务图、工具证据与协作消息。'}</span>
      </div>

      <section className="detail-section">
        <h3>用户问题</h3>
        <p>{session.message}</p>
      </section>

      <section className="detail-section">
        <h3>Agent 回答</h3>
        <p>{session.answer}</p>
      </section>

      <section className="detail-section">
        <h3>执行计划</h3>
        {session.plan.length ? (
          <ul className="detail-bullet-list">
            {session.plan.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}
          </ul>
        ) : <Empty text="没有执行计划" />}
      </section>

      <section className="detail-section">
        <h3>任务图</h3>
        {session.task_graph.length ? (
          <div className="detail-mini-list">
            {session.task_graph.map((task) => (
              <div className="detail-mini-item" key={task.task_id}>
                <div>
                  <strong>{task.goal}</strong>
                  <span>{task.task_id} · {task.agent_name} · priority {task.priority}</span>
                </div>
                <Badge text={task.status} tone={statusTone(task.status)} />
              </div>
            ))}
          </div>
        ) : <Empty text="没有任务图" />}
      </section>

      <section className="detail-section">
        <h3>工具调用</h3>
        {session.tool_calls.length ? (
          <div className="detail-mini-list">
            {session.tool_calls.map((call) => (
              <div className="detail-mini-item" key={call.id}>
                <div>
                  <strong>{call.name}</strong>
                  <span>{call.risk_level} · {call.requires_confirmation ? 'requires confirmation' : 'auto allowed'}</span>
                </div>
                <Badge text={call.status} tone={statusTone(call.status)} />
              </div>
            ))}
          </div>
        ) : <Empty text="没有工具调用" />}
      </section>

      <section className="detail-section">
        <h3>协作消息</h3>
        {messages.length ? (
          <div className="detail-mini-list">
            {messages.map((item) => (
              <div className="detail-mini-item" key={item.id}>
                <div>
                  <strong>{item.task}</strong>
                  <span>{item.agent_name} · {item.message_type} · confidence {item.confidence.toFixed(2)}</span>
                </div>
                <Badge text={item.status} tone={statusTone(item.status)} />
              </div>
            ))}
          </div>
        ) : <Empty text="没有协作消息" />}
      </section>

      {latestRun ? (
        <section className="detail-section">
          <h3>Consensus / Evidence</h3>
          <JsonBlock value={{ consensus: latestRun.consensus, evidence_gaps: latestRun.evidence_gaps }} />
        </section>
      ) : null}
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
  const [detailSession, setDetailSession] = useState<AgentSessionOut | null>(null)
  const [detailMessage, setDetailMessage] = useState<AgentMessageOut | null>(null)
  const [detailMemory, setDetailMemory] = useState<AgentMemoryOut | null>(null)

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
                <div className="meta"><span>Hermes</span><strong>{String(status.hermes_available)}</strong><span>隔离</span><strong>{String(status.hermes_isolated)}</strong></div>
                <div className="meta"><span>最大并行</span><strong>{fmtNumber(status.max_parallelism)}</strong><span>需确认</span><strong>{String(status.require_confirmation)}</strong></div>
                <div className="meta"><span>角色</span><strong>{status.agent_roles.join(', ') || '-'}</strong></div>
                <div className="meta"><span>工具</span><strong>{status.allowed_tools.join(', ') || '-'}</strong></div>
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

      <Card title="Agent 会话" description="按时间倒序展示对话、执行状态和协作证据，点击详细信息查看完整上下文。">
        {sessions.length ? (
          <div className="review-list">
            {sessions.map((session) => {
              const messageCount = session.runs.reduce((total, run) => total + run.messages.length, 0)
              return (
                <article className="review-row" key={session.id}>
                  <div className="review-row-main">
                    <div className="review-row-top">
                      <Badge text={session.id.slice(0, 8)} tone="blue" />
                      <Badge text={session.status} tone={statusTone(session.status)} />
                      <Badge text={session.runs.some((run) => run.llm_used) ? 'LLM' : 'local'} tone="purple" />
                    </div>
                    <h3>{session.message}</h3>
                    <p>{session.answer}</p>
                    <div className="review-row-meta">
                      <span>{session.actor}</span>
                      <span>{fmtDate(session.created_at)}</span>
                      <span>{fmtNumber(session.tool_calls.length)} tools</span>
                      <span>{fmtNumber(messageCount)} messages</span>
                    </div>
                  </div>
                  <div className="review-row-actions">
                    <button className="ghost-btn" type="button" onClick={() => setSelectedSessionId(session.id)}>选中</button>
                    <button className="primary-btn" type="button" onClick={() => setDetailSession(session)}>详细信息</button>
                  </div>
                </article>
              )
            })}
          </div>
        ) : <Empty text="后端返回空 Agent 会话列表" />}
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
                      <div className="meta"><span>目标</span><strong>{item.recipient || '-'}</strong></div>
                      <div className="meta"><span>动作</span><strong>{JSON.stringify(item.follow_up_action || {})}</strong></div>
                    </div>
                  ))}
                </div>
              ) : <Empty text="当前会话没有待补证据或二次任务" />}
            </Card>
          </div>
          <div className="grid two">
            <Card title="消息流" description="完整展示角色消息、verification 和 summary。">
              <MessageFlow messages={selectedMessages} onOpenDetail={setDetailMessage} />
            </Card>
            <Card title="长期记忆" description="展示当前数据集或全局范围内的角色记忆。">
              <MemoryList memory={memory} onOpenDetail={setDetailMemory} />
            </Card>
          </div>
        </>
      ) : null}

      {detailSession ? (
        <DetailModal
          title={detailSession.message}
          subtitle={`${detailSession.actor} · ${fmtDate(detailSession.created_at)} · ${detailSession.runtime}`}
          onClose={() => setDetailSession(null)}
        >
          <AgentSessionDetail session={detailSession} />
        </DetailModal>
      ) : null}

      {detailMessage ? (
        <DetailModal
          title={detailMessage.task}
          subtitle={`${detailMessage.agent_name} · ${detailMessage.message_type} · confidence ${detailMessage.confidence.toFixed(2)}`}
          onClose={() => setDetailMessage(null)}
        >
          <AgentMessageDetail message={detailMessage} />
        </DetailModal>
      ) : null}

      {detailMemory ? (
        <DetailModal
          title={detailMemory.summary}
          subtitle={`${detailMemory.agent_name} · ${detailMemory.memory_type} · ${fmtDate(detailMemory.updated_at)}`}
          onClose={() => setDetailMemory(null)}
        >
          <AgentMemoryDetail memory={detailMemory} />
        </DetailModal>
      ) : null}
    </>
  )
}

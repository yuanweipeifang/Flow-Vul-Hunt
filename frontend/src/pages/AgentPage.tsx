import React, { useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type AgentChatResult, type AgentSessionOut, type AgentStatusOut, type ProvidersOut } from '../api'
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, statusTone } from '../ui'

interface AgentBundle {
  status: AgentStatusOut | null
  providers: ProvidersOut | null
  sessions: AgentSessionOut[]
  error: unknown | null
}

interface ChatMessage {
  id: string
  role: 'user' | 'agent'
  text: string
  createdAt: string
  result?: AgentChatResult
}

export function AgentPage({ context }: { context: AppContextValue }) {
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<unknown>(null)
  const [chat, setChat] = useState<ChatMessage[]>([])
  const [reloadToken, setReloadToken] = useState(0)

  const { data, error, loading } = useApiData<AgentBundle>(async () => {
    const [statusResult, providersResult, sessionsResult] = await Promise.allSettled([
      context.api<AgentStatusOut>('/api/agent/status'),
      context.api<ProvidersOut>('/api/llm/providers'),
      context.api<AgentSessionOut[]>(`/api/agent/sessions${queryString({ dataset_id: context.selectedDataset, limit: 12 })}`),
    ])
    const failed = [statusResult, providersResult, sessionsResult].find((item) => item.status === 'rejected')
    return {
      status: statusResult.status === 'fulfilled' ? statusResult.value : null,
      providers: providersResult.status === 'fulfilled' ? providersResult.value : null,
      sessions: sessionsResult.status === 'fulfilled' ? sessionsResult.value : [],
      error: failed && failed.status === 'rejected' ? failed.reason : null,
    }
  }, [context, context.selectedDataset, reloadToken])

  const status = data?.status || null
  const providers = data?.providers?.providers || []
  const sessions = data?.sessions || []
  const partialError = data?.error || error
  const selectedDataset = context.datasets.find((dataset) => dataset.id === context.selectedDataset) || null

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
      setReloadToken((value) => value + 1)
    } catch (reason) {
      setSendError(reason)
    } finally {
      setSending(false)
    }
  }

  const quickPrompts = [
    '读取这个 CSV，概括这批流量的主要风险',
    '找出最高风险的 payload 和证据',
    '按攻击类型总结这份数据集',
    '哪些事件更像误报？',
  ]

  return (
    <>
      <PageHeader title="Agent 会话" description="直接和在线 LLM Agent 对话；选择数据集后，Agent 会读取已上传 CSV 样本和后端分析证据。">
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
        <Card title="对话窗口" description={selectedDataset ? `当前上下文：${selectedDataset.filename}` : '未选择数据集时，Agent 会先读取数据集和 CSV 文件列表。'}>
          <div className="chat-window">
            {!chat.length ? (
              <div className="chat-empty">
                <strong>问它一句，别让模型闲着。</strong>
                <span>选中数据集后，Agent 会先调用 CSV 读取工具，再结合 hunt、漏洞候选和攻击面证据回答。</span>
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
                <div className="meta"><span>最大并行</span><strong>{fmtNumber(status.max_parallelism)}</strong><span>确认门</span><strong>{String(status.require_confirmation)}</strong></div>
                <div className="meta"><span>工具</span><strong>{status.allowed_tools.join(', ') || '-'}</strong></div>
              </div>
            ) : <Empty text="尚未获取 Agent 状态" />}
          </Card>

          <Card title="LLM Provider">
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
                {sessions.map((session) => (
                  <button className="history-item" type="button" key={session.id} onClick={() => setChat((current) => [
                    ...current,
                    { id: `h-u-${session.id}`, role: 'user', text: session.message, createdAt: session.created_at },
                    { id: `h-a-${session.id}`, role: 'agent', text: session.answer, createdAt: session.updated_at },
                  ])}>
                    <span>{session.message}</span>
                    <Badge text={session.status} tone={statusTone(session.status)} />
                  </button>
                ))}
              </div>
            ) : <Empty text="暂无历史会话" />}
          </Card>
        </aside>
      </div>
    </>
  )
}

import React, { useMemo, useState } from 'react'
import type { AppContextValue } from '../App'
import {
  queryString,
  type AgentChatResult,
  type AgentMemoryOut,
  type AgentMessageOut,
  type AgentSessionOut,
  type AgentStatusOut,
  type AgentTaskSpecOut,
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

const agentLooks = [
  { match: 'coordinator', icon: 'hub', label: 'CO', tone: 'cyan', role: '调度', task: '编排任务' },
  { match: 'triage', icon: 'funnel', label: 'TR', tone: 'orange', role: '分诊', task: '筛选风险' },
  { match: 'evidence', icon: 'evidence', label: 'EV', tone: 'green', role: '证据', task: '提取证据' },
  { match: 'hunt', icon: 'radar', label: 'HU', tone: 'purple', role: '狩猎', task: '搜索攻击' },
  { match: 'planner', icon: 'plan', label: 'PL', tone: 'blue', role: '规划', task: '生成路径' },
  { match: 'verifier', icon: 'shield', label: 'VE', tone: 'green', role: '验证', task: '核验结论' },
]

function getAgentLook(agent: string, index: number) {
  const normalized = agent.toLowerCase()
  return agentLooks.find((look) => normalized.includes(look.match)) || {
    icon: 'network',
    label: agent.slice(0, 2).toUpperCase(),
    tone: ['cyan', 'orange', 'green', 'purple', 'blue'][index % 5],
    role: '协同',
    task: '协同处理',
  }
}

function AgentIcon({ name, label }: { name: string; label: string }) {
  let glyph: React.ReactNode
  switch (name) {
    case 'hub':
      glyph = <><circle cx="12" cy="12" r="3" /><circle cx="5" cy="6" r="1.8" /><circle cx="19" cy="6" r="1.8" /><circle cx="6" cy="19" r="1.8" /><path d="m7 7.5 3 2.4m4 0 3-2.4m-7 7-3 2.5m7-2.5 3 2.5" /></>
      break
    case 'funnel':
      glyph = <><path d="M4 5h16l-6.2 7.1v5.1l-3.6 1.8v-6.9z" /><path d="M8 8h8M9.5 11h5" /></>
      break
    case 'evidence':
      glyph = <><path d="M7 3.8h7l3 3V20H7z" /><path d="M14 3.8v3h3M9.5 12.5l1.8 1.8 3.6-4" /><path d="M9.5 17h5" /></>
      break
    case 'radar':
      glyph = <><circle cx="12" cy="12" r="7.5" /><circle cx="12" cy="12" r="3" /><path d="M12 12 17.5 6.5M12 3v2M3 12h2M12 19v2M19 12h2" /></>
      break
    case 'plan':
      glyph = <><path d="M5 5h4v4H5zM15 15h4v4h-4zM15 5h4v4h-4z" /><path d="M9 7h6M17 9v6M15 17H9V9" /><circle cx="7" cy="17" r="2" /></>
      break
    case 'shield':
      glyph = <><path d="M12 3 19 6v5.2c0 4.2-2.9 7.9-7 9.8-4.1-1.9-7-5.6-7-9.8V6z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>
      break
    default:
      glyph = <><circle cx="6" cy="12" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="18" cy="18" r="2" /><path d="m8 11 8-4m-8 6 8 4" /></>
  }
  return <svg className="agent-svg" viewBox="0 0 24 24" role="img" aria-label={`${label} ${name}`}><title>{label} 工作图标</title>{glyph}</svg>
}

function messageTone(messageType: string): string {
  if (messageType === 'task') return 'blue'
  if (messageType === 'verification') return 'orange'
  if (messageType === 'summary') return 'purple'
  return 'green'
}

interface TaskPosition {
  x: number
  y: number
  task: AgentTaskSpecOut
}

const STATUS_LEGEND = [
  { tone: 'cyan', label: 'running' },
  { tone: 'green', label: 'completed' },
  { tone: 'orange', label: 'queued' },
  { tone: 'red', label: 'failed' },
]

function TaskGraphCanvas({
  session,
  onSelectTask,
}: {
  session: AgentSessionOut
  onSelectTask: (task: AgentTaskSpecOut) => void
}) {
  const tasks = session.task_graph || []

  const { layers, positions, edges } = useMemo(() => {
    const depthMap = new Map<string, number>()
    const visiting = new Set<string>()
    const resolve = (taskId: string): number => {
      if (depthMap.has(taskId)) return depthMap.get(taskId)!
      if (visiting.has(taskId)) return 0
      visiting.add(taskId)
      const task = tasks.find((t) => t.task_id === taskId)
      if (!task || !task.depends_on.length) {
        depthMap.set(taskId, 0)
        return 0
      }
      const depth = 1 + Math.max(...task.depends_on.map((d) => resolve(d)))
      depthMap.set(taskId, depth)
      return depth
    }
    tasks.forEach((t) => resolve(t.task_id))

    const grouped: AgentTaskSpecOut[][] = []
    tasks.forEach((t) => {
      const d = depthMap.get(t.task_id) || 0
      while (grouped.length <= d) grouped.push([])
      grouped[d].push(t)
    })
    grouped.forEach((layer) => layer.sort((a, b) => b.priority - a.priority))

    const pos = new Map<string, TaskPosition>()
    const layerCount = grouped.length || 1
    grouped.forEach((layerTasks, depth) => {
      const yPercent = layerCount === 1 ? 50 : ((depth + 0.5) / layerCount) * 100
      const widthPerTask = 100 / Math.max(layerTasks.length, 1)
      layerTasks.forEach((task, i) => {
        const xPercent = widthPerTask * (i + 0.5)
        pos.set(task.task_id, { x: xPercent, y: yPercent, task })
      })
    })

    const e: { from: TaskPosition; to: TaskPosition }[] = []
    tasks.forEach((t) => {
      const to = pos.get(t.task_id)
      if (!to) return
      t.depends_on.forEach((depId) => {
        const from = pos.get(depId)
        if (from) e.push({ from, to })
      })
    })
    return { layers: grouped, positions: pos, edges: e }
  }, [tasks])

  if (!tasks.length) {
    return (
      <div className="task-canvas task-canvas-empty">
        <Empty text="后端返回空任务图，等待 Agent 启动后渲染工作流" />
      </div>
    )
  }

  return (
    <div className="task-canvas" style={{ minHeight: Math.max(460, layers.length * 140) }}>
      <div className="task-canvas-grid" aria-hidden="true" />
      <svg className="task-canvas-edges" viewBox="0 0 100 100" preserveAspectRatio="none">
        {edges.map(({ from, to }, i) => (
          <path
            key={`edge-${i}`}
            className={`task-edge ${to.task.status === 'failed' ? 'failed' : ''}`}
            d={`M ${from.x} ${from.y} C ${from.x} ${(from.y + to.y) / 2}, ${to.x} ${(from.y + to.y) / 2}, ${to.x} ${to.y}`}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      {Array.from(positions.values()).map(({ x, y, task }) => {
        const look = getAgentLook(task.agent_name, 0)
        const statusKey = (task.status || 'pending').toLowerCase()
        return (
          <button
            key={task.task_id}
            type="button"
            className={`task-node tone-${look.tone} status-${statusKey}`}
            style={{ left: `${x}%`, top: `${y}%` }}
            onClick={() => onSelectTask(task)}
            title={task.goal}
          >
            <div className="task-node-icon">
              <AgentIcon name={look.icon} label={look.role} />
            </div>
            <div className="task-node-content">
              <div className="task-node-head">
                <strong>{look.label}</strong>
                <span className="task-node-role">{look.role} · {task.agent_name}</span>
              </div>
              <p className="task-node-goal">{task.goal}</p>
              <div className="task-node-meta">
                <Badge text={task.status || 'pending'} tone={statusTone(task.status || 'pending')} />
                {task.requires_confirmation ? <Badge text="需确认" tone="orange" /> : null}
              </div>
            </div>
          </button>
        )
      })}
      <div className="task-canvas-legend" aria-hidden="true">
        {STATUS_LEGEND.map((item) => (
          <span key={item.label} style={{ '--swatch': `var(--color-${item.tone})` } as React.CSSProperties}>
            <i />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  )
}

function TaskDetail({ task }: { task: AgentTaskSpecOut }) {
  return (
    <div className="detail-stack">
      <div className="detail-summary-grid">
        <div><span>任务 ID</span><strong>{task.task_id}</strong></div>
        <div><span>Agent</span><strong>{task.agent_name}</strong></div>
        <div><span>状态</span><strong>{task.status || 'pending'}</strong></div>
        <div><span>优先级</span><strong>P{task.priority}</strong></div>
        <div><span>需要确认</span><strong>{task.requires_confirmation ? '是' : '否'}</strong></div>
        <div><span>依赖任务</span><strong>{task.depends_on.join(', ') || '无'}</strong></div>
      </div>
      <div className="detail-callout">
        <Badge text={task.status || 'pending'} tone={statusTone(task.status || 'pending')} />
        <Badge text={`P${task.priority}`} tone="purple" />
        {task.requires_confirmation ? <Badge text="需要确认" tone="orange" /> : null}
        <Badge text={task.agent_name} tone="blue" />
      </div>
      <section className="detail-section">
        <h3>任务目标</h3>
        <p>{task.goal}</p>
      </section>
      <section className="detail-section">
        <h3>工具列表</h3>
        {task.tool_names.length ? (
          <div className="detail-mini-list">
            {task.tool_names.map((name) => (
              <div className="detail-mini-item" key={name}>
                <div><strong>{name}</strong></div>
              </div>
            ))}
          </div>
        ) : <Empty text="该任务没有声明工具" />}
      </section>
      <section className="detail-section">
        <h3>依赖关系</h3>
        {task.depends_on.length ? (
          <div className="detail-mini-list">
            {task.depends_on.map((dep) => (
              <div className="detail-mini-item" key={dep}>
                <div><strong>{dep}</strong><span>前置任务</span></div>
              </div>
            ))}
          </div>
        ) : <Empty text="无前置依赖，可立即执行" />}
      </section>
      <section className="detail-section">
        <h3>原始任务对象</h3>
        <JsonBlock value={task} />
      </section>
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
        <h3>协作消息摘要</h3>
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

function CollapsibleSection({
  title,
  count,
  hint,
  children,
  defaultOpen = false,
}: {
  title: string
  count?: number
  hint?: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details className="collapsible-section" open={defaultOpen}>
      <summary>
        <span className="collapsible-summary-title">{title}</span>
        {hint ? <span className="collapsible-summary-hint">{hint}</span> : null}
        {count !== undefined ? <span className="collapsible-summary-count">{fmtNumber(count)}</span> : null}
      </summary>
      <div className="collapsible-body">{children}</div>
    </details>
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
  const [detailTask, setDetailTask] = useState<AgentTaskSpecOut | null>(null)

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
      <PageHeader title="Agent 会话" description="左侧选择会话驱动右侧画布，任务图、消息流与长期记忆在同一卡片内串联呈现。">
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
        </aside>
      </div>

      <Card
        title={`工作流画布${selectedSession ? ` · ${selectedSession.id.slice(0, 8)}` : ''}`}
        description="左侧选择会话，右侧按依赖深度分层渲染任务节点；点击节点查看任务详情，下方折叠面板按需展开。"
      >
        <div className="workflow-split">
          <div className="session-rail">
            <div className="session-rail-head">
              <span>会话</span>
              <small>{fmtNumber(sessions.length)}</small>
            </div>
            {sessions.length ? (
              <div className="session-rail-list">
                {sessions.map((session) => {
                  const messageCount = session.runs.reduce((total, run) => total + run.messages.length, 0)
                  const isActive = selectedSession?.id === session.id
                  return (
                    <button
                      key={session.id}
                      type="button"
                      className={`session-rail-item${isActive ? ' active' : ''}`}
                      onClick={() => setSelectedSessionId(session.id)}
                    >
                      <div className="session-rail-top">
                        <Badge text={session.id.slice(0, 8)} tone="blue" />
                        <Badge text={session.status} tone={statusTone(session.status)} />
                      </div>
                      <p>{session.message}</p>
                      <div className="session-rail-meta">
                        <span>{fmtDate(session.created_at)}</span>
                        <span>{fmtNumber(messageCount)} msg</span>
                        <span>{fmtNumber(session.tool_calls.length)} tools</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            ) : <Empty text="暂无历史会话，发送消息后此处会出现记录" />}
          </div>

          <div className="workflow-canvas-area">
            {selectedSession ? (
              <>
                <div className="workflow-canvas-head">
                  <div className="workflow-canvas-title">
                    <Badge text={selectedSession.id.slice(0, 8)} tone="blue" />
                    <Badge text={selectedSession.status} tone={statusTone(selectedSession.status)} />
                    <Badge text={selectedSession.runs.some((run) => run.llm_used) ? 'LLM' : 'local'} tone="purple" />
                    <span>{selectedSession.message}</span>
                  </div>
                  <div className="workflow-canvas-actions">
                    <button className="ghost-btn" type="button" onClick={() => loadSessionIntoChat(selectedSession)}>载入对话</button>
                    <button className="primary-btn" type="button" onClick={() => setDetailSession(selectedSession)}>详细信息</button>
                  </div>
                </div>
                <TaskGraphCanvas session={selectedSession} onSelectTask={setDetailTask} />
              </>
            ) : (
              <div className="task-canvas task-canvas-empty">
                <Empty text="选择左侧会话或发起一次对话后，画布将渲染对应任务图" />
              </div>
            )}
          </div>
        </div>

        {selectedSession ? (
          <div className="workflow-collapsibles">
            <CollapsibleSection
              title="二次任务与待补证据"
              count={followUps.length}
              hint="展示 verifier 或 specialist 生成的后续动作"
            >
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
            </CollapsibleSection>

            <CollapsibleSection
              title="消息流"
              count={selectedMessages.length}
              hint="完整展示角色消息、verification 和 summary"
            >
              <MessageFlow messages={selectedMessages} onOpenDetail={setDetailMessage} />
            </CollapsibleSection>

            <CollapsibleSection
              title="长期记忆"
              count={memory.length}
              hint="展示当前数据集或全局范围内的角色记忆"
            >
              <MemoryList memory={memory} onOpenDetail={setDetailMemory} />
            </CollapsibleSection>
          </div>
        ) : null}
      </Card>

      {detailSession ? (
        <DetailModal
          title={detailSession.message}
          subtitle={`${detailSession.actor} · ${fmtDate(detailSession.created_at)} · ${detailSession.runtime}`}
          onClose={() => setDetailSession(null)}
        >
          <AgentSessionDetail session={detailSession} />
        </DetailModal>
      ) : null}

      {detailTask ? (
        <DetailModal
          title={detailTask.goal}
          subtitle={`${detailTask.agent_name} · ${detailTask.status || 'pending'} · P${detailTask.priority}`}
          onClose={() => setDetailTask(null)}
        >
          <TaskDetail task={detailTask} />
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

import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { AppContextValue } from '../App'
import { queryString, type DashboardOverview, type PaginatedEvents } from '../api'
import { useApiData } from '../useApiData'
import { fmtNumber, fmtDate } from '../ui'

const capabilities = [
  {
    to: '/datasets',
    icon: '📁',
    title: '数据集管理',
    description: '上传和管理 CSV Payload 数据，支持解析、分析和对比。',
    accent: 'var(--color-primary)',
  },
  {
    to: '/events',
    icon: '⚡',
    title: 'Payload 事件',
    description: '查看解析后的事件和检测结果，支持筛选与详情核验。',
    accent: 'var(--color-cyan)',
  },
  {
    to: '/incidents',
    icon: '🔗',
    title: 'Incident 聚类',
    description: '查看相关事件聚合结果，按严重度和状态筛选。',
    accent: 'var(--color-purple)',
  },
  {
    to: '/vulnerabilities',
    icon: '🛡️',
    title: '漏洞候选',
    description: '查看漏洞候选及风险信息，支持深度分析与验证。',
    accent: 'var(--color-orange)',
  },
  {
    to: '/hunt',
    icon: '🔍',
    title: '狩猎工作台',
    description: '使用自然语言查询安全事件，支持 LLM 智能解释。',
    accent: 'var(--color-green)',
  },
  {
    to: '/agent',
    icon: '🤖',
    title: 'Agent 会话',
    description: '通过多 Agent 协同分析 Payload，追踪会话与执行状态。',
    accent: 'var(--color-primary)',
  },
]

const workflowSteps = [
  { num: 1, title: '上传 Payload', desc: 'CSV 数据导入' },
  { num: 2, title: '解析事件', desc: '字段提取与解码' },
  { num: 3, title: '规则检测', desc: '多引擎匹配' },
  { num: 4, title: '风险评分', desc: '量化威胁等级' },
  { num: 5, title: 'Agent 研判', desc: 'LLM 协同分析' },
  { num: 6, title: '证据与报告', desc: '完整溯源输出' },
]

const orbitNodes = [
  { to: '/', icon: '📊', label: '控制台', english: 'Console', description: '查看系统健康状态、运行指标与全局分析概览。', accent: 'var(--color-primary)' },
  { to: '/datasets', icon: '📁', label: '数据集管理', english: 'Datasets', description: '上传、解析和管理 Payload 数据集，统一沉淀分析样本。', accent: 'var(--color-cyan)' },
  { to: '/events', icon: '⚡', label: 'Payload 事件', english: 'Events', description: '追踪解析后的 Payload 事件、检测结果与证据详情。', accent: 'var(--color-orange)' },
  { to: '/incidents', icon: '🔗', label: 'Incident 聚类', english: 'Incidents', description: '将相关安全事件聚合成 Incident，快速定位攻击链路。', accent: 'var(--color-purple)' },
  { to: '/vulnerabilities', icon: '🛡️', label: '漏洞候选', english: 'Vulnerabilities', description: '查看漏洞候选、风险等级与深度验证结果。', accent: 'var(--color-red)' },
  { to: '/hunt', icon: '🔎', label: '狩猎工作台', english: 'Hunt', description: '用自然语言检索安全事件，开展证据驱动的威胁狩猎。', accent: 'var(--color-green)' },
  { to: '/jobs', icon: '📋', label: '分析任务', english: 'Jobs', description: '查看任务队列、执行进度和批量分析状态。', accent: 'var(--color-primary)' },
  { to: '/agent', icon: '🤖', label: 'Agent 会话', english: 'Agent', description: '通过多 Agent 协同分析 Payload，追踪推理与执行过程。', accent: 'var(--color-cyan)' },
] as const

function PayloadOrb() {
  const [rotation, setRotation] = useState(0)
  const [pulsePhase, setPulsePhase] = useState(0)
  const [activeNode, setActiveNode] = useState<number | null>(null)
  const rotationRef = useRef(0)
  const navigate = useNavigate()

  useEffect(() => {
    if (activeNode !== null) return undefined
    let frame: number
    const start = performance.now() - (rotationRef.current / 5) * 1000
    const animate = (now: number) => {
      const elapsed = (now - start) / 1000
      const nextRotation = (elapsed * 5) % 360
      rotationRef.current = nextRotation
      setRotation(nextRotation)
      setPulsePhase(elapsed)
      frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [activeNode])

  const particleCount = 12
  const particles = Array.from({ length: particleCount }, (_, i) => {
    const angle = (i / particleCount) * Math.PI * 2 + rotation * (Math.PI / 180)
    const radius = 100 + Math.sin(pulsePhase * 0.5 + i) * 8
    const x = 160 + Math.cos(angle) * radius
    const y = 160 + Math.sin(angle) * radius
    return { x, y, i }
  })

  const selectedNode = orbitNodes[activeNode ?? 0]
  const orbitPaused = activeNode !== null

  return (
    <div className={`orb-container${orbitPaused ? ' orbit-paused' : ''}`}>
      <svg viewBox="0 0 320 320" className="orb-svg" aria-hidden="true">
        <defs>
          <radialGradient id="coreGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--color-cyan)" stopOpacity="0.6" />
            <stop offset="40%" stopColor="var(--color-primary)" stopOpacity="0.3" />
            <stop offset="100%" stopColor="var(--bg-card)" stopOpacity="0" />
          </radialGradient>
          <filter id="orbGlow">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {Array.from({ length: 8 }, (_, i) => i * 45).map((deg) => {
          const r = 120
          const rad = ((deg + rotation) * Math.PI) / 180
          const x1 = 160 + Math.cos(rad) * r
          const y1 = 160 + Math.sin(rad) * r
          return (
            <line
              key={`scan-${deg}`}
              x1={x1}
              y1={y1}
              x2={160}
              y2={160}
              stroke="var(--color-cyan)"
              strokeWidth="0.5"
              opacity={0.08 + Math.abs(Math.sin(pulsePhase * 2 + deg)) * 0.12}
            />
          )
        })}

        <circle cx="160" cy="160" r="110" fill="none" stroke="var(--border-hover)" strokeWidth="0.5" strokeDasharray="2 4" opacity="0.4">
          <animateTransform attributeName="transform" type="rotate" from="0 160 160" to="360 160 160" dur="30s" repeatCount="indefinite" />
        </circle>

        <circle cx="160" cy="160" r="90" fill="none" stroke="var(--color-cyan)" strokeWidth="0.5" strokeDasharray="1 6" opacity="0.25">
          <animateTransform attributeName="transform" type="rotate" from="360 160 160" to="0 160 160" dur="20s" repeatCount="indefinite" />
        </circle>

        <circle cx="160" cy="160" r="65" fill="none" stroke="var(--color-primary)" strokeWidth="0.5" opacity="0.15" />

        <circle cx="160" cy="160" r="55" fill="url(#coreGrad)" filter="url(#orbGlow)">
          <animate attributeName="r" values="52;58;52" dur="3s" repeatCount="indefinite" />
        </circle>

        {orbitNodes.map((node, i) => {
          const angle = -90 + i * 45
          const rad = ((angle + rotation * 0.5) * Math.PI) / 180
          const r = 116
          const x = 160 + Math.cos(rad) * r
          const y = 160 + Math.sin(rad) * r
          return (
            <g key={i}>
              <line x1={160} y1={160} x2={x} y2={y} stroke="var(--color-cyan)" strokeWidth="0.8" opacity="0.2" strokeDasharray="3 3">
                <animate attributeName="stroke-dashoffset" values="0;-12" dur="1.5s" repeatCount="indefinite" />
              </line>
              <circle cx={x} cy={y} r={activeNode === i ? 18 : 14} fill="var(--bg-card)" stroke={node.accent} strokeWidth={activeNode === i ? 1.8 : 1} opacity={activeNode === i ? 1 : 0.85}>
                <animate attributeName="opacity" values="0.7;1;0.7" dur={`${2 + i * 0.3}s`} repeatCount="indefinite" />
              </circle>
              <text x={x} y={y + 3} textAnchor="middle" fill="var(--text-primary)" fontSize="7" fontWeight="600">{node.english}</text>
              <text x={x} y={y + 19} textAnchor="middle" fill={node.accent} fontSize="5.5" letterSpacing=".7">{node.label}</text>
            </g>
          )
        })}

        {particles.map((p) => (
          <circle key={p.i} cx={p.x} cy={p.y} r="1.5" fill="var(--color-cyan)" opacity={0.3 + Math.sin(pulsePhase * 3 + p.i) * 0.3}>
            <animate attributeName="opacity" values="0.2;0.7;0.2" dur={`${1.5 + (p.i % 3) * 0.5}s`} repeatCount="indefinite" />
          </circle>
        ))}

        <circle cx="160" cy="160" r="28" fill="none" stroke="var(--color-cyan)" strokeWidth="1" opacity="0.5">
          <animate attributeName="r" values="26;32;26" dur="2.5s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.3;0.7;0.3" dur="2.5s" repeatCount="indefinite" />
        </circle>

        <text x="160" y="163" textAnchor="middle" fill="var(--text-primary)" fontSize="7" fontWeight="700" letterSpacing="1.8">FLOW VUL HUNT</text>
      </svg>
      <div className="orbit-node-layer" onMouseLeave={() => setActiveNode(null)}>
        {orbitNodes.map((node, i) => {
          const angle = -90 + i * 45
          const rad = ((angle + rotation * 0.5) * Math.PI) / 180
          const x = 50 + Math.cos(rad) * 36.25
          const y = 50 + Math.sin(rad) * 36.25
          return (
            <button
              key={node.to}
              type="button"
              className={`orbit-node-hit${activeNode === i ? ' is-active' : ''}`}
              style={{ left: `${x}%`, top: `${y}%`, '--node-accent': node.accent } as React.CSSProperties}
              aria-label={`进入${node.label}`}
              onMouseEnter={() => setActiveNode(i)}
              onFocus={() => setActiveNode(i)}
              onBlur={() => setActiveNode(null)}
              onClick={() => navigate(node.to)}
            >
              <span className="orbit-node-icon" aria-hidden="true">{node.icon}</span>
            </button>
          )
        })}
      </div>
      {activeNode !== null && (
        <div className="orbit-node-card" style={{ '--node-accent': selectedNode.accent } as React.CSSProperties}>
          <div className="orbit-card-kicker"><span className="orbit-card-dot" /> MODULE {String(activeNode + 1).padStart(2, '0')}</div>
          <strong>{selectedNode.icon} {selectedNode.label}</strong>
          <span>{selectedNode.description}</span>
          <button type="button" onClick={() => navigate(selectedNode.to)}>进入模块 <span aria-hidden="true">→</span></button>
        </div>
      )}
    </div>
  )
}

function AnimatedNumber({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    const start = display
    const end = value
    if (start === end) return
    const duration = 800
    const startTime = performance.now()
    let frame: number

    const tick = (now: number) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(start + (end - start) * eased)
      if (progress < 1) frame = requestAnimationFrame(tick)
    }

    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value])

  const formatted = decimals > 0
    ? display.toFixed(decimals)
    : fmtNumber(Math.round(display))

  return <span className="tick-number">{formatted}</span>
}

export function HomePage({ context }: { context: AppContextValue }) {
  const navigate = useNavigate()
  const { data: overview, error, loading } = useApiData(
    () => context.api<DashboardOverview>(`/api/dashboard/overview${queryString({ dataset_id: context.selectedDataset })}`),
    [context, context.selectedDataset],
  )

  const { data: eventsData } = useApiData(
    () => context.api<PaginatedEvents>(`/api/events${queryString({ dataset_id: context.selectedDataset, limit: 8 })}`),
    [context, context.selectedDataset],
  )

  const totals = overview?.totals || {}
  const risk = overview?.risk || {}
  const events = eventsData?.items || []

  const tickerItems = [
    { label: 'DATASETS', value: totals.datasets ?? 0 },
    { label: 'EVENTS', value: totals.events ?? 0 },
    { label: 'EVIDENCE', value: totals.findings ?? 0 },
    { label: 'INCIDENTS', value: totals.incidents ?? 0 },
    { label: 'ACTIVE JOBS', value: context.metrics?.running_jobs ?? 0 },
    { label: 'MAX RISK', value: risk.maximum ?? 0, decimals: 1 },
  ]

  const eventStream = events.map((e, i) => {
    const verdictLabel = e.verdict?.toUpperCase() || 'UNKNOWN'
    const target = `${e.host || '—'}${e.path || ''}`
    return {
      id: e.id,
      time: fmtDate(e.created_at),
      verdictLabel,
      method: e.http_method || e.protocol || '—',
      target,
      risk: e.risk_score ?? 0,
      riskPct: Math.min(100, Math.max(0, Math.round(e.risk_score ?? 0))),
      payloadLength: e.payload_length ?? 0,
      tone: e.verdict === 'malicious' ? 'red' : e.verdict === 'suspicious' ? 'orange' : 'blue',
      delay: i * 0.15,
    }
  })

  const streamItems = eventStream.length ? eventStream : null

  return (
    <div className="home-root home-page">
      <section className="hero-fullscreen">
        <div className="hero-bg-grid" />
        <div className="hero-bg-particles">
          {Array.from({ length: 30 }).map((_, i) => (
            <span
              key={i}
              className="bg-particle"
              style={{
                left: `${(i * 37 + 13) % 100}%`,
                top: `${(i * 53 + 7) % 100}%`,
                animationDelay: `${(i * 0.2) % 5}s`,
                animationDuration: `${4 + (i % 4)}s`,
              }}
            />
          ))}
        </div>
        <div className="hero-scanline" />

        <div className="hero-fullscreen-inner">
          <div className="hero-left">
            <div className="hero-eyebrow">
              <span className="eyebrow-dot" />
              PAYLOAD THREAT HUNTING PLATFORM
            </div>
            <h1 className="hero-title">
              Flow <span className="title-glow">Vul</span> Hunt
            </h1>
            <p className="hero-tagline">
              Evidence-based security operations for payload threat hunting
            </p>
            <div className="hero-desc">
              面向 Payload 数据的多引擎检测、证据核验与风险研判平台
            </div>
            <div className="hero-pills">
              {[
                { text: '多引擎检测', accent: 'var(--color-cyan)' },
                { text: '证据核验', accent: 'var(--color-green)' },
                { text: '风险研判', accent: 'var(--color-orange)' },
                { text: 'Agent 协同', accent: 'var(--color-purple)' },
                { text: '威胁狩猎', accent: 'var(--color-red)' },
              ].map((pill) => (
                <span key={pill.text} className="capsule" style={{ '--cap-accent': pill.accent } as React.CSSProperties}>{pill.text}</span>
              ))}
            </div>
            <div className="hero-actions">
              <button className="primary-btn hero-cta-primary" type="button" onClick={() => navigate('/')}>
                进入系统控制台
                <span className="cta-arrow">→</span>
              </button>
              <button className="ghost-btn hero-cta-secondary" type="button" onClick={() => navigate('/hunt')}>
                开始一次数据分析
              </button>
            </div>
            <div className="hero-status-row">
              <div className="status-indicator online">
                <span className="status-pulse" />
                SYSTEM ONLINE
              </div>
              <div className="status-indicator">
                <span className="status-dot-sm" />
                {context.health?.llm_configured ? 'LLM READY' : 'LLM STANDBY'}
              </div>
              {context.health?.database && (
                <div className="status-indicator">
                  <span className="status-dot-sm" />
                  DB: {context.health.database}
                </div>
              )}
            </div>
          </div>

          <div className="hero-right">
            <PayloadOrb />
          </div>
        </div>
      </section>

      <div className="section-title">
        <h2>核心能力</h2>
        <span className="section-sub">六大功能模块，覆盖 Payload 威胁检测全流程</span>
      </div>

      <div className="capability-grid">
        {capabilities.map((cap, i) => (
          <a
            key={cap.to}
            className="capability-card"
            style={{ '--cap-accent': cap.accent } as React.CSSProperties}
            onClick={(e) => { e.preventDefault(); navigate(cap.to) }}
            href={cap.to}
          >
            <div className="capability-icon">{cap.icon}</div>
            <h3>{cap.title}</h3>
            <p>{cap.description}</p>
            <div className="capability-meta">
              <span className="capsule">MODULE {String(i + 1).padStart(2, '0')}</span>
              <span className="enter-link">进入模块</span>
            </div>
          </a>
        ))}
      </div>

      <div className="section-title">
        <h2>工作流程</h2>
        <span className="section-sub">从 Payload 上传到报告输出的完整链路</span>
      </div>

      <div className="workflow">
        {workflowSteps.map((step) => (
          <div key={step.num} className="workflow-step">
            <div className="step-num">{step.num}</div>
            <h4>{step.title}</h4>
            <p>{step.desc}</p>
          </div>
        ))}
      </div>

      <section className="data-ticker-section">
        <div className="ticker-label-row">
          <span className="ticker-label">
            <span className="status-dot-sm online" />
            LIVE METRICS
          </span>
          <span className="ticker-meta">REAL-TIME · {loading ? 'LOADING' : error ? 'OFFLINE' : 'STREAMING'}</span>
        </div>
        <div className="data-ticker">
          {tickerItems.map((item, i) => (
            <div key={item.label} className="ticker-cell">
              <div className="ticker-value">
                {loading ? '—' : <AnimatedNumber value={item.value} decimals={item.decimals || 0} />}
              </div>
              <div className="ticker-label-sm">{item.label}</div>
              {i < tickerItems.length - 1 && <div className="ticker-sep" />}
            </div>
          ))}
        </div>
      </section>

      <section className="event-stream-section">
        <div className="stream-label-row">
          <span className="stream-label">
            <span className="status-dot-sm online" />
            RECENT EVENTS
          </span>
          <span className="stream-meta">{streamItems ? `${streamItems.length} EVENTS · LIVE FEED` : 'AWAITING INGESTION'}</span>
        </div>

        <div className="event-stream">
          {streamItems ? (
            <div className="stream-list">
              {streamItems.map((evt) => (
                <div
                  key={evt.id}
                  className={`stream-item tone-${evt.tone}`}
                  style={{ animationDelay: `${evt.delay}s` }}
                >
                  <div className="stream-head">
                    <span className={`capsule stream-verdict tone-${evt.tone}`}>{evt.verdictLabel}</span>
                    <span className="stream-time">{evt.time}</span>
                  </div>
                  <div className="stream-main">
                    <span className="stream-method">{evt.method}</span>
                    <span className="stream-target" title={evt.target}>{evt.target}</span>
                  </div>
                  <div className="stream-stats">
                    <div className="stream-risk" title={`风险分 ${evt.risk}`}>
                      <span className="stream-risk-label">RISK</span>
                      <div className="stream-risk-bar"><span style={{ width: `${evt.riskPct}%` }} /></div>
                      <strong>{evt.risk.toFixed(1)}</strong>
                    </div>
                    <span className="stream-len" title="Payload 大小">{fmtNumber(evt.payloadLength)} B</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="stream-empty">
              <div className="stream-empty-pulse" />
              <div className="stream-empty-title">NO ACTIVE EVENTS</div>
              <div className="stream-empty-sub">WAITING FOR PAYLOAD INGESTION</div>
            </div>
          )}
        </div>
      </section>

      <footer className="home-footer">
        <div className="footer-grid-line" />
        <div className="footer-inner">
          <span>FLOW VUL HUNT</span>
          <span className="footer-dot">●</span>
          <span>Payload Threat Command Center</span>
          <span className="footer-dot">●</span>
          <span>{new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  )
}

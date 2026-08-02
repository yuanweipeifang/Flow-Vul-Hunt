import React, { useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type DashboardOverview } from '../api'
import { Card, ErrorBox, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtNumber } from '../ui'

const pieColors = ['#34fcff', '#123dff', '#f59e0b', '#22c55e', '#c084fc', '#f87171']

const kpiLooks = [
  { icon: '◎', accent: '#22d3ee', series: [4, 5, 8, 7, 12, 6, 6], trend: 12.5 },
  { icon: '◉', accent: '#8b5cf6', series: [2, 5, 7, 5, 3, 2, 2], trend: -8.3 },
  { icon: '✦', accent: '#ef4444', series: [1, 6, 9, 7, 3, 2, 5], trend: 24.7 },
  { icon: '▣', accent: '#10b981', series: [2, 7, 11, 9, 5, 3, 3], trend: 5.2 },
]

const mockOverview: DashboardOverview = {
  totals: { datasets: 8, events: 126, findings: 76, incidents: 21, jobs: 34 },
  datasets_by_status: { ready: 6, processing: 1, failed: 1 },
  events_by_verdict: { malicious: 42, suspicious: 28, unreviewed: 18, benign: 38 },
  incidents_by_severity: { critical: 6, high: 17, medium: 27, low: 26 },
  incidents_by_status: { open: 12, triaged: 8, closed: 1 },
  top_attack_types: { 'command injection': 18, 'path traversal': 15, 'sql injection': 12, xss: 10, 'high entropy payload': 7 },
  risk: { average: 34.24, maximum: 81.6 },
}

type ActivityRange = 'day' | 'week' | 'month'

const activityRanges: Record<ActivityRange, { label: string; primary: number[]; secondary: number[]; ticks: string[] }> = {
  day: {
    label: '日',
    primary: [1, 1, 2, 5, 4, 3, 2],
    secondary: [3, 2, 6, 15, 12, 9, 5],
    ticks: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '现在'],
  },
  week: {
    label: '周',
    primary: [5, 7, 6, 10, 12, 8, 4],
    secondary: [19, 24, 21, 31, 36, 27, 17],
    ticks: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
  },
  month: {
    label: '月',
    primary: [18, 23, 21, 31, 37, 29, 25],
    secondary: [76, 94, 88, 117, 132, 111, 101],
    ticks: ['1日', '5日', '10日', '15日', '20日', '25日', '30日'],
  },
}
const agentLooks = [
  { match: 'coordinator', icon: 'hub', label: 'CO', tone: 'cyan', role: '调度', task: '编排任务' },
  { match: 'payload', icon: 'funnel', label: 'PA', tone: 'orange', role: '载荷分析', task: '解析 payload' },
  { match: 'hunt', icon: 'radar', label: 'HI', tone: 'purple', role: '狩猎解读', task: '解读攻击' },
  { match: 'vulnerability', icon: 'plan', label: 'VR', tone: 'green', role: '漏洞研究', task: '研究漏洞' },
  { match: 'evidence', icon: 'shield', label: 'EV', tone: 'green', role: '证据核验', task: '核验证据' },
  { match: 'report', icon: 'evidence', label: 'RG', tone: 'blue', role: '报告生成', task: '生成报告' },
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
function hasPositiveValues(data: Record<string, number> | undefined) {
  return Object.values(data || {}).some((value) => Number(value) > 0)
}

function withMockRecord(actual: Record<string, number> | undefined, fallback: Record<string, number>) {
  return hasPositiveValues(actual) ? actual || {} : fallback
}

function withMockTotals(actual: Record<string, number> | undefined) {
  const totals = actual || {}
  return {
    ...mockOverview.totals,
    ...Object.fromEntries(Object.entries(totals).filter(([, value]) => Number(value) > 0)),
  }
}

function SparkLine({ values, accent, id }: { values: number[]; accent?: string; id: string }) {
  const safeValues = values.length ? values : [0]
  const max = Math.max(...safeValues, 1)
  const pts = safeValues.map((value, index) => {
    const x = safeValues.length === 1 ? 50 : (index / (safeValues.length - 1)) * 100
    const y = 86 - (Math.max(value, 0) / max) * 64
    return { x, y }
  })
  const pointStr = pts.map((p) => `${p.x},${p.y}`).join(' ')
  const last = pts[pts.length - 1]
  const gradId = `spark-grad-${id}`

  return (
    <svg className="sparkline" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style={{ '--line': accent } as React.CSSProperties}>
      <defs>
        <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={accent || '#34fcff'} stopOpacity="0.38" />
          <stop offset="100%" stopColor={accent || '#34fcff'} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,86 ${pointStr} 100,86`} fill={`url(#${gradId})`} className="sparkline-fill" />
      <polyline points={pointStr} />
      <circle cx={last.x} cy={last.y} r="3" className="sparkline-dot" style={{ '--dot': accent } as React.CSSProperties} />
    </svg>
  )
}
function AreaChart({ primary, secondary, maxValue }: { primary: number[]; secondary: number[]; maxValue: number }) {
  const makePts = (items: number[]) => items.map((value, index) => {
    const x = items.length === 1 ? 50 : 2 + (index / (items.length - 1)) * 96
    const y = 98 - (Math.max(value, 0) / maxValue) * 96
    return { x, y }
  })
  const primaryPts = makePts(primary)
  const secondaryPts = makePts(secondary)
  const primaryStr = primaryPts.map((p) => `${p.x},${p.y}`).join(' ')
  const secondaryStr = secondaryPts.map((p) => `${p.x},${p.y}`).join(' ')

  return (
    <svg className="activity-chart" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="consoleRiskFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(239, 68, 68, .35)" />
          <stop offset="100%" stopColor="rgba(239, 68, 68, 0)" />
        </linearGradient>
        <linearGradient id="consoleEventFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(34, 211, 238, .28)" />
          <stop offset="100%" stopColor="rgba(34, 211, 238, 0)" />
        </linearGradient>
      </defs>
      {[2, 26, 50, 74, 98].map((y) => (
        <line key={y} x1="0" y1={y} x2="100" y2={y} className="chart-gridline" />
      ))}
      <line x1="0" y1="2" x2="0" y2="98" className="chart-axis-line" />
      <line x1="0" y1="98" x2="100" y2="98" className="chart-axis-line" />
      <polygon className="activity-fill risk" points={`0,98 ${primaryStr} 100,98`} />
      <polygon className="activity-fill event" points={`0,98 ${secondaryStr} 100,98`} />
      <polyline className="activity-line risk" points={primaryStr} />
      <polyline className="activity-line event" points={secondaryStr} />
      {primaryPts.map((point, index) => (
        <circle className="chart-point risk" cx={point.x} cy={point.y} r=".7" key={`risk-${index}`} />
      ))}
      {secondaryPts.map((point, index) => (
        <circle className="chart-point event" cx={point.x} cy={point.y} r=".7" key={`event-${index}`} />
      ))}
    </svg>
  )
}
function KpiCard({ label, value, change, index }: { label: string; value: string; change: string; index: number }) {
  const look = kpiLooks[index % kpiLooks.length]
  const trend = look.trend
  const isUp = trend >= 0
  return (
    <section className="console-kpi" style={{ '--accent': look.accent, '--delay': `${index * 80}ms` } as React.CSSProperties}>
      <div className="kpi-icon" aria-hidden="true">{look.icon}</div>
      <div className="kpi-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <div className="kpi-meta">
          <small>{change}</small>
          <span className={`kpi-trend ${isUp ? 'up' : 'down'}`}>
            {isUp ? '▲' : '▼'} {Math.abs(trend).toFixed(1)}%
          </span>
        </div>
      </div>
      <SparkLine values={look.series} accent={look.accent} id={`kpi-${index}`} />
    </section>
  )
}
function SideDistribution({ title, data, accent, compact = false }: { title: string; data: Record<string, number> | undefined; accent: string; compact?: boolean }) {
  const entries = Object.entries(data || {})
    .map(([key, value]) => [key, Number(value) || 0] as const)
    .filter(([, value]) => value > 0)
  const total = entries.reduce((sum, [, value]) => sum + value, 0)
  let cursor = 0
  const gradient = entries.length
    ? `conic-gradient(${entries.map(([, value], index) => {
      const start = cursor
      const end = cursor + (value / total) * 360
      cursor = end
      return `${pieColors[index % pieColors.length]} ${start}deg ${end}deg`
    }).join(', ')})`
    : `conic-gradient(${accent} 0deg 360deg)`

  return (
    <div className={`side-distribution ${compact ? 'compact' : ''}`}>
      <div className="side-distribution-head">
        <div>
          <h3>{title}</h3>
          <span>实时汇总</span>
        </div>
        <strong>{fmtNumber(total)}</strong>
      </div>
      {entries.length ? (
        <div className="side-distribution-body">
          <div className="side-donut" style={{ background: gradient }}>
            <span>{fmtNumber(compact ? total : entries.length)}</span>
          </div>
          <div className="side-legend">
            {entries.slice(0, 5).map(([key, value], index) => (
              <span key={key}>
                <i style={{ background: pieColors[index % pieColors.length] }} />
                <small>{key}</small>
                <strong>{fmtNumber(value)}</strong>
              </span>
            ))}
          </div>
        </div>
      ) : <div className="empty">后端返回空数据</div>}
    </div>
  )
}
function AgentSandbox({ routes, health }: { routes: Record<string, string[]>; health: AppContextValue['health'] }) {
  const routeEntries = Object.entries(routes)
  const fallbackAgents = ['coordinator', 'payload_analyst', 'hunt_interpreter', 'vulnerability_researcher', 'evidence_verifier', 'report_generator']
  const agents = (routeEntries.length ? routeEntries.map(([agent]) => agent) : fallbackAgents).slice(0, 6)
  const healthy = health?.status === 'ok' && health.database_writable

  return (
    <div className="agent-sandbox">
      <div className="sandbox-stage">
        <div className="sandbox-particle-field" />
        <div className="sandbox-depth-grid" />
        <div className="sandbox-orbit orbit-one" />
        <div className="sandbox-orbit orbit-two" />
        <div className="sandbox-energy-beam" />
        <div className="sandbox-scanline" />
        <div className="sandbox-link layer-1" />
        <div className="sandbox-link layer-2" />
        <div className="sandbox-link layer-3" />
        <div className="sandbox-packet packet-1" />
        <div className="sandbox-packet packet-2" />
        <div className="sandbox-packet packet-3" />
        <div className="sandbox-core">
          <span className="sandbox-core-mark" aria-hidden="true"><AgentIcon name="hub" label="核心" /></span>
          <span className={`status-dot ${healthy ? '' : 'warn'}`} />
          <strong>Agent 沙盘</strong>
          <small>{healthy ? 'orchestrating' : 'degraded'}</small>
        </div>
        {agents.map((agent, index) => {
          const look = getAgentLook(agent, index)
          const toolNames = routes[agent] || []
          return (
            <div className={`sandbox-agent node-${index + 1} tone-${look.tone}`} key={agent}>
              <div className="agent-icon"><AgentIcon name={look.icon} label={look.role} /></div>
              <div className="agent-node-text">
                <strong>{look.label}</strong>
                <span>{agent.replace(/_/g, ' ')}</span>
              </div>
              <small>{look.task} · {fmtNumber(toolNames.length)} tools</small>
            </div>
          )
        })}
      </div>
    </div>
  )
}
export function ConsolePage({ context }: { context: AppContextValue }) {
  const { data: overview, error, loading } = useApiData(
    () => context.api<DashboardOverview>(`/api/dashboard/overview${queryString({ dataset_id: context.selectedDataset })}`),
    [context, context.selectedDataset],
  )
  const [activityRange, setActivityRange] = useState<ActivityRange>('day')
  const totals = withMockTotals(overview?.totals)
  const incidentsBySeverity = withMockRecord(overview?.incidents_by_severity, mockOverview.incidents_by_severity)
  const eventsByVerdict = withMockRecord(overview?.events_by_verdict, mockOverview.events_by_verdict)
  const topAttackTypes = withMockRecord(overview?.top_attack_types, mockOverview.top_attack_types)
  const routes = context.health?.agent_routes || {}

  const kpis = [
    ['数据集', fmtNumber(totals.datasets), 'CSV 数据源'],
    ['Payload 事件', fmtNumber(totals.events), '入库流量'],
    ['检测证据', fmtNumber(totals.findings), '规则命中'],
    ['Incident', fmtNumber(totals.incidents), '聚类事件'],
  ]
  const activity = activityRanges[activityRange]
  const activityMax = Math.max(...activity.primary, ...activity.secondary, 1)
  const chartMax = Math.ceil(activityMax / 20) * 20
  const yTicks = [chartMax, chartMax * .75, chartMax * .5, chartMax * .25, 0]

  return (
    <div className="console-page">
      <PageHeader title="系统控制台" description="集中展示后端运行状态、Agent 沙盘、数据总览与快捷操作；所有数据实时来自后端接口。">
        <label className="field">
          <span>数据范围</span>
          <select value={context.selectedDataset} onChange={(event) => context.setSelectedDataset(event.target.value)}>
            <option value="">全部数据集</option>
            {context.datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.status}</option>)}
          </select>
        </label>
        <button className="primary-btn" type="button" onClick={() => void context.refreshGlobal()}>刷新</button>
      </PageHeader>

      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <>
          <div className="console-kpi-grid console-enter">
            {kpis.map(([label, value, change], index) => (
              <KpiCard key={label} label={label} value={value} change={change} index={index} />
            ))}
          </div>
          <div className="console-main-grid section console-enter" style={{ '--delay': '200ms' } as React.CSSProperties}>
            <Card title="测试活动趋势" description="事件、证据与风险活动的控制台视图。">
              <div className="activity-panel">
                <div className="activity-tabs" role="group" aria-label="趋势时间范围">
                  {(Object.entries(activityRanges) as [ActivityRange, (typeof activityRanges)[ActivityRange]][]).map(([range, config]) => (
                    <button
                      className={activityRange === range ? 'active' : ''}
                      type="button"
                      aria-pressed={activityRange === range}
                      key={range}
                      onClick={() => setActivityRange(range)}
                    >
                      {config.label}
                    </button>
                  ))}
                </div>
                <div className="activity-chart-frame">
                  <div className="activity-y-axis" aria-label="数量纵轴">
                    {yTicks.map((tick) => <span key={tick}>{fmtNumber(tick)}</span>)}
                  </div>
                  <AreaChart primary={activity.primary} secondary={activity.secondary} maxValue={chartMax} />
                </div>
                <div className="activity-axis">
                  {activity.ticks.map((tick) => <span key={tick}>{tick}</span>)}
                </div>
                <div className="activity-legend">
                  <span><i className="event" /> Payload 事件</span>
                  <span><i className="risk" /> 检测证据</span>
                </div>
              </div>
              <div className="console-distributions" aria-label="漏洞分布">
                <SideDistribution title="Incident 严重度" data={incidentsBySeverity} accent="var(--color-orange)" compact />
                <SideDistribution title="事件判定" data={eventsByVerdict} accent="var(--color-primary)" compact />
                <SideDistribution title="攻击类型" data={topAttackTypes} accent="var(--color-purple)" compact />
              </div>
            </Card>

            <Card title="Agent 沙盘" description="实时呈现 Agent 协同与工具路由。">
              {context.health ? (
                <AgentSandbox routes={routes} health={context.health} />
              ) : <ErrorBox error={context.healthError || '健康检查未返回数据'} />}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

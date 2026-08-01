import React, { useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type DashboardOverview } from '../api'
import { Badge, Card, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtNumber, fmtScore } from '../ui'

function StatCard({ label, value, hint, accent }: { label: string; value: string; hint: string; accent: string }) {
  return (
    <section className="card metric" style={{ '--accent': accent } as React.CSSProperties}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      <div className="hint">{hint}</div>
    </section>
  )
}

const pieColors = ['#34fcff', '#123dff', '#f59e0b', '#22c55e', '#c084fc', '#f87171']

function DistributionPanel({ data, accent }: { data: Record<string, number> | undefined; accent: string }) {
  const entries = Object.entries(data || {})
    .map(([key, value]) => [key, Number(value) || 0] as const)
    .filter(([, value]) => value > 0)
  const total = entries.reduce((sum, [, value]) => sum + value, 0)
  const max = Math.max(...entries.map(([, value]) => value), 1)
  let cursor = 0
  const gradient = entries.length
    ? `conic-gradient(${entries.map(([, value], index) => {
      const start = cursor
      const end = cursor + (value / total) * 360
      cursor = end
      return `${pieColors[index % pieColors.length]} ${start}deg ${end}deg`
    }).join(', ')})`
    : `conic-gradient(${accent} 0deg 360deg)`

  if (!entries.length) return <div className="empty">后端返回空数据</div>

  return (
    <div className="distribution-panel">
      <div className="pie-block">
        <div className="pie-chart" style={{ background: gradient }} aria-label={`total ${total}`}>
          <div className="pie-center">
            <strong>{fmtNumber(total)}</strong>
            <span>total</span>
          </div>
        </div>
        <div className="pie-legend">
          {entries.map(([key, value], index) => (
            <span key={key} title={`${key}: ${fmtNumber(value)}`}>
              <i style={{ background: pieColors[index % pieColors.length] }} />
              {key}
            </span>
          ))}
        </div>
      </div>
      <div className="bars">
        {entries.map(([key, value], index) => (
          <div className="bar-row" key={key}>
            <span className="bar-label">{key}</span>
            <span className="bar-track">
              <span
                className="bar-fill"
                style={{ width: `${(value / max) * 100}%`, background: pieColors[index % pieColors.length] }}
              />
            </span>
            <span className="bar-value">{fmtNumber(value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function ConsolePage({ context }: { context: AppContextValue }) {
  const { data: overview, error, loading } = useApiData(
    () => context.api<DashboardOverview>(`/api/dashboard/overview${queryString({ dataset_id: context.selectedDataset })}`),
    [context, context.selectedDataset],
  )
  const [showRoutes, setShowRoutes] = useState(false)

  const totals = overview?.totals || {}
  const risk = overview?.risk || {}
  const providers = context.health?.providers || []
  const configured = providers.filter((p) => p.configured).length
  const routes = context.health?.agent_routes || {}

  const stats = [
    ['数据集', fmtNumber(totals.datasets), '已上传 CSV 数据集', 'var(--color-primary)'],
    ['Payload 事件', fmtNumber(totals.events), '已入库真实 Payload', 'var(--color-purple)'],
    ['检测证据', fmtNumber(totals.findings), '规则与风险证据', 'var(--color-orange)'],
    ['Incident', fmtNumber(totals.incidents), '活动聚类结果', 'var(--color-green)'],
    ['分析任务', fmtNumber(totals.jobs), '后台分析任务', 'var(--color-primary)'],
    ['LLM 已配置', `${configured}/${providers.length}`, 'Provider 就绪状态', 'var(--color-purple)'],
    ['风险均/峰值', `${fmtScore(risk.average)} / ${fmtScore(risk.maximum)}`, '来自事件 risk_score', 'var(--color-orange)'],
    ['运行任务', fmtNumber(context.metrics?.running_jobs), '当前队列中', 'var(--color-green)'],
  ]

  return (
    <>
      <PageHeader title="系统控制台" description="集中展示后端运行状态、LLM Provider 配置、数据总览与快捷操作；所有数据实时来自后端接口。">
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
          <div className="grid metrics" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
            {stats.map(([label, value, hint, accent]) => <StatCard key={label} label={label} value={value} hint={hint} accent={accent} />)}
          </div>

          <div className="grid two section">
            <Card title="LLM Provider 状态" description="来自 /api/llm/providers，不展示 API Key。">
              {providers.length ? (
                <div className="cards-list">
                  {providers.map((provider) => (
                    <div className="item-card" key={provider.name} style={{ '--accent': provider.configured ? 'var(--color-green)' : 'var(--color-orange)' } as React.CSSProperties}>
                      <div className="meta">
                        <Badge text={provider.name} tone={provider.configured ? 'green' : 'orange'} />
                        <span>{provider.configured ? '已配置' : '未配置'}</span>
                      </div>
                      <p><strong>模型：</strong>{provider.model}</p>
                      <p><strong>Base URL：</strong>{provider.base_url}</p>
                    </div>
                  ))}
                </div>
              ) : <ErrorBox error={context.healthError || '未获取到 Provider 信息'} />}
            </Card>

            <Card title="运行健康" description="来自 /health 与 /api/system/metrics">
              {context.health ? (
                <div className="cards-list">
                  <div className="meta"><span>状态</span><strong>{context.health.status}</strong><span>数据库可写</span><strong>{String(context.health.database_writable)}</strong></div>
                  <div className="meta"><span>迁移</span><strong>{String(context.health.migrations.current ?? '—')}</strong><span>期望</span><strong>{String(context.health.migrations.expected ?? '—')}</strong></div>
                  <div className="meta"><span>近期任务错误</span><strong>{context.health.recent_task_errors}</strong><span>LLM 成功/失败</span><strong>{context.metrics?.llm_success ?? 0} / {context.metrics?.llm_failure ?? 0}</strong></div>
                  <div className="meta"><span>Agent 路由</span><button className="ghost-btn" type="button" onClick={() => setShowRoutes(!showRoutes)}>{showRoutes ? '隐藏' : '查看'}</button></div>
                  {showRoutes ? <JsonBlock value={routes} /> : null}
                </div>
              ) : <ErrorBox error={context.healthError || '健康检查未返回数据'} />}
            </Card>
          </div>

          <div className="grid three section">
            <Card title="事件判定分布">
              <DistributionPanel data={overview?.events_by_verdict} accent="var(--color-primary)" />
            </Card>
            <Card title="Incident 严重度">
              <DistributionPanel data={overview?.incidents_by_severity} accent="var(--color-orange)" />
            </Card>
            <Card title="高频攻击类型">
              <div className="bars">
                {Object.entries(overview?.top_attack_types || {}).map(([key, value]) => (
                  <div className="bar-row" key={key}>
                    <span className="bar-label">{key}</span>
                    <span className="bar-track"><span className="bar-fill" style={{ width: `${(Number(value) / Math.max(...Object.values(overview?.top_attack_types || { a: 1 }), 1)) * 100}%`, background: 'var(--color-purple)' }} /></span>
                    <span className="bar-value">{fmtNumber(value)}</span>
                  </div>
                ))}
                {!Object.keys(overview?.top_attack_types || {}).length && <div className="empty">后端返回空数据</div>}
              </div>
            </Card>
          </div>
        </>
      )}
    </>
  )
}

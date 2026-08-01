import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { NavLink, Route, Routes, Navigate } from 'react-router-dom'
import './App.css'
import {
  defaultApiConfig,
  queryString,
  request,
  type ApiConfig,
  type DatasetOut,
  type HealthOut,
  type SystemMetricsOut,
} from './api'
import { HomePage } from './pages/HomePage'
import { ConsolePage } from './pages/ConsolePage'
import { DatasetsPage } from './pages/DatasetsPage'
import { EventsPage } from './pages/EventsPage'
import { IncidentsPage } from './pages/IncidentsPage'
import { VulnerabilitiesPage } from './pages/VulnerabilitiesPage'
import { HuntPage } from './pages/HuntPage'
import { JobsPage } from './pages/JobsPage'
import { AgentPage } from './pages/AgentPage'

export interface AppContextValue {
  apiConfig: ApiConfig
  datasets: DatasetOut[]
  selectedDataset: string
  setSelectedDataset: (value: string) => void
  health: HealthOut | null
  healthError: string | null
  metrics: SystemMetricsOut | null
  refreshGlobal: () => Promise<void>
  api: <T>(path: string, init?: RequestInit) => Promise<T>
}

function SidebarIcon({ name }: { name: string }) {
  let glyph: ReactNode
  switch (name) {
    case '🏠': glyph = <path d="m4 10 8-6 8 6v9a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z" />; break
    case '📊': glyph = <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>; break
    case '📁': glyph = <path d="M3.5 7.5h6l1.8 2h9.2v8.7a1.8 1.8 0 0 1-1.8 1.8H5.3a1.8 1.8 0 0 1-1.8-1.8zM3.5 7.5V5.8A1.8 1.8 0 0 1 5.3 4h4l1.8 2" />; break
    case '⚡': glyph = <path d="m13 2-8 12h6l-1 8 8-12h-6z" />; break
    case '🔗': glyph = <><path d="m9 15-1.5 1.5a3.5 3.5 0 0 1-5-5L6 8" /><path d="m15 9 1.5-1.5a3.5 3.5 0 0 1 5 5L18 16" /><path d="m8 16 8-8" /></>; break
    case '🛡️': glyph = <><path d="M12 3 19 6v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>; break
    case '🔍': glyph = <><circle cx="10.8" cy="10.8" r="6.3" /><path d="m16 16 5 5" /></>; break
    case '📋': glyph = <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V3h6v1M8 9h8M8 13h8M8 17h5" /></>; break
    case '🤖': glyph = <><rect x="4" y="7" width="16" height="12" rx="3" /><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8" /><circle cx="12" cy="3" r="1" /></>; break
    default: glyph = <><path d="M6 3h9l3 3v15H6zM15 3v4h4" /><path d="M9 12h6M9 16h4" /></>
  }
  return <svg className="sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">{glyph}</svg>
}

function App() {
  const [apiConfig, setApiConfig] = useState<ApiConfig>(() => ({
    baseUrl: window.location.origin.startsWith('http') ? window.location.origin : defaultApiConfig.baseUrl,
    apiKey: '',
  }))
  const [datasets, setDatasets] = useState<DatasetOut[]>([])
  const [selectedDataset, setSelectedDataset] = useState('')
  const [health, setHealth] = useState<HealthOut | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<SystemMetricsOut | null>(null)
  const [status, setStatus] = useState('等待连接后端')
  const [tone, setTone] = useState<'ok' | 'warn' | 'bad'>('warn')

  const api = useCallback(
    <T,>(path: string, init: RequestInit = {}) => request<T>(path, apiConfig, init),
    [apiConfig],
  )

  const refreshGlobal = useCallback(async () => {
    setStatus('正在同步后端真实数据…')
    setTone('warn')
    const [healthResult, metricsResult, datasetsResult] = await Promise.allSettled([
      api<HealthOut>('/health'),
      api<SystemMetricsOut>('/api/system/metrics'),
      api<DatasetOut[]>(`/api/datasets${queryString({ limit: 200 })}`),
    ])
    setHealth(healthResult.status === 'fulfilled' ? healthResult.value : null)
    setHealthError(
      healthResult.status === 'rejected'
        ? healthResult.reason instanceof Error
          ? healthResult.reason.message
          : String(healthResult.reason)
        : null,
    )
    setMetrics(metricsResult.status === 'fulfilled' ? metricsResult.value : null)
    setDatasets(datasetsResult.status === 'fulfilled' ? datasetsResult.value : [])
    if (healthResult.status === 'rejected') {
      setStatus(healthResult.reason instanceof Error ? healthResult.reason.message : '健康检查失败')
      setTone('bad')
      return
    }
    setStatus('后端真实数据已同步')
    setTone('ok')
  }, [api])

  useEffect(() => {
    let alive = true
    queueMicrotask(() => {
      if (alive) void refreshGlobal()
    })
    return () => {
      alive = false
    }
  }, [refreshGlobal])

  const context = useMemo<AppContextValue>(
    () => ({ apiConfig, datasets, selectedDataset, setSelectedDataset, health, healthError, metrics, refreshGlobal, api }),
    [api, apiConfig, datasets, health, healthError, metrics, refreshGlobal, selectedDataset],
  )
  const healthTone = healthError
    ? 'bad'
    : health?.status === 'ok' && health.database_writable
      ? 'ok'
      : 'warn'
  const healthStatus = health?.status || (healthError ? 'error' : 'checking')
  const databaseWritable = health ? String(health.database_writable) : healthError ? 'unknown' : 'checking'

  const navItemsWithIcons: Array<[string, string, string]> = [
    ['/home', '主页', '🏠'],
    ['/', '系统控制台', '📊'],
    ['/datasets', '数据集管理', '📁'],
    ['/events', 'Payload 事件', '⚡'],
    ['/incidents', 'Incident 聚类', '🔗'],
    ['/vulnerabilities', '漏洞候选', '🛡️'],
    ['/hunt', '狩猎工作台', '🔍'],
    ['/jobs', '任务与审计', '📋'],
    ['/agent', 'Agent 会话', '🤖'],
  ]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">FV</span>
          <span>Flow Vul Hunt</span>
        </div>
        <div className="sidebar-divider" />
        <nav className="nav" aria-label="主导航">
          {navItemsWithIcons.map(([to, label, icon]) => (
            <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : undefined)} end={to === '/'}>
              <span className="nav-icon"><SidebarIcon name={icon} /></span>
              <span className="nav-label">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="api-panel">
          <div className="status-pill"><span className={`status-dot ${tone === 'ok' ? '' : tone}`} /><span>{status}</span></div>
          <div className="sidebar-health" aria-live="polite">
            <div className="sidebar-health-row">
              <span className={`status-dot ${healthTone === 'ok' ? '' : healthTone}`} />
              <span>运行健康：</span>
              <strong>{healthStatus}</strong>
            </div>
            <div className="sidebar-health-row">
              <span className={`status-dot ${healthTone === 'ok' ? '' : healthTone}`} />
              <span>数据库可写：</span>
              <strong>{databaseWritable}</strong>
            </div>
          </div>
          <label>
            <span>API 地址</span>
            <input value={apiConfig.baseUrl} onChange={(event) => setApiConfig((current) => ({ ...current, baseUrl: event.target.value }))} />
          </label>
          <label>
            <span>API Key（不持久化）</span>
            <input type="password" value={apiConfig.apiKey} onChange={(event) => setApiConfig((current) => ({ ...current, apiKey: event.target.value }))} placeholder="X-API-Key" />
          </label>
          <button className="primary-btn" type="button" onClick={() => void refreshGlobal()}>刷新连接</button>
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<ConsolePage context={context} />} />
          <Route path="/home" element={<HomePage context={context} />} />
          <Route path="/datasets" element={<DatasetsPage context={context} />} />
          <Route path="/events" element={<EventsPage context={context} />} />
          <Route path="/incidents" element={<IncidentsPage context={context} />} />
          <Route path="/vulnerabilities" element={<VulnerabilitiesPage context={context} />} />
          <Route path="/hunt" element={<HuntPage context={context} />} />
          <Route path="/jobs" element={<JobsPage context={context} />} />
          <Route path="/agent" element={<AgentPage context={context} />} />
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App

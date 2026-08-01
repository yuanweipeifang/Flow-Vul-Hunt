import { useCallback, useEffect, useMemo, useState } from 'react'
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
import { AuditPage } from './pages/AuditPage'

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
    ['/jobs', '分析任务', '📋'],
    ['/agent', 'Agent 会话', '🤖'],
    ['/audit', '审计日志', '📝'],
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
              <span className="nav-icon" aria-hidden="true">{icon}</span>
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
          <Route path="/audit" element={<AuditPage context={context} />} />
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App

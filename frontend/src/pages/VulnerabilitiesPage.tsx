import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type AuthorizedTargetOut, type ValidationRunOut, type VulnerabilityAnalysisOut, type VulnerabilityCandidateOut } from '../api'
import { Badge, Card, DistributionPanel, Empty, ErrorBox, Loading, MarkdownCode, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtScore, severityTone, statusTone } from '../ui'
import { useSearchParams } from 'react-router-dom'

function countBy<T>(items: T[], selector: (item: T) => string | null | undefined) {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = selector(item) || 'unknown'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
}

function confidenceBand(confidence: number) {
  if (confidence >= 0.8) return '高置信 (>=80%)'
  if (confidence >= 0.5) return '中置信 (50%-79%)'
  return '低置信 (<50%)'
}

function validationStage(status: string) {
  if (['validated', 'confirmed', 'fixed'].includes(status)) return '已验证'
  if (['false_positive', 'rejected'].includes(status)) return '已排除'
  if (status === 'triaged') return '已研判'
  return '待验证'
}

function confidenceTone(confidence: number) {
  if (confidence >= 0.8) return 'confidence-high'
  if (confidence >= 0.5) return 'confidence-medium'
  return 'confidence-low'
}

function severityChipTone(severity: string) {
  const value = severity.toLowerCase()
  if (value === 'critical') return 'red'
  if (value === 'high') return 'orange'
  if (value === 'medium') return 'cyan'
  if (value === 'low' || value === 'info') return 'green'
  return 'blue'
}

function normalizeSearchValue(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function extractCveIds(value: unknown): string[] {
  const matches = normalizeSearchValue(value).match(/CVE-\d{4}-\d{4,}/gi) || []
  return Array.from(new Set(matches.map((item) => item.toUpperCase())))
}

function vulnerabilitySearchText(item: VulnerabilityCandidateOut) {
  return [
    item.title,
    item.candidate_type,
    item.target_component,
    item.severity,
    item.status,
    item.impact,
    item.signature,
    normalizeSearchValue(item.evidence),
    normalizeSearchValue(item.validation_summary),
    ...extractCveIds(item.evidence),
  ].filter(Boolean).join(' ').toLowerCase()
}

function VulnerabilityChip({ tone, title, onClick, children }: { tone: string; title?: string; onClick: () => void; children: ReactNode }) {
  return (
    <button className={`vulnerability-chip ${tone}`} type="button" title={title} onClick={onClick}>
      {children}
    </button>
  )
}

function MarkdownList({ items, empty }: { items: string[]; empty: string }) {
  return items.length ? <ul>{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <p className="event-markdown-empty">{empty}</p>
}

function VulnerabilityAnalysisDocument({ analysis }: { analysis: VulnerabilityAnalysisOut }) {
  const vulnerability = analysis.vulnerability
  const cveResearch = (vulnerability.evidence?.cve_research as Record<string, unknown> | undefined) || null
  return (
    <article className="event-markdown vulnerability-markdown">
      <blockquote>
        <strong>{vulnerability.title}</strong>
        <span>{vulnerability.candidate_type} · {vulnerability.target_component || '未标注目标组件'}</span>
      </blockquote>

      <section>
        <h2>分析结论</h2>
        <div className="event-markdown-callout">
          <Badge text={vulnerability.severity} tone={severityTone(vulnerability.severity)} />
          <Badge text={vulnerability.status} tone={statusTone(vulnerability.status)} />
          <span>置信度 <strong>{fmtScore(vulnerability.confidence)}</strong></span>
        </div>
        <p>{analysis.analysis_summary || '暂无分析摘要。'}</p>
      </section>

      <section>
        <h2>置信因素</h2>
        <MarkdownList items={analysis.confidence_factors} empty="暂无置信因素。" />
      </section>

      <section>
        <h2>误报风险</h2>
        <MarkdownList items={analysis.false_positive_risks} empty="暂无误报风险提示。" />
      </section>

      <section>
        <h2>验证重点</h2>
        <MarkdownList items={analysis.validation_focus} empty="暂无验证重点。" />
      </section>

      <section>
        <h2>关联事件</h2>
        <MarkdownCode language="json">{JSON.stringify(analysis.related_event || {}, null, 2)}</MarkdownCode>
      </section>

      <section>
        <h2>候选证据</h2>
        <MarkdownCode language="json">{JSON.stringify(vulnerability.evidence || {}, null, 2)}</MarkdownCode>
      </section>

      {cveResearch ? (
        <section>
          <h2>CVE 研判</h2>
          <MarkdownCode language="json">{JSON.stringify(cveResearch, null, 2)}</MarkdownCode>
        </section>
      ) : null}

      <section>
        <h2>验证历史</h2>
        <MarkdownCode language="json">{JSON.stringify(analysis.validation_history || [], null, 2)}</MarkdownCode>
      </section>
    </article>
  )
}

export function VulnerabilitiesPage({ context }: { context: AppContextValue }) {
  const [searchParams] = useSearchParams()
  const eventId = searchParams.get('event_id') || ''
  const [analysis, setAnalysis] = useState<VulnerabilityAnalysisOut | null>(null)
  const [detailError, setDetailError] = useState<unknown>(null)
  const [filters, setFilters] = useState({ status: '', severity: '', candidate_type: '' })
  const [featureQuery, setFeatureQuery] = useState('')
  const [targets, setTargets] = useState<AuthorizedTargetOut[]>([])
  const [validationForm, setValidationForm] = useState({ targetId: '', method: 'HEAD', path: '', probe: 'none' })
  const [validationLoading, setValidationLoading] = useState(false)
  const [validationError, setValidationError] = useState<unknown>(null)
  const [cveLoading, setCveLoading] = useState(false)
  const [cveError, setCveError] = useState<unknown>(null)
  const { data: itemsData, error, loading } = useApiData(
    () => context.api<VulnerabilityCandidateOut[]>(`/api/vulnerabilities${queryString({ dataset_id: context.selectedDataset, event_id: eventId, ...filters, limit: 100 })}`),
    [context, context.selectedDataset, eventId, filters],
  )
  const items = itemsData || []
  const normalizedFeatureQuery = featureQuery.trim().toLowerCase()
  const visibleItems = useMemo(() => {
    if (!normalizedFeatureQuery) return items
    return items.filter((item) => vulnerabilitySearchText(item).includes(normalizedFeatureQuery))
  }, [items, normalizedFeatureQuery])
  const charts = useMemo(() => ({
    type: countBy(visibleItems, (item) => item.candidate_type),
    confidence: countBy(visibleItems, (item) => confidenceBand(item.confidence)),
    validation: countBy(visibleItems, (item) => validationStage(item.status)),
  }), [visibleItems])

  async function showAnalysis(id: string) {
    try {
      setAnalysis(null)
      setDetailError(null)
      setValidationError(null)
      setCveError(null)
      setTargets([])
      setAnalysis(await context.api<VulnerabilityAnalysisOut>(`/api/vulnerabilities/${encodeURIComponent(id)}/analysis`))
    } catch (reason) {
      setDetailError(reason)
      return
    }
    try {
      const availableTargets = await context.api<AuthorizedTargetOut[]>('/api/targets?enabled=true')
      setTargets(availableTargets)
      setValidationForm((current) => ({ ...current, targetId: current.targetId || availableTargets[0]?.id || '' }))
    } catch (reason) {
      setValidationError(reason)
    }
  }

  useEffect(() => {
    if (!analysis) return
    setValidationForm((current) => ({ ...current, path: analysis.related_event.path || '/' }))
  }, [analysis])

  async function runValidation(event: FormEvent) {
    event.preventDefault()
    if (!analysis || !validationForm.targetId) return
    setValidationLoading(true)
    setValidationError(null)
    try {
      const run = await context.api<ValidationRunOut>(`/api/vulnerabilities/${encodeURIComponent(analysis.vulnerability.id)}/validate`, {
        method: 'POST',
        body: JSON.stringify({
          target_id: validationForm.targetId,
          method: validationForm.method,
          path: validationForm.path || analysis.related_event.path || '/',
          probe: validationForm.probe,
        }),
      })
      setAnalysis((current) => current ? { ...current, validation_history: [run, ...current.validation_history.filter((item) => item.id !== run.id)] } : current)
    } catch (reason) {
      setValidationError(reason)
    } finally {
      setValidationLoading(false)
    }
  }

  async function runCveResearch() {
    if (!analysis || cveLoading) return
    setCveLoading(true)
    setCveError(null)
    try {
      setAnalysis(await context.api<VulnerabilityAnalysisOut>(`/api/vulnerabilities/${encodeURIComponent(analysis.vulnerability.id)}/cve-research`, {
        method: 'POST',
      }))
    } catch (reason) {
      setCveError(reason)
    } finally {
      setCveLoading(false)
    }
  }

  return (
    <div className="vulnerabilities-page">
      <PageHeader title="漏洞候选" description="集中评估候选漏洞的类型、置信水平、验证进展与关联证据。">
        <label className="field">
          <span>状态</span>
          <select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
            <option value="">全部</option>
            <option value="candidate">candidate</option>
            <option value="needs_review">needs_review</option>
            <option value="triaged">triaged</option>
            <option value="validated">validated</option>
            <option value="confirmed">confirmed</option>
            <option value="fixed">fixed</option>
            <option value="false_positive">false_positive</option>
            <option value="rejected">rejected</option>
          </select>
        </label>
        <label className="field">
          <span>严重度</span>
          <select value={filters.severity} onChange={(event) => setFilters((current) => ({ ...current, severity: event.target.value }))}>
            <option value="">全部</option>
            <option value="critical">critical</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
            <option value="info">info</option>
          </select>
        </label>
        <label className="field vulnerability-feature-search">
          <span>特征 / CVE</span>
          <input value={featureQuery} onChange={(event) => setFeatureQuery(event.target.value)} placeholder="SSRF、JNDI、组件、CVE-2021-44228" />
        </label>
      </PageHeader>

      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <>
          <div className="grid three">
            <Card title="漏洞类型">
              <DistributionPanel data={charts.type} accent="var(--color-red)" />
            </Card>
            <Card title="置信区间">
              <DistributionPanel data={charts.confidence} accent="var(--color-orange)" />
            </Card>
            <Card title="验证进展">
              <DistributionPanel data={charts.validation} accent="var(--color-cyan)" />
            </Card>
          </div>

          <Card title="候选列表">
            {visibleItems.length ? (
              <div className="vulnerability-list" role="list" aria-label="漏洞候选列表">
                {visibleItems.map((item) => {
                  const openAnalysis = () => void showAnalysis(item.id)
                  return (
                    <article className="vulnerability-row" role="listitem" key={item.id}>
                      <div className="vulnerability-main">
                        <VulnerabilityChip tone="title" title={item.title} onClick={openAnalysis}>
                          {item.title}
                        </VulnerabilityChip>
                        <div className="vulnerability-meta">
                          <VulnerabilityChip tone="type" onClick={openAnalysis}>类型 {item.candidate_type}</VulnerabilityChip>
                          <VulnerabilityChip tone={`severity ${severityChipTone(item.severity)}`} onClick={openAnalysis}>严重度 {item.severity}</VulnerabilityChip>
                          <VulnerabilityChip tone={confidenceTone(item.confidence)} onClick={openAnalysis}>置信度 {fmtScore(item.confidence)}</VulnerabilityChip>
                          <VulnerabilityChip tone={`status ${statusTone(item.status)}`} onClick={openAnalysis}>状态 {item.status}</VulnerabilityChip>
                          <VulnerabilityChip tone="component" title={item.target_component || '未标注组件'} onClick={openAnalysis}>组件 {item.target_component || '未标注'}</VulnerabilityChip>
                          <VulnerabilityChip tone="time" onClick={openAnalysis}>创建 {fmtDate(item.created_at)}</VulnerabilityChip>
                        </div>
                      </div>
                      <div className="vulnerability-actions">
                        <button className="ghost-btn vulnerability-analysis-btn" type="button" onClick={openAnalysis}>查看分析</button>
                      </div>
                    </article>
                  )
                })}
              </div>
            ) : <Empty text={items.length ? '没有匹配当前漏洞特征或 CVE 关键词的候选' : '后端返回空漏洞候选列表'} />}
            {detailError ? <div className="section"><ErrorBox error={detailError} /></div> : null}
          </Card>
        </>
      )}

      {analysis && (
        <div className="modal" onClick={(event) => { if (event.target === event.currentTarget) setAnalysis(null) }}>
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="vuln-analysis-title">
            <div className="modal-head">
              <h2 id="vuln-analysis-title">漏洞候选分析</h2>
              <button className="ghost-btn" type="button" onClick={() => setAnalysis(null)}>关闭</button>
            </div>
            <div className="modal-body">
              <section className="vulnerability-validation-panel" aria-labelledby="validation-panel-title">
                <div className="vulnerability-validation-head">
                  <div>
                    <h3 id="validation-panel-title">授权验证</h3>
                    <p>仅对已登记目标发起安全方法请求；验证结果只代表响应证据，不等同于漏洞确认。</p>
                  </div>
                  <span className="validation-policy-label">白名单 · GET / HEAD / OPTIONS</span>
                </div>
                <div className="vulnerability-research-head">
                  <button className="ghost-btn" type="button" onClick={() => void runCveResearch()} disabled={cveLoading || !analysis}>
                    {cveLoading ? '研判中…' : '模型研判 CVE'}
                  </button>
                  <p>由大模型基于当前候选的特征、证据和关联事件给出 CVE 研判，并写回到本候选分析中。</p>
                </div>
                {cveError ? <ErrorBox error={cveError} /> : null}
                <form className="vulnerability-validation-form" onSubmit={(event) => void runValidation(event)}>
                  <label className="field">
                    <span>授权目标</span>
                    <select value={validationForm.targetId} onChange={(event) => setValidationForm((current) => ({ ...current, targetId: event.target.value }))} required>
                      <option value="">选择已登记目标</option>
                      {targets.map((target) => <option key={target.id} value={target.id}>{target.name} · {target.scheme}://{target.host}{target.path_scope}</option>)}
                    </select>
                  </label>
                  <label className="field">
                    <span>方法</span>
                    <select value={validationForm.method} onChange={(event) => setValidationForm((current) => ({ ...current, method: event.target.value }))}>
                      <option value="HEAD">HEAD</option>
                      <option value="GET">GET</option>
                      <option value="OPTIONS">OPTIONS</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>路径</span>
                    <input value={validationForm.path} onChange={(event) => setValidationForm((current) => ({ ...current, path: event.target.value }))} placeholder="默认使用关联事件路径" />
                  </label>
                  <label className="checkbox-line vulnerability-probe-option">
                    <input type="checkbox" checked={validationForm.probe === 'safe_marker'} onChange={(event) => setValidationForm((current) => ({ ...current, probe: event.target.checked ? 'safe_marker' : 'none', method: event.target.checked && current.method === 'HEAD' ? 'GET' : current.method }))} />
                    <span>附加无害反射标记</span>
                  </label>
                  <button className="primary-btn" type="submit" disabled={validationLoading || !targets.length || !validationForm.targetId}>{validationLoading ? '验证中…' : '开始验证'}</button>
                </form>
                {!targets.length ? <p className="vulnerability-validation-empty">暂无启用的授权目标，请先配置目标白名单。</p> : null}
                {validationError ? <ErrorBox error={validationError} /> : null}
              </section>
              <VulnerabilityAnalysisDocument analysis={analysis} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

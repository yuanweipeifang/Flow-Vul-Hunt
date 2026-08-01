import { useMemo, useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type VulnerabilityAnalysisOut, type VulnerabilityCandidateOut } from '../api'
import { Badge, Card, DataTable, DistributionPanel, Empty, ErrorBox, JsonBlock, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtScore, severityTone, statusTone } from '../ui'

function countBy<T>(items: T[], selector: (item: T) => string | null | undefined) {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = selector(item) || 'unknown'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
}

export function VulnerabilitiesPage({ context }: { context: AppContextValue }) {
  const [analysis, setAnalysis] = useState<VulnerabilityAnalysisOut | null>(null)
  const [detailError, setDetailError] = useState<unknown>(null)
  const [filters, setFilters] = useState({ status: '', severity: '', candidate_type: '' })
  const { data: itemsData, error, loading } = useApiData(
    () => context.api<VulnerabilityCandidateOut[]>(`/api/vulnerabilities${queryString({ dataset_id: context.selectedDataset, ...filters, limit: 100 })}`),
    [context, context.selectedDataset, filters],
  )
  const items = itemsData || []
  const charts = useMemo(() => ({
    severity: countBy(items, (item) => item.severity),
    status: countBy(items, (item) => item.status),
    type: countBy(items, (item) => item.candidate_type),
  }), [items])

  async function showAnalysis(id: string) {
    try {
      setAnalysis(null)
      setDetailError(null)
      setAnalysis(await context.api<VulnerabilityAnalysisOut>(`/api/vulnerabilities/${encodeURIComponent(id)}/analysis`))
    } catch (reason) {
      setDetailError(reason)
    }
  }

  const rows = items.map((item) => [
    <span title={item.title}>{item.title}</span>,
    item.candidate_type,
    <Badge text={item.severity} tone={severityTone(item.severity)} />,
    fmtScore(item.confidence),
    <Badge text={item.status} tone={statusTone(item.status)} />,
    item.target_component || '-',
    <span className="nowrap">{fmtDate(item.created_at)}</span>,
    <button className="ghost-btn" type="button" onClick={() => void showAnalysis(item.id)}>分析</button>,
  ])

  return (
    <>
      <PageHeader title="漏洞候选" description="漏洞候选和分析视图分别来自 /api/vulnerabilities 与 /api/vulnerabilities/{id}/analysis；饼图根据当前筛选结果实时统计。">
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
      </PageHeader>

      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <>
          <div className="grid three">
            <Card title="严重度分布">
              <DistributionPanel data={charts.severity} accent="var(--color-orange)" />
            </Card>
            <Card title="状态分布">
              <DistributionPanel data={charts.status} accent="var(--color-cyan)" />
            </Card>
            <Card title="漏洞类型">
              <DistributionPanel data={charts.type} accent="var(--color-red)" />
            </Card>
          </div>

          <Card title="候选列表">
            {rows.length ? (
              <DataTable
                caption="漏洞候选列表"
                headers={['标题', '类型', '严重度', '置信度', '状态', '组件', '创建时间', '操作']}
                rows={rows}
              />
            ) : <Empty text="后端返回空漏洞候选列表" />}
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
              <div className="item-card">
                <div className="meta">
                  <Badge text={analysis.vulnerability.severity} tone={severityTone(analysis.vulnerability.severity)} />
                  <Badge text={analysis.vulnerability.status} tone={statusTone(analysis.vulnerability.status)} />
                  <span>置信度 {fmtScore(analysis.vulnerability.confidence)}</span>
                </div>
                <h3>{analysis.vulnerability.title}</h3>
                <p>{analysis.analysis_summary}</p>
              </div>
              <div className="grid two section">
                <Card title="置信因素">
                  {analysis.confidence_factors.length ? <ul>{analysis.confidence_factors.map((factor) => <li key={factor}>{factor}</li>)}</ul> : <Empty text="无置信因素" />}
                </Card>
                <Card title="误报风险">
                  {analysis.false_positive_risks.length ? <ul>{analysis.false_positive_risks.map((risk) => <li key={risk}>{risk}</li>)}</ul> : <Empty text="无误报风险提示" />}
                </Card>
              </div>
              <Card title="验证重点">{analysis.validation_focus.length ? <ul>{analysis.validation_focus.map((focus) => <li key={focus}>{focus}</li>)}</ul> : <Empty text="无验证重点" />}</Card>
              <Card title="关联事件"><JsonBlock value={analysis.related_event} /></Card>
              <Card title="证据"><JsonBlock value={analysis.vulnerability.evidence} /></Card>
              <Card title="验证历史"><JsonBlock value={analysis.validation_history} /></Card>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

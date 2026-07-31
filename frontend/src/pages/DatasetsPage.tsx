import { useRef, useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type DatasetCompareResult, type DatasetOut, type JobOut } from '../api'
import { Badge, Card, DataTable, Empty, ErrorBox, Loading, PageHeader } from '../components'
import { useApiData } from '../useApiData'
import { fmtDate, fmtNumber, statusTone } from '../ui'

export function DatasetsPage({ context }: { context: AppContextValue }) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<unknown>(null)
  const [analyzingId, setAnalyzingId] = useState<string | null>(null)
  const [compareIds, setCompareIds] = useState({ baseline: '', candidate: '' })
  const [compareResult, setCompareResult] = useState<DatasetCompareResult | null>(null)
  const [compareError, setCompareError] = useState<unknown>(null)

  const { data: datasetsData, error, loading } = useApiData(
    () => context.api<DatasetOut[]>(`/api/datasets${queryString({ limit: 200 })}`),
    [context],
  )
  const datasets = datasetsData || []

  async function upload(file: File) {
    setUploading(true)
    setUploadError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      await context.api<DatasetOut>('/api/datasets/upload', { method: 'POST', body: form })
      await context.refreshGlobal()
      if (fileInput.current) fileInput.current.value = ''
    } catch (reason) {
      setUploadError(reason)
    } finally {
      setUploading(false)
    }
  }

  async function analyze(datasetId: string) {
    setAnalyzingId(datasetId)
    try {
      await context.api<JobOut>(`/api/datasets/${datasetId}/analyze`, {
        method: 'POST',
        body: JSON.stringify({ use_llm: true, llm_scope: 'suspicious', force: false }),
      })
      await context.refreshGlobal()
    } finally {
      setAnalyzingId(null)
    }
  }

  async function compare() {
    if (!compareIds.baseline || !compareIds.candidate || compareIds.baseline === compareIds.candidate) return
    setCompareError(null)
    setCompareResult(null)
    try {
      const result = await context.api<DatasetCompareResult>(
        `/api/datasets/compare${queryString({ baseline_dataset_id: compareIds.baseline, candidate_dataset_id: compareIds.candidate })}`,
      )
      setCompareResult(result)
    } catch (reason) {
      setCompareError(reason)
    }
  }

  const rows = datasets.map((dataset) => [
    <code>{dataset.id.slice(0, 8)}</code>,
    dataset.name,
    <Badge text={dataset.status} tone={statusTone(dataset.status)} />,
    fmtNumber(dataset.row_count),
    `${fmtNumber(dataset.parsed_count)} / ${fmtNumber(dataset.failed_count)}`,
    fmtNumber(dataset.analyzed_count),
    <span className="nowrap">{fmtDate(dataset.created_at)}</span>,
    <button className="ghost-btn" type="button" disabled={analyzingId === dataset.id} onClick={() => void analyze(dataset.id)}>
      {analyzingId === dataset.id ? '分析中…' : '启动分析'}
    </button>,
  ])

  return (
    <>
      <PageHeader title="数据集管理" description="上传、分析、对比和删除 CSV Payload 数据集；所有操作直接调用后端真实接口。">
        <input ref={fileInput} type="file" accept=".csv" style={{ display: 'none' }} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file) }} />
        <button className="primary-btn" type="button" disabled={uploading} onClick={() => fileInput.current?.click()}>
          {uploading ? '上传中…' : '上传 CSV'}
        </button>
      </PageHeader>

      {uploadError ? <div className="section"><ErrorBox error={uploadError} /></div> : null}

      <Card title="数据集列表" description={`共 ${fmtNumber(datasets.length)} 个数据集。`}>
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : rows.length ? (
          <DataTable caption="数据集列表" headers={['ID','名称','状态','行数','解析/失败','已分析','上传时间','操作']} rows={rows} />
        ) : <Empty text="后端返回空数据集列表" />}
      </Card>

      <Card title="数据集对比" description="对比两个数据集的差异，返回新增 Host、Path、攻击类型和重复 Payload 哈希。">
        <div className="filters">
          <label className="field">
            <span>基准数据集</span>
            <select value={compareIds.baseline} onChange={(event) => setCompareIds((current) => ({ ...current, baseline: event.target.value }))}>
              <option value="">选择基准</option>
              {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>候选数据集</span>
            <select value={compareIds.candidate} onChange={(event) => setCompareIds((current) => ({ ...current, candidate: event.target.value }))}>
              <option value="">选择候选</option>
              {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}
            </select>
          </label>
          <button className="primary-btn" type="button" onClick={() => void compare()}>执行对比</button>
        </div>
        {compareError ? <div className="section"><ErrorBox error={compareError} /></div> : null}
        {compareResult ? (
          <div className="section">
            <div className="grid two">
              <div className="item-card">
                <h3>统计对比</h3>
                <pre>{JSON.stringify(compareResult.counts, null, 2)}</pre>
              </div>
              <div className="item-card">
                <h3>风险对比</h3>
                <pre>{JSON.stringify(compareResult.risk, null, 2)}</pre>
              </div>
            </div>
            <div className="grid two section">
              <div className="item-card">
                <h3>新增 Host</h3>
                {compareResult.new_hosts.length ? <ul>{compareResult.new_hosts.map((host) => <li key={host}>{host}</li>)}</ul> : <Empty text="无新增 Host" />}
              </div>
              <div className="item-card">
                <h3>新增 Path</h3>
                {compareResult.new_paths.length ? <ul>{compareResult.new_paths.map((path) => <li key={path}>{path}</li>)}</ul> : <Empty text="无新增 Path" />}
              </div>
            </div>
          </div>
        ) : null}
      </Card>
    </>
  )
}

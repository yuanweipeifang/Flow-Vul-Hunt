import { useRef, useState } from 'react'
import type { AppContextValue } from '../App'
import { queryString, type DatasetCompareResult, type DatasetOut, type JobOut, type StoredCsvFileOut } from '../api'
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
  const [reloadToken, setReloadToken] = useState(0)

  const { data: datasetsData } = useApiData(
    () => context.api<DatasetOut[]>(`/api/datasets${queryString({ limit: 200 })}`),
    [context, reloadToken],
  )
  const datasets = datasetsData || context.datasets || []

  const { data: storedFilesData, error, loading } = useApiData(
    () => context.api<StoredCsvFileOut[]>(`/api/datasets/files${queryString({ limit: 500 })}`),
    [context, reloadToken],
  )
  const storedFiles = storedFilesData || []

  async function upload(file: File) {
    setUploading(true)
    setUploadError(null)
    try {
      const form = new FormData()
      form.append('file', file, file.name)
      await context.api<DatasetOut>('/api/datasets/upload', { method: 'POST', body: form })
      await context.refreshGlobal()
      setReloadToken((value) => value + 1)
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
        body: JSON.stringify({ use_llm: false, llm_scope: 'suspicious', force: false }),
      })
      await context.refreshGlobal()
      setReloadToken((value) => value + 1)
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

  const fileRows = storedFiles.map((file) => [
    <code>{file.filename}</code>,
    file.dataset_id ? <Badge text={file.status || 'unknown'} tone={statusTone(file.status || 'unknown')} /> : <Badge text="stored only" tone="gray" />,
    fmtNumber(file.size_bytes),
    file.row_count === null ? '-' : fmtNumber(file.row_count),
    <span className="nowrap">{fmtDate(file.modified_at)}</span>,
    file.dataset_id ? (
      <button className="ghost-btn" type="button" disabled={analyzingId === file.dataset_id} onClick={() => void analyze(file.dataset_id as string)}>
        {analyzingId === file.dataset_id ? '分析中...' : '启动分析'}
      </button>
    ) : (
      <span className="muted">仅文件</span>
    ),
  ])

  return (
    <>
      <PageHeader title="数据集管理" description="上传 CSV 后会保存到后端存储目录；列表直接读取存储目录中的 CSV 文件。">
        <input
          ref={fileInput}
          type="file"
          accept=".csv,text/csv"
          style={{ display: 'none' }}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) void upload(file)
          }}
        />
        <button className="primary-btn" type="button" disabled={uploading} onClick={() => fileInput.current?.click()}>
          {uploading ? '上传中...' : '上传 CSV'}
        </button>
      </PageHeader>

      {uploadError ? <div className="section"><ErrorBox error={uploadError} /></div> : null}

      <Card title="数据集列表" description={`存储目录中共有 ${fmtNumber(storedFiles.length)} 个 CSV 文件。`}>
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : fileRows.length ? (
          <DataTable caption="数据集列表" headers={['文件名', '状态', '大小(B)', '行数', '存储时间', '操作']} rows={fileRows} />
        ) : <Empty text="存储目录中还没有 CSV 文件" />}
      </Card>

      <Card title="数据集对比" description="对比两个已成功入库的数据集，返回新增 Host、Path、攻击类型和重复 Payload 哈希。">
        <div className="filters">
          <label className="field">
            <span>基准数据集</span>
            <select value={compareIds.baseline} onChange={(event) => setCompareIds((current) => ({ ...current, baseline: event.target.value }))}>
              <option value="">选择基准</option>
              {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.filename}</option>)}
            </select>
          </label>
          <label className="field">
            <span>候选数据集</span>
            <select value={compareIds.candidate} onChange={(event) => setCompareIds((current) => ({ ...current, candidate: event.target.value }))}>
              <option value="">选择候选</option>
              {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.filename}</option>)}
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

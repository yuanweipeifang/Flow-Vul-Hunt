export type JsonObject = Record<string, unknown>

export interface DatasetOut {
  id: string
  name: string
  filename: string
  file_sha256: string
  storage_path: string | null
  status: string
  row_count: number
  parsed_count: number
  failed_count: number
  analyzed_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface AuthorizedTargetOut {
  id: string
  name: string
  scheme: string
  host: string
  port: number | null
  path_scope: string
  enabled: boolean
  note: string | null
  created_at: string
  updated_at: string
}

export interface StoredCsvFileOut {
  filename: string
  storage_path: string
  size_bytes: number
  modified_at: string
  dataset_id: string | null
  dataset_name: string | null
  status: string | null
  row_count: number | null
  file_sha256: string | null
}

export interface DatasetCompareResult {
  baseline_dataset_id: string
  candidate_dataset_id: string
  counts: Record<string, number>
  risk: Record<string, number>
  new_hosts: string[]
  new_paths: string[]
  new_attack_types: string[]
  repeated_payload_hashes: string[]
}

export interface EventSummary {
  id: string
  dataset_id: string
  row_number: number
  protocol: string
  http_method: string | null
  host: string | null
  path: string | null
  payload_length: number
  is_binary: boolean
  parse_status: string
  verdict: string
  risk_score: number
  created_at: string
}

export interface PaginatedEvents {
  total: number
  offset: number
  limit: number
  items: EventSummary[]
}

export interface EventDetail extends EventSummary {
  raw_payload: string
  decoded_payload: string
  payload_hash: string
  query: string | null
  headers: JsonObject
  body: string | null
  content_type: string | null
  entropy: number
  printable_ratio: number
  encoded_segment_count: number
  parse_error: string | null
  findings: FindingOut[]
  llm_analyses: LLMAnalysisOut[]
}

export interface FindingOut {
  id: string
  detector_type: string
  detector_name: string
  attack_type: string
  severity: string
  confidence: number
  matched_fragment: string | null
  evidence: JsonObject
  created_at: string
}

export interface LLMAnalysisOut {
  id: string
  agent_name: string
  provider: string
  model_name: string
  prompt_version: string
  structured_result: JsonObject | null
  token_usage: JsonObject
  latency_ms: number | null
  status: string
  error_message: string | null
  created_at: string
}

export interface DashboardOverview {
  totals: Record<string, number>
  datasets_by_status: Record<string, number>
  events_by_verdict: Record<string, number>
  incidents_by_severity: Record<string, number>
  incidents_by_status: Record<string, number>
  top_attack_types: Record<string, number>
  risk: Record<string, number>
}

export interface IncidentOut {
  id: string
  dataset_id: string
  title: string
  incident_type: string
  summary: string
  risk_score: number
  severity: string
  status: string
  assignee: string | null
  resolution: string | null
  closed_at: string | null
  is_simulated: boolean
  created_at: string
  updated_at: string
  event_links: Array<{ event_id: string; relation_type: string; evidence: JsonObject; sort_order: number }>
}

export interface IncidentReportOut {
  id: string
  incident_id: string
  generator: string
  model_name: string | null
  content: JsonObject
  status: string
  error_message: string | null
  created_at: string
}

export interface JobOut {
  id: string
  dataset_id: string
  status: string
  phase: string
  use_llm: boolean
  llm_scope: string
  force: boolean
  cancel_requested: boolean
  total: number
  processed: number
  succeeded: number
  failed: number
  current_event_id: string | null
  last_heartbeat_at: string | null
  last_error_at: string | null
  error_count: number
  error_message: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
}

export interface VulnerabilityCandidateOut {
  id: string
  dataset_id: string
  event_id: string
  candidate_type: string
  title: string
  target_component: string | null
  severity: string
  confidence: number
  status: string
  signature: string
  evidence: JsonObject
  impact: string
  validation_summary: JsonObject
  reviewer: string | null
  comment: string | null
  created_at: string
  updated_at: string
}

export interface VulnerabilityAnalysisOut {
  vulnerability: VulnerabilityCandidateOut
  analysis_summary: string
  confidence_factors: string[]
  false_positive_risks: string[]
  validation_focus: string[]
  related_event: EventSummary
  validation_history: ValidationRunOut[]
}

export interface ValidationRunOut {
  id: string
  vulnerability_id: string
  target_id: string
  status: string
  requested_by: string | null
  request_options: JsonObject
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  results: ValidationResultOut[]
}

export interface ValidationResultOut {
  id: string
  run_id: string
  target_id: string
  method: string
  url: string
  status: string
  conclusion: string
  request_summary: JsonObject
  response_summary: JsonObject
  latency_ms: number | null
  error_message: string | null
  created_at: string
}

export interface HuntResult {
  interpreted_filters: JsonObject
  events: EventSummary[]
  summary: string | null
  llm_used: boolean
  warning: string | null
  matched_events: number
  suppressed_events: number
  suppression_policy: string | null
}

export interface AuditLogOut {
  id: string
  action: string
  actor: string
  role: string
  request_id: string | null
  resource_type: string
  resource_id: string | null
  details: JsonObject
  created_at: string
}

export interface SystemMetricsOut {
  datasets: number
  events: number
  running_jobs: number
  failed_jobs: number
  llm_success: number
  llm_failure: number
  validation_runs_by_status: Record<string, number>
}

export interface HealthOut {
  status: string
  database: string
  migrations: Record<string, unknown>
  database_writable: boolean
  recent_task_errors: number
  llm_configured: boolean
  llm_enabled: boolean
  providers: ProviderOut[]
  agent_routes: Record<string, string[]>
}

export interface ProviderOut {
  name: string
  configured: boolean
  base_url: string
  model: string
}

export interface ProvidersOut {
  providers: ProviderOut[]
  agent_routes: Record<string, string[]>
}

export interface AgentStatusOut {
  enabled: boolean
  runtime: string
  hermes_available: boolean
  hermes_python_available: boolean
  hermes_cli_available: boolean
  hermes_config_dir: string
  hermes_plugin_dir: string
  hermes_isolated: boolean
  allowed_tools: string[]
  require_confirmation: boolean
  collaboration_enabled: boolean
  collaboration_mode: string
  agent_roles: string[]
  max_parallelism: number
  require_verifier: boolean
}

export interface AgentTaskSpecOut {
  task_id: string
  agent_name: string
  goal: string
  tool_names: string[]
  depends_on: string[]
  priority: number
  requires_confirmation: boolean
  status: string
}

export interface AgentSessionOut {
  id: string
  actor: string
  role: string
  message: string
  dataset_id: string | null
  runtime: string
  planner_used: string
  status: string
  plan: string[]
  answer: string
  warning: string | null
  requires_confirmation: boolean
  created_at: string
  updated_at: string
  task_graph: AgentTaskSpecOut[]
  tool_calls: AgentToolCallOut[]
  runs: AgentRunOut[]
}

export interface AgentToolCallOut {
  id: string
  name: string
  risk_level: string
  arguments: JsonObject
  status: string
  requires_confirmation: boolean
  result: unknown | null
  error: string | null
}

export interface AgentChatResult {
  session_id: string
  runtime: string
  hermes_isolated: boolean
  plan: string[]
  tool_calls: AgentToolCallOut[]
  answer: string
  requires_confirmation: boolean
  warning: string | null
  planner_used: string
  collaboration_mode: string
  task_graph: AgentTaskSpecOut[]
  agents: AgentMessageOut[]
  consensus: JsonObject
  evidence_gaps: string[]
  llm_used: boolean
}

export interface AgentRunOut {
  id: string
  session_id: string
  collaboration_mode: string
  runtime: string
  planner_used: string
  status: string
  max_parallelism: number
  llm_used: boolean
  consensus: JsonObject
  evidence_gaps: string[]
  error: string | null
  started_at: string | null
  completed_at: string | null
  task_graph: AgentTaskSpecOut[]
  messages: AgentMessageOut[]
}

export interface AgentMessageOut {
  id: string
  agent_name: string
  role: string
  task: string
  message_type: string
  recipient: string | null
  follow_up_action: JsonObject
  resolved: boolean
  input_summary: JsonObject
  output: JsonObject
  depends_on: string[]
  evidence_refs: JsonObject[]
  confidence: number
  llm_used: boolean
  status: string
  error: string | null
  created_at: string | null
}

export interface AgentMemoryOut {
  id: string
  dataset_id: string | null
  agent_name: string
  memory_type: string
  summary: string
  content: JsonObject
  confidence: number
  created_at: string
  updated_at: string
}

export interface ApiConfig {
  baseUrl: string
  apiKey: string
}

export const defaultApiConfig: ApiConfig = {
  baseUrl: 'http://127.0.0.1:8000',
  apiKey: '',
}

export function queryString(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

export async function request<T>(path: string, config: ApiConfig, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (config.apiKey.trim()) headers.set('X-API-Key', config.apiKey.trim())
  const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData
  if (init.body && !headers.has('Content-Type') && !isFormData) headers.set('Content-Type', 'application/json')
  const base = config.baseUrl.trim().replace(/\/$/, '')
  const response = await fetch(`${base}${path}`, { ...init, headers })
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const data = await response.json()
      message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail ?? data)
    } catch {
      const text = await response.text().catch(() => '')
      if (text) message = text
    }
    throw new Error(message)
  }
  if (response.status === 204) return null as T
  return response.json() as Promise<T>
}

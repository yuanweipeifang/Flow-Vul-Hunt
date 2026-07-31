# Flow Vul Hunt Backend

基于真实 CSV Payload 的威胁检测、证据验证、事件聚类和风险告警后端。所有持久化数据均存储在 SQLite；系统不会创建 Mock 事件、虚拟 IP 或虚拟时间线。

## 已实现能力

- 无表头、单列 Payload CSV 上传与校验；
- UTF-8 BOM、CSV 引号、`\0D\0A`、`\xx` 字节转义解析；
- HTTP 方法、Host、Path、Query、Header、Body 提取；
- 文本/二进制识别、熵值和可打印字符比例计算；
- 命令注入、SQL 注入、路径穿越、表达式注入、JNDI、WebShell、SSRF、XSS 等确定性检测；
- 可解释风险评分，二进制或高熵本身不会被判为恶意；
- OpenAI-compatible API Payload 分析智能体；
- 独立证据验证智能体，模型引用必须存在于原始或解码 Payload；
- 基于真实 Host 和攻击类型的 Payload 活动簇；
- 自然语言狩猎及确定性降级；
- 基于真实事件证据的调查报告；
- 模型调用状态、Token、延迟、Prompt 版本及错误审计。

## 环境要求

- Python 3.11+
- SQLite 3

安装依赖：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

复制配置：

```bash
cp .env.example .env
```

应用会通过 `python-dotenv` 自动读取 `backend/.env`，系统环境变量优先级高于文件内容。

## 大模型配置

应用启动时会自动读取 `backend/.env`。先复制模板：

```bash
cp .env.example .env
```

然后只在本地编辑 `.env` 中的 Key，不要提交该文件：

```text
DEEPSEEK_API_KEY=你的DeepSeek-Key
BAILIAN_API_KEY=你的百炼-Key
ZHIPU_API_KEY=你的智谱-Key
```

默认供应商和模型：

| 供应商 | Base URL | 默认模型 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com` | `deepseek-v4-flash` |
| 阿里云百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.7-plus` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2` |

如果百炼控制台提供的是带 `WorkspaceId` 的地域专属 URL，必须用控制台地址覆盖 `BAILIAN_BASE_URL`；API Key、模型和 Base URL 必须属于同一地域。

默认智能体路由：

```text
Payload研判：DeepSeek → 百炼 → 智谱
证据复核：智谱 → 百炼 → DeepSeek
狩猎解释：百炼 → 智谱 → DeepSeek
报告生成：百炼 → DeepSeek → 智谱
```

箭头表示调用失败后的切换顺序。可通过 `LLM_ROUTE_*` 环境变量调整。

某个供应商的 API Key 为空时：

- 规则检测、风险计算、事件聚类和确定性报告继续工作；
- 路由会跳过该供应商并尝试下一家；
- 三家均未配置时，需要模型的步骤记录为 `unavailable` 或使用明确标注的确定性降级；
- 系统不会生成伪造的模型分析结果。

### 检查配置

重启后访问：

```text
GET /health
GET /api/llm/providers
```

响应只显示是否已配置、Base URL 和模型，不会返回 API Key。

### 发起真实连接测试

以下接口会对所选供应商各产生一次很小的真实模型调用：

```bash
curl -X POST http://localhost:8000/api/llm/test \
  -H "Content-Type: application/json" \
  -d '{"providers":["deepseek","bailian","zhipu"]}'
```

每项会返回 `success`、实际模型、延迟、Token 用量或经过截断的错误信息，不会返回密钥。

## 数据库

默认数据库：

```text
backend/data/flow_vul_hunt.db
```

应用启动时会为全新数据库创建当前结构。正式环境也可以使用 Alembic：

```bash
alembic upgrade head
```

所有表，包括事件、检测证据、模型审计、任务、事件簇、报告和标注，都在同一个 SQLite 数据库中。

## 启动

在仓库根目录运行唯一的后端启动入口：

```bash
python run_backend.py
```

默认监听 `127.0.0.1:8000`，实时输出访问日志、请求 ID、状态码和耗时。开发时启用热重载：

```bash
python run_backend.py --reload --log-level debug
```

使用 `--host`、`--port` 和 `--log-level` 可以覆盖默认启动参数。

接口文档：

```text
http://localhost:8000/docs
```

健康检查：

```text
GET /health
```

## 基本使用流程

### 1. 上传真实 CSV

```bash
curl -X POST http://localhost:8000/api/datasets/upload \
  -F "file=@data/test_5+5_no_label.csv"
```

只接受无表头、单列 Payload CSV。格式错误会返回具体行号，不会部分导入。

### 2. 启动分析

```bash
curl -X POST http://localhost:8000/api/datasets/DATASET_ID/analyze \
  -H "Content-Type: application/json" \
  -d '{"use_llm":true,"llm_scope":"suspicious","force":false}'
```

`llm_scope`：

- `suspicious`：只分析规则命中、解析异常或高熵文本，推荐默认值；
- `all`：分析所有文本 Payload，二进制内容只有规则命中时才发送。

分析作为后台任务执行，通过 `GET /api/jobs/{job_id}` 查询进度。

### 3. 查询事件和证据

```text
GET /api/events?dataset_id=...&min_risk=60
GET /api/events/{event_id}
POST /api/events/{event_id}/reanalyze
```

### 4. 查询事件簇与生成报告

```text
GET  /api/incidents?dataset_id=...
POST /api/incidents/{incident_id}/reports
GET  /api/incidents/{incident_id}/reports
```

事件簇只表示数据库中 Payload 的关联性，不代表已确认来自同一攻击者，也不证明攻击成功。

### 5. 自然语言狩猎

```bash
curl -X POST http://localhost:8000/api/hunt/query \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"DATASET_ID","query":"查找所有高危命令注入事件","limit":50,"use_llm":true}'
```

模型只负责把问题转成白名单过滤字段，数据库查询由后端执行。

### 6. 漏洞候选与受控验证

分析任务会自动抽取事件特征并生成漏洞候选：

```text
GET /api/events/EVENT_ID/features
GET /api/vulnerabilities?dataset_id=DATASET_ID
GET /api/vulnerabilities/VULNERABILITY_ID
PATCH /api/vulnerabilities/VULNERABILITY_ID
```

受控验证必须先配置授权目标，只允许 `GET`、`HEAD`、`OPTIONS` 低风险请求，不复放原始攻击 Query 或 Body：

```bash
curl -X POST http://localhost:8000/api/targets \
  -H "Content-Type: application/json" \
  -d '{"name":"staging-app","scheme":"https","host":"app.example.test","path_scope":"/api","enabled":true}'

curl -X POST http://localhost:8000/api/vulnerabilities/VULNERABILITY_ID/validate \
  -H "Content-Type: application/json" \
  -d '{"target_id":"TARGET_ID","method":"HEAD","path":"/api/health","requested_by":"analyst"}'
```

验证结果通过 `GET /api/validation-runs/RUN_ID` 查询；系统只保存请求摘要、响应摘要、状态码、有限 Header 和截断后的响应片段。

### 7. 项目私有多 Agent 协同运行时

系统提供项目内隔离的多 Agent 协同后端。默认角色包括 `coordinator`、`payload_analyst`、`hunt_interpreter`、`vulnerability_researcher`、`evidence_verifier` 和 `report_generator`。Hermes 或模型不可用时，后端仍会使用本地 planner 跑完整协作轨迹，并在响应中标记 `llm_used=false`。

```bash
AGENT_ENABLED=true
AGENT_COLLABORATION_ENABLED=true
AGENT_MAX_PARALLELISM=3
AGENT_REQUIRE_VERIFIER=true
FVH_HERMES_CONFIG_DIR=.hermes/flow-vul-hunt
FVH_HERMES_PLUGIN_DIR=.hermes/plugins/flow-vul-hunt
AGENT_REQUIRE_CONFIRMATION=true
```

检查 Agent、Hermes 和协作状态：

```text
GET /api/agent/status
GET /api/agent/hermes/smoke
GET /api/agent/sessions
GET /api/agent/sessions/SESSION_ID
GET /api/agent/sessions/SESSION_ID/trace
```

发起一次编排请求：

```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"DATASET_ID","message":"分析这个数据集的高危漏洞并过滤误报","auto_execute":false}'
```

`/api/agent/chat` 会返回 `collaboration_mode`、`agents`、`consensus`、`evidence_gaps` 和 `llm_used`。每个 Agent 的任务、依赖、证据引用和输出会落库到协作 trace 中，便于观测和审计。

Hermes 插件和系统提示词位于仓库内 `.hermes/`，不会读写用户级 Hermes 配置。`/api/agent/hermes/smoke` 只做静态就绪检查，不触发外网模型调用；只有环境已安装 Hermes 且已有 provider key 时，才能单独执行真实模型 E2E 验证。高风险工具默认只生成计划，必须确认后才执行。

确认执行某个等待确认的工具调用：

```bash
curl -X POST http://localhost:8000/api/agent/sessions/SESSION_ID/confirm \
  -H "Content-Type: application/json" \
  -d '{"tool_call_ids":["tool-4"]}'
```

保存和复用狩猎查询：

```text
POST /api/hunt/saved
GET  /api/hunt/saved
POST /api/hunt/saved/SAVED_QUERY_ID/run
```

`run_backend.py` 会通过后端配置自动加载 `backend/.env` 和 `backend/.env.agent`。

## 测试

```bash
pytest -q
```

测试覆盖 CSV/字节解析、二进制处理、规则证据、风险上限、真实示例数据导入、检测、事件聚类和确定性报告。

## 安全边界

- Payload 始终作为不可信证据，不作为系统指令；
- Authorization、Cookie 等 Header 在发送给模型前会脱敏；
- 模型无命令执行、网络检索、封禁或隔离权限；
- 高风险模型结论必须通过独立验证，并引用实际存在的 Payload 片段；
- 缺少 IP、时间、会话和资产字段时，不生成虚假的攻击链。

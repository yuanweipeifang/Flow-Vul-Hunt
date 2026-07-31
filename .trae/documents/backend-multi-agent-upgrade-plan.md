# 后端多 Agent 升级计划

## Summary

当前后端已经具备多 Agent 的雏形：`security_brain` planner、工具执行、协作 trace、审计与确认机制。但从实际实现看，它仍主要是“单规划器 + 固定角色结果拼装”的编排，而不是让多个角色真正围绕业务问题独立推理、并行处理、相互校验和汇总。

本计划将后端升级为**角色级并发编排**的多 Agent 运行时，优先打通**数据集调查闭环**：围绕上传的数据集，由多个角色并行完成威胁狩猎、payload 证据分析、攻击面聚合、漏洞候选研判、证据复核和报告生成，并将结果持久化为可审计的协作轨迹。

## Current State Analysis

基于已读代码，现状如下：

- `backend/app/services/agent/chat.py` 是统一入口，当前流程是：planner 规划工具 -> 顺序执行工具 -> `build_collaboration()` 生成固定角色消息 -> 持久化 session/run/messages。
- `backend/app/services/agent/planner.py` 只有两类 planner：Hermes/LLM planner 与本地 fallback planner，规划结果是“工具列表”，不是多角色任务图。
- `backend/app/services/agent/tools.py` 已有可用的业务工具集合，覆盖 `get_dataset`、`hunt_query`、`attack_surface_map`、`red_team_hypotheses`、`list_vulnerabilities`、`get_vulnerability_analysis`、`start_dataset_analysis` 等，适合作为多 Agent 的业务执行面。
- `backend/app/services/agent/collaboration.py` 当前只是根据工具结果拼装 coordinator/specialist/verifier/report 的输出，角色本身并不独立推理，也没有并行调度。
- `backend/app/models.py` 已存在 `AgentSession`、`AgentRun`、`AgentMessage`、`AgentToolCall`，非常适合扩展为真正的多 Agent trace 模型。
- `backend/app/config.py` 已经按角色配置了 provider route，说明后端已经有“角色级 LLM 路由”的配置基础，但当前主要只有 planner 等少数链路真正使用 LLM。
- `backend/tests/test_operational_hardening.py` 已经覆盖了当前多 Agent 的基本行为：只读工具执行、高风险确认、协作角色输出、trace 落库。升级时必须保持这些约束不回退。

## Proposed Changes

### 1. 将 planner 输出升级为“多角色任务图”

**文件**
- `backend/app/services/agent/constants.py`
- `backend/app/services/agent/planner.py`
- `backend/app/services/agent/chat.py`

**做什么**
- 新增结构化任务图模型，例如 `AgentTaskSpec`，包含：
  - `task_id`
  - `agent_name`
  - `goal`
  - `tool_names`
  - `depends_on`
  - `priority`
  - `requires_confirmation`
- planner 不再只返回工具列表，而是返回：
  - `plan`
  - `tasks`
  - `tool_calls`（兼容旧字段）
  - `final_focus`

**为什么**
- 真正多 Agent 的核心不是“多个名字”，而是“多个有明确职责的任务节点”。
- 当前 planner 只产出工具序列，无法表达 coordinator/specialist/verifier 之间的业务分工。

**怎么做**
- 在 `constants.py` 增加角色定义和任务模板。
- 在 `planner.py` 增加任务图生成逻辑：
  - 若 LLM 可用，则让 `security_brain` 输出任务图 JSON。
  - 若不可用，则本地生成默认调查任务图。
- 在 `chat.py` 中先构建任务图，再执行调度。

### 2. 引入角色级执行器，让每个角色真正处理业务子任务

**文件**
- 新增 `backend/app/services/agent/roles.py`
- `backend/app/services/agent/chat.py`
- `backend/app/services/agent/collaboration.py`

**做什么**
- 把当前 `collaboration.py` 中“根据工具结果拼角色消息”的逻辑，升级为“角色执行器”：
  - `coordinator`
  - `payload_analyst`
  - `hunt_interpreter`
  - `vulnerability_researcher`
  - `evidence_verifier`
  - `report_generator`
- 每个角色执行器都接收：
  - 当前任务
  - 共享上下文
  - 可访问工具结果
  - 会话约束

**为什么**
- 这是从“多角色包装”走向“多角色业务处理”的关键一步。

**怎么做**
- 每个角色至少实现一个 `run(context)` 方法。
- 角色输出统一为结构化结果：
  - `summary`
  - `findings`
  - `evidence_refs`
  - `confidence`
  - `next_actions`
  - `llm_used`
- `payload_analyst` 侧重事件/payload 证据归并。
- `hunt_interpreter` 侧重狩猎命中、误报抑制和攻击面解释。
- `vulnerability_researcher` 侧重漏洞候选、影响假设、验证路线。
- `evidence_verifier` 独立复核证据是否足以支撑结论。
- `report_generator` 基于验证后的事实生成最终答复。

### 3. 让 specialist / verifier 支持角色级 LLM 推理

**文件**
- `backend/app/llm/gateway.py`
- `backend/app/services/agent/roles.py`
- `backend/app/services/agent/collaboration.py`
- `backend/app/config.py`

**做什么**
- 不再只让 planner 使用 LLM。
- 让以下角色支持真实 LLM 推理：
  - `payload_analyst`
  - `hunt_interpreter`
  - `vulnerability_researcher`
  - `evidence_verifier`
  - `report_generator`
- 每个角色使用独立 prompt 和 schema 输出。

**为什么**
- 没有角色级推理，就不是“真正多 Agent”，只是多视图包装。

**怎么做**
- 为每个角色定义独立 system prompt 和结构化输出 schema。
- 复用 `config.py` 中现有 `agent_routes`，保持角色级 provider 路由。
- LLM 不可用时回退到确定性规则摘要，但必须显式标记 `llm_used=false`。

### 4. 引入真正的并行调度器

**文件**
- 新增 `backend/app/services/agent/orchestrator.py`
- `backend/app/services/agent/chat.py`

**做什么**
- 新增调度器，负责按依赖关系执行任务图。
- 支持：
  - 并行执行无依赖任务
  - 依赖任务等待
  - 单任务失败不阻塞全局
  - 最大并发度受 `agent_max_parallelism` 控制

**为什么**
- 当前工具执行是顺序循环，无法体现多 Agent 并行协作。

**怎么做**
- 使用线程池或异步任务执行器实现。
- 只读任务可并行。
- 高风险任务仍然走确认 gate，不进入自动并行执行。
- 调度器输出统一执行状态和错误信息，供 trace 落库。

### 5. 把 Agent 消息升级为“可驱动后续任务”的协议

**文件**
- `backend/app/models.py`
- `backend/app/schemas/agent.py`
- `backend/app/services/agent/collaboration.py`
- `backend/app/services/agent/orchestrator.py`
- `backend/app/api/agent.py`

**做什么**
- 扩展 `AgentMessage` 的语义，使其不仅是展示记录，还能描述：
  - `message_type`（task/result/question/verification/summary）
  - `recipient`
  - `follow_up_action`
  - `resolved`
- 允许 verifier 对 specialist 输出提出 `follow_up_action`，例如要求补充证据。

**为什么**
- 真正多 Agent 需要消息能驱动后续行为，而不是只用于审计回放。

**怎么做**
- 先保持数据库兼容，新增字段即可，不破坏现有 API。
- 在 trace 返回中暴露消息流。
- 在 orchestrator 中识别 verifier 的 follow-up 请求并触发二次任务。

### 6. 优先打通“数据集调查闭环”业务流

**文件**
- `backend/app/services/agent/tools.py`
- `backend/app/services/agent/roles.py`
- `backend/app/services/agent/planner.py`
- `backend/app/api/agent.py`

**做什么**
- 将默认多 Agent 业务闭环固定为：
  1. 读取数据集范围
  2. 威胁狩猎
  3. payload 证据分析
  4. 攻击面聚合
  5. 漏洞候选研判
  6. 证据复核
  7. 报告生成

**为什么**
- 先打穿一个稳定业务闭环，比一次性做全链路更稳。

**怎么做**
- 对 `dataset_id` 请求，默认生成上述调查任务图。
- 工具结果作为共享上下文在角色间流转。
- 最终报告必须区分：
  - confirmed facts
  - inferences
  - evidence gaps
  - recommended next steps

### 7. 扩展持久化和 API，让多 Agent 运行轨迹可观测

**文件**
- `backend/app/models.py`
- `backend/app/schemas/agent.py`
- `backend/app/services/agent/sessions.py`
- `backend/app/api/agent.py`

**做什么**
- 在 trace 中保留：
  - 任务图
  - 每个角色的输入摘要、输出摘要、耗时、是否使用 LLM、错误信息
  - 消息流
- 如有必要，新增接口查看 run 级别的任务执行状态。

**为什么**
- 真多 Agent 系统必须可观测、可排障、可审计。

**怎么做**
- 优先复用现有 `AgentSession/AgentRun/AgentMessage/AgentToolCall`。
- 如字段不足，再做轻量迁移，避免大范围重构。

### 8. 增加回归测试与集成测试

**文件**
- `backend/tests/test_operational_hardening.py`
- 新增或扩展 agent 相关测试文件

**做什么**
- 覆盖以下场景：
  - planner 输出任务图
  - specialist 并行执行
  - LLM 不可用时确定性回退
  - verifier 发现证据缺口并生成 follow-up
  - 高风险工具仍需确认
  - trace 完整落库

**为什么**
- 这次升级是核心运行时改造，必须防止回退。

## Assumptions & Decisions

- 优先实现**角色级并发编排**，不引入外部消息队列、Redis、Celery 等新基础设施。
- 优先打通**数据集调查闭环**，暂不扩展到主动验证和 incident 自动处置闭环。
- 继续保留现有高风险工具确认机制，不允许多 Agent 自动绕过确认。
- LLM 不可用时系统仍可运行，但必须明确降级并标记 `llm_used=false`。
- 数据库演进保持兼容优先，尽量通过新增字段/新表实现，不做破坏性变更。

## Verification

实施完成后至少验证：

1. `pytest -q` 全部通过。
2. `GET /api/agent/status` 能正确反映新的多 Agent runtime 状态。
3. `POST /api/agent/chat` 在数据集调查场景下返回：
   - 多角色任务图
   - 并行执行结果
   - verifier 结论
   - 最终报告
4. `GET /api/agent/sessions/{session_id}/trace` 能看到完整角色消息流和工具调用链。
5. 在 LLM 可用与不可用两种环境下分别验证：
   - 可用时角色级 `llm_used=true`
   - 不可用时 deterministic fallback 仍稳定工作

## Implementation Order

1. 扩展任务图 schema 与 planner。
2. 新增角色执行器与 orchestrator。
3. 接入角色级 LLM 推理与降级策略。
4. 扩展消息协议和 trace 持久化。
5. 补齐测试并回归验证。

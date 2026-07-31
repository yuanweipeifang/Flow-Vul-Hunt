# Flow Vul Hunt 后端精简计划

目标：将项目整理为职责清晰、依赖最少的单体后端，并提供仓库根目录下唯一的 Python 启动入口 `run_backend.py`。整个过程保持 SQLite 兼容，并逐步执行、逐步验证。

## 原则

- 不删除用户数据或现有 SQLite 数据库。
- 未确认模块范围前不删除 API、模型或迁移。
- 每完成一步运行相关测试，最后运行完整测试。
- 启动入口必须使用无缓冲日志，并能直接看到请求日志和后端异常。
- 不引入 Redis、Celery、PostgreSQL 或前端依赖。

## 功能范围建议

### 核心保留

- CSV Payload 上传、校验和分批导入
- HTTP Payload 解析和特征提取
- 内置规则检测与风险评分
- 数据集、事件和检测证据查询
- 后台分析任务、进度、取消和重试
- SQLite 持久化、迁移和健康检查

### 待确认是否保留

- 自定义规则及 dry-run
- 人工标注和误报抑制
- 自然语言狩猎及保存查询
- 漏洞候选、授权目标和主动验证
- LLM 多供应商分析与报告生成
- Hermes Agent、会话和确认流程
- Incident 聚类和报告
- Dashboard、导出、审计日志、API Key/RBAC、系统指标

## 执行步骤

- [x] 1. 确认最终保留的产品工作流和兼容性要求
- [x] 2. 生成 API、数据表、服务和依赖关系清单，标记可安全移除项
- [x] 3. 新增根目录 `run_backend.py`，统一加载环境、启动迁移和 Uvicorn
- [x] 4. 为启动入口增加参数：host、port、reload、log-level，并默认实时输出日志
- [x] 5. 增加启动入口测试和一次本地启动冒烟验证
- [x] 6. 按确认范围从路由注册层停用人工研判模块
- [x] 7. 清理不再引用的人工研判服务、Schema、脚本和测试
- [x] 8. 保留旧 annotations 表和数据，不做破坏性降级迁移
- [x] 9. 精简 README，只保留一个推荐启动命令和实际存在的 API 工作流
- [x] 10. 运行完整测试并输出最终保留功能、移除功能和迁移说明
- [x] 11. 将单 planner Agent 升级为可观测多 Agent 协同运行时
- [x] 12. 增加协作 trace 持久化、状态接口、Hermes 静态 smoke check 和回归测试

## 已确认范围

除人工标注和人工研判入口外，其余后端功能全部保留。狩猎中的误报过滤仅依据事件自身的 `benign` 判定，不再依赖人工标注。

## 多 Agent 协作范围

已实现 `coordinator`、`payload_analyst`、`hunt_interpreter`、`vulnerability_researcher`、`evidence_verifier`、`report_generator` 的后端协同链路。协作结果通过 `/api/agent/chat` 返回，并通过 `/api/agent/sessions/{session_id}/trace` 查询完整轨迹。Hermes/model E2E 仍以当前环境是否具备 Hermes 和 provider key 为准，静态检查入口为 `/api/agent/hermes/smoke`。

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ...config import Settings
from ...models import AgentMemory
from ...schemas import AgentChatRequest, AgentToolCallOut
from .constants import AgentTaskSpec
from .roles import AgentRole, ROLE_REGISTRY, RoleExecution
from .tools import _risk_level, execute_tool


class AgentOrchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def execute(
        self,
        request: AgentChatRequest,
        tasks: list[AgentTaskSpec],
        planned: list[dict[str, Any]],
        db,
        background_tasks,
        allowed: set[str],
    ) -> tuple[list[AgentToolCallOut], list[RoleExecution], dict[str, Any], list[str], str]:
        tool_calls = self._execute_tools(request, planned, db, background_tasks, allowed)
        memory_context = self._load_memory(db, request)
        role_executions = self._execute_roles(request, tasks, tool_calls, memory_context)
        role_executions = self._apply_follow_up_tasks(request, tasks, tool_calls, role_executions, memory_context)
        self._store_memory(db, request, role_executions)
        consensus, evidence_gaps, answer = self._build_consensus(role_executions)
        return tool_calls, role_executions, consensus, evidence_gaps, answer

    def _execute_tools(
        self,
        request: AgentChatRequest,
        planned: list[dict[str, Any]],
        db,
        background_tasks,
        allowed: set[str],
    ) -> list[AgentToolCallOut]:
        tool_calls: list[AgentToolCallOut] = []
        for index, planned_call in enumerate(planned, start=1):
            name = planned_call["name"]
            call_id = f"tool-{index}"
            risk_level = _risk_level(name)
            call = AgentToolCallOut(
                id=call_id,
                name=name,
                risk_level=risk_level,
                arguments=planned_call["arguments"],
                status="planned",
                requires_confirmation=risk_level == "high_risk",
            )
            if name not in allowed:
                call.status = "blocked"
                call.error = "tool is not allowed by AGENT_ALLOWED_TOOLS"
            elif call.requires_confirmation and (
                self.settings.agent_require_confirmation
                and (not request.auto_execute or call_id not in request.confirmed_tool_call_ids)
            ):
                call.status = "blocked"
                call.error = "confirmation required before executing this high-risk tool"
            elif request.auto_execute or risk_level == "read_only":
                try:
                    call.result = execute_tool(db, background_tasks, name, planned_call["arguments"])
                    call.status = "executed"
                except Exception as exc:
                    call.status = "failed"
                    call.error = f"{type(exc).__name__}: {exc}"[:500]
            tool_calls.append(call)
        return tool_calls

    def _execute_roles(
        self,
        request: AgentChatRequest,
        tasks: list[AgentTaskSpec],
        tool_calls: list[AgentToolCallOut],
        memory_context: list[AgentMemory],
    ) -> list[RoleExecution]:
        executions: list[RoleExecution] = []
        completed: dict[str, RoleExecution] = {}
        pending = {task.task_id: task for task in sorted(tasks, key=lambda item: item.priority, reverse=True)}
        blocked = [call for call in tool_calls if call.status == "blocked"]
        while pending:
            ready = [
                task for task in pending.values()
                if all(dep in completed for dep in task.depends_on)
            ]
            if not ready:
                for task in pending.values():
                    execution = RoleExecution(
                        task=task,
                        summary="依赖未满足，任务未执行。",
                        findings=[f"未满足依赖：{', '.join(task.depends_on) or '无'}"],
                        confidence=0.0,
                        error="dependency_unresolved",
                        status="failed",
                    )
                    completed[task.task_id] = execution
                    executions.append(execution)
                break
            with ThreadPoolExecutor(max_workers=max(1, min(len(ready), self.settings.agent_max_parallelism))) as pool:
                future_map = {}
                for task in ready:
                    role_cls = ROLE_REGISTRY.get(task.agent_name)
                    if not role_cls:
                        completed[task.task_id] = RoleExecution(
                            task=task,
                            summary="未注册角色，任务跳过。",
                            findings=[f"角色 {task.agent_name} 未注册。"],
                            confidence=0.0,
                            error="role_not_registered",
                            status="failed",
                        )
                        executions.append(completed[task.task_id])
                        pending.pop(task.task_id, None)
                        continue
                    context = {
                        "request": request,
                        "tasks": tasks,
                        "current_task": task,
                        "tool_calls": tool_calls,
                        "blocked_tool_calls": blocked,
                        "role_executions": list(completed.values()),
                        "memory_context": memory_context,
                    }
                    role: AgentRole = role_cls(self.settings)
                    future_map[pool.submit(role.run, task, context)] = task
                for future in as_completed(future_map):
                    task = future_map[future]
                    try:
                        execution = future.result()
                    except Exception as exc:
                        execution = RoleExecution(
                            task=task,
                            summary="角色执行失败。",
                            findings=[f"{type(exc).__name__}: {exc}"],
                            confidence=0.0,
                            error=f"{type(exc).__name__}: {exc}"[:500],
                            status="failed",
                        )
                    completed[task.task_id] = execution
                    executions.append(execution)
                    pending.pop(task.task_id, None)
        executions.sort(key=lambda item: item.task.priority, reverse=True)
        return executions

    def _apply_follow_up_tasks(
        self,
        request: AgentChatRequest,
        tasks: list[AgentTaskSpec],
        tool_calls: list[AgentToolCallOut],
        executions: list[RoleExecution],
        memory_context: list[AgentMemory],
    ) -> list[RoleExecution]:
        verifier = next((item for item in reversed(executions) if item.task.agent_name == "evidence_verifier"), None)
        if not verifier or verifier.resolved:
            return executions
        targets = verifier.follow_up_action.get("targets") or []
        if isinstance(verifier.follow_up_action.get("target"), str):
            targets.append(verifier.follow_up_action["target"])
        targets = list(dict.fromkeys(targets))
        if not targets:
            return executions
        new_tasks: list[AgentTaskSpec] = []
        for target in targets:
            if target not in ROLE_REGISTRY or target in {"evidence_verifier", "report_generator", "coordinator"}:
                continue
            new_tasks.append(
                AgentTaskSpec(
                    task_id=f"followup-{target}",
                    agent_name=target,
                    goal=f"补充 {target} 证据并重新提交给 verifier",
                    tool_names=[],
                    depends_on=[],
                    priority=5,
                    requires_confirmation=False,
                )
            )
        if not new_tasks:
            return executions
        followup_executions = self._execute_roles(request, new_tasks, tool_calls, memory_context)
        merged = [*executions, *followup_executions]
        final_verifier_task = AgentTaskSpec(
            task_id="followup-verify",
            agent_name="evidence_verifier",
            goal="复核补充证据后的最终结论",
            depends_on=[task.task_id for task in new_tasks],
            priority=4,
        )
        final_verifier = self._execute_roles(request, [final_verifier_task], tool_calls, memory_context)
        merged.extend(final_verifier)
        merged.sort(key=lambda item: item.task.priority, reverse=True)
        return merged

    def _load_memory(self, db, request: AgentChatRequest) -> list[AgentMemory]:
        if db is None:
            return []
        query = db.query(AgentMemory)
        if request.dataset_id:
            query = query.filter((AgentMemory.dataset_id == request.dataset_id) | (AgentMemory.dataset_id.is_(None)))
        return query.order_by(AgentMemory.created_at.desc()).limit(20).all()

    def _store_memory(self, db, request: AgentChatRequest, executions: list[RoleExecution]) -> None:
        if db is None:
            return
        for execution in executions:
            if execution.task.agent_name not in {"payload_analyst", "hunt_interpreter", "vulnerability_researcher", "evidence_verifier", "report_generator"}:
                continue
            if not execution.findings:
                continue
            db.add(
                AgentMemory(
                    dataset_id=request.dataset_id,
                    agent_name=execution.task.agent_name,
                    memory_type=execution.message_type,
                    summary=execution.summary,
                    content={
                        "task_id": execution.task.task_id,
                        "goal": execution.task.goal,
                        "findings": execution.findings[:8],
                        "next_actions": execution.next_actions[:8],
                        "resolved": execution.resolved,
                    },
                    confidence=execution.confidence,
                )
            )

    def _build_consensus(self, executions: list[RoleExecution]) -> tuple[dict[str, Any], list[str], str]:
        confirmed_facts: list[str] = []
        inferences: list[str] = []
        recommended_next_steps: list[str] = []
        evidence_gaps: list[str] = []
        for execution in executions:
            if execution.task.agent_name in {"payload_analyst", "hunt_interpreter", "vulnerability_researcher"}:
                if execution.evidence_refs:
                    confirmed_facts.extend(execution.findings)
                else:
                    inferences.extend(execution.findings)
                recommended_next_steps.extend(execution.next_actions)
            elif execution.task.agent_name == "evidence_verifier":
                evidence_gaps.extend(execution.findings)
        if not recommended_next_steps:
            recommended_next_steps.append("继续导入或分析数据集后，再运行多 Agent 调查流程。")
        consensus = {
            "confirmed_facts": confirmed_facts[:12],
            "inferences": inferences[:8],
            "evidence_gaps": evidence_gaps,
            "recommended_next_steps": recommended_next_steps[:8],
        }
        answer = (
            f"多 Agent 调查完成：确认事实 {len(consensus['confirmed_facts'])} 条，"
            f"待补证据 {len(evidence_gaps)} 条，建议下一步 {len(consensus['recommended_next_steps'])} 条。"
        )
        return consensus, evidence_gaps, answer

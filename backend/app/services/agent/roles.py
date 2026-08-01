from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from ...config import Settings
from ...llm.gateway import LLMGateway, LLMResponseError, LLMUnavailableError
from ...schemas import AgentChatRequest, AgentToolCallOut
from .constants import AgentTaskSpec


class RoleLLMResult(BaseModel):
    summary: str
    findings: list[str] = []
    evidence_refs: list[dict[str, Any]] = []
    confidence: float = 0.5
    next_actions: list[str] = []
    message_type: str = "result"
    recipient: str | None = None
    follow_up_action: dict[str, Any] = {}
    resolved: bool = True


@dataclass(slots=True)
class RoleExecution:
    task: AgentTaskSpec
    summary: str
    findings: list[str] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    next_actions: list[str] = field(default_factory=list)
    llm_used: bool = False
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    message_type: str = "result"
    recipient: str | None = None
    follow_up_action: dict[str, Any] = field(default_factory=dict)
    resolved: bool = True
    status: str = "completed"


class AgentRole:
    name = "base"
    role = "specialist"
    task_label = "处理业务子任务"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.gateway = LLMGateway(settings)

    def system_prompt(self) -> str:
        return (
            "You are a Flow-Vul-Hunt security agent. Return one JSON object only with keys "
            "summary, findings, evidence_refs, confidence, next_actions, message_type, recipient, "
            "follow_up_action, resolved. Do not include markdown."
        )

    def payload(self, context: dict[str, Any]) -> dict[str, Any]:
        return jsonable_encoder(context, exclude_none=True, sqlalchemy_safe=True)

    def fallback(self, context: dict[str, Any]) -> RoleExecution:
        raise NotImplementedError

    def run(self, task: AgentTaskSpec, context: dict[str, Any]) -> RoleExecution:
        payload = self.payload(context)
        try:
            result = self.gateway.complete_json(self.system_prompt(), payload, RoleLLMResult, agent_name=self.name)
            return RoleExecution(
                task=task,
                summary=result.data.summary,
                findings=result.data.findings,
                evidence_refs=result.data.evidence_refs,
                confidence=result.data.confidence,
                next_actions=result.data.next_actions,
                llm_used=True,
                output=result.data.model_dump(),
                message_type=result.data.message_type,
                recipient=result.data.recipient,
                follow_up_action=result.data.follow_up_action,
                resolved=result.data.resolved,
                status="completed" if result.data.resolved else "waiting_follow_up",
            )
        except (LLMUnavailableError, LLMResponseError, RuntimeError):
            execution = self.fallback(context)
            execution.llm_used = False
            return execution


def _executed_tools(context: dict[str, Any]) -> dict[str, AgentToolCallOut]:
    tool_calls: list[AgentToolCallOut] = context.get("tool_calls", [])
    return {call.name: call for call in tool_calls if call.status == "executed"}


def _evidence_ref(call: AgentToolCallOut, note: str) -> dict[str, Any]:
    return {"tool_call_id": call.id, "tool": call.name, "status": call.status, "note": note}


class CoordinatorRole(AgentRole):
    name = "coordinator"
    role = "coordinator"
    task_label = "拆分用户目标并生成多 Agent 分工"

    def fallback(self, context: dict[str, Any]) -> RoleExecution:
        request: AgentChatRequest = context["request"]
        tasks: list[AgentTaskSpec] = context["tasks"]
        return RoleExecution(
            task=context["current_task"],
            summary="已生成多 Agent 调查分工。",
            findings=[f"任务数：{len(tasks)}", f"数据集：{request.dataset_id or '未指定'}"],
            confidence=0.72,
            next_actions=["按任务依赖执行 specialist 分析", "由 verifier 复核证据"],
            output={"delegated_agents": [task.agent_name for task in tasks]},
            message_type="task",
            recipient="specialists",
            resolved=True,
        )


class PayloadAnalystRole(AgentRole):
    name = "payload_analyst"
    role = "specialist"
    task_label = "分析 payload、事件元数据和检测命中证据"

    def fallback(self, context: dict[str, Any]) -> RoleExecution:
        tools = _executed_tools(context)
        refs = []
        findings = []
        event_count = 0
        if call := tools.get("get_event"):
            refs.append(_evidence_ref(call, "inspected explicit event"))
            findings.append("已读取指定事件并提取 payload 元数据。")
            event_count = 1
        if call := tools.get("hunt_query"):
            refs.append(_evidence_ref(call, "hunt results used for payload clustering"))
            if isinstance(call.result, dict):
                event_count = len(call.result.get("events") or [])
            findings.append(f"狩猎结果返回 {event_count} 条未抑制事件用于 payload 侧分析。")
        if not findings:
            findings.append("当前请求没有产生可供 payload_analyst 独立分析的事件证据。")
        return RoleExecution(
            task=context["current_task"],
            summary="payload 侧证据分析完成。",
            findings=findings,
            evidence_refs=refs,
            confidence=0.78 if refs else 0.35,
            next_actions=["必要时补充单事件深度分析"] if refs else ["补充事件证据后重试"],
            output={"event_count": event_count},
            message_type="result",
            resolved=bool(refs),
            status="completed" if refs else "waiting_follow_up",
            follow_up_action={} if refs else {"type": "request_more_evidence", "target": "hunt_interpreter"},
        )


class HuntInterpreterRole(AgentRole):
    name = "hunt_interpreter"
    role = "specialist"
    task_label = "解释狩猎查询、攻击面聚合和误报过滤结果"

    def fallback(self, context: dict[str, Any]) -> RoleExecution:
        tools = _executed_tools(context)
        refs = []
        findings = []
        if call := tools.get("hunt_query"):
            refs.append(_evidence_ref(call, "interpreted hunt result"))
            matched = call.result.get("matched_events", len(call.result.get("events") or [])) if isinstance(call.result, dict) else 0
            suppressed = call.result.get("suppressed_events", 0) if isinstance(call.result, dict) else 0
            findings.append(f"狩猎查询命中 {matched} 条事件，排除/抑制 {suppressed} 条。")
        if call := tools.get("attack_surface_map"):
            refs.append(_evidence_ref(call, "attack surface map"))
            surfaces = len(call.result.get("top_surfaces") or []) if isinstance(call.result, dict) else 0
            findings.append(f"攻击面梳理返回 {surfaces} 个高风险 host/path 聚合点。")
        if not findings:
            findings.append("当前请求没有触发狩猎或攻击面工具，无法形成独立狩猎结论。")
        return RoleExecution(
            task=context["current_task"],
            summary="狩猎与攻击面解释完成。",
            findings=findings,
            evidence_refs=refs,
            confidence=0.82 if refs else 0.3,
            next_actions=["根据攻击面聚合结果决定后续验证重点"],
            output={},
            message_type="result",
            resolved=bool(refs),
            status="completed" if refs else "waiting_follow_up",
            follow_up_action={} if refs else {"type": "request_more_evidence", "target": "payload_analyst"},
        )


class VulnerabilityResearcherRole(AgentRole):
    name = "vulnerability_researcher"
    role = "specialist"
    task_label = "整理漏洞候选、影响假设、误报风险和安全验证路线"

    def fallback(self, context: dict[str, Any]) -> RoleExecution:
        tools = _executed_tools(context)
        refs = []
        findings = []
        validation_routes = []
        if call := tools.get("list_vulnerabilities"):
            refs.append(_evidence_ref(call, "vulnerability candidates"))
            count = len(call.result) if isinstance(call.result, list) else 0
            findings.append(f"漏洞候选列表返回 {count} 个候选项。")
        if call := tools.get("get_vulnerability_analysis"):
            refs.append(_evidence_ref(call, "single vulnerability analysis"))
            if isinstance(call.result, dict):
                validation_routes.extend(call.result.get("validation_focus") or [])
            findings.append("已读取指定漏洞候选的分析、误报风险和验证历史。")
        if call := tools.get("red_team_hypotheses"):
            refs.append(_evidence_ref(call, "safe red-team hypotheses"))
            hypotheses = call.result.get("hypotheses", []) if isinstance(call.result, dict) else []
            findings.append(f"安全红队假设生成 {len(hypotheses)} 条验证路线，未执行主动攻击。")
            for item in hypotheses[:3]:
                validation_routes.extend(item.get("safe_validation_plan") or [])
        if not findings:
            findings.append("当前请求没有可用漏洞候选或红队假设证据。")
        return RoleExecution(
            task=context["current_task"],
            summary="漏洞候选研判完成。",
            findings=findings,
            evidence_refs=refs,
            confidence=0.8 if refs else 0.32,
            next_actions=validation_routes[:8] or ["补充候选漏洞证据后重试"],
            output={"validation_routes": validation_routes[:8]},
            message_type="result",
            resolved=bool(refs),
            status="completed" if refs else "waiting_follow_up",
            follow_up_action={} if refs else {"type": "request_more_evidence", "target": "hunt_interpreter"},
        )


class EvidenceVerifierRole(AgentRole):
    name = "evidence_verifier"
    role = "verifier"
    task_label = "独立复核专家 Agent 结论是否有工具证据支撑"

    def fallback(self, context: dict[str, Any]) -> RoleExecution:
        executions: list[RoleExecution] = context.get("role_executions", [])
        blocked: list[AgentToolCallOut] = context.get("blocked_tool_calls", [])
        gaps = []
        refs = []
        checked_agents = []
        unresolved_targets: list[str] = []
        for execution in executions:
            if execution.task.agent_name in {"payload_analyst", "hunt_interpreter", "vulnerability_researcher"}:
                checked_agents.append(execution.task.agent_name)
                refs.extend(execution.evidence_refs)
                if not execution.evidence_refs:
                    gaps.append(f"{execution.task.agent_name} 缺少已执行工具证据，结论只能作为待补充线索。")
                    unresolved_targets.append(execution.task.agent_name)
        for call in blocked:
            gaps.append(f"工具 {call.name} 等待确认或被策略拦截，相关结论不能视为已执行结果。")
        if not gaps:
            gaps.append("未发现关键证据缺口；结论仍应限于当前数据集和已执行工具结果。")
        resolved = not unresolved_targets and not blocked
        return RoleExecution(
            task=context["current_task"],
            summary="证据复核完成。",
            findings=gaps,
            evidence_refs=refs,
            confidence=0.86 if refs else 0.5,
            next_actions=["必要时要求 specialist 补充证据"],
            output={"checked_agents": checked_agents, "blocked_tool_count": len(blocked)},
            message_type="verification",
            recipient=",".join(unresolved_targets) if unresolved_targets else None,
            follow_up_action={} if resolved else {"type": "request_more_evidence", "targets": unresolved_targets},
            resolved=resolved,
            status="completed" if resolved else "waiting_follow_up",
        )


class ReportGeneratorRole(AgentRole):
    name = "report_generator"
    role = "aggregator"
    task_label = "基于 verifier 通过的证据生成最终共识回答"

    def fallback(self, context: dict[str, Any]) -> RoleExecution:
        executions: list[RoleExecution] = context.get("role_executions", [])
        confirmed_facts = []
        inferences = []
        recommended_next_steps = []
        evidence_gaps = []
        for execution in executions:
            if execution.task.agent_name in {"payload_analyst", "hunt_interpreter", "vulnerability_researcher"}:
                if execution.evidence_refs:
                    confirmed_facts.extend(execution.findings)
                else:
                    inferences.extend(execution.findings)
                recommended_next_steps.extend(execution.next_actions)
            if execution.task.agent_name == "evidence_verifier":
                evidence_gaps.extend(execution.findings)
        if not recommended_next_steps:
            recommended_next_steps.append("继续导入或分析数据集后，再运行多 Agent 调查流程。")
        summary = (
            f"多 Agent 调查完成：确认事实 {len(confirmed_facts)} 条，"
            f"待补证据 {len(evidence_gaps)} 条，建议下一步 {len(recommended_next_steps)} 条。"
        )
        return RoleExecution(
            task=context["current_task"],
            summary=summary,
            findings=confirmed_facts[:12] + inferences[:8],
            evidence_refs=[ref for execution in executions for ref in execution.evidence_refs],
            confidence=0.82 if confirmed_facts else 0.55,
            next_actions=recommended_next_steps[:8],
            output={
                "confirmed_facts": confirmed_facts[:12],
                "inferences": inferences[:8],
                "evidence_gaps": evidence_gaps,
                "recommended_next_steps": recommended_next_steps[:8],
            },
            message_type="summary",
            resolved=True,
        )


ROLE_REGISTRY = {
    "coordinator": CoordinatorRole,
    "payload_analyst": PayloadAnalystRole,
    "hunt_interpreter": HuntInterpreterRole,
    "vulnerability_researcher": VulnerabilityResearcherRole,
    "evidence_verifier": EvidenceVerifierRole,
    "report_generator": ReportGeneratorRole,
}

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...config import Settings
from ...schemas import AgentChatRequest, AgentToolCallOut


@dataclass(slots=True)
class CollaborationMessage:
    id: str
    agent_name: str
    role: str
    task: str
    input_summary: dict[str, Any]
    output: dict[str, Any]
    depends_on: list[str]
    evidence_refs: list[dict[str, Any]]
    confidence: float
    llm_used: bool = False
    status: str = "completed"
    error: str | None = None
    created_at: Any | None = None


def _tool_summary(tool_calls: list[AgentToolCallOut]) -> dict[str, AgentToolCallOut]:
    return {call.name: call for call in tool_calls if call.status == "executed"}


def _evidence_ref(call: AgentToolCallOut, note: str) -> dict[str, Any]:
    return {"tool_call_id": call.id, "tool": call.name, "status": call.status, "note": note}


def _safe_count(value: Any, key: str) -> int:
    if isinstance(value, dict) and isinstance(value.get(key), list):
        return len(value[key])
    return 0


def _coordinator_message(request: AgentChatRequest, planned: list[dict[str, Any]], settings: Settings) -> CollaborationMessage:
    tool_names = [item.get("name") for item in planned]
    tasks = ["payload_analyst", "hunt_interpreter", "vulnerability_researcher"]
    return CollaborationMessage(
        id="agent-1",
        agent_name="coordinator",
        role="coordinator",
        task="拆分用户目标并生成多 Agent 协作任务图",
        input_summary={
            "message": request.message,
            "dataset_id": request.dataset_id,
            "planned_tools": tool_names,
            "max_parallelism": settings.agent_max_parallelism,
        },
        output={
            "delegated_agents": tasks,
            "verification_required": settings.agent_require_verifier,
            "aggregation_agent": "report_generator",
        },
        depends_on=[],
        evidence_refs=[],
        confidence=0.72,
    )


def _payload_analyst_message(tool_calls: list[AgentToolCallOut], depends_on: list[str]) -> CollaborationMessage:
    tools = _tool_summary(tool_calls)
    refs = []
    findings = []
    event_count = 0
    if call := tools.get("get_event"):
        refs.append(_evidence_ref(call, "inspected explicit event"))
        findings.append("已读取指定事件并提取 payload 元数据。")
        event_count = 1
    if call := tools.get("hunt_query"):
        refs.append(_evidence_ref(call, "hunt results used for payload clustering"))
        event_count = _safe_count(call.result, "events")
        findings.append(f"狩猎结果返回 {event_count} 条未抑制事件用于 payload 侧分析。")
    if not findings:
        findings.append("当前请求没有产生可供 payload_analyst 独立分析的事件证据。")
    return CollaborationMessage(
        id="agent-2",
        agent_name="payload_analyst",
        role="specialist",
        task="分析 payload、事件元数据和检测命中证据",
        input_summary={"tool_inputs": [ref["tool"] for ref in refs]},
        output={"findings": findings, "event_count": event_count},
        depends_on=depends_on,
        evidence_refs=refs,
        confidence=0.78 if refs else 0.35,
    )


def _hunt_interpreter_message(tool_calls: list[AgentToolCallOut], depends_on: list[str]) -> CollaborationMessage:
    tools = _tool_summary(tool_calls)
    refs = []
    findings = []
    if call := tools.get("hunt_query"):
        refs.append(_evidence_ref(call, "interpreted hunt result"))
        matched = call.result.get("matched_events", _safe_count(call.result, "events")) if isinstance(call.result, dict) else 0
        suppressed = call.result.get("suppressed_events", 0) if isinstance(call.result, dict) else 0
        findings.append(f"狩猎查询命中 {matched} 条事件，排除/抑制 {suppressed} 条。")
    if call := tools.get("attack_surface_map"):
        refs.append(_evidence_ref(call, "attack surface map"))
        surfaces = _safe_count(call.result, "top_surfaces")
        findings.append(f"攻击面梳理返回 {surfaces} 个高风险 host/path 聚合点。")
    if not findings:
        findings.append("当前请求没有触发狩猎或攻击面工具，无法形成独立狩猎结论。")
    return CollaborationMessage(
        id="agent-3",
        agent_name="hunt_interpreter",
        role="specialist",
        task="解释狩猎查询、攻击面聚合和误报过滤结果",
        input_summary={"tool_inputs": [ref["tool"] for ref in refs]},
        output={"findings": findings},
        depends_on=depends_on,
        evidence_refs=refs,
        confidence=0.82 if refs else 0.3,
    )


def _vulnerability_researcher_message(tool_calls: list[AgentToolCallOut], depends_on: list[str]) -> CollaborationMessage:
    tools = _tool_summary(tool_calls)
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
    return CollaborationMessage(
        id="agent-4",
        agent_name="vulnerability_researcher",
        role="specialist",
        task="整理漏洞候选、影响假设、误报风险和安全验证路线",
        input_summary={"tool_inputs": [ref["tool"] for ref in refs]},
        output={"findings": findings, "validation_routes": validation_routes[:8]},
        depends_on=depends_on,
        evidence_refs=refs,
        confidence=0.8 if refs else 0.32,
    )


def _verifier_message(messages: list[CollaborationMessage], blocked: list[AgentToolCallOut], require_verifier: bool) -> CollaborationMessage:
    refs = []
    gaps = []
    checked_agents = []
    for message in messages:
        if message.role != "specialist":
            continue
        checked_agents.append(message.agent_name)
        refs.extend(message.evidence_refs)
        if not message.evidence_refs:
            gaps.append(f"{message.agent_name} 缺少已执行工具证据，结论只能作为待补充线索。")
    for call in blocked:
        gaps.append(f"工具 {call.name} 等待确认或被策略拦截，相关结论不能视为已执行结果。")
    if not gaps:
        gaps.append("未发现关键证据缺口；结论仍应限于当前数据集和已执行工具结果。")
    return CollaborationMessage(
        id="agent-5",
        agent_name="evidence_verifier",
        role="verifier",
        task="独立复核专家 Agent 结论是否有工具证据支撑",
        input_summary={"checked_agents": checked_agents, "require_verifier": require_verifier},
        output={"verified": True, "evidence_gaps": gaps, "blocked_tool_count": len(blocked)},
        depends_on=[message.id for message in messages if message.role == "specialist"],
        evidence_refs=refs,
        confidence=0.86 if refs else 0.5,
    )


def _report_message(messages: list[CollaborationMessage], verifier: CollaborationMessage) -> tuple[CollaborationMessage, dict[str, Any], list[str], str]:
    confirmed_facts = []
    inferences = []
    recommended_next_steps = []
    for message in messages:
        if message.role != "specialist":
            continue
        facts = message.output.get("findings") or []
        if message.evidence_refs:
            confirmed_facts.extend(facts)
        else:
            inferences.extend(facts)
        recommended_next_steps.extend(message.output.get("validation_routes") or [])
    evidence_gaps = list(verifier.output.get("evidence_gaps") or [])
    if not recommended_next_steps:
        recommended_next_steps.append("继续导入或分析数据集后，再运行狩猎、攻击面和漏洞候选协作流程。")
    consensus = {
        "confirmed_facts": confirmed_facts[:12],
        "inferences": inferences[:8],
        "evidence_gaps": evidence_gaps,
        "recommended_next_steps": recommended_next_steps[:8],
    }
    answer = (
        f"多 Agent 协作完成：确认事实 {len(consensus['confirmed_facts'])} 条，"
        f"待补证据 {len(evidence_gaps)} 条，建议下一步 {len(consensus['recommended_next_steps'])} 条。"
    )
    message = CollaborationMessage(
        id="agent-6",
        agent_name="report_generator",
        role="aggregator",
        task="基于 verifier 通过的证据生成最终共识回答",
        input_summary={"verified_by": verifier.agent_name},
        output={"answer": answer, **consensus},
        depends_on=[verifier.id],
        evidence_refs=verifier.evidence_refs,
        confidence=0.82 if confirmed_facts else 0.55,
    )
    return message, consensus, evidence_gaps, answer


def build_collaboration(
    request: AgentChatRequest,
    planned: list[dict[str, Any]],
    tool_calls: list[AgentToolCallOut],
    settings: Settings,
) -> tuple[list[CollaborationMessage], dict[str, Any], list[str], str]:
    coordinator = _coordinator_message(request, planned, settings)
    specialists = [
        _payload_analyst_message(tool_calls, [coordinator.id]),
        _hunt_interpreter_message(tool_calls, [coordinator.id]),
        _vulnerability_researcher_message(tool_calls, [coordinator.id]),
    ]
    blocked = [call for call in tool_calls if call.status == "blocked"]
    verifier = _verifier_message([coordinator, *specialists], blocked, settings.agent_require_verifier)
    reporter, consensus, evidence_gaps, answer = _report_message([coordinator, *specialists], verifier)
    return [coordinator, *specialists, verifier, reporter], consensus, evidence_gaps, answer

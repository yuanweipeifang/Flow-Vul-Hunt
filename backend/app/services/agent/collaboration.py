from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...config import Settings
from ...schemas import AgentChatRequest, AgentToolCallOut
from .roles import RoleExecution


@dataclass(slots=True)
class CollaborationMessage:
    id: str
    agent_name: str
    role: str
    task: str
    message_type: str
    recipient: str | None
    follow_up_action: dict[str, Any]
    resolved: bool
    input_summary: dict[str, Any]
    output: dict[str, Any]
    depends_on: list[str]
    evidence_refs: list[dict[str, Any]]
    confidence: float
    llm_used: bool = False
    status: str = "completed"
    error: str | None = None
    created_at: Any | None = None


def _message_from_execution(execution: RoleExecution) -> CollaborationMessage:
    return CollaborationMessage(
        id=execution.task.task_id,
        agent_name=execution.task.agent_name,
        role={
            "coordinator": "coordinator",
            "payload_analyst": "specialist",
            "hunt_interpreter": "specialist",
            "vulnerability_researcher": "specialist",
            "evidence_verifier": "verifier",
            "report_generator": "aggregator",
        }.get(execution.task.agent_name, "specialist"),
        task=execution.task.goal,
        message_type=execution.message_type,
        recipient=execution.recipient,
        follow_up_action=execution.follow_up_action,
        resolved=execution.resolved,
        input_summary={
            "tool_names": execution.task.tool_names,
            "depends_on": execution.task.depends_on,
            "priority": execution.task.priority,
        },
        output={
            "summary": execution.summary,
            "findings": execution.findings,
            "next_actions": execution.next_actions,
            **execution.output,
        },
        depends_on=execution.task.depends_on,
        evidence_refs=execution.evidence_refs,
        confidence=execution.confidence,
        llm_used=execution.llm_used,
        status=execution.status,
        error=execution.error,
    )


def build_collaboration(
    request: AgentChatRequest,
    planned: list[dict[str, Any]],
    tool_calls: list[AgentToolCallOut],
    settings: Settings,
    executions: list[RoleExecution],
) -> tuple[list[CollaborationMessage], dict[str, Any], list[str], str]:
    messages = [_message_from_execution(execution) for execution in executions]
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
    return messages, consensus, evidence_gaps, answer

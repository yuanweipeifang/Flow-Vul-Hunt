from __future__ import annotations

from typing import Any

from ...config import Settings
from ...llm.gateway import LLMGateway
from ...schemas import AgentChatRequest
from .constants import AgentPlan, AgentTaskSpec, SECURITY_BRAIN_PROMPT


def planned_tools_fallback(request: AgentChatRequest) -> list[dict[str, Any]]:
    lowered = request.message.lower()
    dataset_args = {"dataset_id": request.dataset_id} if request.dataset_id else {}
    calls: list[dict[str, Any]] = []
    if request.dataset_id:
        calls.append({"name": "get_dataset", "arguments": dataset_args})
    else:
        calls.append({"name": "list_datasets", "arguments": {"limit": 10}})
    if any(word in lowered for word in ("狩猎", "hunt", "高危", "威胁", "事件", "误报")):
        calls.append(
            {
                "name": "hunt_query",
                "arguments": {
                    **dataset_args,
                    "query": request.message,
                    "limit": 20,
                    "exclude_suppressed": True,
                },
            }
        )
    if any(word in lowered for word in ("攻击面", "attack surface", "资产", "入口", "路径")):
        calls.append({"name": "attack_surface_map", "arguments": {**dataset_args, "limit": 20}})
    if any(word in lowered for word in ("红队", "red team", "假设", "验证路线", "利用链", "攻击路径")):
        calls.append({"name": "red_team_hypotheses", "arguments": {**dataset_args, "limit": 10}})
    if any(word in lowered for word in ("漏洞", "vulnerability", "cve", "验证")):
        calls.append({"name": "list_vulnerabilities", "arguments": {**dataset_args, "limit": 20}})
    if any(word in lowered for word in ("分析", "reanalyze", "启动")) and request.dataset_id:
        calls.append(
            {
                "name": "start_dataset_analysis",
                "arguments": {**dataset_args, "use_llm": True, "llm_scope": "suspicious", "force": False},
            }
        )
    return calls


def _default_tasks(request: AgentChatRequest, planned: list[dict[str, Any]]) -> list[AgentTaskSpec]:
    tool_names = [str(item.get("name", "")) for item in planned if item.get("name")]
    tasks = [
        AgentTaskSpec(
            task_id="task-scope",
            agent_name="coordinator",
            goal="确认调查范围并生成多 Agent 分工",
            tool_names=[name for name in tool_names if name in {"get_dataset", "list_datasets"}],
            priority=100,
        )
    ]
    if any(name in tool_names for name in {"hunt_query", "attack_surface_map"}):
        tasks.append(
            AgentTaskSpec(
                task_id="task-hunt",
                agent_name="hunt_interpreter",
                goal="解释狩猎命中、误报抑制和攻击面聚合",
                tool_names=[name for name in tool_names if name in {"hunt_query", "attack_surface_map"}],
                depends_on=["task-scope"],
                priority=90,
            )
        )
    if any(name in tool_names for name in {"get_event", "hunt_query"}):
        tasks.append(
            AgentTaskSpec(
                task_id="task-payload",
                agent_name="payload_analyst",
                goal="分析 payload 证据和事件元数据",
                tool_names=[name for name in tool_names if name in {"get_event", "hunt_query"}],
                depends_on=["task-scope"],
                priority=90,
            )
        )
    if any(name in tool_names for name in {"list_vulnerabilities", "get_vulnerability_analysis", "red_team_hypotheses"}):
        tasks.append(
            AgentTaskSpec(
                task_id="task-vulnerability",
                agent_name="vulnerability_researcher",
                goal="整理漏洞候选、影响假设和验证路线",
                tool_names=[name for name in tool_names if name in {"list_vulnerabilities", "get_vulnerability_analysis", "red_team_hypotheses"}],
                depends_on=["task-scope"],
                priority=80,
            )
        )
    tasks.append(
        AgentTaskSpec(
            task_id="task-verify",
            agent_name="evidence_verifier",
            goal="复核专家结论是否有足够证据",
            depends_on=[task.task_id for task in tasks if task.agent_name in {"payload_analyst", "hunt_interpreter", "vulnerability_researcher"}],
            priority=40,
        )
    )
    tasks.append(
        AgentTaskSpec(
            task_id="task-report",
            agent_name="report_generator",
            goal="生成最终调查报告与下一步建议",
            depends_on=["task-verify"],
            priority=10,
        )
    )
    return tasks


def _normalize_tasks(request: AgentChatRequest, plan: AgentPlan, planned: list[dict[str, Any]]) -> list[AgentTaskSpec]:
    if plan.tasks:
        return plan.tasks
    return _default_tasks(request, planned)


def _derive_tools_from_tasks(tasks: list[AgentTaskSpec], request: AgentChatRequest) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    dataset_args = {"dataset_id": request.dataset_id} if request.dataset_id else {}
    for task in sorted(tasks, key=lambda item: item.priority, reverse=True):
        for name in task.tool_names:
            if any(call["name"] == name for call in calls):
                continue
            arguments: dict[str, Any] = {}
            if request.dataset_id and name in {
                "get_dataset",
                "hunt_query",
                "attack_surface_map",
                "red_team_hypotheses",
                "list_vulnerabilities",
                "get_vulnerability_analysis",
                "start_dataset_analysis",
            }:
                arguments["dataset_id"] = request.dataset_id
            if name == "list_datasets":
                arguments["limit"] = 10
            if name == "hunt_query":
                arguments.update({"query": request.message, "limit": 20, "exclude_suppressed": True})
            if name in {"attack_surface_map", "list_vulnerabilities"}:
                arguments["limit"] = 20
            if name == "red_team_hypotheses":
                arguments["limit"] = 10
            if name == "start_dataset_analysis":
                arguments.update({"use_llm": True, "llm_scope": "suspicious", "force": False})
            calls.append({"name": name, "arguments": arguments})
    return calls or planned_tools_fallback(request)


def hermes_planned_tools(
    request: AgentChatRequest,
    settings: Settings,
    allowed: set[str],
) -> tuple[list[str], list[dict[str, Any]], list[AgentTaskSpec], str | None]:
    payload = {
        "message": request.message,
        "dataset_id": request.dataset_id,
        "allowed_tools": sorted(allowed),
        "max_steps": request.max_steps or settings.agent_max_steps,
    }
    result = LLMGateway(settings).complete_json(
        SECURITY_BRAIN_PROMPT,
        payload,
        AgentPlan,
        agent_name="security_brain",
    )
    plan = [item[:300] for item in result.data.plan[: settings.agent_max_steps]]
    calls = []
    for item in result.data.tool_calls[: settings.agent_max_steps]:
        name = str(item.get("name", ""))
        arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        if name in allowed:
            if request.dataset_id and name in {
                "get_dataset",
                "hunt_query",
                "attack_surface_map",
                "red_team_hypotheses",
                "list_vulnerabilities",
                "start_dataset_analysis",
            }:
                arguments.setdefault("dataset_id", request.dataset_id)
            if name == "hunt_query":
                arguments.setdefault("query", request.message)
                arguments.setdefault("exclude_suppressed", True)
                arguments.setdefault("limit", 20)
            if name in {"attack_surface_map", "list_vulnerabilities"}:
                arguments.setdefault("limit", 20)
            if name == "red_team_hypotheses":
                arguments.setdefault("limit", 10)
            calls.append({"name": name, "arguments": arguments})
    tasks = _normalize_tasks(request, result.data, calls)
    if not calls:
        calls = _derive_tools_from_tasks(tasks, request)
    if not plan:
        plan = [
            "确认分析范围",
            "并行执行狩猎、payload 分析和漏洞研判",
            "复核证据链后生成最终报告",
        ]
    return plan, calls, tasks, result.data.final_focus


def planned_task_graph_fallback(request: AgentChatRequest) -> tuple[list[str], list[dict[str, Any]], list[AgentTaskSpec], str | None]:
    calls = planned_tools_fallback(request)
    plan = [
        "确认数据集范围和当前状态",
        "并行执行狩猎、payload 分析和漏洞候选研判",
        "复核证据链并生成最终报告",
        "高风险动作在确认后再执行",
    ]
    return plan, calls, _default_tasks(request, calls), "优先完成数据集调查闭环，并保留证据缺口说明。"

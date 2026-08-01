from __future__ import annotations

from typing import Any

from ...config import Settings
from ...llm.gateway import LLMGateway
from ...schemas import AgentChatRequest
from .constants import SECURITY_BRAIN_PROMPT, AgentPlan


def planned_tools_fallback(request: AgentChatRequest) -> list[dict[str, Any]]:
    lowered = request.message.lower()
    dataset_args = {"dataset_id": request.dataset_id} if request.dataset_id else {}
    calls: list[dict[str, Any]] = []
    if request.dataset_id:
        calls.append({"name": "get_dataset", "arguments": dataset_args})
        calls.append({"name": "read_dataset_csv_sample", "arguments": {**dataset_args, "limit": 12}})
    else:
        calls.append({"name": "list_datasets", "arguments": {"limit": 10}})
        calls.append({"name": "list_stored_csv_files", "arguments": {"limit": 20}})
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


def hermes_planned_tools(
    request: AgentChatRequest,
    settings: Settings,
    allowed: set[str],
) -> tuple[list[str], list[dict[str, Any]], str | None]:
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
                "read_dataset_csv_sample",
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
            if name in {"read_dataset_csv_sample", "list_stored_csv_files"}:
                arguments.setdefault("limit", 20)
            if name == "red_team_hypotheses":
                arguments.setdefault("limit", 10)
            calls.append({"name": name, "arguments": arguments})
    if not calls:
        calls = planned_tools_fallback(request)
    if not plan:
        plan = [
            "确认分析范围",
            "优先执行只读狩猎和攻击面梳理",
            "输出可验证的红队假设和误报风险",
        ]
    return plan, calls, result.data.final_focus

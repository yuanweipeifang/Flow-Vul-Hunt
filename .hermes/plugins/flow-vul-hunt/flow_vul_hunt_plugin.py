from __future__ import annotations

import json
import os
from typing import Any

import httpx


BASE_URL = os.getenv("FLOW_VUL_HUNT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("FLOW_VUL_HUNT_INTERNAL_API_KEY", "")


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY} if API_KEY else {}


def _request(method: str, path: str, **kwargs: Any) -> str:
    with httpx.Client(timeout=60) as client:
        response = client.request(method, f"{BASE_URL}{path}", headers=_headers(), **kwargs)
        response.raise_for_status()
        if not response.content:
            return "{}"
        return json.dumps(response.json(), ensure_ascii=False)


def hunt_query(params: dict[str, Any], **_: Any) -> str:
    return _request(
        "POST",
        "/api/hunt/query",
        json={
            "dataset_id": params.get("dataset_id"),
            "query": params["query"],
            "limit": params.get("limit", 50),
            "use_llm": params.get("use_llm", True),
            "exclude_suppressed": params.get("exclude_suppressed", True),
        },
    )


def get_vulnerability_analysis(params: dict[str, Any], **_: Any) -> str:
    return _request("GET", f"/api/vulnerabilities/{params['vulnerability_id']}/analysis")


def list_vulnerabilities(params: dict[str, Any], **_: Any) -> str:
    query = {"limit": params.get("limit", 50)}
    if params.get("dataset_id"):
        query["dataset_id"] = params["dataset_id"]
    return _request("GET", "/api/vulnerabilities", params=query)


def agent_chat(params: dict[str, Any], **_: Any) -> str:
    return _request(
        "POST",
        "/api/agent/chat",
        json={
            "message": params["message"],
            "dataset_id": params.get("dataset_id"),
            "auto_execute": params.get("auto_execute", False),
            "confirmed_tool_call_ids": params.get("confirmed_tool_call_ids", []),
            "max_steps": params.get("max_steps"),
        },
    )


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="hunt_query",
        toolset="flow_vul_hunt",
        description="Run a Flow-Vul-Hunt threat hunting query. Confirmed benign events are excluded by default.",
        schema={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
                "use_llm": {"type": "boolean", "default": True},
                "exclude_suppressed": {"type": "boolean", "default": True},
            },
            "required": ["query"],
        },
        handler=hunt_query,
    )
    ctx.register_tool(
        name="agent_chat",
        toolset="flow_vul_hunt",
        description="Ask Flow-Vul-Hunt's project-local agent gateway to plan and orchestrate red-team and hunting work.",
        schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "dataset_id": {"type": "string"},
                "auto_execute": {"type": "boolean", "default": False},
                "confirmed_tool_call_ids": {"type": "array", "items": {"type": "string"}},
                "max_steps": {"type": "integer"},
            },
            "required": ["message"],
        },
        handler=agent_chat,
    )
    ctx.register_tool(
        name="list_vulnerabilities",
        toolset="flow_vul_hunt",
        description="List vulnerability candidates for triage.",
        schema={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
        handler=list_vulnerabilities,
    )
    ctx.register_tool(
        name="get_vulnerability_analysis",
        toolset="flow_vul_hunt",
        description="Get vulnerability analysis with confidence factors, false-positive risks, validation focus and history.",
        schema={
            "type": "object",
            "properties": {"vulnerability_id": {"type": "string"}},
            "required": ["vulnerability_id"],
        },
        handler=get_vulnerability_analysis,
    )

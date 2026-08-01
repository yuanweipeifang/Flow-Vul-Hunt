# Agent Version Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the chat-first local Agent experience with the collaborator multi-agent task graph and observability experience, resolve all existing merge conflicts, and verify the result.

**Architecture:** Keep the collaborator backend orchestration pipeline as the execution source of truth. Add the local structured LLM final-answer layer after deterministic consensus, and expose one backward-compatible response containing task graph, tool evidence, messages, memory-related session data, and the final answer. Keep the frontend chat as the primary interaction and render selected-session observability below it.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, pytest, React 19, TypeScript, Vite, ESLint.

---

## File Map

- Modify: `.gitignore` to retain all existing ignore rules in one normal text file.
- Modify: `backend/app/schemas/agent.py` to unify task, message, memory, session, run, chat result, and final-answer schemas.
- Modify: `backend/app/services/agent/chat.py` to remove conflict markers/debug side effects and combine orchestrator execution with the final LLM answer path.
- Modify: `backend/tests/test_operational_hardening.py` to add a regression assertion for the merged response contract and deterministic fallback.
- Modify: `frontend/src/api.ts` to type `AgentChatResult.task_graph`.
- Modify: `frontend/src/pages/AgentPage.tsx` to combine chat-first interaction with selected-session observability.
- Verify: `backend` with pytest and `frontend` with TypeScript build and ESLint.

### Task 1: Add the failing backend regression test

**Files:**
- Modify: `backend/tests/test_operational_hardening.py`

- [ ] **Step 1: Add a test for the merged response contract**

Append a focused test that creates a minimal in-memory Agent request and verifies
that the response exposes both task graph data and a usable deterministic answer
when no provider key is configured:

```python
def test_agent_chat_result_keeps_task_graph_and_fallback_answer(db_session) -> None:
    settings = Settings(
        app_name="test",
        app_env="test",
        database_url="sqlite:///:memory:",
        max_upload_bytes=1,
        max_payload_chars=1000,
        llm_timeout_seconds=1,
        llm_max_retries=0,
        llm_max_input_chars=1000,
        providers={},
        agent_routes={},
        agent_enabled=True,
        agent_collaboration_enabled=True,
    )
    dataset = Dataset(
        name="merge-contract",
        filename="merge.csv",
        file_sha256="f" * 64,
        row_count=1,
        status="ready",
    )
    db_session.add(dataset)
    db_session.flush()
    db_session.add(
        PayloadEvent(
            dataset_id=dataset.id,
            row_number=1,
            raw_payload="GET /search?q=hello HTTP/1.1",
            decoded_payload="GET /search?q=hello HTTP/1.1",
            payload_hash="1" * 64,
            risk_score=0,
            verdict="benign",
        )
    )
    db_session.commit()

    result = run_agent_chat(
        AgentChatRequest(
            message="总结这个数据集",
            dataset_id=dataset.id,
            auto_execute=False,
        ),
        db_session,
        BackgroundTasks(),
        Actor("api_key:analyst", "analyst", True),
        settings,
    )

    assert result.answer
    assert result.task_graph
    assert result.collaboration_mode == "multi_agent"
    assert result.llm_used is False
```

- [ ] **Step 2: Run the focused test and record the red result**

Run:

```powershell
cd backend
python -m pytest tests/test_operational_hardening.py::test_agent_chat_result_keeps_task_graph_and_fallback_answer -q
```

Expected before conflict resolution: collection fails because the conflicted
schema or chat module still contains merge markers. This confirms the current
repository state is not a valid implementation baseline.

### Task 2: Unify the backend schemas

**Files:**
- Modify: `backend/app/schemas/agent.py`

- [ ] **Step 1: Resolve the schema conflict**

Keep one import block and define these fields:

```python
class AgentTaskSpecOut(BaseModel):
    task_id: str
    agent_name: str
    goal: str
    tool_names: list[str] = []
    depends_on: list[str] = []
    priority: int = 0
    requires_confirmation: bool = False
    status: str = "pending"
```

Add `message_type`, `recipient`, `follow_up_action`, and `resolved` to
`AgentMessageOut`; add `task_graph` to `AgentRunOut`, `AgentChatResult`, and
`AgentSessionOut`; retain `AgentMemoryOut` and `AgentAnswerDraft`.

- [ ] **Step 2: Run the schema-focused regression**

Run:

```powershell
cd backend
python -m pytest tests/test_operational_hardening.py::test_agent_chat_result_keeps_task_graph_and_fallback_answer -q
```

Expected: the import phase proceeds past the schema conflict and the test still
fails in the chat path until Task 3 is complete.

### Task 3: Merge the backend chat execution path

**Files:**
- Modify: `backend/app/services/agent/chat.py`

- [ ] **Step 1: Keep formal event callback support**

Keep `Callable` and `_emit_agent_event` for the existing SSE endpoint. Remove
`urllib.request`, `_debug_event`, and every debug region that posts to a local
port.

- [ ] **Step 2: Preserve the collaborator planner and orchestrator**

Keep `hermes_planned_tools`, `planned_task_graph_fallback`,
`AgentOrchestrator.execute`, `task_graph_out`, role executions, consensus, and
evidence gaps.

- [ ] **Step 3: Add the local final-answer layer after orchestration**

After `tool_calls` and deterministic consensus are available:

```python
executed_count = sum(call.status == "executed" for call in tool_calls)
blocked_count = sum(call.status == "blocked" for call in tool_calls)
requires_confirmation = any(
    call.status == "blocked" and call.requires_confirmation
    for call in tool_calls
)
answer = collaboration_answer
if settings.agent_collaboration_enabled:
    answer = (
        f"{collaboration_answer} 工具执行概况："
        f"计划 {len(planned)} 步，已执行 {executed_count} 个。"
    )
    if requires_confirmation or blocked_count:
        answer += " 仍有受策略限制或需确认的工具。"

llm_used = planner_used == "hermes" or any(
    execution.llm_used for execution in role_executions
)
llm_answer, llm_meta, llm_warning = _llm_chat_answer(
    request,
    tool_calls,
    consensus,
    settings,
)
if llm_answer:
    answer = llm_answer
    llm_used = True
    consensus = {**consensus, "llm_answer": llm_meta}
elif llm_warning:
    warning = f"{warning}; {llm_warning}" if warning else llm_warning
```

This keeps deterministic output when the provider is disabled or unavailable.

- [ ] **Step 4: Include task graph in confirmation responses**

When `confirm_agent_tools` builds `AgentChatResult`, pass
`task_graph=task_graph_out(list(session.task_graph or []))` so the frontend
does not lose the selected session's task graph after a confirmation action.

- [ ] **Step 5: Run the focused regression to green**

Run:

```powershell
cd backend
python -m pytest tests/test_operational_hardening.py::test_agent_chat_result_keeps_task_graph_and_fallback_answer -q
```

Expected: PASS.

### Task 4: Complete the frontend API contract

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add the response task graph field**

Add this field to `AgentChatResult` before `agents`:

```typescript
task_graph: AgentTaskSpecOut[]
```

- [ ] **Step 2: Run TypeScript compilation**

Run:

```powershell
cd frontend
npm run build
```

Expected before the page conflict is resolved: compilation still fails in
`AgentPage.tsx`; the API type itself must not introduce a new error.

### Task 5: Build the chat-first Agent page with observability details

**Files:**
- Modify: `frontend/src/pages/AgentPage.tsx`

- [ ] **Step 1: Use the combined imports and state**

Keep `useState` and add `useMemo`; import `AgentChatResult`,
`AgentMemoryOut`, `AgentMessageOut`, `AgentSessionOut`, `AgentStatusOut`, and
`ProvidersOut`. Keep `Badge`, `Card`, `DataTable`, `Empty`, `ErrorBox`,
`JsonBlock`, `Loading`, and `PageHeader`.

The page state must include:

```typescript
const [message, setMessage] = useState('')
const [sending, setSending] = useState(false)
const [sendError, setSendError] = useState<unknown>(null)
const [chat, setChat] = useState<ChatMessage[]>([])
const [reloadToken, setReloadToken] = useState(0)
const [selectedSessionId, setSelectedSessionId] = useState('')
```

- [ ] **Step 2: Fetch all four data sources**

Use `Promise.allSettled` for status, providers, sessions, and memory. Normalize
provider data as `data?.providers?.providers || []`, keep partial errors, and
include `reloadToken` in the fetch dependency list so a successful send
refreshes stored data.

- [ ] **Step 3: Preserve the chat send behavior**

POST to `/api/agent/chat` with:

```typescript
{
  message: text,
  dataset_id: context.selectedDataset || null,
  auto_execute: true,
  max_steps: 8,
}
```

Append the user message before the request, append the returned answer and full
`AgentChatResult` after success, refresh the bundle, and always restore the
send state in `finally`.

- [ ] **Step 4: Render selected-session observability**

Use helper components for task graph, message flow, and memory. Derive:

```typescript
const selectedSession = useMemo(
  () => sessions.find((session) => session.id === selectedSessionId)
    || sessions[0]
    || null,
  [selectedSessionId, sessions],
)
const selectedMessages = selectedSession?.runs.flatMap((run) => run.messages) || []
const followUps = selectedMessages.filter(
  (item) => Object.keys(item.follow_up_action || {}).length > 0 || !item.resolved,
)
```

Render chat first, then status/providers/history, then task graph, follow-ups,
message flow, and memory for `selectedSession`.

- [ ] **Step 5: Run frontend build and lint**

Run:

```powershell
cd frontend
npm run build
npm run lint
```

Expected: both commands exit with code 0 and report no merge-marker syntax
errors.

### Task 6: Normalize the repository ignore file

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Keep the existing rules**

Retain Python caches, environment files, backend data artifacts, and
`backups/`. Remove the conflict representation and write the final file as
plain text with one rule per line.

- [ ] **Step 2: Verify no conflict markers remain**

Run:

```powershell
rg -n '^(<<<<<<<|=======|>>>>>>>)' .gitignore backend frontend
```

Expected: no output and exit code 1.

### Task 7: Run the full verification suite

**Files:**
- Verify: `backend`, `frontend`, and all resolved conflict files.

- [ ] **Step 1: Run backend tests**

Run:

```powershell
cd backend
python -m pytest -q
```

Expected: all tests pass with zero failures and zero collection errors.

- [ ] **Step 2: Run frontend checks**

Run:

```powershell
cd frontend
npm run build
npm run lint
```

Expected: both commands exit 0.

- [ ] **Step 3: Check repository state**

Run:

```powershell
cd ..
rg -n '^(<<<<<<<|=======|>>>>>>>)' backend frontend .gitignore
git diff --check
git status --short
```

Expected: no conflict markers, no whitespace errors, and only the intended
merge files plus the documented planning/spec files appear in the status.

- [ ] **Step 4: Start local services for smoke verification**

Run the backend with `python run_backend.py` from the repository root and the
frontend with `npm run dev -- --host 127.0.0.1` from `frontend`. Verify the
Agent page loads, the status/provider/history sections render, and a chat
request returns a response or an explicit disabled-agent error without a
frontend crash.


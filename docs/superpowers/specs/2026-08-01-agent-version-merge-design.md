# Flow-Vul-Hunt Agent Version Merge Design

## Goal

Merge the local `my_version_*` implementation with the collaborator
`their_version_*` implementation while preserving both feature sets:

- interactive Agent chat and LLM-generated final answers;
- multi-agent orchestration, task graphs, message protocol, evidence gaps,
  persistent memory, and session observability.

The final Agent page will be chat-first. Observability remains available for
the selected session on the same page.

## Current Conflict Surface

The working tree has unresolved merge conflicts in:

- `.gitignore`
- `backend/app/schemas/agent.py`
- `backend/app/services/agent/chat.py`
- `frontend/src/pages/AgentPage.tsx`

The surrounding collaborator changes already provide the task graph,
orchestrator, persistent memory model, memory endpoint, and SSE event callback.
The local snapshot adds the chat UI, the final LLM answer draft, and the
answer-building path.

## Backend Design

### Schema contract

`backend/app/schemas/agent.py` will expose the union of both contracts:

- `AgentTaskSpecOut` for planned role tasks;
- task graph fields on `AgentRunOut`, `AgentSessionOut`, and
  `AgentChatResult`;
- message protocol fields on `AgentMessageOut`;
- `AgentMemoryOut` for persisted role memory;
- `AgentAnswerDraft` for structured LLM final answers.

Existing request fields, tool call fields, confirmation fields, and default
values remain backward compatible.

### Chat execution

`backend/app/services/agent/chat.py` will keep the collaborator execution
pipeline:

1. determine isolated Hermes status;
2. obtain a Hermes plan or local task-graph fallback;
3. execute the `AgentOrchestrator`;
4. build deterministic collaboration consensus;
5. optionally call the final-answer LLM;
6. persist the session, run, messages, tool calls, and audit record;
7. emit formal SSE events when streaming is used.

The final answer selection rule is:

- use the LLM answer when the provider is configured and the structured
  response validates;
- otherwise keep the deterministic collaboration answer and append a warning;
- never discard task graph, tool evidence, consensus, or evidence gaps because
  the LLM is unavailable.

Executed and blocked tool counts will be derived directly from `tool_calls`.
Temporary debug HTTP reporting to `127.0.0.1:7777` will be removed; the formal
event callback remains.

## Frontend Design

`frontend/src/pages/AgentPage.tsx` will combine the two existing views:

- the main area contains dataset selection, chat history, quick prompts, send
  state, warnings, and expandable tool evidence;
- the side area contains Agent status, provider status, and recent sessions;
- selecting a session displays its task graph, follow-up actions, message flow,
  and memory records;
- sending a message appends the live response, refreshes sessions and memory,
  and keeps the response available in the chat view;
- selecting a historical session fills a compact user/answer pair and selects
  its stored observability details.

`frontend/src/api.ts` will include every field returned by the merged backend,
including `AgentChatResult.task_graph`.

## Conflict and Encoding Rules

- Resolve `.gitignore` by retaining all existing ignore rules and normalizing
  the file to a normal UTF-8 text file.
- Keep `my_version_*` and `their_version_*` as comparison snapshots during this
  task; they are not runtime entry points.
- Do not delete or rewrite existing SQLite data, uploaded CSVs, backups, or
  unrelated dirty files.
- Do not retain temporary debug hooks as product behavior.

## Error Handling

- Partial status/provider/session/memory fetch failures remain visible through
  the existing `ErrorBox` path while successful sections still render.
- Chat failures leave the typed message in the input flow, show the error, and
  restore the send control.
- LLM provider failure falls back to deterministic output.
- High-risk tool confirmation semantics remain unchanged.
- SSE worker errors are emitted as an `error` event and the stream closes with
  a `done` event.

## Verification

The implementation will add focused backend regression coverage for:

- merged task graph and message metadata serialization;
- deterministic answer fallback when no LLM provider is configured;
- preservation of confirmation and persisted session state.

Verification commands:

- `python -m pytest` from `backend`;
- `npm run build` from `frontend`;
- `npm run lint` from `frontend`;
- conflict-marker search across tracked source files;
- local backend and frontend smoke checks for the Agent page and
  `/api/agent/chat`.

## Non-Goals

- no new agent roles or new tool capabilities;
- no redesign of the global frontend visual system;
- no database schema changes beyond the already-present collaborator migration;
- no live provider key changes;
- no deletion of user-generated data.


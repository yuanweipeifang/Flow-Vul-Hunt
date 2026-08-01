# Agent Version Merge Findings

## Confirmed

- The repository is currently on branch `main` with unresolved conflicts in
  `.gitignore`, `backend/app/schemas/agent.py`,
  `backend/app/services/agent/chat.py`, and
  `frontend/src/pages/AgentPage.tsx`.
- The local version contains the direct chat UI and the structured final LLM
  answer path.
- The collaborator version contains task graph schemas, task graph planning,
  `AgentOrchestrator`, role execution, persistent memory, session trace data,
  and the memory endpoint.
- `backend/app/api/agent.py`, models, migration `0009`, mappers, and the
  collaborator service modules already expect the observability fields.
- `frontend/src/api.ts` already contains most task graph, message, run, and
  memory types, but `AgentChatResult` is missing `task_graph`.
- The current conflicted `chat.py` references `executed` and `blocked` in one
  conflict branch even though the merged scope does not define them.
- The collaborator snapshot contains temporary HTTP debug reporting to
  `127.0.0.1:7777`; this is not part of the product contract.

## Open Verification Items

- Confirm the exact merged `chat.py` behavior with the existing operational
  hardening test.
- Confirm the frontend type contract after the page combines chat and
  observability.
- Confirm that the current SQLite database is already compatible with
  migration `0009` without destructive changes.


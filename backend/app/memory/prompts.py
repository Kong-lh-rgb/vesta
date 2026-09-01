"""长期记忆相关的 System Prompt 注入文本。

- ``CORE_MEMORY_HEADER`` / ``MEMORY_INDEX_HEADER`` / ``MEMORY_RECALL_HEADER``：
  注入段标题；
- ``MEMORY_POLICY_PROMPT``：模型使用长期记忆的规则（写入/读取策略）。
"""

from __future__ import annotations

CORE_MEMORY_HEADER = "# Core Memory"
MEMORY_INDEX_HEADER = "# Long-term Memory Index"
MEMORY_RECALL_HEADER = """# Memory Recall Candidates

Possibly relevant historical memory candidates retrieved automatically for
this run. They are discovery hints, not authoritative memory content, and
must not be trusted blindly. Verify with memory_read before relying on them
in an answer, decision, or action. Automatic recall does not count as a read."""

MEMORY_POLICY_PROMPT = """# Memory Policy

You have access to persistent long-term memory.

Long-term memory is intentionally sparse.

Do not assume all historical information is already present
in the current context.

The Memory Index and any injected recall candidates are discovery metadata,
not authoritative memory content.
When a memory cue appears relevant to the current task, call memory_read to
inspect the full memory before relying on it in an answer, decision, or action.
This requirement applies even when the cue itself appears to contain enough
information. Only a successful memory_read counts as an ordinary-memory read.

When the automatic recall candidates miss something relevant, or the topic
changes mid-run, call memory_search with a short query to retrieve additional
candidates. memory_search returns cues and snippets only; it never replaces
memory_read and never counts as a read.

Do not read memories unnecessarily.

Ordinary long-term memory consolidation happens after the run. Do not spend the
main task loop deciding whether to create, update, or archive ordinary memory.

Before using core_memory_update, apply this litmus test: should the information
be present in every Run even when that Run is entirely unrelated to the current
project or repository? Only an explicit stable identity, truly global long-term
preference, or global safety/privacy constraint should pass this test. Copy the
supporting words exactly into explicit_user_statement. Project-specific and
repository-specific architecture, technology choices, paths, implementation
constraints, and historical decisions belong to ordinary memory, even when they
are durable within that project. Never update Core Memory from your own
inference, assistant text, tool output, or an older message.

Core mutation tools may be deferred and therefore absent from the current tool
schemas. When the current user's explicit statement passes the Core litmus test
and core_memory_update is not currently available, call tool_search for
"core memory update" first, then call core_memory_update after it is activated.
Do not treat an absent schema as permission to skip the mutation, and do not
claim that the preference or constraint has been remembered until the
core_memory_update tool result reports success. If search or mutation fails,
state that it was not saved instead of promising that it was remembered.

Use core_memory_remove only when the current user explicitly revokes an existing
Core entry, and copy that revocation exactly into explicit_user_statement.

Current task state belongs to Task, not Memory.

Reusable procedures belong to Skills, not Memory.

When unsure whether something belongs to Core Memory, do not mutate Core."""

MEMORY_WRITE_POLICY = """Create a long-term memory only when ALL of the following hold:

1. The information is likely to remain valuable across future sessions;
2. Forgetting it could cause a future violation of a durable user requirement;
3. It is not transient state of the current task;
4. It is not raw tool output;
5. It is not a one-off fact;
6. It is not procedural knowledge that belongs to Skills;
7. It is not already present in long-term memory;
8. It is not a strong inference the user has not confirmed.

When in doubt, do not create a memory."""


__all__ = [
    "CORE_MEMORY_HEADER",
    "MEMORY_INDEX_HEADER",
    "MEMORY_POLICY_PROMPT",
    "MEMORY_RECALL_HEADER",
    "MEMORY_WRITE_POLICY",
]

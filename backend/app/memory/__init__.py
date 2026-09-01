"""长期记忆：Sparse, Model-Directed Long-Term Memory System。

设计要点：

- 持久化介质为 Markdown 文件（``CORE.md`` / ``INDEX.md`` / ``active/Mxxx.md``），
  是唯一权威存储；``search.sqlite`` 只是可删除、可重建的搜索投影；
- 普通记忆召回 = Harness 自动 Hybrid Recall（FTS5 + 向量 + RRF，每 Run
  一次）+ ``memory_search`` 补充检索 + ``memory_read`` 正式读取；只有
  成功 ``memory_read`` 才计入读取并授权 Reflection Update；
- Main Agent 只处理用户明确要求的 Core 变更；
- 普通 Memory 的创建或更新由正常 Run 后的独立 Reflection 模型决定；
- 向量服务独立分层（可与主模型 Provider 不同），失败时降级 FTS5，
  索引整体不可用时回退 Legacy INDEX.md 注入，不影响 Run。
"""

from .core import DEFAULT_MAX_CORE_TOKENS, CoreMemoryEntry, CoreMemoryManager
from .embedding import (
    EmbeddingAdapter,
    FakeEmbeddingAdapter,
    MemoryEmbeddingSettings,
    OpenAICompatibleEmbeddingAdapter,
    build_embedding_adapter,
)
from .index import MemoryIndex
from .maintenance import MemoryMaintenance
from .maintenance_models import (
    MaintenanceAction,
    MemoryMaintenanceCandidate,
    MemoryMaintenanceConfig,
    MemoryMaintenanceDecision,
    MemoryMaintenanceInput,
    MemoryMaintenanceProposal,
)
from .maintenance_reflection import MemoryMaintenanceReflector
from .manager import (
    CORE_MEMORY_MESSAGE_NAME,
    MEMORY_INDEX_MESSAGE_NAME,
    MEMORY_POLICY_MESSAGE_NAME,
    MemoryManager,
    MemoryRecallQueryInputs,
    MemoryRecallSnapshot,
    MemorySearchResult,
    MemorySearchSettings,
    SearchMode,
)
from .models import (
    MemoryRecord,
    MemoryStatus,
    next_memory_id,
    parse_memory_markdown,
)
from .prompts import (
    MEMORY_POLICY_PROMPT,
    MEMORY_RECALL_HEADER,
    MEMORY_WRITE_POLICY,
)
from .recall import (
    MEMORY_RECALL_MESSAGE_NAME,
    MemoryRecallService,
    recent_user_message_texts,
)
from .reflection import PostRunMemoryReflector
from .reflection_gate import (
    ReflectionGateDecision,
    ReflectionGateReason,
    decide_reflection_gate,
)
from .reflection_models import (
    MemoryReflectionConfig,
    MemoryReflectionInput,
    MemoryReflectionProposal,
    ReflectionAction,
    ReflectionDecision,
)
from .search_index import MemorySearchIndex
from .store import DEFAULT_MEMORY_DIR, MemoryStore
from .tools import (
    DEFAULT_DEFERRED_MEMORY_TOOL_NAMES,
    MEMORY_SEARCH_TOOL_NAME,
    CoreMemoryRemoveTool,
    CoreMemoryUpdateTool,
    MemoryArchiveTool,
    MemoryCreateTool,
    MemoryListTool,
    MemoryReadTool,
    MemorySearchTool,
    MemoryUpdateTool,
    register_memory_tools,
    register_memory_write_tools,
)

__all__ = [
    "DEFAULT_DEFERRED_MEMORY_TOOL_NAMES",
    "CORE_MEMORY_MESSAGE_NAME",
    "CoreMemoryEntry",
    "CoreMemoryManager",
    "CoreMemoryRemoveTool",
    "CoreMemoryUpdateTool",
    "DEFAULT_MAX_CORE_TOKENS",
    "DEFAULT_MEMORY_DIR",
    "EmbeddingAdapter",
    "FakeEmbeddingAdapter",
    "MEMORY_INDEX_MESSAGE_NAME",
    "MEMORY_POLICY_MESSAGE_NAME",
    "MEMORY_POLICY_PROMPT",
    "MEMORY_RECALL_HEADER",
    "MEMORY_RECALL_MESSAGE_NAME",
    "MEMORY_SEARCH_TOOL_NAME",
    "MEMORY_WRITE_POLICY",
    "MaintenanceAction",
    "MemoryEmbeddingSettings",
    "MemoryMaintenanceCandidate",
    "MemoryMaintenanceConfig",
    "MemoryMaintenanceDecision",
    "MemoryMaintenanceInput",
    "MemoryMaintenanceProposal",
    "MemoryMaintenanceReflector",
    "MemoryReflectionConfig",
    "MemoryReflectionInput",
    "MemoryReflectionProposal",
    "MemoryArchiveTool",
    "MemoryCreateTool",
    "MemoryIndex",
    "MemoryListTool",
    "MemoryMaintenance",
    "MemoryManager",
    "MemoryReadTool",
    "MemoryRecallQueryInputs",
    "MemoryRecallService",
    "MemoryRecallSnapshot",
    "MemoryRecord",
    "MemorySearchIndex",
    "MemorySearchResult",
    "MemorySearchSettings",
    "MemorySearchTool",
    "MemoryStatus",
    "MemoryStore",
    "MemoryUpdateTool",
    "OpenAICompatibleEmbeddingAdapter",
    "PostRunMemoryReflector",
    "ReflectionGateDecision",
    "ReflectionGateReason",
    "ReflectionAction",
    "ReflectionDecision",
    "SearchMode",
    "build_embedding_adapter",
    "decide_reflection_gate",
    "next_memory_id",
    "parse_memory_markdown",
    "recent_user_message_texts",
    "register_memory_tools",
    "register_memory_write_tools",
]

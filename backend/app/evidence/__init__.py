"""不可变工具证据与按需回读能力。"""

from .models import EvidenceDocument, EvidenceRecord, EvidenceSearchHit
from .recorder import EvidenceRecorder
from .store import (
    DEFAULT_MAX_EVIDENCE_ITEM_BYTES,
    DEFAULT_MAX_EVIDENCE_TOTAL_BYTES,
    EvidenceCapacityError,
    SQLiteEvidenceStore,
)
from .tools import EvidenceReadTool, EvidenceSearchTool, register_evidence_tools

__all__ = [
    "DEFAULT_MAX_EVIDENCE_ITEM_BYTES",
    "DEFAULT_MAX_EVIDENCE_TOTAL_BYTES",
    "EvidenceCapacityError",
    "EvidenceDocument",
    "EvidenceReadTool",
    "EvidenceRecord",
    "EvidenceRecorder",
    "EvidenceSearchHit",
    "EvidenceSearchTool",
    "SQLiteEvidenceStore",
    "register_evidence_tools",
]

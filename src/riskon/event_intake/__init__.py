"""Read-only event corpus intake and compatibility adapter."""

from riskon.event_intake.errors import CorpusBlockedError, EventIntakeError, ManifestError
from riskon.event_intake.inspection import CorpusInspector, EventCorpusAdapter
from riskon.event_intake.models import (
    CorpusCompatibilityReport,
    CorpusIntakeReport,
    CorpusIntakeRequest,
    CorpusSmokeCase,
    CorpusStatus,
    PreparedCorpus,
)

__all__ = [
    "CorpusBlockedError",
    "CorpusCompatibilityReport",
    "CorpusInspector",
    "CorpusIntakeReport",
    "CorpusIntakeRequest",
    "CorpusSmokeCase",
    "CorpusStatus",
    "EventCorpusAdapter",
    "EventIntakeError",
    "ManifestError",
    "PreparedCorpus",
]

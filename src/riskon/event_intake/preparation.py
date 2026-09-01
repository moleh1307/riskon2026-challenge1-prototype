"""Descriptor-only preparation for event corpora."""

from __future__ import annotations

from riskon.event_intake.errors import CorpusBlockedError
from riskon.event_intake.models import (
    CorpusIntakeReport,
    CorpusIntakeRequest,
    CorpusStatus,
    PreparedCorpus,
)


def prepare_corpus(
    report: CorpusIntakeReport,
    request: CorpusIntakeRequest,
) -> PreparedCorpus | None:
    """Prepare only references and descriptors; never copy source content."""

    if report.status is CorpusStatus.BLOCKED:
        return None
    if report.manifest is None:
        raise CorpusBlockedError("A prepared corpus requires a valid manifest")
    return PreparedCorpus(
        source_root=request.source_root.expanduser().resolve(strict=False),
        manifest_descriptor=report.manifest,
        documents=report.documents,
        assets=report.assets,
        local_link_edges=report.local_link_edges,
        corpus_fingerprint=report.corpus_fingerprint,
        warnings=sorted({issue.code for issue in report.warnings}),
    )

"""ER-B model contract tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from riskon.demo.models import CounterfactualView, EvidenceView, MetricView


def test_demo_models_validate_safe_display_shapes() -> None:
    evidence = EvidenceView(
        source_title="Synthetic source",
        section_heading="Applicability",
        provenance_ref="local://synthetic-m4d/source.html",
        criticality="STANDARD",
        excerpt="A short excerpt.",
    )
    transition = CounterfactualView(
        variant_id="cf-001",
        dimension="region",
        before="REGION_BETA",
        after="REGION_ALPHA",
        decision="ABSTAIN",
        passed=True,
    )
    metric = MetricView(
        id="network_violations",
        label="Network violations",
        value="0",
        status="PASS",
        source="M5B.metrics.network_violation_count",
    )
    assert evidence.provenance_ref.startswith("local://")
    assert transition.passed is True
    assert metric.value == "0"


def test_demo_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EvidenceView(
            source_title="Synthetic source",
            section_heading="Applicability",
            provenance_ref="local://synthetic-m4d/source.html",
            criticality="STANDARD",
            excerpt="A short excerpt.",
            raw_html="<p>not allowed</p>",
        )

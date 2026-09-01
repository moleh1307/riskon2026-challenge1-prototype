"""M1 provenance stability and resolution tests."""

from pathlib import Path

from riskon.ingestion import load_sections_from_manifest, load_synthetic_sections
from riskon.models import Evidence
from riskon.provenance import ProvenanceIndex

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data" / "synthetic"
M1_ROOT = DATA_ROOT / "m1"


def _m1_index() -> ProvenanceIndex:
    sections = load_sections_from_manifest(
        M1_ROOT / "manifest.xlsx",
        M1_ROOT / "knowledge",
        url_prefix="local://synthetic-m1/",
    )
    return ProvenanceIndex(sections, knowledge_root=M1_ROOT / "knowledge")


def test_repeated_m1_ingestion_has_identical_refs() -> None:
    first = _m1_index()
    second = _m1_index()
    assert sorted(first.local_refs()) == sorted(second.local_refs())
    assert len(first.local_refs()) == len(set(first.local_refs()))


def test_section_sentence_and_asset_refs_are_stable_and_local() -> None:
    index = _m1_index()
    refs = index.local_refs()
    assert "local://synthetic-m1/acronym_registry.html#section-acronym-registry-01" in refs
    assert (
        "local://synthetic-m1/acronym_registry.html#section-acronym-registry-01:sentence-1" in refs
    )
    assert "local://synthetic-m1/image_only_methodology.html#asset-1" in refs
    assert all(not ref.startswith("/") for ref in refs)
    assert all("http://" not in ref and "https://" not in ref for ref in refs)


def test_table_row_refs_preserve_header_context() -> None:
    sections = load_synthetic_sections(DATA_ROOT)
    index = ProvenanceIndex(sections, knowledge_root=DATA_ROOT / "knowledge")
    table_units = [unit for unit in index.units.values() if unit.kind == "table_row"]
    assert table_units
    row = next(unit for unit in table_units if "Concentration" in unit.text)
    assert row.ref == "local://synthetic/alert_matrix.html#table-1:row-1"
    assert row.headers == ["Alert class", "Status", "Control type"]
    assert "Alert class: Concentration" in row.text


def test_evidence_refs_resolve_to_existing_units() -> None:
    index = _m1_index()
    section = next(
        section for section in index.sections if section.filename == "service_model_scope.html"
    )
    evidence = Evidence(
        section_id=section.section_id,
        source_ref=section.source_ref,
        title=section.title,
        heading_path=section.heading_path,
        score=1.0,
        excerpt=section.text,
        table_rows=[],
    )
    refs = index.refs_for_evidence(evidence)
    assert refs
    assert all(index.resolve(ref) is not None for ref in refs)


def test_required_relative_form_is_unresolved_and_http_is_rejected() -> None:
    index = _m1_index()
    section = next(
        section
        for section in index.sections
        if section.filename == "procedure_with_required_form.html"
    )
    assert index.resolve_link(section, "attachments/exception-request-form.pdf") is None
    assert index.resolve_link(section, "https://example.invalid/form.pdf") is None
    assert index.resolve_link(section, "../outside.pdf") is None

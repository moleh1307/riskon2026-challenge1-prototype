"""Local corpus and source-safety boundaries for M4B workers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Comment, Tag
from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.adapter import StructuralEventCorpus
from riskon.ingestion import load_sections_from_manifest
from riskon.models import Section
from riskon.provenance import ProvenanceIndex, ProvenanceUnit


@dataclass(frozen=True)
class LocalCorpus:
    """Read-only view of the synthetic M4 corpus and its provenance index."""

    sections: tuple[Section, ...]
    provenance: ProvenanceIndex
    knowledge_root: Path
    structural: StructuralEventCorpus | None = None

    def resolve(self, reference: str) -> ProvenanceUnit | None:
        """Resolve one local evidence reference."""

        return self.provenance.resolve(reference)

    def section_for_reference(self, reference: str) -> Section | None:
        """Resolve the section containing one local evidence reference."""

        unit = self.resolve(reference)
        if unit is None or unit.section_id is None:
            return None
        return next(
            (section for section in self.sections if section.section_id == unit.section_id),
            None,
        )


def build_local_corpus(
    manifest_path: Path,
    knowledge_root: Path,
    *,
    url_prefix: str = "local://synthetic-m4/",
) -> LocalCorpus:
    """Load only the manifest-declared synthetic M4 HTML corpus."""

    sections = load_sections_from_manifest(
        manifest_path,
        knowledge_root,
        url_prefix=url_prefix,
    )
    provenance = ProvenanceIndex(
        sections,
        knowledge_root=manifest_path.parent,
        ref_style="m2",
    )
    return LocalCorpus(
        sections=tuple(sections),
        provenance=provenance,
        knowledge_root=knowledge_root.resolve(),
    )


class SourceSafetyDiagnostic(BaseModel):
    """A safe diagnostic for suspicious source content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    diagnostic_code: str = Field(min_length=1)
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SourceSafetyReport:
    """Deterministic source-safety observations shared with the Skeptic."""

    unsafe_refs: frozenset[str]
    diagnostics: tuple[SourceSafetyDiagnostic, ...]

    def is_unsafe(self, reference: str) -> bool:
        """Return whether a section or child reference is unsafe as evidence."""

        return any(reference == ref or reference.startswith(f"{ref}:") for ref in self.unsafe_refs)


@dataclass(frozen=True)
class SourceSafetyContext:
    """Policy plus one immutable inspection snapshot for a worker wave."""

    policy: SourceSafetyPolicy
    report: SourceSafetyReport


class SourceSafetyPolicy:
    """Load and apply the frozen source-content safety policy."""

    _allowed_prefixes = (
        "local://synthetic/",
        "local://synthetic-m1/",
        "local://synthetic-m2/",
        "local://synthetic-m4/",
        "local://synthetic-m4d/",
        "local://event-wiki/",
    )

    def __init__(self, raw: dict[str, Any], source_path: Path) -> None:
        self.source_path = source_path
        self.source_content_trust = str(raw["source_content_trust"])
        self.suspicious_phrases = tuple(
            str(phrase).lower()
            for rule in raw["rules"]
            if isinstance(rule, dict)
            for phrase in rule.get("suspicious_phrases", [])
            if isinstance(phrase, str)
        )
        diagnostic_codes = raw.get("diagnostic_codes")
        if not isinstance(diagnostic_codes, list) or not diagnostic_codes:
            raise ValueError("M4 source-safety policy must declare diagnostic_codes")
        self.diagnostic_code = str(diagnostic_codes[0])

    @classmethod
    def from_file(cls, path: Path) -> SourceSafetyPolicy:
        """Read the frozen JSON policy without accepting unknown top-level fields."""

        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"M4 source-safety policy not found: {resolved}")
        try:
            raw_value = json.loads(resolved.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid M4 source-safety policy: {exc}") from exc
        if not isinstance(raw_value, dict):
            raise ValueError("M4 source-safety policy must be a JSON object")
        if set(raw_value) != {
            "schema_version",
            "source_content_trust",
            "rules",
            "diagnostic_codes",
        }:
            raise ValueError("M4 source-safety policy fields do not match the frozen schema")
        if raw_value.get("schema_version") != "1.0":
            raise ValueError("Unsupported M4 source-safety policy schema")
        if raw_value.get("source_content_trust") != "UNTRUSTED_DATA":
            raise ValueError("M4 source-safety policy must treat source content as data")
        rules = raw_value.get("rules")
        if not isinstance(rules, list):
            raise ValueError("M4 source-safety policy rules must be an array")
        return cls(raw_value, resolved)

    def inspect(self, corpus: LocalCorpus) -> SourceSafetyReport:
        """Detect suspicious visible source instructions without exposing their text."""

        unsafe_refs: set[str] = set()
        diagnostics: list[SourceSafetyDiagnostic] = []
        for section in corpus.sections:
            visible_text = self._visible_source_text(corpus.knowledge_root / section.filename)
            if not any(phrase in visible_text.lower() for phrase in self.suspicious_phrases):
                continue
            candidates = {
                unit.ref
                for unit in corpus.provenance.units_for_section(section.section_id)
                if any(phrase in unit.text.lower() for phrase in self.suspicious_phrases)
            }
            suspicious_refs = tuple(
                sorted(
                    reference
                    for reference in candidates
                    if not any(
                        other != reference and other.startswith(f"{reference}:")
                        for other in candidates
                    )
                )
            )
            if not suspicious_refs:
                continue
            references = suspicious_refs
            unsafe_refs.update(references)
            diagnostics.append(
                SourceSafetyDiagnostic(
                    diagnostic_code=self.diagnostic_code,
                    evidence_refs=(corpus.provenance.section_ref(section),),
                )
            )
        return SourceSafetyReport(
            unsafe_refs=frozenset(unsafe_refs),
            diagnostics=tuple(sorted(diagnostics, key=lambda item: item.evidence_refs)),
        )

    def validate_evidence_ref(self, reference: str) -> None:
        """Reject non-local, agent, task, URL, and absolute-path references."""

        if (
            not isinstance(reference, str)
            or not reference
            or reference.startswith(("http://", "https://", "agent://", "task://", "worker://"))
            or reference.startswith("/")
            or not reference.startswith(self._allowed_prefixes)
        ):
            raise ValueError(f"Unsafe or non-source evidence reference: {reference!r}")

    def evidence_allowed(self, reference: str, report: SourceSafetyReport) -> bool:
        """Return whether a validated source reference may support a claim."""

        self.validate_evidence_ref(reference)
        return not report.is_unsafe(reference)

    @staticmethod
    def _visible_source_text(path: Path) -> str:
        """Extract visible source data while excluding executable/hidden markup."""

        if not path.is_file():
            return ""
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
        for node in soup.find_all(["script", "style", "template", "noscript", "form"]):
            node.decompose()
        for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
            comment.extract()
        for tag in soup.find_all(True):
            if not isinstance(tag, Tag):
                continue
            if any(
                name.startswith("hidden") or name in {"aria-hidden", "style"}
                for name in (tag.attrs or {})
            ):
                tag.decompose()
        return " ".join(soup.get_text(" ", strip=True).split())

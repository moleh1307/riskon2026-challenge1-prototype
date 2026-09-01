"""Deterministic local provenance addresses for M0/M1 evidence units."""

import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from riskon.models import Evidence, Section


class ProvenanceUnit(BaseModel):
    """One addressable local source unit."""

    model_config = ConfigDict(extra="forbid")

    ref: str
    kind: str
    source_ref: str
    filename: str
    section_id: str | None = None
    text: str
    heading_path: list[str]
    headers: list[str]
    row: list[str]
    claim_id: str | None = None
    claim_text: str | None = None
    scope: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class _SectionAddress:
    section_ref: str
    sentence_refs: tuple[str, ...]
    table_row_refs: tuple[str, ...]
    asset_refs: tuple[str, ...]


class ProvenanceIndex:
    """Index section, sentence, table-row, and asset references stably."""

    def __init__(
        self,
        sections: list[Section],
        knowledge_root: Path | None = None,
        *,
        ref_style: str = "standard",
        attachment_root: Path | None = None,
    ) -> None:
        self.sections = sections
        self.knowledge_root = knowledge_root.resolve() if knowledge_root else None
        if ref_style not in {"standard", "m2"}:
            raise ValueError(f"Unsupported provenance reference style: {ref_style}")
        self.ref_style = ref_style
        self.attachment_root = attachment_root.resolve() if attachment_root else None
        self.units: dict[str, ProvenanceUnit] = {}
        self._addresses: dict[str, _SectionAddress] = {}
        self._link_prefix = self._infer_prefix(sections)
        self._build()
        self._build_attachments()

    @staticmethod
    def _infer_prefix(sections: list[Section]) -> str:
        if not sections:
            return "local://synthetic/"
        source_ref = sections[0].source_ref
        return source_ref.rsplit("/", 1)[0] + "/"

    def _build(self) -> None:
        asset_numbers: dict[tuple[str, str], int] = {}
        asset_counts: dict[str, int] = {}
        for section in self.sections:
            section_ref = self.section_ref(section)
            self.units[section_ref] = ProvenanceUnit(
                ref=section_ref,
                kind="section",
                source_ref=section.source_ref,
                filename=section.filename,
                section_id=section.section_id,
                text=section.text,
                heading_path=section.heading_path,
                headers=[],
                row=[],
                scope=section.scope,
            )

            sentence_refs: list[str] = []
            sentence_number = 0
            for paragraph in section.paragraphs:
                for sentence in self._sentences(paragraph):
                    sentence_number += 1
                    ref = f"{section_ref}:sentence-{sentence_number}"
                    claim_id = self._claim_id_for_sentence(section, paragraph, sentence)
                    self.units[ref] = ProvenanceUnit(
                        ref=ref,
                        kind="sentence",
                        source_ref=section.source_ref,
                        filename=section.filename,
                        section_id=section.section_id,
                        text=sentence,
                        heading_path=section.heading_path,
                        headers=[],
                        row=[],
                        claim_id=claim_id,
                        claim_text=section.claims.get(claim_id) if claim_id else None,
                        scope=section.scope,
                    )
                    sentence_refs.append(ref)

            table_row_refs: list[str] = []
            for table_number, table in enumerate(section.tables, start=1):
                for row_number, row in enumerate(table.rows, start=1):
                    if self.ref_style == "m2":
                        ref = f"{section_ref}:table-{table_number}:row-{row_number}"
                    else:
                        ref = f"{section.source_ref}#table-{table_number}:row-{row_number}"
                    row_scope = dict(section.scope)
                    if row_number <= len(table.row_scopes):
                        row_scope.update(table.row_scopes[row_number - 1])
                    claim_id = (
                        table.claim_ids[row_number - 1]
                        if row_number <= len(table.claim_ids)
                        else None
                    )
                    self.units[ref] = ProvenanceUnit(
                        ref=ref,
                        kind="table_row",
                        source_ref=section.source_ref,
                        filename=section.filename,
                        section_id=section.section_id,
                        text="; ".join(
                            f"{header}: {value}"
                            for header, value in zip(table.headers, row, strict=False)
                        ),
                        heading_path=section.heading_path,
                        headers=table.headers,
                        row=row,
                        claim_id=claim_id,
                        claim_text=section.claims.get(claim_id) if claim_id else None,
                        scope=row_scope,
                    )
                    table_row_refs.append(ref)

            asset_refs: list[str] = []
            for image in section.images:
                key = (section.source_ref, image.src)
                if key not in asset_numbers:
                    next_number = asset_counts.get(section.source_ref, 0) + 1
                    asset_counts[section.source_ref] = next_number
                    asset_numbers[key] = next_number
                asset_number = asset_numbers[key]
                ref = f"{section.source_ref}#asset-{asset_number}"
                if ref not in self.units:
                    self.units[ref] = ProvenanceUnit(
                        ref=ref,
                        kind="asset",
                        source_ref=section.source_ref,
                        filename=section.filename,
                        section_id=section.section_id,
                        text=image.alt,
                        heading_path=section.heading_path,
                        headers=[],
                        row=[],
                        scope=section.scope,
                    )
                asset_refs.append(ref)

            self._addresses[section.section_id] = _SectionAddress(
                section_ref=section_ref,
                sentence_refs=tuple(sentence_refs),
                table_row_refs=tuple(table_row_refs),
                asset_refs=tuple(dict.fromkeys(asset_refs)),
            )

    @staticmethod
    def _sentences(text: str) -> list[str]:
        cleaned = " ".join(text.split())
        return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]

    @staticmethod
    def _slug(text: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return value or "introduction"

    def section_ref(self, section: Section) -> str:
        match = re.search(r"::section-(\d+)$", section.section_id)
        number = match.group(1) if match else "00"
        label = section.heading_path[-1] if section.heading_path else "introduction"
        if self.ref_style == "m2":
            return f"{section.source_ref}#section-{self._slug(label)}"
        return f"{section.source_ref}#section-{self._slug(label)}-{int(number):02d}"

    def refs_for_evidence(self, evidence: Evidence) -> list[str]:
        """Return stable units for one retrieved evidence section."""

        address = self._addresses.get(evidence.section_id)
        if address is None:
            return []
        refs = [
            address.section_ref,
            *address.sentence_refs,
            *address.table_row_refs,
            *address.asset_refs,
        ]
        return list(dict.fromkeys(refs))

    def section_address(self, section_id: str) -> _SectionAddress | None:
        return self._addresses.get(section_id)

    def units_for_section(self, section_id: str) -> list[ProvenanceUnit]:
        address = self._addresses.get(section_id)
        if address is None:
            return []
        refs = [
            address.section_ref,
            *address.sentence_refs,
            *address.table_row_refs,
            *address.asset_refs,
        ]
        return [self.units[ref] for ref in refs]

    def resolve(self, ref: str) -> ProvenanceUnit | None:
        return self.units.get(ref)

    def resolve_link(self, section: Section, href: str) -> str | None:
        """Resolve a relative link to a local ref, without accepting URLs or traversal."""

        if href.startswith("http://") or href.startswith("https://"):
            return None
        if href.startswith("local://"):
            return href if href in self.units else None
        if self.knowledge_root is None:
            return None
        relative = Path(href)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        target = (self.knowledge_root / relative).resolve()
        if self.knowledge_root not in target.parents or not target.is_file():
            return None
        ref = f"{self._link_prefix}{relative.as_posix()}"
        return ref if ref in self.units else None

    def local_refs(self) -> set[str]:
        return set(self.units)

    def _build_attachments(self) -> None:
        """Add explicitly supplied local attachments without broad filesystem crawling."""

        if self.attachment_root is None or not self.attachment_root.is_dir():
            return
        for path in sorted(self.attachment_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.attachment_root.parent)
            ref = f"{self._link_prefix}{relative.as_posix()}"
            self.units[ref] = ProvenanceUnit(
                ref=ref,
                kind="attachment",
                source_ref=ref,
                filename=relative.as_posix(),
                text=path.read_text(encoding="utf-8"),
                heading_path=["Attachment"],
                headers=[],
                row=[],
            )

    @staticmethod
    def _claim_id_for_sentence(
        section: Section,
        paragraph: str,
        sentence: str,
    ) -> str | None:
        for claim_id, claim_text in section.claims.items():
            if claim_text == paragraph and sentence == ProvenanceIndex._sentences(claim_text)[0]:
                return claim_id
        return None

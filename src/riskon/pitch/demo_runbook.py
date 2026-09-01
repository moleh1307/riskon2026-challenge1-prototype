"""Event-day runbooks generated from the frozen ER-C operating boundary."""

from __future__ import annotations

from riskon.pitch.catalog import PitchCatalog


def render_backup_demo_runbook(catalog: PitchCatalog) -> str:
    """Render the operator cue sheet for the standalone backup replay."""

    controls = ", ".join(catalog.backup.controls)
    scenes = "\n".join(
        f"{index}. **{scene.title}** — {scene.story_id}"
        for index, scene in enumerate(catalog.backup.scenes, start=1)
    )
    return "\n".join(
        [
            "# RiskON Orchestra — backup demo runbook",
            "",
            "The backup is a deterministic offline replay generated from the frozen ER-B "
            "demo bundle.",
            "It is independent of the Python runtime, CLI, terminal, live pipeline, evaluator "
            "execution, network and server.",
            "",
            "## Before the pitch",
            "",
            "- Open the generated backup HTML locally.",
            "- Confirm the first scene is visible and the browser tab is ready.",
            f"- Controls: {controls}.",
            "",
            "## Scenes",
            "",
            scenes,
            "",
            "## If the primary demo fails",
            "",
            f"> {catalog.backup.fallback_sentence}",
            "",
            "Do not troubleshoot on stage. Continue the narrative through the six frozen scenes.",
            "",
        ]
    )


def render_event_day_runbook(catalog: PitchCatalog) -> str:
    """Render the operational runbook for the event package and pitch."""

    del catalog
    return "\n".join(
        [
            "# RiskON Orchestra — event-day runbook",
            "",
            "## At opening — ask only three operational questions",
            "",
            "1. What is the exact team pitch duration?",
            "2. Is live demo time inside or outside the pitch allocation?",
            "3. Must the final deck use an official template?",
            "",
            "## After receiving event data",
            "",
            "Use the read-only ER-A adapter and the supplied manifest. Run the commands with "
            "the actual event paths:",
            "",
            "```bash",
            "uv run riskon inspect-corpus ...",
            "uv run riskon smoke-corpus ...",
            "```",
            "",
            "- **READY** — proceed.",
            "- **READY_WITH_WARNINGS** — review warnings and proceed only if they are "
            "non-blocking.",
            "- **BLOCKED** — do not ingest; fix the mapping or ask the organisers.",
            "",
            "## Before 14:00 on 2 September",
            "",
            "- [ ] Deck frozen",
            "- [ ] Demo generated",
            "- [ ] Backup demo generated",
            "- [ ] Evaluation snapshot frozen",
            "- [ ] No confidential data in slides",
            "- [ ] No absolute paths in artifacts",
            "- [ ] Primary and backup opened locally",
            "- [ ] Presenter handoffs rehearsed",
            "",
            "## Immediately before the pitch",
            "",
            "- Airplane mode or network off",
            "- Deck already open",
            "- Demo index already open",
            "- Backup demo already open",
            "- Terminal closed unless specifically needed",
            "- Screen notifications disabled",
            "",
        ]
    )

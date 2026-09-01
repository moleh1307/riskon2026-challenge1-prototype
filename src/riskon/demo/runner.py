"""Run frozen M4D/M5B behavior and build the five safe story views."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from riskon.config import EventDemoConfig, load_milestone5b_config
from riskon.demo.catalog import DemoCatalog
from riskon.demo.errors import DemoContractError
from riskon.demo.models import (
    CounterfactualView,
    DemoCase,
    GovernanceChecksView,
    StoryView,
)
from riskon.demo.view_models import (
    before_view_from_capsule,
    governed_view,
    story_view_from_run,
)
from riskon.governance.models import KnowledgeOverlaySnapshot
from riskon.m5b_evaluation import M5BEvaluationDocument, M5BEvaluator
from riskon.models import QueryInput
from riskon.orchestra.models import OrchestraRun
from riskon.pipeline import M4DRiskonPipeline, M5BRiskonPipeline


class DemoRun:
    """Runtime artifacts needed to render stories and dashboard metrics."""

    def __init__(
        self,
        stories: tuple[StoryView, ...],
        m4d_runs: dict[str, OrchestraRun],
        m5b_document: M5BEvaluationDocument,
        m5b_after_run: OrchestraRun,
    ) -> None:
        self.stories = stories
        self.m4d_runs = m4d_runs
        self.m5b_document = m5b_document
        self.m5b_after_run = m5b_after_run


class DemoRunner:
    """Execute ER-B stories against the existing local runtime only."""

    def __init__(self, config: EventDemoConfig, catalog: DemoCatalog | None = None) -> None:
        self.config = config
        self.catalog = catalog or DemoCatalog.from_config(config)

    def run_all(self) -> DemoRun:
        """Run all story inputs and the canonical M5B governance evaluator."""

        m5b_config = load_milestone5b_config(self.config.runtime.pipeline_config)
        m4d_pipeline = M4DRiskonPipeline.from_milestone4d_config(m5b_config.base)
        m4d_runs: dict[str, OrchestraRun] = {}
        stories: list[StoryView] = []
        frozen_m4d_cases = self._load_m4d_cases(m5b_config.base.orchestra.m4d.evaluation_cases)
        for source_case_id, raw_case in frozen_m4d_cases.items():
            run = m4d_pipeline.run_orchestrated(
                QueryInput(
                    query=str(raw_case["query"]),
                    context={
                        str(key): str(value) for key, value in raw_case["input_context"].items()
                    },
                    trace_id=f"demo-regression-{source_case_id}-{uuid4().hex}",
                )
            )
            m4d_runs[source_case_id] = run
        for case in self.catalog.cases:
            if case.source_milestone == "M4D":
                stories.append(self._story_from_m4d(case, m4d_runs[case.source_case_id]))

        m5b_document = M5BEvaluator(m5b_config).run()
        m5b_pipeline = M5BRiskonPipeline.from_milestone5b_config(m5b_config)
        snapshot = KnowledgeOverlaySnapshot.model_validate(m5b_document.overlay_snapshot)
        governed_case = self.catalog.case("ERB-005")
        m5b_after_run = m5b_pipeline.run_orchestrated_with_overlay(
            QueryInput(
                query=governed_case.question,
                context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
                trace_id=f"demo-ERB-005-{uuid4().hex}",
            ),
            snapshot,
        )
        stories.append(self._story_from_m5b(governed_case, m5b_document, m5b_after_run))
        ordered = tuple(stories)
        self._validate_story_order(ordered)
        return DemoRun(
            stories=ordered,
            m4d_runs=m4d_runs,
            m5b_document=m5b_document,
            m5b_after_run=m5b_after_run,
        )

    def run_case(self, case_id: str) -> StoryView:
        """Run one story for the `demo-case` CLI command."""

        case = self.catalog.case(case_id)
        m5b_config = load_milestone5b_config(self.config.runtime.pipeline_config)
        if case.source_milestone == "M4D":
            pipeline = M4DRiskonPipeline.from_milestone4d_config(m5b_config.base)
            run = self._run_m4d_case(pipeline, case, trace_id=f"demo-{case.id}-{uuid4().hex}")
            view = self._story_from_m4d(case, run)
        elif case.source_milestone == "M5B":
            document = M5BEvaluator(m5b_config).run()
            pipeline = M5BRiskonPipeline.from_milestone5b_config(m5b_config)
            snapshot = KnowledgeOverlaySnapshot.model_validate(document.overlay_snapshot)
            run = pipeline.run_orchestrated_with_overlay(
                QueryInput(
                    query=case.question,
                    context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
                    trace_id=f"demo-{case.id}-{uuid4().hex}",
                ),
                snapshot,
            )
            view = self._story_from_m5b(case, document, run)
        else:
            raise DemoContractError(f"Unsupported ER-B source milestone: {case.source_milestone}")
        self._validate_story(view)
        return view

    def _run_m4d_case(
        self,
        pipeline: M4DRiskonPipeline,
        case: DemoCase,
        trace_id: str | None = None,
    ) -> OrchestraRun:
        context = (
            {"region": "REGION_BETA", "service_model": "SERVICE_BASIC"}
            if case.source_case_id == "M4D-045"
            else {}
        )
        return pipeline.run_orchestrated(
            QueryInput(
                query=case.question,
                context=context,
                trace_id=trace_id or f"demo-{case.id}",
            )
        )

    @staticmethod
    def _load_m4d_cases(path: Any) -> dict[str, dict[str, Any]]:
        """Load the frozen M4D input matrix for story and dashboard execution."""

        raw = json.loads(path.read_text(encoding="utf-8"))
        cases = raw.get("cases")
        if not isinstance(cases, list):
            raise DemoContractError("M4D evaluation fixture does not contain cases")
        return {str(item["id"]): item for item in cases}

    def _story_from_m4d(self, case: DemoCase, run: OrchestraRun) -> StoryView:
        view = story_view_from_run(
            run,
            case_id=case.id,
            source_case_id=case.source_case_id,
            story_kind=case.story_kind,
            title=case.title,
            question=case.question,
            presentation_message=case.presentation_message,
            audit_reference=f"m4d-eval-{case.source_case_id}",
            maximum_excerpt_characters=self.config.rendering.maximum_evidence_excerpt_characters,
        )
        self._validate_story(view)
        return view

    def _story_from_m5b(
        self,
        case: DemoCase,
        document: M5BEvaluationDocument,
        after_run: OrchestraRun,
    ) -> StoryView:
        result = next(
            (item for item in document.case_results if item.case_id == case.source_case_id),
            None,
        )
        if result is None:
            raise DemoContractError(f"M5B evaluator did not return {case.source_case_id}")
        capsule = self._load_m5a_capsule(case.source_case_id)
        checks = GovernanceChecksView(
            policy_ci={
                "matched": sum(status == "PASS" for status in result.check_statuses.values()),
                "expected": len(result.check_statuses),
            },
            regression={
                "matched": document.metrics.regression_matched,
                "expected": document.metrics.regression_expected,
            },
            counterfactual_containment={
                "matched": result.counterfactual_transition_count,
                "expected": document.metrics.counterfactual_expected,
            },
            automatic_approval=document.metrics.automatic_approval_count,
            automatic_activation=document.metrics.automatic_activation_count,
            human_approval=result.check_statuses.get("HUMAN_APPROVAL_PRESENT") == "PASS",
            release_activation=result.actual_active_release is not None,
        )
        before = before_view_from_capsule(capsule)
        governance = governed_view(
            before=before,
            checks=checks,
            after={
                "exact_scope": result.post_patch.get("exact", "NOT MEASURED"),
                "alternate_region": result.post_patch.get("region", "NOT MEASURED"),
                "alternate_service_model": result.post_patch.get("service", "NOT MEASURED"),
                "required_context_removed": result.post_patch.get("missing", "NOT MEASURED"),
            },
            patch_status=result.actual_patch_status,
            active_release=result.actual_active_release,
        )
        view = story_view_from_run(
            after_run,
            case_id=case.id,
            source_case_id=case.source_case_id,
            story_kind=case.story_kind,
            title=case.title,
            question=case.question,
            presentation_message=case.presentation_message,
            audit_reference=f"m5b:{case.source_case_id}",
            activation_profile=case.expected_activation_profile,
            governance=governance,
            maximum_excerpt_characters=self.config.rendering.maximum_evidence_excerpt_characters,
        )
        return self._with_governed_counterfactuals(view, result)

    @staticmethod
    def _with_governed_counterfactuals(view: StoryView, result: Any) -> StoryView:
        """Present the three requested post-patch context changes from M5B results."""

        transitions = [
            {
                "variant_id": "M5A-046-region-alpha",
                "dimension": "region",
                "before": "REGION_BETA",
                "after": "REGION_ALPHA",
                "decision": result.post_patch.get("region", "NOT MEASURED"),
            },
            {
                "variant_id": "M5A-046-service-plus",
                "dimension": "service_model",
                "before": "SERVICE_BASIC",
                "after": "SERVICE_PLUS",
                "decision": result.post_patch.get("service", "NOT MEASURED"),
            },
            {
                "variant_id": "M5A-046-context-removed",
                "dimension": "required_context",
                "before": "present",
                "after": "removed",
                "decision": result.post_patch.get("missing", "NOT MEASURED"),
            },
        ]
        return view.model_copy(
            update={
                "counterfactuals": [
                    CounterfactualView(
                        **item,
                        reason_codes=[],
                        passed=item["decision"] in {"ABSTAIN", "CLARIFY"},
                    )
                    for item in transitions
                ]
            }
        )

    def _load_m5a_capsule(self, case_id: str) -> dict[str, Any]:
        """Resolve the frozen capsule reference without exposing its filesystem path."""

        m5b_config = load_milestone5b_config(self.config.runtime.pipeline_config)
        raw = json.loads(m5b_config.governance.contract_cases.read_text(encoding="utf-8"))
        case = next(item for item in raw["cases"] if item["id"] == case_id)
        reference = str(case["case_capsule_ref"])
        prefix = "local://synthetic-m5a/"
        if not reference.startswith(prefix):
            raise DemoContractError("M5A capsule reference is not local")
        path = m5b_config.project_root / "data" / "synthetic" / "m5a" / reference[len(prefix) :]
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise DemoContractError("M5A capsule must be a JSON object")
        return value

    def _validate_story_order(self, stories: tuple[StoryView, ...]) -> None:
        expected = tuple(self.config.demo.included_cases)
        actual = tuple(story.case_id for story in stories)
        if actual != expected:
            raise DemoContractError(f"ER-B story order mismatch: {actual!r}")
        for story in stories:
            self._validate_story(story)

    def _validate_story(self, story: StoryView) -> None:
        """Compare safety-critical view fields to the frozen expected-view file."""

        expected = self.catalog.expected_views[story.case_id]
        if story.source_case_id != expected.source_case_id:
            raise DemoContractError(f"{story.case_id}: source case mismatch")
        if story.decision != expected.decision:
            raise DemoContractError(f"{story.case_id}: decision mismatch")
        if story.activation_profile != expected.activation_profile:
            raise DemoContractError(f"{story.case_id}: activation profile mismatch")
        actual_roles = [
            step.actor.upper().replace(" ", "_")
            for step in story.orchestra_activity
            if step.stage == "Worker activated"
        ]
        if expected.agent_roles and actual_roles != expected.agent_roles:
            raise DemoContractError(f"{story.case_id}: worker-role mismatch")
        if story.reason_codes != expected.reason_codes:
            raise DemoContractError(f"{story.case_id}: reason-code mismatch")
        if bool(story.answer) != expected.answer_present:
            raise DemoContractError(f"{story.case_id}: answer-presence mismatch")
        if (
            expected.clarifying_question is not None
            and story.clarifying_question != expected.clarifying_question
        ):
            raise DemoContractError(f"{story.case_id}: clarification mismatch")
        if expected.evidence_required and not story.evidence:
            raise DemoContractError(f"{story.case_id}: evidence missing")
        if expected.route is None and story.route is not None:
            raise DemoContractError(f"{story.case_id}: unexpected route")
        if expected.route is not None:
            if story.route is None:
                raise DemoContractError(f"{story.case_id}: expected route missing")
            actual_route = story.route.model_dump(mode="json")
            for key, value in expected.route.items():
                if actual_route.get(key) != value:
                    raise DemoContractError(f"{story.case_id}: route field {key} mismatch")
        if expected.case_id == "ERB-003" and len(story.counterfactuals) != 3:
            raise DemoContractError("ERB-003: counterfactual count mismatch")
        if expected.case_id == "ERB-005" and story.governance is None:
            raise DemoContractError("ERB-005: governance panel missing")
